# -*- coding: utf-8 -*-
"""小红书登录 v8（后台 + 弹屏扫码）：
- headless 持久化 profile，不占鼠标键盘；
- creator 登录页切扫码模式，二维码持续截图 .publish-state/xhs_qr.png（60s 自动刷新）；
- 登录成功信号：登录页 URL 跳离 /login（扫码确认后自动跳转）→ 存 cookie/storage → done；
- 每圈写心跳 .publish-state/xhs_heartbeat（外部可查是否卡死）。
"""
import os
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
STATE_DIR = BASE / ".publish-state"
PROFILE = STATE_DIR / "xhs_profile"
QR_FILE = STATE_DIR / "xhs_qr.png"
SS_FILE = STATE_DIR / "小红书_storage.json"
CK_FILE = STATE_DIR / "小红书.json"
DONE = STATE_DIR / "xhs_login_done.txt"
BEAT = STATE_DIR / "xhs_heartbeat"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

def log(*a): print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)

def snap_qr(pg):
    try:
        el = pg.locator("img.css-1lhmg90").first
        if el.count():
            el.screenshot(path=str(QR_FILE), timeout=8000)
            return QR_FILE.exists() and QR_FILE.stat().st_size > 2000
    except Exception:
        pass
    return False

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            viewport={"width": 1280, "height": 900}, locale="zh-CN")
        ctx.add_init_script("()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        log("打开创作者中心登录页 ...")
        pg.goto("https://creator.xiaohongshu.com/login", wait_until="domcontentloaded", timeout=45000)
        time.sleep(6)
        try:
            pg.locator("img.css-wemwzq").first.click(force=True)
        except Exception as e:
            log("切扫码失败:", e)
        time.sleep(4)
        ok = snap_qr(pg)
        log(f"二维码{'已生成' if ok else '生成失败'} → {QR_FILE}（60s 自动换新，10s 内会弹到宝屏幕上）")

        deadline = time.time() + 1200
        last_snap = time.time()
        while time.time() < deadline:
            time.sleep(3)
            try: BEAT.write_text(time.strftime("%H:%M:%S"), encoding="utf-8")
            except Exception: pass
            try:
                if "/login" not in pg.url:
                    log(f"✅ 登录页已跳转：{pg.url}")
                    break
            except Exception:
                log("页面读取异常，重试")
                time.sleep(2)
                continue
            if time.time() - last_snap > 60:
                if snap_qr(pg):
                    log("二维码已换新")
                last_snap = time.time()

        if "/login" in (pg.url or ""):
            log("⏳ 20 分钟未登录，退出（profile 保留）")
            try: ctx.close()
            except Exception: pass
            return

        ck = ctx.cookies()
        CK_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            SS_FILE.write_text(json.dumps(ctx.storage_state(), ensure_ascii=False, indent=2),
                               encoding="utf-8")
        except Exception: pass
        DONE.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        log(f"✅ 登录态已保存：{CK_FILE.name}（{len(ck)} 条 cookie）")
        try: QR_FILE.unlink()
        except Exception: pass
        try: ctx.close()
        except Exception: pass

if __name__ == "__main__":
    main()
