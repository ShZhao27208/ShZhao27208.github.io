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
    if not pubs:  # safety: never overwrite with empty list
        return
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


def _extract_contacts(content: str) -> list[dict]:
    """Extract contacts as grouped items: {label, values: [v1, v2, ...]}"""
    m = re.search(r'id="contactGrid"[^>]*>([\s\S]*?)</div>\s*<div class="hero-links"', content)
    if not m:
        return []
    block = m.group(1)
    # Find each contact-item block
    items = re.findall(r'<div class="contact-item">([\s\S]*?)</div>', block)
    result = []
    for item in items:
        label_m = re.search(r'<span class="contact-label">([^<]+)</span>', item)
        values = re.findall(r'<span class="contact-value">([^<]+)</span>', item)
        if label_m and values:
            result.append({"label": label_m.group(1).strip(), "values": [v.strip() for v in values]})
    return result


def write_contacts(contacts: list[dict]) -> None:
    content = read_html()
    items_html = ""
    for c in contacts:
        values = c.get("values") or ([c["value"]] if c.get("value") else [])
        vals_html = "\n".join(f'          <span class="contact-value">{v}</span>' for v in values)
        items_html += (
            f'        <div class="contact-item">\n'
            f'          <span class="contact-label">{c["label"]}</span>\n'
            f'{vals_html}\n'
            f'        </div>\n'
        )
    new_grid = f'<div class="contact-grid" id="contactGrid">\n{items_html}      </div>'
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



ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>主页管理器 — Shuo Zhao</title>
<style>
  :root{--bg:#F7F3EC;--card:#EDE6DA;--ink:#1A1208;--muted:#7A6E5E;--red:#C0392B;--border:rgba(26,18,8,0.15)}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--ink);font-family:'Segoe UI',sans-serif;font-size:14px;line-height:1.6}
  header{background:var(--ink);color:#F7F3EC;padding:.8rem 2rem;display:flex;align-items:center;justify-content:space-between}
  header h1{font-size:1rem;letter-spacing:.06em}
  header small{font-size:.7rem;opacity:.5;font-family:monospace}
  .wrap{max-width:960px;margin:0 auto;padding:1.2rem 1rem}
  .tabs{display:flex;border-bottom:2px solid var(--border);margin-bottom:1.2rem}
  .tab{padding:.45rem 1.1rem;cursor:pointer;font-size:.83rem;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px;transition:color .2s,border-color .2s}
  .tab.active{color:var(--red);border-bottom-color:var(--red);font-weight:600}
  .panel{display:none}.panel.active{display:block}
  label{display:block;font-size:.75rem;color:var(--muted);margin-bottom:.25rem;letter-spacing:.04em}
  input,textarea,select{width:100%;padding:.4rem .65rem;border:1px solid var(--border);border-radius:4px;background:#fff;color:var(--ink);font-size:.85rem;font-family:inherit;outline:none;transition:border-color .2s}
  input:focus,textarea:focus{border-color:var(--red)}
  textarea{resize:vertical;min-height:72px}
  .g2{display:grid;grid-template-columns:1fr 1fr;gap:.65rem;margin-bottom:.65rem}
  .g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.65rem;margin-bottom:.65rem}
  .g4{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:.65rem;margin-bottom:.65rem}
  .btn{padding:.35rem .9rem;border-radius:4px;cursor:pointer;font-size:.8rem;font-family:inherit;border:1px solid;transition:background .2s}
  .btn-red{background:var(--red);color:#fff;border-color:var(--red)}.btn-red:hover{background:#9B2D20}
  .btn-out{background:transparent;color:var(--red);border-color:var(--red)}.btn-out:hover{background:rgba(192,57,43,.08)}
  .btn-dark{background:var(--ink);color:#F7F3EC;border-color:var(--ink)}.btn-dark:hover{background:#2d2010}
  .btn-del{background:transparent;color:#aaa;border-color:#ddd;font-size:.72rem;padding:.2rem .5rem}.btn-del:hover{color:var(--red);border-color:var(--red)}
  .btn-sm{padding:.22rem .6rem;font-size:.72rem}
  .card{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:.85rem 1.1rem;margin-bottom:.6rem}
  .card-hd{display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem;margin-bottom:.35rem}
  .card-title{font-size:.85rem;font-weight:600;color:var(--ink);line-height:1.4;flex:1}
  .card-meta{font-size:.72rem;color:var(--muted);font-family:monospace;display:flex;flex-wrap:wrap;gap:.3rem .8rem;margin-top:.25rem}
  .badge{display:inline-block;font-size:.62rem;padding:.08rem .38rem;border-radius:3px;font-family:monospace}
  .bq1{background:rgba(192,57,43,.1);color:var(--red);border:1px solid rgba(192,57,43,.3)}
  .bq2{background:rgba(74,63,47,.07);color:var(--muted);border:1px solid var(--border)}
  .bsci{background:rgba(0,100,200,.07);color:#1a5a9a;border:1px solid rgba(0,100,200,.2)}
  .bfirst{background:rgba(192,57,43,.12);color:var(--red);border:1px solid rgba(192,57,43,.4)}
  .sec-title{font-size:.95rem;font-weight:600;margin-bottom:.9rem;padding-left:.65rem;border-left:3px solid var(--red)}
  .add-form{background:#fff;border:1px dashed var(--border);border-radius:6px;padding:.9rem 1.1rem;margin-top:.9rem}
  .add-form h4{font-size:.75rem;color:var(--muted);margin-bottom:.65rem;letter-spacing:.05em;text-transform:uppercase}
  .chk-row{display:flex;align-items:center;gap:.45rem}
  .chk-row input[type=checkbox]{width:auto}
  .edit-form{display:none;background:#fff;border:1px solid rgba(192,57,43,.2);border-radius:5px;padding:.8rem 1rem;margin-top:.5rem}
  .edit-form.open{display:block}
  .push-bar{display:flex;gap:.65rem;align-items:center;margin-top:1.4rem;padding-top:.9rem;border-top:1px solid var(--border)}
  .push-bar input{flex:1}
  #statusMsg{font-size:.75rem;color:var(--muted);font-family:monospace}
  .toast{position:fixed;bottom:1.2rem;right:1.2rem;padding:.6rem 1.1rem;border-radius:6px;font-size:.82rem;font-family:monospace;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none}
  .toast.show{opacity:1}
  .toast.ok{background:#1a7a3a;color:#fff}
  .toast.err{background:var(--red);color:#fff}
  .wos-bar{display:flex;gap:.5rem;align-items:center;margin-bottom:.9rem;padding:.6rem .9rem;background:rgba(0,100,200,.05);border:1px solid rgba(0,100,200,.15);border-radius:5px}
  .wos-bar span{font-size:.75rem;color:var(--muted);font-family:monospace;flex:1}
</style>
</head>
<body>
<header>
  <h1>主页管理器 · Homepage Manager</h1>
  <small>shzhao27208.github.io · port 8765</small>
</header>
<div class="wrap">
  <div class="tabs">
    <div class="tab active" onclick="sw('bio')">个人简介</div>
    <div class="tab" onclick="sw('pubs')">学术项目</div>
    <div class="tab" onclick="sw('projs')">开源项目</div>
    <div class="tab" onclick="sw('contacts')">联系方式</div>
  </div>

  <!-- Bio -->
  <div class="panel active" id="panel-bio">
    <div class="sec-title">个人简介 / Bio</div>
    <div class="g2">
      <div><label>English Bio</label><textarea id="bioEn" rows="4"></textarea></div>
      <div><label>中文简介</label><textarea id="bioZh" rows="4"></textarea></div>
    </div>
    <button class="btn btn-red" onclick="saveBio()">保存简介</button>
  </div>

  <!-- Pubs -->
  <div class="panel" id="panel-pubs">
    <div class="wos-bar">
      <span id="wosStatus">WoS API — 点击同步 JCR/IF 数据</span>
      <button class="btn btn-out btn-sm" onclick="wosSync()">🔄 从 WoS 同步</button>
    </div>
    <div class="sec-title">学术论文列表</div>
    <div id="pubCards"></div>
    <div class="add-form">
      <h4>+ 添加新论文</h4>
      <div class="g2">
        <div><label>论文标题 *</label><input id="apTitle" placeholder="Full paper title"></div>
        <div><label>期刊名称 *</label><input id="apJournal" placeholder="e.g. CrystEngComm"></div>
      </div>
      <div class="g4">
        <div><label>年份</label><input id="apYear" placeholder="2025"></div>
        <div><label>DOI</label><input id="apDoi" placeholder="10.1039/xxx"></div>
        <div><label>JCR 分区</label>
          <select id="apJcr"><option value="">—</option><option>Q1</option><option>Q2</option><option>Q3</option><option>Q4</option></select>
        </div>
        <div><label>IF</label><input id="apIf" placeholder="3.1"></div>
      </div>
      <div class="g4" style="margin-bottom:.5rem">
        <div><label>作者排名</label><input id="apRank" placeholder="1" type="number" min="1"></div>
        <div><label>作者总数</label><input id="apTotal" placeholder="9" type="number" min="1"></div>
        <div><label>一作类型</label>
          <select id="apFirstType"><option value="">普通作者</option><option value="sole">一作</option><option value="co">共同一作</option></select>
        </div>
        <div style="display:flex;align-items:flex-end;gap:.5rem">
          <div class="chk-row"><input type="checkbox" id="apSci" checked><label style="margin:0">SCI</label></div>
        </div>
      </div>
      <button class="btn btn-out" onclick="addPub()">+ 添加</button>
    </div>
  </div>

  <!-- Projs -->
  <div class="panel" id="panel-projs">
    <div class="sec-title">开源项目列表</div>
    <div id="projCards"></div>
    <div class="add-form">
      <h4>+ 添加新项目</h4>
      <div class="g2">
        <div><label>项目名称 *</label><input id="aprName" placeholder="Repo name"></div>
        <div><label>GitHub Repo slug *</label><input id="aprRepo" placeholder="e.g. Aut_Sci_Write"></div>
      </div>
      <div class="g2">
        <div><label>英文描述</label><input id="aprDescEn" placeholder="English description"></div>
        <div><label>中文描述</label><input id="aprDescZh" placeholder="中文描述"></div>
      </div>
      <button class="btn btn-out" onclick="addProj()">+ 添加</button>
    </div>
  </div>

  <!-- Contacts -->
  <div class="panel" id="panel-contacts">
    <div class="sec-title">联系方式</div>
    <div id="contactCards"></div>
    <div class="add-form">
      <h4>+ 添加联系方式</h4>
      <div class="g2">
        <div><label>类型</label>
          <select id="acLabel">
            <option>Tel</option><option>Email</option><option>QQ</option>
            <option>WeChat</option><option>GitHub</option><option>其他</option>
          </select>
        </div>
        <div><label>值</label><input id="acValue" placeholder="号码 / 地址"></div>
      </div>
      <button class="btn btn-out" onclick="addContact()">+ 添加</button>
    </div>
  </div>

  <!-- Push bar -->
  <div class="push-bar">
    <input id="commitMsg" placeholder="Commit message（留空使用默认）">
    <button class="btn btn-dark" onclick="pushAll()">💾 保存并推送到 GitHub</button>
    <span id="statusMsg"></span>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
let D = {pubs:[], projs:[], bioEn:'', bioZh:'', contacts:[]};

async function load() {
  const r = await fetch('/api/data');
  D = await r.json();
  document.getElementById('bioEn').value = D.bioEn || '';
  document.getElementById('bioZh').value = D.bioZh || '';
  renderPubs(); renderProjs(); renderContacts();
}

function sw(name) {
  const names = ['bio','pubs','projs','contacts'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', names[i]===name));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
}

/* ── Pubs ── */
function renderPubs() {
  const el = document.getElementById('pubCards');
  el.innerHTML = '';
  D.pubs.forEach((p, i) => {
    const jb = p.jcr ? `<span class="badge b${p.jcr.toLowerCase()}">${p.jcr}</span>` : '';
    const fb = p.firstType==='sole' ? `<span class="badge bfirst">★ 一作</span>`
             : p.firstType==='co'   ? `<span class="badge bfirst">☆ 共同一作</span>` : '';
    const sb = p.sci ? `<span class="badge bsci">SCI</span>` : '';
    const rank = (p.authorRank && p.authorTotal) ? `${p.authorRank}/${p.authorTotal}` : '';
    el.innerHTML += `
      <div class="card" id="pc${i}">
        <div class="card-hd">
          <div class="card-title">${p.title}</div>
          <div style="display:flex;gap:.35rem;flex-shrink:0">
            <button class="btn btn-out btn-sm" onclick="toggleEdit('pe${i}')">编辑</button>
            <button class="btn btn-del" onclick="delPub(${i})">删除</button>
          </div>
        </div>
        <div class="card-meta">
          ${jb}${fb}${sb}
          <span>${p.journal||''}</span><span>${p.year||''}</span>
          ${p.if ? `<span>IF ${p.if}</span>` : ''}
          ${rank ? `<span>${rank}</span>` : ''}
          ${p.doi ? `<a href="https://doi.org/${p.doi}" target="_blank" style="color:var(--red)">DOI: ${p.doi}</a>` : ''}
        </div>
        <div class="edit-form" id="pe${i}">
          <div class="g2"><input placeholder="标题" value="${esc(p.title)}" onchange="D.pubs[${i}].title=this.value">
          <input placeholder="期刊" value="${esc(p.journal||'')}" onchange="D.pubs[${i}].journal=this.value"></div>
          <div class="g4" style="margin-bottom:.5rem">
            <input placeholder="年份" value="${esc(p.year||'')}" onchange="D.pubs[${i}].year=this.value">
            <input placeholder="DOI" value="${esc(p.doi||'')}" onchange="D.pubs[${i}].doi=this.value">
            <select onchange="D.pubs[${i}].jcr=this.value">
              ${['','Q1','Q2','Q3','Q4'].map(v=>`<option${v===p.jcr?' selected':''}>${v||'—'}</option>`).join('')}
            </select>
            <input placeholder="IF" value="${esc(p.if||'')}" onchange="D.pubs[${i}].if=this.value">
          </div>
          <div class="g4" style="margin-bottom:.5rem">
            <input placeholder="作者排名" type="number" value="${p.authorRank||''}" onchange="D.pubs[${i}].authorRank=+this.value">
            <input placeholder="作者总数" type="number" value="${p.authorTotal||''}" onchange="D.pubs[${i}].authorTotal=+this.value">
            <select onchange="D.pubs[${i}].firstType=this.value">
              ${[['','普通作者'],['sole','一作'],['co','共同一作']].map(([v,l])=>`<option value="${v}"${v===p.firstType?' selected':''}>${l}</option>`).join('')}
            </select>
            <div class="chk-row"><input type="checkbox" ${p.sci?'checked':''} onchange="D.pubs[${i}].sci=this.checked"><label style="margin:0">SCI</label></div>
          </div>
          <button class="btn btn-red btn-sm" onclick="renderPubs();toast('已更新')">✓ 确认</button>
        </div>
      </div>`;
  });
}

function toggleEdit(id) {
  const el = document.getElementById(id);
  el.classList.toggle('open');
}

function addPub() {
  const title = document.getElementById('apTitle').value.trim();
  if (!title) { toast('请填写标题', false); return; }
  D.pubs.push({
    title, journal: document.getElementById('apJournal').value.trim(),
    year: document.getElementById('apYear').value.trim(),
    doi: document.getElementById('apDoi').value.trim(),
    jcr: document.getElementById('apJcr').value,
    if: document.getElementById('apIf').value.trim(),
    sci: document.getElementById('apSci').checked,
    authorRank: +document.getElementById('apRank').value || 0,
    authorTotal: +document.getElementById('apTotal').value || 0,
    firstType: document.getElementById('apFirstType').value,
  });
  renderPubs();
  ['apTitle','apJournal','apYear','apDoi','apIf','apRank','apTotal'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('apJcr').value='';
  document.getElementById('apFirstType').value='';
  toast('论文已添加');
}

function delPub(i) {
  if (!confirm('确认删除？')) return;
  D.pubs.splice(i,1); renderPubs();
}

/* ── Projs ── */
function renderProjs() {
  const el = document.getElementById('projCards');
  el.innerHTML = '';
  D.projs.forEach((p, i) => {
    el.innerHTML += `
      <div class="card">
        <div class="card-hd">
          <div class="card-title" style="font-family:monospace">${p.name}</div>
          <div style="display:flex;gap:.35rem;flex-shrink:0">
            <button class="btn btn-out btn-sm" onclick="toggleEdit('prje${i}')">编辑</button>
            <button class="btn btn-del" onclick="delProj(${i})">删除</button>
          </div>
        </div>
        <div class="card-meta"><span>github.com/ShZhao27208/${p.repo}</span><span>${p.descEn}</span></div>
        <div class="edit-form" id="prje${i}">
          <div class="g2" style="margin-bottom:.5rem">
            <input placeholder="名称" value="${esc(p.name)}" onchange="D.projs[${i}].name=this.value">
            <input placeholder="Repo slug" value="${esc(p.repo)}" onchange="D.projs[${i}].repo=this.value">
          </div>
          <div class="g2" style="margin-bottom:.5rem">
            <input placeholder="英文描述" value="${esc(p.descEn||'')}" onchange="D.projs[${i}].descEn=this.value">
            <input placeholder="中文描述" value="${esc(p.descZh||'')}" onchange="D.projs[${i}].descZh=this.value">
          </div>
          <button class="btn btn-red btn-sm" onclick="renderProjs();toast('已更新')">✓ 确认</button>
        </div>
      </div>`;
  });
}

function addProj() {
  const name = document.getElementById('aprName').value.trim();
  const repo = document.getElementById('aprRepo').value.trim();
  if (!name||!repo) { toast('请填写名称和 Repo', false); return; }
  D.projs.push({ name, repo,
    descEn: document.getElementById('aprDescEn').value.trim(),
    descZh: document.getElementById('aprDescZh').value.trim(),
  });
  renderProjs();
  ['aprName','aprRepo','aprDescEn','aprDescZh'].forEach(id=>document.getElementById(id).value='');
  toast('项目已添加');
}

function delProj(i) {
  if (!confirm('确认删除？')) return;
  D.projs.splice(i,1); renderProjs();
}

/* ── Contacts ── */
function renderContacts() {
  const el = document.getElementById('contactCards');
  el.innerHTML = '';
  (D.contacts||[]).forEach((c, i) => {
    el.innerHTML += `
      <div class="card">
        <div class="card-hd">
          <div class="card-title"><span style="color:var(--red);font-family:monospace;font-size:.8rem">${c.label}</span> &nbsp; ${c.value}</div>
          <div style="display:flex;gap:.35rem;flex-shrink:0">
            <button class="btn btn-out btn-sm" onclick="toggleEdit('ce${i}')">编辑</button>
            <button class="btn btn-del" onclick="delContact(${i})">删除</button>
          </div>
        </div>
        <div class="edit-form" id="ce${i}">
          <div class="g2" style="margin-bottom:.5rem">
            <input placeholder="类型" value="${esc(c.label)}" onchange="D.contacts[${i}].label=this.value">
            <input placeholder="值" value="${esc(c.value)}" onchange="D.contacts[${i}].value=this.value">
          </div>
          <button class="btn btn-red btn-sm" onclick="renderContacts();toast('已更新')">✓ 确认</button>
        </div>
      </div>`;
  });
}

function addContact() {
  const label = document.getElementById('acLabel').value;
  const value = document.getElementById('acValue').value.trim();
  if (!value) { toast('请填写值', false); return; }
  if (!D.contacts) D.contacts = [];
  D.contacts.push({label, value});
  renderContacts();
  document.getElementById('acValue').value = '';
  toast('联系方式已添加');
}

function delContact(i) {
  if (!confirm('确认删除？')) return;
  D.contacts.splice(i,1); renderContacts();
}

/* ── Bio ── */
async function saveBio() {
  D.bioEn = document.getElementById('bioEn').value.trim();
  D.bioZh = document.getElementById('bioZh').value.trim();
  const r = await post('/api/save-bio', {bioEn: D.bioEn, bioZh: D.bioZh});
  toast(r.ok ? '简介已保存 ✓' : '失败: '+r.msg, r.ok);
}

/* ── WoS sync ── */
async function wosSync() {
  document.getElementById('wosStatus').textContent = '正在同步...';
  const r = await post('/api/wos-sync', {pubs: D.pubs});
  if (r.ok) { D.pubs = r.pubs; renderPubs(); }
  document.getElementById('wosStatus').textContent = r.msg || (r.ok ? '同步完成' : '同步失败');
  toast(r.ok ? r.msg : r.msg, r.ok);
}

/* ── Push ── */
async function pushAll() {
  const msg = document.getElementById('commitMsg').value.trim() || 'update: homepage content via manager';
  document.getElementById('statusMsg').textContent = '保存中...';
  const s = await post('/api/save', D);
  if (!s.ok) { toast('保存失败: '+s.msg, false); document.getElementById('statusMsg').textContent=''; return; }
  document.getElementById('statusMsg').textContent = '推送中...';
  const p = await post('/api/push', {message: msg});
  document.getElementById('statusMsg').textContent = p.ok ? '✓ 推送成功' : '✗ '+p.msg;
  toast(p.ok ? '已推送到 GitHub ✓' : '推送失败: '+p.msg, p.ok);
}

/* ── Helpers ── */
async function post(url, body) {
  try {
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    return await r.json();
  } catch(e) { return {ok:false, msg:String(e)}; }
}

function esc(s) { return String(s||'').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }

function toast(msg, ok=true) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.className = 'toast show '+(ok?'ok':'err');
  setTimeout(()=>el.classList.remove('show'), 3000);
}

load();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            body = ADMIN_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        elif urlparse(self.path).path == "/api/data":
            self.send_json(extract_data())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode())
        path = urlparse(self.path).path

        if path == "/api/save":
            try:
                write_pubs(body.get("pubs", []))
                write_projs(body.get("projs", []))
                if body.get("contacts") is not None:
                    write_contacts(body["contacts"])
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "msg": str(e)})

        elif path == "/api/save-bio":
            try:
                write_bio(body.get("bioEn", ""), body.get("bioZh", ""))
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "msg": str(e)})

        elif path == "/api/wos-sync":
            try:
                pubs, msg = wos_sync(body.get("pubs", []))
                self.send_json({"ok": True, "pubs": pubs, "msg": msg})
            except Exception as e:
                self.send_json({"ok": False, "msg": str(e)})

        elif path == "/api/push":
            self.send_json(git_push(body.get("message", "update: homepage content via manager")))

        else:
            self.send_response(404); self.end_headers()


def main():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"主页管理器已启动: {url}")
    print("按 Ctrl+C 退出")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()

