#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).parent
INDEX_HTML = BASE_DIR / "index.html"
PORT = 8765
WOS_API_KEY = "54d3152b36052806649159575dfa2cad1102c69f"
WOS_ENDPOINT = "https://api.clarivate.com/apis/wos-starter/v1/documents"


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
    try:
        pubs = json.loads(pubs_m.group(1)) if pubs_m else []
    except Exception:
        pubs = []
    try:
        projs = json.loads(projs_m.group(1)) if projs_m else []
    except Exception:
        projs = []
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
    write_html(re.sub(r"// @PUBS_START[\s\S]*?// @PUBS_END", new_block, content, count=1))


def write_projs(projs: list) -> None:
    content = read_html()
    new_block = (
        "// @PROJS_START\n"
        "  const DEFAULT_PROJS = "
        + json.dumps(projs, ensure_ascii=False, indent=4)
        + ";\n  // @PROJS_END"
    )
    write_html(re.sub(r"// @PROJS_START[\s\S]*?// @PROJS_END", new_block, content, count=1))


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
    write_html(re.sub(
        r'<div class="contact-grid" id="contactGrid">[\s\S]*?</div>(?=\s*<div class="hero-links")',
        new_grid, content, count=1,
    ))


def wos_sync(pubs: list[dict]) -> tuple[list[dict], str]:
    import urllib.parse
    updated, errors = 0, []
    wos_map: dict[str, dict] = {}
    try:
        params = urllib.parse.urlencode({"q": "AU=(Zhao S) AND OG=(Chongqing Jiaotong)", "db": "WOS", "limit": 50})
        req = urllib.request.Request(
            f"{WOS_ENDPOINT}?{params}",
            headers={"X-ApiKey": WOS_API_KEY, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        for hit in data.get("hits", []):
            doi = (hit.get("identifiers", {}).get("doi") or [{}])[0].get("value", "").lower()
            jcr = hit.get("jcrQuartile", "")
            if_val = str(hit.get("impactFactor", "") or "")
            if doi:
                wos_map[doi] = {"jcr": jcr, "if": if_val}
    except Exception as e:
        errors.append(str(e))
    for pub in pubs:
        doi = (pub.get("doi") or "").lower()
        if doi in wos_map:
            rec = wos_map[doi]
            if rec.get("jcr"):
                pub["jcr"] = rec["jcr"]
                updated += 1
            if rec.get("if"):
                pub["if"] = rec["if"]
    msg = f"同步完成，更新 {updated} 条"
    if errors:
        msg += "；错误: " + "; ".join(errors[:2])
    return pubs, msg


def git_push(message: str = "update: homepage content via manager") -> dict:
    try:
        subprocess.run(["git", "-C", str(BASE_DIR), "add", "index.html"], check=True)
        subprocess.run(["git", "-C", str(BASE_DIR), "commit", "-m", message], check=True)
        r = subprocess.run(
            ["git", "-C", str(BASE_DIR), "push", "origin", "main"],
            capture_output=True, text=True,
        )
        return {"ok": r.returncode == 0, "msg": "推送成功" if r.returncode == 0 else r.stderr}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "msg": str(e)}


# PLACEHOLDER_ADMIN_HTML
