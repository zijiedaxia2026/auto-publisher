#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删除今天新发的 3 篇掘金重复稿（保留有展现的旧版）。"""
import os
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
STATE = BASE / ".publish-state" / "掘金.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
ARGS = ["--disable-blink-features=AutomationControlled", "--window-position=960,0", "--window-size=1200,1000"]

DEL = [
    ("01新版", "7699818345805824043"),
    ("02新版", "7699871906405662762"),
    ("07新版", "7699871906405695530"),
]
KEEP = [
    ("01旧版", "7698737595539013695"),
    ("02旧版", "7699411361328021547"),
    ("07旧版", "7699764120468111414"),
]

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

JS = r"""async ([id, doDel]) => {
  const url = doDel
    ? 'https://api.juejin.cn/content_api/v1/article/delete'
    : 'https://api.juejin.cn/content_api/v1/article/detail';
  const body = {article_id: id, req_from: 1, client_type: 2608};
  try {
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body), credentials:'include'});
    const t = await r.text();
    return {status: r.status, body: t.slice(0, 300)};
  } catch(e) { return {status: -1, body: String(e)}; }
}"""

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=ARGS)
    ctx = br.new_context(user_agent=UA, viewport={"width": 1200, "height": 1000}, locale="zh-CN")
    ctx.add_init_script("""()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}""")
    ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8")))
    pg = ctx.new_page()
    pg.goto("https://juejin.cn/", wait_until="domcontentloaded", timeout=30000); time.sleep(4)
    log("== 删除前 detail 预检 ==")
    for name, aid in DEL:
        r = pg.evaluate(JS, [aid, False])
        log(f"  {name} {aid} detail: {json.dumps(r, ensure_ascii=False)[:220]}")
    log("== 执行删除 ==")
    for name, aid in DEL:
        r = pg.evaluate(JS, [aid, True])
        log(f"  {name} {aid} delete: {json.dumps(r, ensure_ascii=False)[:300]}")
        time.sleep(2)
    log("== 删除后 detail 复核（应 404/err） ==")
    for name, aid in DEL:
        r = pg.evaluate(JS, [aid, False])
        log(f"  {name} {aid} detail: {json.dumps(r, ensure_ascii=False)[:220]}")
    log("== 保留版复核（应 err 0） ==")
    for name, aid in KEEP:
        r = pg.evaluate(JS, [aid, False])
        log(f"  {name} {aid} detail: {json.dumps(r, ensure_ascii=False)[:150]}")
    br.close()
log("DONE")
