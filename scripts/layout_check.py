#!/usr/bin/env python3
"""Automated layout audit (v109) — no eyeballing.

Playwright is not installed in this container (the npm package is absent and installing browsers
needs network). This uses the same idea over the Chrome DevTools Protocol, against the headless
Chrome already running on :9222: navigate, run the assertions in-page, print one line per screen.

Usage: python3 scripts/layout_check.py [base_url]
Exit code 1 if any screen fails.
"""
import asyncio
import json
import os
import sys
import urllib.request

import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
# Any CDP endpoint works: :9222 is the managed browser, a separate headless instance can be pointed
# at the deployed app with CDP=http://127.0.0.1:9333 and left to the person's own tabs.
CDP = os.environ.get("CDP", "http://127.0.0.1:9222")

JS = r"""
(async () => {
  const out = {screens: []};
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const app = document;
  // The app is not always the top document: on Streamlit Cloud it is served inside one wrapper
  // iframe, so the component lives two levels down. Walk them; a document we cannot read is skipped.
  function frames() {
    const out = [];
    (function walk(doc, depth) {
      if (!doc || depth > 2) return;
      [...doc.querySelectorAll('iframe')].forEach(f => {
        let d = null;
        try { d = f.contentDocument; } catch (e) { return; }
        if (!d) return;
        out.push(d);
        walk(d, depth + 1);
      });
    })(app, 0);
    return out;
  }
  function incidentDoc() {
    const f = frames().find(d => d.querySelector('.tiles'));
    return f || null;
  }
  function rect(e) { const r = e.getBoundingClientRect(); return {t:r.top,b:r.bottom,l:r.left,r:r.right,w:r.width,h:r.height}; }
  function overlap(a, b) {
    const x = Math.min(a.r, b.r) - Math.max(a.l, b.l);
    const y = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    return (x > 1 && y > 1) ? {x: Math.round(x), y: Math.round(y)} : null;
  }
  function label(el) { return (el.className || el.tagName || '').toString().slice(0, 40); }

  function checkIncident(doc, name) {
    const res = {screen: name, pass: true, notes: []};
    const cards = [...doc.querySelectorAll('.card, .tile')];
    for (let i = 0; i < cards.length; i++) {
      for (let j = i + 1; j < cards.length; j++) {
        if (cards[i].contains(cards[j]) || cards[j].contains(cards[i])) continue;
        const o = overlap(rect(cards[i]), rect(cards[j]));
        if (o) { res.pass = false; res.notes.push('overlap ' + label(cards[i]) + ' / ' + label(cards[j]) + ' ' + o.x + 'x' + o.y); }
      }
    }
    const body = doc.body, win = doc.defaultView;
    if (body.scrollHeight > win.innerHeight + 1) { res.pass = false; res.notes.push('scrollY ' + body.scrollHeight + '>' + win.innerHeight); }
    if (body.scrollWidth > win.innerWidth + 1) { res.pass = false; res.notes.push('scrollX ' + body.scrollWidth + '>' + win.innerWidth); }

    const bands = ['.hdr', '.tiles', '.hero', '.tabbar', '.panes'].map(s => doc.querySelector(s)).filter(Boolean);
    for (let i = 1; i < bands.length; i++) {
      const a = rect(bands[i-1]), b = rect(bands[i]);
      if (b.t < a.b - 1) { res.pass = false; res.notes.push('order ' + label(bands[i-1]) + ' overlaps ' + label(bands[i])); }
    }
    return res;
  }

  // 1. incident screens, one per tab
  const doc = incidentDoc();
  if (doc) {
    const tabs = [...doc.querySelectorAll('.tab')];
    for (let i = 0; i < tabs.length; i++) {
      tabs[i].click();
      await sleep(60);
      let r = checkIncident(doc, 'incident · ' + tabs[i].innerText.split('\n')[0]);
      const pane = doc.querySelector('.pane.on');
      if (!pane || !pane.innerText.trim()) { r.pass = false; r.notes.push('empty pane'); }
      const name = tabs[i].innerText.split('\n')[0].trim();
      if (name === 'Requests') {
        // v110: the Requests tab pages in place. "Show all" must expand inside the pane (no modal),
        // the pane must keep its height, and every row must offer a live ?action= link.
        const box = doc.querySelector('.panes');
        const h0 = Math.round(rect(box).h);
        if (!doc.querySelectorAll('.pane.on .req').length) { r.pass = false; r.notes.push('no request cards'); }
        const tog = doc.querySelector('.pane.on [data-req="1"]');
        if (!tog) { r.pass = false; r.notes.push('no show-all control'); }
        else {
          tog.click(); await sleep(90);
          const fullBox = doc.querySelector('.pane.on .reqfull');
          if (!fullBox || fullBox.hasAttribute('hidden')) { r.pass = false; r.notes.push('show all did not expand in place'); }
          if (doc.getElementById('ov').classList.contains('on')) { r.pass = false; r.notes.push('show all opened a modal'); }
          const h1 = Math.round(rect(box).h);
          if (Math.abs(h1 - h0) > 1) { r.pass = false; r.notes.push('pane height ' + h0 + '->' + h1); }
          const range = doc.querySelector('.pane.on .pager .range');
          if (!range || !/^\d+–\d+ of \d+$/.test(range.innerText.trim())) { r.pass = false; r.notes.push('no 1–N of M range'); }
          const rows = [...doc.querySelectorAll('.pane.on .rrow')];
          if (!rows.length) { r.pass = false; r.notes.push('expanded view empty'); }
          const live = rows.filter(x => !/DONE/.test((x.querySelector('.st') || {}).innerText || ''));
          const dead = live.filter(x => !x.querySelector('a[href*="action="]')).length;
          if (dead) { r.pass = false; r.notes.push(dead + ' live row(s) without an action'); }
          const back = doc.querySelector('.pane.on [data-req="0"]');
          if (back) { back.click(); await sleep(90); }
          const prev = doc.querySelector('.pane.on .reqprev');
          if (!prev || prev.hasAttribute('hidden')) { r.pass = false; r.notes.push('show fewer did not collapse'); }
          const h2 = Math.round(rect(box).h);
          if (Math.abs(h2 - h0) > 1) { r.pass = false; r.notes.push('pane height after collapse ' + h2); }
        }
        out.screens.push(r);
        continue;
      }
      const more = doc.querySelector('.pane.on .more');
      if (more) {
        more.click(); await sleep(60);
        const ov = doc.getElementById('ov');
        if (!ov || !ov.classList.contains('on') || !doc.getElementById('ovbody').innerText.trim()) {
          r.pass = false; r.notes.push('show all failed');
        }
        doc.getElementById('ovclose').click(); await sleep(40);
      }
      out.screens.push(r);
    }
  }

  // 2. streamlit pages: no horizontal overflow, no stVerticalBlock sibling overlap
  function checkPage(name) {
    const res = {screen: name, pass: true, notes: []};
    const el = app.scrollingElement;
    if (el.scrollWidth > window.innerWidth + 1) { res.pass = false; res.notes.push('scrollX ' + el.scrollWidth + '>' + window.innerWidth); }
    const blocks = [...app.querySelectorAll('[data-testid="stVerticalBlock"]')].filter(b => b.offsetParent);
    for (let i = 0; i < blocks.length; i++) {
      for (let j = i + 1; j < blocks.length; j++) {
        if (blocks[i].contains(blocks[j]) || blocks[j].contains(blocks[i])) continue;
        const a = rect(blocks[i]), b = rect(blocks[j]);
        if (Math.abs(a.t - b.t) < 2 && Math.abs(a.l - b.l) < 2 && Math.abs(a.h - b.h) < 2) {
          res.pass = false; res.notes.push('duplicate block at ' + Math.round(a.t));
        }
      }
    }
    out.screens.push(res);
  }
  checkPage('incidents list');
  return out;
})()
"""


