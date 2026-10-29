#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整拉掘金已发布文章（标题/链接/时间），翻页到底。"""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("/Users/lisa/WorkBuddy/内容运营")
STATE = BASE / ".publish-state" / "掘金.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
ARGS = ["--disable-blink-features=AutomationControlled", "--window-position=960,0", "--window-size=1200,1000"]

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

with sync_playwright() as p:
    br = p.chromium.launch(headless=False, args=ARGS)
    ctx = br.new_context(user_agent=UA, viewport={"width": 1200, "height": 1000}, locale="zh-CN")
    ctx.add_init_script("""()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}""")
    ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8")))
    pg = ctx.new_page()
    pg.goto("https://juejin.cn/creator/content/article/essays", wait_until="domcontentloaded", timeout=30000)
    time.sleep(8)
    last = 0
    for i in range(12):
        pg.mouse.wheel(0, 3000); time.sleep(2.2)
        h = pg.evaluate("()=>document.body.scrollHeight")
        n = pg.evaluate(r"""()=>document.querySelectorAll('a[href*="/post/"]').length""")
        log(f"scroll {i} height={h} links={n}")
        if h == last and i > 2: break
        last = h
    rows = pg.evaluate(r"""()=>{
      const out=[];
      document.querySelectorAll('a[href*="/post/"]').forEach(a=>{
        const h=a.getAttribute('href')||'';
        const m=h.match(/\/post\/(\d+)/);
        if(!m) return;
        // 向上找卡片容器取时间
        let card=a.closest('div,li')||a;
        for(let k=0;k<6;k++){ if(card.parentElement && card.textContent.length<400) card=card.parentElement; else break; }
        const txt=(card.textContent||'').replace(/\s+/g,' ').trim();
        const dm=txt.match(/(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2})/);
        out.push({id:m[1], title:(a.textContent||'').replace(/\s+/g,' ').trim().slice(0,50), time: dm?dm[1]:'', txt: txt.slice(0,140)});
      });
      const seen=new Set(), u=[];
      for(const r of out){ if(!seen.has(r.id)){seen.add(r.id); u.push(r);} }
      return u;
    }""")
    log("=== 全部 ===")
    for r in rows:
        log(json.dumps(r, ensure_ascii=False))
    log(f"唯一文章 {len(rows)} 篇")
    br.close()
log("DONE")
