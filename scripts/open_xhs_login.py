# -*- coding: utf-8 -*-
"""小红书登录捕获 v5（持久化）：
- 用 launch_persistent_context，登录态落盘 .publish-state/xhs_profile；
- 就算脚本被杀/超时，profile 里的登录不丢，之后用 xhs_harvest.py 无头收割；
- 每 15 秒静默探测页查 userId，成功即保存 cookie + storage 并关窗。
"""
import os
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
STATE_DIR = BASE / ".publish-state"
PROFILE = STATE_DIR / "xhs_profile"
PROFILE.mkdir(parents=True, exist_ok=True)
SS_FILE = STATE_DIR / "小红书_storage.json"
CK_FILE = STATE_DIR / "小红书.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

def log(*a): print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)

def probe_uid(ctx):
    p2 = ctx.new_page()
    try:
        p2.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        return p2.evaluate(
            "()=>{try{var s=window.__INITIAL_STATE__&&window.__INITIAL_STATE__.user;"
            "var u=s&&s.userId?String(s.userId):'';"
            "var n=s&&s.nickname?String(s.nickname):'';"
            "return u.length>5?u+'|'+n:''}catch(e){return ''}}")
    except Exception:
        return ""
    finally:
        try: p2.close()
        except Exception: pass

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            viewport={"width": 1280, "height": 900}, locale="zh-CN")
        try:
            ctx.add_init_script("()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}")
        except Exception: pass
        pages = ctx.pages
        pg = pages[0] if pages else ctx.new_page()
        try: pg.bring_to_front()
        except Exception: pass

        log("打开小红书登录页（持久化 profile）...")
        pg.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)

        # 先看是否本来就已登录（profile 复用）
        uid = probe_uid(ctx)
        if uid:
            log(f"profile 已是登录态：{uid}，直接收割。")
        else:
            log("窗口已弹出。请【在这个 Chrome 窗口】扫码/手机号登录。")
            log("最长等 30 分钟；期间别关窗（关了也没事，profile 会保留进度）。")
            deadline = time.time() + 1800
            n = 0
            while time.time() < deadline:
                time.sleep(15)
                n += 1
                uid = probe_uid(ctx)
                if uid:
                    log(f"✅ 检测到真实登录：{uid}")
                    break
                if n % 4 == 0:
                    log(f"等待登录 {n*15}s ...")
            if not uid:
                log("⏳ 30 分钟未检测到登录。退出，但 profile 保留，下次继续。")
                try: ctx.close()
                except Exception: pass
                return

        ck = ctx.cookies()
        CK_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            st = ctx.storage_state()
            SS_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log("storage_state 异常（cookie 已存）:", e)

        try:
            pg.goto("https://creator.xiaohongshu.com/publish/publish",
                    wait_until="domcontentloaded", timeout=40000)
            time.sleep(4)
            log("创作者中心发布页 =", pg.url)
        except Exception as e:
            log("创作者中心复核异常:", e)

        log(f"✅ 全部完成：{CK_FILE.name}（{len(ck)} 条）+ {SS_FILE.name}。窗口 3 秒后关闭。")
        time.sleep(3)
        try: ctx.close()
        except Exception: pass

if __name__ == "__main__":
    main()
