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
import sys
import urllib.request

import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
CDP = "http://127.0.0.1:9222"

JS = r"""
(async () => {
  const out = {screens: []};
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const app = document;
  function frames() {
    return [...app.querySelectorAll('iframe')].map(f => { try { return f.contentDocument; } catch (e) { return null; } }).filter(Boolean);
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
