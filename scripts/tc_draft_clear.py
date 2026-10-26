#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯云草稿箱：删除全部孤儿草稿（精确删除按钮 + 确认弹窗『确定』）。"""
import os
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
STATE = BASE / ".publish-state" / "腾讯云.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
DRAFT_URL = "https://cloud.tencent.com/developer/creator/article?type=draft"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def count_drafts(pg):
    return pg.evaluate("""()=>document.querySelectorAll('a[href*="write-new?draftId="]').length""")

def first_href(pg):
    return pg.evaluate("""()=>{const a=document.querySelector('a[href*="write-new?draftId="]');return a?a.getAttribute('href'):null;}""")

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 1200}, locale="zh-CN")
    ctx.add_init_script("()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}")
    ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8")))
    pg = ctx.new_page()
    pg.on("dialog", lambda d: (log(f"  原生对话框[{d.type}]自动确认"), d.accept()))
    deleted, skipped = [], []
    for i in range(40):
        pg.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=40000); time.sleep(5)
        href = first_href(pg)
        if not href:
            log(f"草稿箱已空，结束"); break
        did = href.split("draftId=")[-1]
        log(f"-- 第{i+1}轮：首篇 {did}")
        try:
            panel = pg.locator(f'a[href*="write-new?draftId={did}"]').first \
                        .locator("xpath=ancestor::div[contains(@class,'cdc-2-course-panel')][1]")
            if panel.count() == 0:
                log(f"  {did} 卡片未定位，跳过"); skipped.append(did); continue
            # 精确删除按钮（cdc-svg-icon-text:has-text('删除')）
            delbtn = panel.locator("span.cdc-svg-icon-text:has-text('删除')").first
            if delbtn.count() == 0:
                log(f"  {did} 删除按钮未找到，跳过"); skipped.append(did); continue
            delbtn.click(); time.sleep(2.5)
            # 确认弹窗：『确定』
            ok = False
            for sel in ["[class*='modal'] button:has-text('确定')",
                        "[class*='dialog'] button:has-text('确定')",
                        "[class*='popup'] button:has-text('确定')",
                        "button:has-text('确定')"]:
                try:
                    b = pg.locator(sel).first
                    if b.count() > 0 and b.is_visible():
                        b.click(); log(f"  {did} 点『确定』确认"); ok = True; break
                except Exception:
                    continue
            if not ok:
                # 弹窗可能用其它文案
                for txt in ["确认", "删除", "是"]:
                    b = pg.locator(f"button:has-text('{txt}')").first
                    if b.count() > 0 and b.is_visible():
                        b.click(); log(f"  {did} 点『{txt}』确认"); ok = True; break
            if not ok:
                log(f"  {did} 未找到确认按钮，跳过"); skipped.append(did); continue
            time.sleep(2.5)
            deleted.append(did)
            log(f"  已删 {did}（累计 {len(deleted)}）")
        except Exception as e:
            log(f"  {did} 异常 {type(e).__name__} {e}"); skipped.append(did); continue
    pg.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=40000); time.sleep(5)
    final = count_drafts(pg)
    log(f"=== 终检：草稿箱剩余 {final} 篇（删除 {len(deleted)} / 跳过 {len(skipped)}：{skipped}）===")
    json.dump({"deleted": deleted, "skipped": skipped, "final_remaining": final},
              open("/tmp/tc_draft_del.json", "w"), ensure_ascii=False)
    br.close()
log("DRAFT DELETE DONE")
