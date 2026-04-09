#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Personal Homepage Manager — full CRUD + WoS sync + git push
"""

from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import threading
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent
INDEX_HTML = BASE_DIR / "index.html"
PORT = 8765
WOS_API_KEY = "54d3152b36052806649159575dfa2cad1102c69f"
WOS_ENDPOINT = "https://api.clarivate.com/apis/wos-starter/v1/documents"


# ── Read / Write helpers ──────────────────────────────────────────────────────

def read_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def write_html(content: str) -> None:
    INDEX_HTML.write_text(content, encoding="utf-8")


def extract_data() -> dict:
    content = read_html()

    pubs_m = re.search(
        r"// @PUBS_START\s*\n\s*//[^\n]*\n\s*const DEFAULT_PUBS\s*=\s*(\[[\s\S]*?\])\s*;\s*\n\s*// @PUBS_END",
        content,
    )
    projs_m = re.search(
        r"// @PROJS_START\s*\n\s*const DEFAULT_PROJS\s*=\s*(\[[\s\S]*?\])\s*;\s*\n\s*// @PROJS_END",
        content,
    )

    pubs = json.loads(pubs_m.group(1)) if pubs_m else []
    projs = json.loads(projs_m.group(1)) if projs_m else []
    bio_en = _extract_bio(content, "bioEn")
    bio_zh = _extract_bio(content, "bioZh")
    contacts = _extract_contacts(content)

    return {"pubs": pubs, "projs": projs, "bioEn": bio_en, "bioZh": bio_zh, "contacts": contacts}


def _extract_bio(content: str, elem_id: str) -> str:
    m = re.search(rf'id="{elem_id}"[^>]*>\s*([\s\S]*?)\s*</p>', content)
    return m.group(1).strip() if m else ""


def _extract_contacts(content: str) -> list[dict]:
    m = re.search(r'id="contactGrid"[^>]*>([\s\S]*?)</div>\s*<div class="hero-links"', content)
    if not m:
        return []
    block = m.group(1)
    items = re.findall(
        r'<span class="contact-label">([^<]+)</span>\s*<span class="contact-value">([^<]+)</span>',
        block,
    )
    return [{"label": label.strip(), "value": value.strip()} for label, value in items]


def write_pubs(pubs: list) -> None:
    content = read_html()
    new_block = (
        "// @PUBS_START\n"
        "  // firstAuthor: true = first/co-first author, sci: true = SCI indexed\n"
        "  const DEFAULT_PUBS = "
        + json.dumps(pubs, ensure_ascii=False, indent=4)
        + ";\n  // @PUBS_END"
    )
    content = re.sub(r"// @PUBS_START[\s\S]*?// @PUBS_END", new_block, content, count=1)
    write_html(content)


def write_projs(projs: list) -> None:
    content = read_html()
    new_block = (
        "// @PROJS_START\n"
        "  const DEFAULT_PROJS = "
        + json.dumps(projs, ensure_ascii=False, indent=4)
        + ";\n  // @PROJS_END"
    )
    content = re.sub(r"// @PROJS_START[\s\S]*?// @PROJS_END", new_block, content, count=1)
    write_html(content)


def write_bio(bio_en: str, bio_zh: str) -> None:
    content = read_html()
    content = re.sub(
        r'(id="bioEn"[^>]*>)\s*[\s\S]*?\s*(</p>)',
        lambda m: m.group(1) + "\n        " + bio_en + "\n      " + m.group(2),
        content, count=1,
    )
    content = re.sub(
        r'(id="bioZh"[^>]*>)\s*[\s\S]*?\s*(</p>)',
        lambda m: m.group(1) + "\n        " + bio_zh + "\n      " + m.group(2),
        content, count=1,
    )
    write_html(content)


def write_contacts(contacts: list[dict]) -> None:
    content = read_html()
    items_html = "\n".join(
        f'        <div class="contact-item">\n'
        f'          <span class="contact-label">{c["label"]}</span>\n'
        f'          <span class="contact-value">{c["value"]}</span>\n'
        f'        </div>'
        for c in contacts
    )
    new_grid = f'<div class="contact-grid" id="contactGrid">\n{items_html}\n      </div>'
    content = re.sub(
        r'<div class="contact-grid" id="contactGrid">[\s\S]*?</div>(?=\s*<div class="hero-links")',
        new_grid,
        content, count=1,
    )
    write_html(content)


# ── WoS API ───────────────────────────────────────────────────────────────────

def wos_fetch_by_query(query: str) -> list[dict]:
    """Query WoS Starter API and return list of {doi, jcr, if} dicts."""
    params = urllib.parse.urlencode({  # type: ignore[attr-defined]
        "q": query,
        "db": "WOS",
        "limit": 50,
    })
    url = f"{WOS_ENDPOINT}?{params}"
    req = urllib.request.Request(url, headers={"X-ApiKey": WOS_API_KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return _parse_wos_hits(data)
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _parse_wos_hits(data: dict) -> list[dict]:
    results = []
    for hit in data.get("hits", []):
        doi = ""
        for eid in hit.get("identifiers", {}).get("doi", []):
            doi = eid.get("value", "").lower().replace("https://doi.org/", "")
            break
        jcr = hit.get("jcrQuartile", "") or ""
        if_val = str(hit.get("impactFactor", "") or "")
        if doi:
            results.append({"doi": doi, "jcr": jcr, "if": if_val})
    return results


def wos_sync(pubs: list[dict]) -> tuple[list[dict], str]:
    """Sync JCR/IF for all pubs that have a DOI. Returns updated pubs + status message."""
    import urllib.parse  # noqa: PLC0415

    updated = 0
    errors = []

    # Build DOI lookup from WoS
    wos_map: dict[str, dict] = {}
    try:
        hits = wos_fetch_by_query("AU=(Zhao S) AND OG=(Chongqing Jiaotong)")
        for h in hits:
            wos_map[h["doi"]] = h
    except Exception as exc:
        errors.append(f"Bulk query failed: {exc}")

    # Per-DOI fallback for pubs not found
    for pub in pubs:
        doi = (pub.get("doi") or "").lower().strip()
        if not doi:
            continue
        if doi in wos_map:
            rec = wos_map[doi]
            if rec.get("jcr"):
                pub["jcr"] = rec["jcr"]
                updated += 1
            if rec.get("if"):
                pub["if"] = rec["if"]
        else:
            try:
                hits = wos_fetch_by_query(f"DO={doi}")
                for h in hits:
                    if h["doi"] == doi:
                        if h.get("jcr"):
                            pub["jcr"] = h["jcr"]
                            updated += 1
                        if h.get("if"):
                            pub["if"] = h["if"]
                        break
            except Exception as exc:
                errors.append(f"DOI {doi}: {exc}")

    msg = f"同步完成，更新 {updated} 条记录"
    if errors:
        msg += "；部分失败: " + "; ".join(errors[:3])
    return pubs, msg


# ── Git ───────────────────────────────────────────────────────────────────────

def git_push(message: str = "update: homepage content via manager") -> dict:
    try:
        subprocess.run(["git", "-C", str(BASE_DIR), "add", "index.html"], check=True)
        subprocess.run(["git", "-C", str(BASE_DIR), "commit", "-m", message], check=True)
        result = subprocess.run(
            ["git", "-C", str(BASE_DIR), "push", "origin", "main"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return {"ok": True, "msg": "推送成功"}
        return {"ok": False, "msg": result.stderr or result.stdout}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "msg": str(exc)}
