#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯云后台：点页码 1..N 拉全部文章卡片（标题/状态/日期/ID）。"""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("/Users/lisa/WorkBuddy/内容运营")
STATE = BASE / ".publish-state" / "腾讯云.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

JS = r"""()=>{
  const out=[];
  document.querySelectorAll('a[href*="/developer/article/"]').forEach(a=>{
    const h=a.getAttribute('href')||''; const m=h.match(/article\/(\d+)/); if(!m) return;
    const t=(a.textContent||'').replace(/\s+/g,' ').trim(); if(t.length<8) return;
    // 向上找卡片取状态/日期
    let c=a;
    for(let k=0;k<7&&c.parentElement;k++){c=c.parentElement;
      const tx=(c.textContent||'').replace(/\s+/g,' ');
      if(/2026-\d{2}-\d{2} \d{2}:\d{2}/.test(tx)&&tx.length<800){
        const dm=tx.match(/(2026-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
        const st=/已发布/.test(tx)?'已发布':(/未通过|驳回/.test(tx)?'未通过':(/审核中/.test(tx)?'审核中':'?'));
        out.push({id:m[1], title:t.slice(0,70), status:st, date:dm?dm[1]:''});
        break;
      }
    }
  });
  const seen=new Set(),u=[];
  for(const r of out){if(!seen.has(r.id)){seen.add(r.id);u.push(r);}}
  return u;
}"""

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, viewport={"width": 1280, "height": 1200}, locale="zh-CN")
    ctx.add_init_script("()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}")
    ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8")))
    pg = ctx.new_page()
    pg.goto("https://cloud.tencent.com/developer/creator/article", wait_until="domcontentloaded", timeout=40000)
    time.sleep(9)
    total = {}
    for n in range(1, 7):
        try:
            el = pg.locator(f".tp1-pagination__item:text-is('{n}'), li:text-is('{n}'), a:text-is('{n}')").first
            if el.count() == 0:
                log(f"页码{n} 未找到"); break
            el.click(); time.sleep(4)
        except Exception as e:
            log(f"页码{n} 点击失败 {type(e).__name__}"); break
        rows = pg.evaluate(JS)
        log(f"第{n}页 {len(rows)} 条")
        for r in rows: total[r["id"]] = r
    br.close()

log(f"=== 去重后共 {len(total)} 篇 ===")
for r in sorted(total.values(), key=lambda x: x["date"] or "", reverse=True):
    log(json.dumps(r, ensure_ascii=False))
