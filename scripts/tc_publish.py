"""腾讯云无头发布器（headless，复用 fill_article.py 全部规避逻辑）。
用法：python3 tc_publish.py --title "..." --body <md文件名> --figs a.png b.png --kw WorkBuddy XX
宝 2026-10-24 明确下令发文 → 启用模式 B（自动点确认发布）。"""
import os
import argparse, json, re, sys, time
from pathlib import Path

sys.path.insert(0, os.environ.get("FMJ_BASE", os.getcwd()) + "/scripts")
from md2html import md_to_html
from fill_article import (BASE, STATE, URL, UA, ARGS, dismiss_modals,
                          pick_body_editor, count_chinese, log)
from playwright.sync_api import sync_playwright


def make_summary(body):
    blocks = [l for l in body.splitlines() if l.strip() and not l.startswith(("#", ">", "-", "*", "|"))]
    text = "".join(blocks)
    sents = re.split(r"(?<=[。！？])", text)
    out = ""
    for s in sents:
        if len(out) + len(s) > 190:
            break
        out += s
    return out or text[:190]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--figs", nargs="*", default=[])
    ap.add_argument("--kw", nargs="*", default=["WorkBuddy"])
    ap.add_argument("--tag", default="人工智能")
    a = ap.parse_args()

    bf = BASE / a.body
    ls = bf.read_text("utf-8").splitlines()
    body = "\n".join(l for i, l in enumerate(ls)
                     if not (i == 0 and l.startswith("# ")) and not l.startswith("> 标签：")).strip()
    summary = make_summary(body)
    log(f"正文 {len(body):,} 字符 | 摘要 {len(summary)} 字 | 标签 {a.tag}")

    with sync_playwright() as p:
        args = [x for x in ARGS if not x.startswith("--window-")]  # headless 不需要窗口定位
        br = p.chromium.launch(headless=True, args=args + ["--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(user_agent=UA, viewport={"width": 1360, "height": 860},
                             locale="zh-CN", ignore_https_errors=True)
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        cookies = json.loads(STATE.read_text("utf-8"))
        ctx.add_cookies(cookies)
        log(f"cookie {len(cookies)} 条（{time.strftime('%m-%d %H:%M', time.localtime(STATE.stat().st_mtime))} 存）")
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if "login" in page.url.lower():
            log("❌ 登录态失效，需宝扫码续登录态（attended）")
            br.close(); return 2
        STATE.write_text(json.dumps(ctx.cookies()), encoding="utf-8")
        log("✓ 已登录，登录态已刷新")

        dismiss_modals(page, "（登录后）")
        ed = pick_body_editor(page)
        dismiss_modals(page)
        ed.click(timeout=10000)
        page.keyboard.press("Meta+A"); page.keyboard.press("Delete")
        page.wait_for_timeout(1200)
        html = md_to_html(body)
        ed.click()
        page.evaluate(
            """(h) => new Promise((resolve) => {
                const el = document.activeElement;
                if (!el || !el.isContentEditable) { resolve('no-editor'); return; }
                el.focus();
                const dt = new DataTransfer();
                dt.setData('text/html', h);
                dt.setData('text/plain', h.replace(/<[^>]+>/g, ' '));
                el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
                setTimeout(resolve, 800);
            })""", html)
        page.wait_for_timeout(3000)
        zh = count_chinese(ed.evaluate("(el) => el.innerText"))
        log(f"正文框汉字数：{zh}")
        if zh < 300:
            page.screenshot(path="/tmp/tc_body_fail.png"); br.close(); return 1
        log("✓ 正文已插入")

        ti = page.locator('textarea[placeholder*="标题"]').first
        ti.click(); page.keyboard.press("Meta+A"); page.keyboard.press("Delete")
        ti.fill(a.title); page.wait_for_timeout(2000)
        log(f"✓ 标题已填")

        ok = 0
        for name in a.figs:
            fp = BASE / "配图" / name
            if not fp.is_file():
                log(f"  {name} 不存在，跳过"); continue
            ed.click(); page.keyboard.press("Meta+End"); page.wait_for_timeout(400)
            page.keyboard.press("Enter"); page.wait_for_timeout(500)
            page.locator('input[type="file"]').first.set_input_files(str(fp))
            ok += 1
            log(f"  {name} 已提交"); page.wait_for_timeout(9000)
        log(f"插图 {ok}/{len(a.figs)}")

        # 发布弹窗
        clicked = False
        for sel in ["button.c-btn:has-text('发布')", "button:has-text('发布')"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=6000); clicked = True; break
            except Exception:
                continue
        if not clicked:
            log("✗ 未找到「发布」按钮"); br.close(); return 1
        page.wait_for_selector("text=确认发布", timeout=15000)
        log("✓ 发布弹窗出现")
        dismiss_modals(page, "（弹窗开后）")

        r = page.locator("input.c-radio").first
        r.evaluate("e => { if(!e.checked){ e.click(); } }")
        page.wait_for_timeout(500)
        log(f"来源原创：{'✓' if r.is_checked() else '⚠ 未选中'}")

        # 标签：键盘通路（06 实测唯一可靠）
        tag = page.locator(
            "li.f-list-item:has(label:has-text('文章标签')) input.com-2-tag-input").first
        if tag.count() == 0:
            tag = page.locator("input.com-2-tag-input").first
        tag.click(); page.wait_for_timeout(400)
        page.keyboard.type(a.tag, delay=120)
        page.wait_for_timeout(3000)
        # 点下拉中「文本精确等于」的候选（07 实测：ArrowDown+Enter 会误选「人工智能教育」）
        cand = page.evaluate("""(tg) => {
            for (const el of document.querySelectorAll('.com-2-tagsinput-dropdown *')) {
                if ((el.innerText||'').trim() === tg && el.children.length === 0) {
                    const b = el.getBoundingClientRect();
                    if (b.width > 0 && b.height > 0) return {x: b.x+b.width/2, y: b.y+b.height/2};
                }
            }
            return null;
        }""", a.tag)
        if cand:
            page.mouse.click(cand["x"], cand["y"])
        else:
            page.keyboard.press("ArrowDown"); page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
        chips_txt = page.evaluate("""() => {
            const li = [...document.querySelectorAll('li.f-list-item')]
                .find(l => (l.innerText||'').includes('文章标签'));
            return li ? li.innerText.trim().split('\\n') : [];
        }""")
        chip_ok = a.tag in chips_txt
        log(f"标签复核：{chips_txt[:3]} {'✓' if chip_ok else '⚠ 未精确挂上'}")

        kw = page.locator("div.col-editor-key-input input.com-2-tag-input").first
        if kw.count() > 0 and kw.is_visible():
            for k in a.kw:
                kw.click(); page.wait_for_timeout(300)
                kw.press_sequentially(k, delay=100); page.wait_for_timeout(500)
                kw.press("Enter"); page.wait_for_timeout(500)
                log(f"✓ 关键词：{k}")

        # 封面：尽力，失败照发（先例：发文+10成长值不因封面丢失）
        cover_done = False
        if a.figs:
            try:
                li = page.locator("li.f-list-item:has(label:has-text('文章封面'))").first
                li.scroll_into_view_if_needed(); page.wait_for_timeout(1000)
                if li.locator("img").count() == 0:
                    finp = page.locator("li.f-list-item:has(label:has-text('文章封面')) input[type='file'], input.img-cover-input").first
                    if finp.count() > 0:
                        finp.set_input_files(str(BASE / "配图" / a.figs[0]))
                        page.wait_for_timeout(9000)
                        log("封面图已上传")
                cover_done = li.locator("img").count() > 0
                log(f"封面：{'✓' if cover_done else '⚠ 未生效，照发'}")
            except Exception as e:
                log(f"封面失败（照发）：{e}")

        # 模式 B：宝已授权，点「确认发布」
        done = False
        for sel in ["button.c-btn:has-text('确认发布')", "button:has-text('确认发布')"]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.scroll_into_view_if_needed(timeout=4000)
                    btn.click(timeout=8000, force=True); done = True; break
            except Exception:
                continue
        if not done:
            res = page.evaluate("() => { const b=[...document.querySelectorAll('button')]"
                                ".filter(x=>x.textContent.trim()==='确认发布');"
                                "if(b.length){b[b.length-1].click();return 'clicked';} return 'not_found';}")
            done = (res == "clicked")
        log("✓ 已点「确认发布」" if done else "✗ 未能点中确认发布")
        page.wait_for_timeout(8000)
        page.screenshot(path="/tmp/tc_after_publish.png", full_page=True)
        t = page.evaluate("() => document.body.innerText")
        m = re.search(r"发布成功", t)
        aid = None
        murl = re.search(r"/article/(\d+)", page.url)
        if murl: aid = murl.group(1)
        log(f"发布反馈：{'出现「发布成功」✅' if m else '未见「发布成功」文本'} | URL含ID: {aid}")
        br.close()
        return 0 if (done and (m or aid)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
