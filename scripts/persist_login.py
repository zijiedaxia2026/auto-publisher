"""
登录态持久化 —— 解决"每次新开浏览器都要重新扫码"的根本问题。

用法：
  1. 首次：python3 persist_login.py 腾讯云       # 扫码并保存 cookie
  2. 之后：python3 persist_login.py 腾讯云       # 自动复用；失效才需重扫

保存位置：<BASE>/.publish-state/<平台>.json
"""

import os
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
STATE = BASE / ".publish-state"
VOICE = Path(str(Path.home()) + "/.workbuddy/voice/voice.py")

# 真实 Chrome UA —— Playwright 默认 UA 含 HeadlessChrome，会被掘金反爬拦截
# （实测：默认 UA 访问 juejin.cn 返回 ERR_HTTP_RESPONSE_CODE_FAILURE，换 UA 后 HTTP 200）
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--window-size=1400,900",
]

SITES = {
    "腾讯云": {"home": "https://cloud.tencent.com/developer", "target": "https://cloud.tencent.com/developer/article/write"},
    # 掘金必须先访问首页登录，直接开 /post/new 会返回错误状态码
    "掘金": {"home": "https://juejin.cn/", "target": "https://juejin.cn/post/new"},
}


def say(t, s=""):
    a = ["/usr/bin/python3", str(VOICE), "--title", t]
    if s:
        a += ["--subtitle", s]
    try:
        subprocess_run(a)
    except Exception:
        pass


def subprocess_run(a):
    import subprocess

    subprocess.run(a, capture_output=True, timeout=30)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in SITES:
        print(f"用法: python3 persist_login.py [{'|'.join(SITES)}]")
        return 2
    site = sys.argv[1]
    home = SITES[site]["home"]
    target = SITES[site]["target"]
    sf = STATE / f"{site}.json"

    with sync_playwright() as p:
        br = p.chromium.launch(headless=False, args=LAUNCH_ARGS)

        # 尝试加载旧 cookie
        if sf.is_file():
            log(f"发现已保存的登录态（{time.strftime('%m-%d %H:%M', time.localtime(sf.stat().st_mtime))}）")
            try:
                cookies = json.loads(sf.read_text(encoding="utf-8"))
                ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, locale="zh-CN")
                ctx.add_cookies(cookies)
                log(f"已加载 {len(cookies)} 条 cookie")
            except Exception as e:
                log(f"cookie 解析失败：{e}")
                ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, locale="zh-CN")
        else:
            ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, locale="zh-CN")
            log("无历史登录态")

        page = ctx.new_page()
        # 先访问首页（掘金直接开 /post/new 会 ERR_HTTP_RESPONSE_CODE_FAILURE）
        log(f"访问首页：{home}")
        page.goto(home, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        # 检测是否需要登录
        need_login = "login" in page.url.lower() or "passport" in page.url.lower()
        if not need_login:
            # 首页有「登录」按钮也视为未登录
            has_login_btn = page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('a, button, div, span'));
                for (const el of els) {
                    const t = (el.innerText || '').trim();
                    if (t === '登录' || t === '立即登录') {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) return true;
                    }
                }
                return false;
            }""")
            need_login = has_login_btn

        if need_login:
            say("请扫码登录", site)
            log("=" * 58)
            log(f"需要登录 {site}。请在浏览器窗口扫码登录。")
            log("登录成功后本脚本会自动保存登录态。")
            log("=" * 58)
            # 等待登录成功（最多 5 分钟）
            for _ in range(150):
                time.sleep(2)
                still = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('a, button, div, span'));
                    for (const el of els) {
                        const t = (el.innerText || '').trim();
                        if (t === '登录' || t === '立即登录') {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) return true;
                        }
                    }
                    return false;
                }""")
                if not still:
                    break

        # 访问目标页确认可达
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)
            log(f"目标页：{page.url}")
        except Exception as e:
            log(f"目标页访问异常（不影响登录态保存）：{type(e).__name__}")

        time.sleep(3)
        STATE.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(ctx.cookies()), encoding="utf-8")
        log(f"✓ 登录态已保存 → {sf}")
        say("登录成功", "登录态已保存，下次不用再扫")
        print(f"\n完成。当前页面：{page.url}")
        print("登录态保存位置：", sf)
        print("\n这个窗口可以关掉了。以后同平台的脚本会自动复用登录态。")
        time.sleep(3)
        br.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())