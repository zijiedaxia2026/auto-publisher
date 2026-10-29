#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""掘金批量发布（编辑下方 ARTS 后运行）。

用法：
  /Users/lisa/.workbuddy/binaries/python/envs/default/bin/python juejin_publish.py

必填项（2026-10-24 实测）：
  - 分类（红色*必填）：div.category-list .item:has-text('人工智能')
  - 添加标签（红色*必填）：标签是 byte-select，placeholder 层会拦截 pointer，
    必须先点 div.byte-select__placeholder:has-text('添加标签')，再 keyboard.type，
    然后点 .byte-select-option 第一项。直接 click input.byte-select__input 会超时。
  - 编辑摘要：自动生成 100/100，无需填。
成功判据：URL 跳 https://juejin.cn/published（或含 /post/）。
"""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("/Users/lisa/WorkBuddy/内容运营")
STATE = BASE / ".publish-state" / "掘金.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
ARGS = ["--disable-blink-features=AutomationControlled", "--window-position=960,0", "--window-size=960,1080"]

ARTS = [
    {"f": "13-我哥把自己活埋了-双机互救血泪史-掘金版__待发布.md",
     "title": "我哥把自己活埋了，还在保险柜里打了 1870 个求救电话——两个 AI 智能体的互救实录",
     "cover": "配图/13_1_封面.png",
     "cat": "人工智能", "tags": ["人工智能", "程序员"]},
]

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def body_clean_of(md):
    body = (BASE / md).read_text(encoding="utf-8")
    lines = body.splitlines()
    return "\n".join(
        l for i, l in enumerate(lines)
        if not (i == 0 and l.startswith("# ")) and not l.startswith("> 标签：")
    ).strip()

def add_tag(ed, tg):
    opened = False
    for sel in ["div.byte-select__placeholder:has-text('添加标签')", "div.tag-input .byte-select__wrap", "input.byte-select__input"]:
        try:
            el = ed.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.click(force=True, timeout=3000); opened = True; break
        except Exception:
            continue
    if not opened:
        ed.locator("div.tag-input").first.click(force=True, timeout=3000)
    time.sleep(0.6)
    ed.keyboard.type(tg, delay=80); time.sleep(2.5)
    try:
        opt = ed.locator(".byte-select-option").first
        if opt.count() > 0 and opt.is_visible():
            opt.click(timeout=4000); log(f"标签✓{tg}"); time.sleep(1.2); return
    except Exception:
        pass
    ed.keyboard.press("Enter"); log(f"标签(回车)✓{tg}"); time.sleep(1.2)

def publish_one(ctx, art):
    pg = ctx.new_page()
    pg.goto("https://juejin.cn/", wait_until="domcontentloaded"); time.sleep(5)
    pg.locator("button.add-btn").first.click(timeout=8000); time.sleep(5)
    with ctx.expect_page() as pi:
        pg.locator("button.send-button").first.click(timeout=8000)
    ed = pi.value
    ed.wait_for_load_state("domcontentloaded"); time.sleep(7)
    log(f"editor url={ed.url}")
    ed.wait_for_selector("input.title-input, input[placeholder*='标题'], .CodeMirror", timeout=25000)
    ti = ed.locator("input.title-input, input[placeholder*='标题']").first
    ti.click(); time.sleep(0.3); ti.fill(art["title"]); log(f"标题✓ {len(art['title'])}字")
    clean = body_clean_of(art["f"])
    try:
        eb = ed.locator(".CodeMirror textarea").first; eb.focus(timeout=6000)
    except Exception:
        ed.locator(".CodeMirror").first.click(force=True)
    time.sleep(0.6)
    ed.keyboard.insert_text(clean); time.sleep(4); log(f"正文✓ {len(clean)}字")
    cov = BASE / art["cover"]
    if cov.is_file():
        try:
            ed.locator('input[type="file"]').first.set_input_files(str(cov)); time.sleep(5); log("封面✓")
        except Exception as e: log(f"封面✗{type(e).__name__}")
    time.sleep(2)
    ed.locator("button:has-text('发布')").first.click(timeout=8000); time.sleep(4)
    try:
        ed.locator("div.category-list .item:has-text('%s')" % art["cat"]).first.click(timeout=6000)
        log(f"分类✓{art['cat']}")
    except Exception as e: log(f"分类✗ {e}")
    time.sleep(1)
    for tg in art["tags"]:
        add_tag(ed, tg)
    try:
        ed.locator("button:has-text('确定并发布')").first.click(timeout=6000); log("确定并发布✓")
    except Exception as e:
        log(f"确定并发布✗ {e}")
        ed.locator("button:has-text('确定')").first.click(timeout=5000); log("确定✓(备选)")
    ok = False
    for _ in range(8):
        time.sleep(3)
        try:
            ok = ed.evaluate("""()=>/发布成功|已发布/.test(document.body.innerText)||location.href.includes('/published')||location.href.includes('/post/')""")
        except Exception: ok = False
        if ok: break
    log(f"校验:{ok} url:{ed.url}")
    ed.screenshot(path=f"/tmp/jj_done_{art['f'][:2]}.png", full_page=True)
    ed.close(); pg.close()
    return ok

with sync_playwright() as p:
    br = p.chromium.launch(headless=False, args=ARGS)
    ctx = br.new_context(user_agent=UA, viewport={"width": 960, "height": 1080}, locale="zh-CN")
    ctx.add_init_script("""()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});try{window.navigator.chrome={runtime:{},loadTimes:function(){},csi:function(){},app:{}};}catch(e){}try{delete window.Playwright;}catch(e){}}""")
    ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8")))
    for art in ARTS:
        log(f"===== 开始 {art['f'][:2]} =====")
        try:
            publish_one(ctx, art)
        except Exception as e:
            log(f"失败 {art['f'][:2]}: {type(e).__name__} {e}")
    br.close()
log("DONE")
