#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯云后台批量删除指定文章（定位卡片→删除→确认→复核）。"""
import os
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
STATE = BASE / ".publish-state" / "腾讯云.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
BASEURL = "https://cloud.tencent.com/developer/creator/article"

DELS = [
    # 今天新发的重复稿（旧版已有曝光，留旧删新）
    ("S1新版", "2768271"), ("06新版", "2768263"), ("04-18坑新版", "2768256"),
    ("03新版", "2768255"), ("02新版", "2768254"), ("01新版", "2768253"),
    # 未通过（全部为重复稿）
    ("11驳回", "2768270"), ("10驳回", "2768269"), ("09驳回", "2768268"),
    ("08驳回", "2768267"), ("07驳回", "2768265"), ("05驳回", "2768261"),
    ("01旧驳回", "2763563"),
]

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def goto_page(pg, n):
    try:
        el = pg.locator(f".tp1-pagination__item:text-is('{n}')").first
        if el.count() > 0:
            el.click(); time.sleep(4); return True
    except Exception as e:
        log(f"翻页{n}失败 {type(e).__name__}")
    return False

def delete_one(pg, aid):
    pg.goto(BASEURL, wait_until="domcontentloaded", timeout=40000); time.sleep(8)
    link = None
    for n in range(1, 7):
        l = pg.locator(f'a[href*="/developer/article/{aid}"]').first
        if l.count() > 0 and l.is_visible():
            link = l; log(f"  第{n}页命中"); break
        if n < 6: goto_page(pg, n + 1)
    if link is None:
        log("  未找到"); return False
    panel = link.locator("xpath=ancestor::div[contains(@class,'cdc-2-course-panel')][1]")
    if panel.count() == 0:
        log("  卡片定位失败"); return False
    dbtn = panel.locator("text=删除").first
    dbtn.click(); time.sleep(2.5)
    # 确认弹窗
    for txt in ["确定", "确认", "删除"]:
        try:
            b = pg.locator(f'.tp1-modal button:has-text("{txt}"), .cdc-modal button:has-text("{txt}"), [class*="modal"] button:has-text("{txt}")').first
            if b.count() > 0 and b.is_visible():
                b.click(); log(f"  确认弹窗点击『{txt}』"); time.sleep(4); break
        except Exception:
            continue
    return True

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 1200}, locale="zh-CN")
    ctx.add_init_script("()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}")
    ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8")))
    pg = ctx.new_page()
    okc = 0
    for name, aid in DELS:
        log(f"== 删除 {name} {aid} ==")
        try:
            if delete_one(pg, aid): okc += 1
        except Exception as e:
            log(f"  异常 {type(e).__name__} {e}")
    log(f"完成 {okc}/{len(DELS)}")
    # 复核：公开页是否已下线
    time.sleep(2)
    log("== 复核 ==")
    for name, aid in DELS:
        try:
            r = pg.evaluate("""async (id)=>{const r=await fetch('https://cloud.tencent.com/developer/article/'+id,{credentials:'include'});const t=await r.text();return {s:r.status, gone:/文章不存在|不存在或已删除|404/.test(t), len:t.length};}""", aid)
            log(f"  {name} {aid} → {json.dumps(r, ensure_ascii=False)}")
        except Exception as e:
            log(f"  {name} 复核异常 {type(e).__name__}")
    br.close()
log("DONE")