WAIT_DOC = r"""
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const find = () => {
    const out = [];
    (function walk(doc, depth) {
      if (!doc || depth > 2) return;
      [...doc.querySelectorAll('iframe')].forEach(f => {
        let d = null;
        try { d = f.contentDocument; } catch (e) { return; }
        if (!d) return;
        out.push(d);
        walk(d, depth + 1);
      });
    })(document, 0);
    return out.find(d => d.querySelector('.tiles')) || null;
  };
  for (let i = 0; i < 30; i++) { if (find()) return true; await sleep(2000); }
  return false;
})()
"""


async def evaluate(ws, expr):
    await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                              "params": {"expression": expr, "awaitPromise": True,
                                         "returnByValue": True}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == 1:
            return msg["result"]["result"].get("value")


async def run(screen, url, script=None):
    req = urllib.request.Request(f"{CDP}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    target = json.loads(urllib.request.urlopen(req, timeout=10).read())
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=2 ** 24) as ws:
        await ws.send(json.dumps({"id": 0, "method": "Page.enable"}))
        await asyncio.sleep(6)
        if not await evaluate(ws, WAIT_DOC):
            raise RuntimeError(f"no incident document rendered at {url} after 60s")
        result = await evaluate(ws, JS)
        if script:
            await evaluate(ws, script)
            await asyncio.sleep(1)
            result = await evaluate(ws, JS)
    urllib.request.urlopen(f"{CDP}/json/close/{target['id']}", timeout=10).read()
    return result


async def main():
    screens = [("incident INC-8841", f"{BASE}/?inc=INC-8841"),
               ("incident DOP-1001", f"{BASE}/?inc=DOP-1001")]
    failures = 0
    for name, url in screens:
        res = await run(name, url)
        for r in res["screens"]:
            status = "PASS" if r["pass"] else "FAIL"
            print(f'{status}  {r["screen"]:<38} {" ".join(r["notes"])[:110]}')
            failures += 0 if r["pass"] else 1
    return 1 if failures else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402
    sys.exit(asyncio.run(main()))
