#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Personal Homepage Manager
双击运行，浏览器自动打开管理界面
修改论文/项目信息后一键保存并推送到 GitHub
"""

import http.server
import json
import os
import re
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).parent
INDEX_HTML = BASE_DIR / "index.html"
PORT = 8765

# ── 从 index.html 提取当前数据 ──────────────────────────────────────────────

def extract_data():
    content = INDEX_HTML.read_text(encoding="utf-8")

    pubs_m = re.search(r"// @PUBS_START\s*\n\s*//[^\n]*\n\s*const DEFAULT_PUBS\s*=\s*(\[[\s\S]*?\])\s*;\s*\n\s*// @PUBS_END", content)
    projs_m = re.search(r"// @PROJS_START\s*\n\s*const DEFAULT_PROJS\s*=\s*(\[[\s\S]*?\])\s*;\s*\n\s*// @PROJS_END", content)

    pubs = json.loads(pubs_m.group(1)) if pubs_m else []
    projs = json.loads(projs_m.group(1)) if projs_m else []

    bio_en = _extract_bio(content, "bioEn")
    bio_zh = _extract_bio(content, "bioZh")

    return {"pubs": pubs, "projs": projs, "bioEn": bio_en, "bioZh": bio_zh}


def _extract_bio(content, elem_id):
    m = re.search(rf'id="{elem_id}"[^>]*>\s*([\s\S]*?)\s*</p>', content)
    return m.group(1).strip() if m else ""


def _parse_js_array(js_text):
    try:
        js = re.sub(r'(?<=[{,\s])(\w+)\s*:', r'"\1":', js_text)
        js = re.sub(r"'([^'\\]*)'", r'"\1"', js)
        js = re.sub(r",(\s*[}\]])", r"\1", js)
        return json.loads(js)
    except Exception:
        return []


# ── 将修改写回 index.html ────────────────────────────────────────────────────

def write_pubs(pubs):
    content = INDEX_HTML.read_text(encoding="utf-8")
    new_block = (
        "// @PUBS_START\n"
        "  // firstAuthor: true = first/co-first author, sci: true = SCI indexed\n"
        "  const DEFAULT_PUBS = "
        + json.dumps(pubs, ensure_ascii=False, indent=4)
        + ";\n  // @PUBS_END"
    )
    content = re.sub(
        r"// @PUBS_START[\s\S]*?// @PUBS_END",
        new_block,
        content,
        count=1,
    )
    INDEX_HTML.write_text(content, encoding="utf-8")


def write_projs(projs):
    content = INDEX_HTML.read_text(encoding="utf-8")
    new_block = (
        "// @PROJS_START\n"
        "  const DEFAULT_PROJS = "
        + json.dumps(projs, ensure_ascii=False, indent=4)
        + ";\n  // @PROJS_END"
    )
    content = re.sub(
        r"// @PROJS_START[\s\S]*?// @PROJS_END",
        new_block,
        content,
        count=1,
    )
    INDEX_HTML.write_text(content, encoding="utf-8")


def write_bio(bio_en, bio_zh):
    content = INDEX_HTML.read_text(encoding="utf-8")
    content = re.sub(
        r'(id="bioEn"[^>]*data-lang="en"[^>]*>)\s*[\s\S]*?\s*(</p>)',
        lambda m: m.group(1) + "\n        " + bio_en + "\n      " + m.group(2),
        content,
        count=1,
    )
    content = re.sub(
        r'(id="bioZh"[^>]*data-lang="zh"[^>]*>)\s*[\s\S]*?\s*(</p>)',
        lambda m: m.group(1) + "\n        " + bio_zh + "\n      " + m.group(2),
        content,
        count=1,
    )
    INDEX_HTML.write_text(content, encoding="utf-8")


# ── Git 操作 ─────────────────────────────────────────────────────────────────

def git_push(message="update: homepage content via manager"):
    try:
        subprocess.run(["git", "-C", str(BASE_DIR), "add", "index.html"], check=True)
        subprocess.run(["git", "-C", str(BASE_DIR), "commit", "-m", message], check=True)
        result = subprocess.run(
            ["git", "-C", str(BASE_DIR), "push", "origin", "main"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return {"ok": True, "msg": "推送成功 ✓"}
        else:
            return {"ok": False, "msg": result.stderr or result.stdout}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "msg": str(e)}


# ── HTML 管理界面 ─────────────────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>主页管理器 — Shuo Zhao</title>
<style>
  :root { --bg:#F7F3EC; --card:#EDE6DA; --ink:#1A1208; --muted:#7A6E5E; --red:#C0392B; --border:rgba(26,18,8,0.15); }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--ink); font-family:'Noto Serif SC','Segoe UI',serif; font-size:14px; line-height:1.6; }
  header { background:var(--ink); color:#F7F3EC; padding:1rem 2rem; display:flex; align-items:center; justify-content:space-between; }
  header h1 { font-size:1.1rem; letter-spacing:0.08em; }
  header small { font-size:0.72rem; opacity:0.55; font-family:monospace; }
  .container { max-width:900px; margin:0 auto; padding:1.5rem 1rem; }
  .tabs { display:flex; gap:0; border-bottom:2px solid var(--border); margin-bottom:1.5rem; }
  .tab { padding:0.5rem 1.2rem; cursor:pointer; font-size:0.85rem; color:var(--muted); border-bottom:2px solid transparent; margin-bottom:-2px; transition:color 0.2s,border-color 0.2s; }
  .tab.active { color:var(--red); border-bottom-color:var(--red); font-weight:600; }
  .panel { display:none; } .panel.active { display:block; }
  label { display:block; font-size:0.78rem; color:var(--muted); margin-bottom:0.3rem; letter-spacing:0.04em; }
  input, textarea, select {
    width:100%; padding:0.45rem 0.7rem; border:1px solid var(--border);
    border-radius:4px; background:#fff; color:var(--ink); font-size:0.88rem;
    font-family:inherit; outline:none; transition:border-color 0.2s;
  }
  input:focus, textarea:focus { border-color:var(--red); }
  textarea { resize:vertical; min-height:80px; }
  .row { display:grid; gap:0.75rem; margin-bottom:0.75rem; }
  .row-2 { grid-template-columns:1fr 1fr; }
  .row-3 { grid-template-columns:1fr 1fr 1fr; }
  .row-4 { grid-template-columns:1fr 1fr 1fr 1fr; }
  .btn { padding:0.4rem 1rem; border-radius:4px; cursor:pointer; font-size:0.82rem; font-family:inherit; border:1px solid; transition:background 0.2s; }
  .btn-red { background:var(--red); color:#fff; border-color:var(--red); }
  .btn-red:hover { background:#9B2D20; }
  .btn-outline { background:transparent; color:var(--red); border-color:var(--red); }
  .btn-outline:hover { background:rgba(192,57,43,0.08); }
  .btn-dark { background:var(--ink); color:#F7F3EC; border-color:var(--ink); }
  .btn-dark:hover { background:#2d2010; }
  .btn-del { background:transparent; color:#999; border-color:#ddd; font-size:0.75rem; padding:0.25rem 0.6rem; }
  .btn-del:hover { color:var(--red); border-color:var(--red); }
  .card { background:var(--card); border:1px solid var(--border); border-radius:6px; padding:1rem 1.2rem; margin-bottom:0.75rem; }
  .card-header { display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem; margin-bottom:0.5rem; }
  .card-title { font-size:0.88rem; font-weight:600; color:var(--ink); line-height:1.4; flex:1; }
  .card-meta { font-size:0.75rem; color:var(--muted); font-family:monospace; }
  .badge { display:inline-block; font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:3px; font-family:monospace; }
  .badge-q1 { background:rgba(192,57,43,0.1); color:var(--red); border:1px solid rgba(192,57,43,0.3); }
  .badge-q2 { background:rgba(74,63,47,0.08); color:var(--muted); border:1px solid var(--border); }
  .badge-first { background:rgba(192,57,43,0.12); color:var(--red); border:1px solid rgba(192,57,43,0.4); }
  .section-title { font-size:1rem; font-weight:600; margin-bottom:1rem; padding-left:0.7rem; border-left:3px solid var(--red); }
  .add-form { background:#fff; border:1px dashed var(--border); border-radius:6px; padding:1rem 1.2rem; margin-top:1rem; }
  .add-form h4 { font-size:0.8rem; color:var(--muted); margin-bottom:0.75rem; letter-spacing:0.06em; }
  .checkbox-row { display:flex; align-items:center; gap:0.5rem; }
  .checkbox-row input[type=checkbox] { width:auto; }
  .toast { position:fixed; bottom:1.5rem; right:1.5rem; padding:0.7rem 1.2rem; border-radius:6px; font-size:0.85rem; font-family:monospace; z-index:999; opacity:0; transition:opacity 0.3s; pointer-events:none; }
  .toast.show { opacity:1; }
  .toast.ok { background:#1a7a3a; color:#fff; }
  .toast.err { background:var(--red); color:#fff; }
  .push-bar { display:flex; gap:0.75rem; align-items:center; margin-top:1.5rem; padding-top:1rem; border-top:1px solid var(--border); }
  .push-bar input { flex:1; }
  #statusMsg { font-size:0.78rem; color:var(--muted); font-family:monospace; }
</style>
</head>
<body>
<header>
  <h1>主页管理器 · Homepage Manager</h1>
  <small>shzhao27208.github.io</small>
</header>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('bio')">个人简介</div>
    <div class="tab" onclick="switchTab('pubs')">学术项目</div>
    <div class="tab" onclick="switchTab('projs')">开源项目</div>
  </div>

  <!-- Bio Panel -->
  <div class="panel active" id="panel-bio">
    <div class="section-title">个人简介 / Bio</div>
    <div class="row">
      <div>
        <label>English Bio</label>
        <textarea id="bioEn" rows="4"></textarea>
      </div>
      <div>
        <label>中文简介</label>
        <textarea id="bioZh" rows="4"></textarea>
      </div>
    </div>
    <button class="btn btn-red" onclick="saveBio()">保存简介</button>
  </div>

  <!-- Pubs Panel -->
  <div class="panel" id="panel-pubs">
    <div class="section-title">学术论文列表</div>
    <div id="pubCards"></div>
    <div class="add-form">
      <h4>+ 添加新论文</h4>
      <div class="row row-2">
        <div><label>论文标题 *</label><input id="apTitle" placeholder="Full paper title"></div>
        <div><label>期刊名称 *</label><input id="apJournal" placeholder="e.g. CrystEngComm"></div>
      </div>
      <div class="row row-4">
        <div><label>年份</label><input id="apYear" placeholder="2025"></div>
        <div><label>DOI</label><input id="apDoi" placeholder="10.1039/xxx"></div>
        <div><label>JCR 分区</label>
          <select id="apJcr"><option value="">—</option><option value="Q1">Q1</option><option value="Q2">Q2</option><option value="Q3">Q3</option><option value="Q4">Q4</option></select>
        </div>
        <div><label>影响因子 IF</label><input id="apIf" placeholder="3.1"></div>
      </div>
      <div class="row row-2">
        <div class="checkbox-row"><input type="checkbox" id="apSci" checked><label style="margin:0">SCI 收录</label></div>
        <div class="checkbox-row"><input type="checkbox" id="apFirst"><label style="margin:0">一作 / 共同一作</label></div>
      </div>
      <button class="btn btn-outline" onclick="addPub()" style="margin-top:0.5rem">+ 添加</button>
    </div>
  </div>

  <!-- Projs Panel -->
  <div class="panel" id="panel-projs">
    <div class="section-title">开源项目列表</div>
    <div id="projCards"></div>
    <div class="add-form">
      <h4>+ 添加新项目</h4>
      <div class="row row-2">
        <div><label>项目名称 *</label><input id="aprName" placeholder="Repo name"></div>
        <div><label>GitHub Repo slug *</label><input id="aprRepo" placeholder="e.g. Aut_Sci_Write"></div>
      </div>
      <div class="row row-2">
        <div><label>英文描述</label><input id="aprDescEn" placeholder="English description"></div>
        <div><label>中文描述</label><input id="aprDescZh" placeholder="中文描述"></div>
      </div>
      <button class="btn btn-outline" onclick="addProj()" style="margin-top:0.5rem">+ 添加</button>
    </div>
  </div>

  <!-- Push bar -->
  <div class="push-bar">
    <input id="commitMsg" placeholder="Commit message (留空使用默认)" value="">
    <button class="btn btn-dark" onclick="pushToGitHub()">💾 保存并推送到 GitHub</button>
    <span id="statusMsg"></span>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let data = {pubs:[], projs:[], bioEn:'', bioZh:''};

async function loadData() {
  const res = await fetch('/api/data');
  data = await res.json();
  document.getElementById('bioEn').value = data.bioEn || '';
  document.getElementById('bioZh').value = data.bioZh || '';
  renderPubs();
  renderProjs();
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    const names = ['bio','pubs','projs'];
    t.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
}

function renderPubs() {
  const el = document.getElementById('pubCards');
  el.innerHTML = '';
  data.pubs.forEach((p, i) => {
    const jcrBadge = p.jcr ? `<span class="badge badge-${p.jcr.toLowerCase()}">${p.jcr}</span>` : '';
    const firstBadge = p.firstAuthor ? `<span class="badge badge-first">★ 一作</span>` : '';
    const sciBadge = p.sci ? `<span class="badge" style="background:rgba(0,100,200,0.08);color:#1a5a9a;border:1px solid rgba(0,100,200,0.2)">SCI</span>` : '';
    el.innerHTML += `
      <div class="card">
        <div class="card-header">
          <div class="card-title">${p.title}</div>
          <button class="btn btn-del" onclick="delPub(${i})">删除</button>
        </div>
        <div class="card-meta">
          ${p.journal || ''} · ${p.year || ''} · IF ${p.if || '—'}
          ${jcrBadge} ${firstBadge} ${sciBadge}
          ${p.doi ? `· <a href="https://doi.org/${p.doi}" target="_blank" style="color:#C0392B">DOI: ${p.doi}</a>` : ''}
        </div>
      </div>`;
  });
}

function renderProjs() {
  const el = document.getElementById('projCards');
  el.innerHTML = '';
  data.projs.forEach((p, i) => {
    el.innerHTML += `
      <div class="card">
        <div class="card-header">
          <div class="card-title" style="font-family:monospace">${p.name}</div>
          <button class="btn btn-del" onclick="delProj(${i})">删除</button>
        </div>
        <div class="card-meta">github.com/ShZhao27208/${p.repo} · ${p.descEn}</div>
      </div>`;
  });
}

function addPub() {
  const title = document.getElementById('apTitle').value.trim();
  const journal = document.getElementById('apJournal').value.trim();
  if (!title) { toast('请填写论文标题', false); return; }
  data.pubs.push({
    title, journal,
    year: document.getElementById('apYear').value.trim(),
    doi: document.getElementById('apDoi').value.trim(),
    jcr: document.getElementById('apJcr').value,
    if: document.getElementById('apIf').value.trim(),
    sci: document.getElementById('apSci').checked,
    firstAuthor: document.getElementById('apFirst').checked,
  });
  renderPubs();
  ['apTitle','apJournal','apYear','apDoi','apIf'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('apJcr').value = '';
  document.getElementById('apFirst').checked = false;
  toast('论文已添加，记得保存推送');
}

function delPub(i) {
  if (!confirm('确认删除这篇论文？')) return;
  data.pubs.splice(i, 1);
  renderPubs();
}

function addProj() {
  const name = document.getElementById('aprName').value.trim();
  const repo = document.getElementById('aprRepo').value.trim();
  if (!name || !repo) { toast('请填写项目名称和 Repo slug', false); return; }
  data.projs.push({
    name, repo,
    descEn: document.getElementById('aprDescEn').value.trim(),
    descZh: document.getElementById('aprDescZh').value.trim(),
  });
  renderProjs();
  ['aprName','aprRepo','aprDescEn','aprDescZh'].forEach(id => document.getElementById(id).value = '');
  toast('项目已添加，记得保存推送');
}

function delProj(i) {
  if (!confirm('确认删除这个项目？')) return;
  data.projs.splice(i, 1);
  renderProjs();
}

async function saveBio() {
  data.bioEn = document.getElementById('bioEn').value.trim();
  data.bioZh = document.getElementById('bioZh').value.trim();
  const res = await fetch('/api/save-bio', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({bioEn: data.bioEn, bioZh: data.bioZh})
  });
  const r = await res.json();
  toast(r.ok ? '简介已保存到 index.html ✓' : '保存失败: ' + r.msg, r.ok);
}

async function pushToGitHub() {
  const msg = document.getElementById('commitMsg').value.trim() || 'update: homepage content via manager';
  document.getElementById('statusMsg').textContent = '正在保存并推送...';

  // Save pubs and projs first
  const saveRes = await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  });
  const saveR = await saveRes.json();
  if (!saveR.ok) { toast('保存失败: ' + saveR.msg, false); document.getElementById('statusMsg').textContent = ''; return; }

  const pushRes = await fetch('/api/push', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({message: msg})
  });
  const pushR = await pushRes.json();
  document.getElementById('statusMsg').textContent = pushR.ok ? '✓ 推送成功' : '✗ ' + pushR.msg;
  toast(pushR.ok ? '已推送到 GitHub ✓' : '推送失败: ' + pushR.msg, pushR.ok);
}

function toast(msg, ok=true) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + (ok ? 'ok' : 'err');
  setTimeout(() => el.classList.remove('show'), 3000);
}

loadData();
</script>
</body>
</html>
"""


# ── HTTP 请求处理 ─────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access logs

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            body = ADMIN_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/data":
            self.send_json(extract_data())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        path = urlparse(self.path).path

        if path == "/api/save":
            try:
                write_pubs(body.get("pubs", []))
                write_projs(body.get("projs", []))
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "msg": str(e)})

        elif path == "/api/save-bio":
            try:
                write_bio(body.get("bioEn", ""), body.get("bioZh", ""))
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "msg": str(e)})

        elif path == "/api/push":
            result = git_push(body.get("message", "update: homepage content"))
            self.send_json(result)

        else:
            self.send_response(404)
            self.end_headers()


# ── 启动 ──────────────────────────────────────────────────────────────────────

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
