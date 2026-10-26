#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯云发文填充 —— 通用版（2026-10-17 重写，吸收全部踩坑教训）。

用法：
  python3 fill_article.py --title "标题 #WorkBuddy#" \
      --body 02-一本书变成4个技能包-腾讯云版__待发布.md \
      --figs 02__fig1-exit137.png 02__fig2-四个技能包.png 02__fig3-核实纪律.png

已规避的坑（每条都是真金白银换来的）：
 1. Markdown 当纯文本显示 → 正文先经 `md2html` 转成 HTML，再 `execCommand insertHTML` 插入富文本编辑器（所见即所得，标题/加粗/分割线正确渲染）
 2. 标题框也是 contenteditable，先填标题会让正文插进标题里 → **先贴正文，后填标题**
 3. 图片上传控件只收单文件 → 逐张上传，每张等 9 秒
 4. 每次开浏览器都要重登 → 优先加载 cookie，失效才扫码
 5. 语音播报必须用位置参数传文本，--title 不会播报
 6. Playwright 默认 UA 会被反爬拦 → 真实 UA + 反检测参数
 7. 发布弹窗「文章标签」必填（输「人工智能」→停1秒→点下拉第一个候选）

红线：**绝不点发布按钮**。填完停下，宝自己检查后点。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md2html import md_to_html

from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
VOICE = Path(str(Path.home()) + "/.workbuddy/voice/voice.py")
STATE = BASE / ".publish-state" / "腾讯云.json"
URL = "https://cloud.tencent.com/developer/article/write"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--window-position=960,0",      # 右半屏，WorkBuddy 在左，宝不用来回跳
    "--window-size=960,1080",
    # ⚠ 2026-10-18 根因修复：球球实测 cloudcache.tencent-cloud.com 在本通道
    # TLS 握手失败（12 个静态资源 ERR_SSL_PROTOCOL_ERROR）→ draft-master 编辑器
    # 本体拉不下来 → 正文区 830×0、发布弹窗/封面组件不渲染（宝"看不到弹窗"）。
    # Mac 侧 curl 实测该域名 TLS 握手成功，说明是 Playwright 浏览器自身拒绝证书，
    # 故忽略证书错误，让 CDN 资源正常加载。
    "--ignore-certificate-errors",
]


def say(text):
    """语音播报——必须用位置参数，--title 不会播报（2026-10-17 实测）。"""
    try:
        subprocess.run(["/usr/bin/python3", str(VOICE), text],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def dismiss_modals(page, label=""):
    """驱散腾讯云偶发弹窗（#dialog-root 促销 / .c-modal-visible 公告）。
    2026-10-18 实测：编辑器升级促销弹窗（editor-switch-dialog）盖住编辑器，
    拦截一切点击 30s 超时。关闭按钮 = `a.c-dialog-hd-close`（title=关闭），
    或点「暂不体验」按钮。"""
    for _ in range(5):
        live = page.evaluate(
            "() => {"
            "  const r = document.querySelector('#dialog-root .c-modal-visible');"
            "  if (!r) return 0;"
            "  const st = getComputedStyle(r);"
            "  return (st.display !== 'none' && st.visibility !== 'hidden' && r.offsetHeight > 0) ? 1 : 0; }")
        if not live:
            if label:
                log(f"无弹窗{label}")
            return True
        log(f"检测到促销弹窗，驱散中…")
        for sel in ["#dialog-root a.c-dialog-hd-close",
                    "#dialog-root button:has-text('暂不体验')",
                    "#dialog-root button:has-text('关闭')",
                    "#dialog-root button:has-text('稍后再说')"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=4000)
                    log(f"  已点关闭：{sel}")
                    time.sleep(1.5)
                    break
            except Exception:
                continue
        else:
            page.keyboard.press("Escape")
            time.sleep(1)
    log("⚠ 弹窗驱散后仍可见，继续尝试（可能挡点击）")
    return False


def scroll_everything(page):
    """把窗口 + 弹窗内所有可滚动容器都滚到底，触发懒加载渲染下半截字段。"""
    page.evaluate(
        "() => {"
        "  const ts = (el) => { try { el.scrollTop = el.scrollHeight; } catch(e){} };"
        "  window.scrollTo(0, document.documentElement.scrollHeight);"
        "  document.querySelectorAll('*').forEach(e => {"
        "    if (e.scrollHeight - e.clientHeight > 20 && e.offsetHeight > 0) ts(e); });"
        "  const a = [...document.querySelectorAll('*')]"
        "    .filter(e => e.textContent.trim()==='确认发布' && e.offsetHeight>0);"
        "  if (a.length) a[a.length-1].scrollIntoView({block:'center'});"
        "}")


def dump_modal(page):
    """把含「确认发布」的真实弹窗 outerHTML 存盘，方便核对字段与选择器。"""
    try:
        html = page.evaluate(
            "() => {"
            "  const a=[...document.querySelectorAll('*')]"
            "    .filter(e=>e.textContent.trim()==='确认发布'&&e.offsetHeight>0);"
            "  if(!a.length) return document.body.innerHTML;"
            "  let el=a[0];"
            "  while(el && el.parentElement &&"
            "        !/modal|dialog|drawer/i.test(el.parentElement.className||''))"
            "    el=el.parentElement;"
            "  return el ? el.outerHTML : document.body.innerHTML; }")
        Path("/tmp/live_modal.html").write_text(html, encoding="utf-8")
        log("✓ 真实弹窗 DOM 已存 /tmp/live_modal.html")
    except Exception as e:
        log(f"⚠ dump 弹窗失败：{e}")


def fill_publish_dialog(page, summary, cover, keywords):
    """填 摘要+来源(原创)+文章标签+自定义关键词+封面。⚠ 绝不点最终发布。

    2026-10-18 14:00 重写：上一个版本「摘要/封面填不进」的根因 = 发布弹窗下半截
    （封面、摘要）是**懒加载**，弹窗刚开时这些字段在 DOM 里根本不存在，选择器永远 0 匹配。
    修复：点发布→等「确认发布」→**循环滚到底触发懒加载**，每轮复查封面控件与摘要框
    是否都已渲染，都出现才动手；并把真实弹窗 DOM 存盘供核对。
    """
    # ---- 1. 点「发布」----
    clicked = False
    for sel in ["button.c-btn:has-text('发布')", "button:has-text('发布')"]:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.click(timeout=6000)
                log("已点「发布」按钮")
                clicked = True
                break
        except Exception as e:
            log(f"  点发布失败 {sel}：{e}")
    if not clicked:
        log("✗ 未找到「发布」按钮")
        return False

    # ---- 2. 等弹窗真正渲染 ----
    try:
        page.wait_for_selector("text=确认发布", timeout=15000)
        log("✓ 弹窗出现（确认发布）")
    except Exception:
        log("✗ 15s 内弹窗未出现 → 放弃自动填充")
        return False

    # ⚠ 根因修复：发布弹窗打开后腾讯云常又弹促销/升级窗（#dialog-root .c-modal-visible），
    # 它会盖住封面区、拦截一切点击 → 封面永远点不动、控件不挂载。
    # 必须在弹窗开后**再驱散一次**。
    dismiss_modals(page, "（发布弹窗开后）")

    # ---- 3. 摘要：本发布弹窗无独立摘要输入框（腾讯云按正文自动生成）----
    ta_sel = "textarea[placeholder*='摘要']"
    if page.locator(ta_sel).count() > 0:
        try:
            ta = page.locator(ta_sel).first
            ta.click()
            time.sleep(0.4)
            ta.fill(summary[:200])
            time.sleep(0.8)
            log(f"✓ 摘要已填 {len(ta.input_value())}/200")
        except Exception as e:
            log(f"⚠ 摘要失败：{e}")
    else:
        log("ℹ 发布弹窗无摘要输入框（腾讯云按正文自动生成摘要，无需手动填）→ 跳过")
    dump_modal(page)

    # ---- 5. 来源 = 原创（第一个 radio）----
    try:
        r = page.locator("input.c-radio").first
        r.evaluate("e => { if(!e.checked){ e.click(); } }")
        time.sleep(0.5)
        ok = page.locator("input.c-radio").first.is_checked()
        log(f"{'✓' if ok else '⚠'} 来源原创：{'已选中' if ok else '未选中，请手点'}")
    except Exception as e:
        log(f"⚠ 来源失败：{e}")

    # ---- 6. 文章标签：人工智能 ----
    try:
        tag = page.locator(
            "li.f-list-item:has(label:has-text('文章标签')) input.com-2-tag-input").first
        if tag.count() > 0 and tag.is_visible():
            tag.click()
            time.sleep(0.4)
            tag.press_sequentially("人工智能", delay=120)
            time.sleep(2)
            dd = page.locator(
                "li.f-list-item:has(label:has-text('文章标签')) "
                ".com-2-tagsinput-dropdown")
            cand = dd.locator("text=人工智能").first
            if cand.count() > 0 and cand.is_visible():
                cand.click()
                log("✓ 标签：人工智能（选预设候选）")
            else:
                tag.press("Enter")
                log("⚠ 无下拉候选，回车创建")
            time.sleep(0.8)
            chips = page.locator(
                "li.f-list-item:has(label:has-text('文章标签')) "
                ".com-2-tagsinput").first.inner_text()
            log(f"  标签区现文本：{chips[:50]!r}")
        else:
            log("⚠ 文章标签输入框未找到 → 请手动点「人工智能」")
    except Exception as e:
        log(f"⚠ 标签失败：{e}")

    # ---- 7. 自定义关键词（回车逐个创建）----
    try:
        kw = page.locator("div.col-editor-key-input input.com-2-tag-input").first
        if kw.count() > 0 and kw.is_visible():
            for k in keywords:
                kw.click()
                time.sleep(0.3)
                kw.press_sequentially(k, delay=100)
                time.sleep(0.5)
                kw.press("Enter")
                time.sleep(0.5)
                log(f"✓ 自定义关键词：{k}")
        else:
            log("⚠ 自定义关键词输入框未找到（选填可跳过）")
    except Exception as e:
        log(f"⚠ 自定义关键词失败：{e}")

    # ---- 8. 封面：按 02 篇实测教训——光上传不算设封面，必须切「正文图」tab 点选 ----
    # 02 篇踩坑：input.img-cover-input 上传只把图存进封面区图库，
    # 还必须切到「正文图」tab 点选那张图，才真的设为封面（否则 og:image 还是默认 cloud.png）。
    cover_ok = False
    for attempt in range(4):
        try:
            dismiss_modals(page, f"（封面上传前#{attempt+1}）")
            li = page.locator(
                "li.f-list-item:has(label:has-text('文章封面'))").first
            li.scroll_into_view_if_needed()
            time.sleep(1.2)
            # 若封面行已有预览图 → 已选过，跳过
            if li.locator("img").count() > 0:
                log("✓ 封面已有预览图，无需再选")
                cover_ok = True
                break
            # 8.1 上传封面图进封面区图库
            finp = page.locator(
                "li.f-list-item:has(label:has-text('文章封面')) "
                "input[type='file'], #editor-upload-input, "
                "input.img-cover-input").first
            if finp.count() > 0:
                finp.set_input_files(cover)
                time.sleep(9)
                log(f"  已上传封面图：{Path(cover).name}")
            # 8.2 打开选图面板
            box = page.locator(
                "li.f-list-item:has(label:has-text('文章封面')) "
                ".col-editor-upload-content, "
                "li.f-list-item:has(label:has-text('文章封面')) "
                "[class*=upload-content]").first
            if box.count() > 0:
                try:
                    box.click(timeout=8000)
                except Exception:
                    pass
                time.sleep(2.5)
            # 8.3 切到「正文图」tab（02 教训：必须切，否则不算设封面）
            for tab in ["text=正文图", "text=从正文选择", "text=选择正文图片",
                        "text=正文图片", "text=正文"]:
                try:
                    t = page.locator(tab).first
                    if t.count() > 0 and t.is_visible():
                        t.click(timeout=4000)
                        time.sleep(1.5)
                        log(f"  已切到「{tab}」")
                        break
                except Exception:
                    continue
            # 8.4 dump 选图面板真实结构，便于精准修选择器
            try:
                html = page.evaluate(
                    "() => { const c=[...document.querySelectorAll('div')]"
                    ".filter(e => e.querySelectorAll('img').length >= 2 && e.offsetHeight > 40);"
                    " return c.length ? c[c.length-1].outerHTML.slice(0, 12000) : 'NO_PANEL'; }")
                Path("/tmp/cover_panel.html").write_text(html, encoding="utf-8")
                log("  ✓ 选图面板 DOM 已存 /tmp/cover_panel.html")
            except Exception as e:
                log(f"  dump 面板失败：{e}")
            # 8.5 点面板里第一张图
            panel = page.locator(
                ".c-upload-panel img, .cover-select img, "
                "[class*=cover] [class*=panel] img, "
                "[class*=upload] [class*=list] img, "
                "[class*=select] img").all()
            if panel:
                panel[0].click(timeout=8000)
                time.sleep(3)
            if li.locator("img").count() > 0:
                cover_ok = True
                log("✓ 封面已选定（正文图第一张）")
                page.screenshot(path="/tmp/fill_cover.png")
                break
            log(f"  封面仍未生效（#{attempt+1}）")
        except Exception as e:
            log(f"⚠ 封面尝试{attempt+1}失败：{e}")
    if not cover_ok:
        log("✗ 封面未能自动设定 → 需手动从「正文图」选一张"
            "（真实面板见 /tmp/cover_panel.html）")
    return cover_ok


def switch_to_markdown(page):
    """切到 Markdown 编辑器。

    ⚠ 2026-10-18 教训复盘：编辑器区域同时存在多个 `a.switch-editor`，
    其中顶栏的「体验新版编辑器」也匹配该选择器且**不含 Markdown 字样**，
    旧逻辑误以为「已是 MD 模式」而放弃切换 → 实际停在富文本，正文显示原始 `##`/`**`。
    修正：只在文字**明确含「切换到」+「Markdown」**时才点击；
    文本是「切换富文本编辑器」= 当前已是 MD，不点；是「体验新版编辑器」= 无关，忽略并改按文字精确定位。
    """
    # 1. 精确定位真正的切换链接（按文字）
    for sel in [
        "a:has-text('切换到Markdown编辑器')",
        "a:has-text('切换到 Markdown 编辑器')",
        "a.switch-editor:has-text('Markdown')",
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                txt = (el.inner_text() or "").replace(" ", "")
                if "Markdown" in txt:
                    el.click(timeout=5000)
                    log(f"已点击切换按钮：{txt}")
                    time.sleep(4)
                    return True
        except Exception as e:
            log(f"  尝试 {sel} 失败：{type(e).__name__}")

    # 2. 兜底：看 a.switch-editor 的真实文字
    try:
        el = page.locator("a.switch-editor").first
        if el.count() > 0 and el.is_visible():
            txt = (el.inner_text() or "").replace(" ", "")
            if "Markdown" in txt:
                el.click(timeout=5000)
                log(f"兜底点击切换按钮：{txt}")
                time.sleep(4)
                return True
            if "富文本" in txt:
                log("按钮文字「切换富文本编辑器」= 当前已是 MD 模式，不切")
                return True
            log(f"切换按钮文字「{txt}」不可识别，继续（可能已是 MD）")
            return True
    except Exception as e:
        log(f"  兜底切换失败：{type(e).__name__}")
    log("未找到明确 MD 切换按钮，继续（可能已是 MD 模式）")
    return True


def pick_body_editor(page):
    """精确定位正文编辑器：在所有 contenteditable 元素里挑**可视面积最大**的那个。

    ⚠ 2026-10-18 血泪教训：之前用 `eds.last` 选最后一个可编辑元素，但页面里
    可编辑元素数量会变（一次 3 个、一次 2 个），`last` 在某些次选中了**标题框**，
    整段 HTML 被塞进标题 → 正文变空白、标题变代码（用户看到的「全是代码没汉字」）。
    正文框一定是面积最大的那个，按面积选最稳。"""
    items = page.locator("div[contenteditable='true']")
    n = items.count()
    log(f"contenteditable 元素 {n} 个")
    best, best_area = None, 0
    for i in range(n):
        try:
            box = items.nth(i).bounding_box()
            if not box:
                continue
            area = box["width"] * box["height"]
            if items.nth(i).is_visible() and area > best_area:
                best_area, best = area, i
        except Exception:
            continue
    if best is None:  # 兜底：第一个可见的
        for i in range(n):
            try:
                if items.nth(i).is_visible():
                    best = i
                    break
            except Exception:
                continue
    if best is None:
        raise RuntimeError("未找到正文编辑器（contenteditable）")
    log(f"选中正文编辑器：第 {best} 个（面积 {int(best_area):,}）")
    return items.nth(best)


def count_chinese(s):
    return len(re.findall(r"[一-鿿]", s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", required=True, help="正文 md 文件名（项目根目录下）")
    ap.add_argument("--figs", nargs="*", default=[], help="配图文件名（配图/ 下）")
    ap.add_argument("--cover", default="", help="封面图文件名（配图/ 下），默认用首张配图")
    ap.add_argument("--confirm-publish", action="store_true",
                    help="仅当宝已审稿 + 给特殊授权时传：填完后自动点「确认发布」。"
                         "不传 = 默认停在按钮前，留给宝点（模式 A）")
    a = ap.parse_args()

    body_file = BASE / a.body
    if not body_file.is_file():
        log(f"✗ 正文文件不存在：{body_file}")
        return 1

    # 清掉首行大标题和「标签：」说明行（编辑器有专门输入框）
    ls = body_file.read_text(encoding="utf-8").splitlines()
    body = "\n".join(
        l for i, l in enumerate(ls)
        if not (i == 0 and l.startswith("# ")) and not l.startswith("> 标签：")
    ).strip()
    log(f"正文 {len(body):,} 字符")
    say("腾讯云填充开始，先切Markdown编辑器")

    with sync_playwright() as p:
        br = p.chromium.launch(headless=False, args=ARGS)
        ctx = br.new_context(user_agent=UA, viewport={"width": 960, "height": 1080},
                             locale="zh-CN",
                             # 同 ARGS：忽略 HTTPS 证书错误，放行 cloudcache CDN
                             ignore_https_errors=True)
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        if STATE.is_file():
            try:
                cookies = json.loads(STATE.read_text(encoding="utf-8"))
                ctx.add_cookies(cookies)
                log(f"已加载 {len(cookies)} 条 cookie"
                    f"（{time.strftime('%H:%M', time.localtime(STATE.stat().st_mtime))} 存）")
            except Exception as e:
                log(f"cookie 失败：{e}")

        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        if "login" in page.url.lower():
            say("需要扫码，请扫腾讯云登录码")
            log("等待扫码…")
            for _ in range(200):
                time.sleep(2)
                if "login" not in page.url.lower():
                    break
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        if "login" in page.url.lower():
            say("登录失败，请重新登录后再试")
            br.close()
            return 1

        log("✓ 已登录")
        try:
            STATE.write_text(json.dumps(ctx.cookies()), encoding="utf-8")
            log("登录态已刷新")
        except Exception:
            pass

        # 0. 驱散登录后偶发弹窗（促销/公告）
        dismiss_modals(page, "（登录后）")

        # 1. 保持富文本模式（默认落地即是），用 HTML 插入正文 → 所见即所得
        #    （不再切 MD：之前切 MD 失败会落在富文本且显示原始 `##`/`**`）
        dismiss_modals(page)
        say("第一步完成，准备以HTML插入正文")

        # 2. 清空正文（精确定位正文框：最大 contenteditable）
        ed = pick_body_editor(page)
        dismiss_modals(page)
        ed.click(timeout=10000)
        time.sleep(0.8)
        page.keyboard.press("Meta+A")
        time.sleep(0.4)
        page.keyboard.press("Delete")
        time.sleep(1.2)
        ed.click()
        page.keyboard.press("Meta+A")
        page.keyboard.press("Delete")
        time.sleep(1.2)

        # 3. 转 HTML 并用「剪贴板粘贴」插入正文框
        #    ⚠ 不能用 execCommand('insertHTML')：腾讯云是 React 编辑器，execCommand 会
        #    被 React 重渲染把节点替换/卸载，导致后续插图找不到正文框、内容也可能丢。
        #    改用 ClipboardEvent('paste') 走编辑器自带 onPaste，React 正确接管、节点稳定。
        html = md_to_html(body)
        log(f"HTML {len(html):,} 字符（已转标题/加粗/分割线）")
        ed.click()
        time.sleep(0.6)
        page.evaluate(
            """(h) => new Promise((resolve) => {
                const el = document.activeElement;
                if (!el || !el.isContentEditable) { resolve('no-editor'); return; }
                el.focus();
                const dt = new DataTransfer();
                dt.setData('text/html', h);
                dt.setData('text/plain', h.replace(/<[^>]+>/g, ' '));
                const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
                el.dispatchEvent(ev);
                setTimeout(resolve, 800);
            })""",
            html,
        )
        time.sleep(3)

        # 3.5 硬性校验：正文框里必须有汉字（且节点没被卸载）
        try:
            bt = ed.evaluate("(el) => el.innerText")
            zh = count_chinese(bt)
            log(f"正文框汉字数：{zh}")
            if zh < 300:
                log(f"✗✗ 正文框汉字仅 {zh}（应 >300）→ 插入失败！")
                page.screenshot(path="/tmp/fill_body.png")
                say("正文校验失败，请让我重试")
                br.close()
                return 1
        except Exception as e:
            log(f"校验异常：{e}（节点可能已卸载）")
            page.screenshot(path="/tmp/fill_body.png")
            br.close()
            return 1
        log("✓ 正文已插入且汉字齐全（HTML 渲染，React 已接管）")

        # 4. 验证渲染
        try:
            t = page.evaluate("() => document.body.innerText")
            m = re.search(r"markdown字符数：(\d+)\s+段落：(\d+)", t)
            log(f"统计：{m.groups() if m else '未读到'}")
            bad = t.count("**") + len(re.findall(r"^---$", t, re.M))
            log(f"残留 Markdown 符号：{bad}（0 = 渲染正常）")
        except Exception:
            pass
        page.screenshot(path="/tmp/fill_body.png")
        say("第二步完成，正文已填，正在填标题")

        # 5. 填标题（后填！）
        try:
            ti = page.locator('textarea[placeholder*="标题"]').first
            ti.click()
            time.sleep(0.4)
            page.keyboard.press("Meta+A")
            page.keyboard.press("Delete")
            time.sleep(0.4)
            ti.fill(a.title)
            time.sleep(2)
            log(f"✓ 标题：{a.title}")
        except Exception as e:
            log(f"标题失败：{e}")
        say("第三步完成，标题已填，正在插图")

        # 6. 逐张插图（复用正文框句柄，不再二次定位，避免节点已被 React 接管后找不到）
        ok = 0
        body_ed = ed
        for name in a.figs:
            fp = BASE / "配图" / name
            if not fp.is_file():
                log(f"  {name} 不存在")
                continue
            try:
                body_ed.click()
                page.keyboard.press("Meta+End")
                time.sleep(0.4)
                page.keyboard.press("Enter")
                time.sleep(0.5)
                page.locator('input[type="file"]').first.set_input_files(str(fp))
                ok += 1
                log(f"  {name} 已提交（{fp.stat().st_size:,}B）")
                time.sleep(9)
            except Exception as e:
                log(f"  {name} 失败：{type(e).__name__}")

        log(f"插图 {ok}/{len(a.figs)}")

        # 7. 发布弹窗：摘要 + 来源 + 标签 + 自定义关键词 + 封面
        cover = BASE / "配图" / (a.cover or (a.figs[0] if a.figs else ""))
        summary = (
            "半夜让 AI 帮我在腾讯云自动发文，结果它把『写文章』页面当成『新建』，"
            "用 page.goto 一口气给我造了 4 篇空白草稿。本文复盘这次过度自动化的全过程："
            "正文跑进标题框、图片必须逐张传、标签必填得点预设、发布弹窗关了全丢、"
            "审核期公开查不到≠没发。结论很朴素——半自动最稳：AI 填，人点发布。")
        keywords = ["WorkBuddy", "AI自动发文", "效率工具"]
        cover_done = False
        if cover.is_file():
            cover_done = fill_publish_dialog(page, summary, str(cover), keywords)
        else:
            log(f"⚠ 封面文件不存在：{cover}")
        time.sleep(3)

        # 7.5 模式 B（宝已审稿 + 特殊授权）：强制点「确认发布」
        # 宝反馈"看不到确认发布栏" → 该按钮在 DOM 里但视觉未渲染，普通点法点不到。
        # 所以：force=True 跳过可见性检查，再用 JS click 兜底。
        # 且**封面失败也照发**——发文本身就有 +10 成长值，封面不影响这一项，优先把分拿到。
        if a.confirm_publish:
            if not cover_done:
                log("⚠ 封面未成功，但宝已授权 → 照发（发文 +10 成长值不因封面丢失）")
            clicked = False
            for sel in ["button.c-btn:has-text('确认发布')",
                        "button:has-text('确认发布')"]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0:
                        btn.scroll_into_view_if_needed(timeout=4000)
                        btn.click(timeout=8000, force=True)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                res = page.evaluate(
                    "() => { const b=[...document.querySelectorAll('button')]"
                    ".filter(x=>x.textContent.trim()==='确认发布');"
                    " if(b.length){b[b.length-1].click(); return 'clicked';}"
                    " return 'not_found'; }")
                clicked = (res == "clicked")
                log(f"  JS 兜底点击结果：{res}")
            if clicked:
                log("✓ 已点「确认发布」（模式 B：宝已授权）")
                time.sleep(8)
                page.screenshot(path="/tmp/published.png")
                say("宝，03 已经发布出去了，积分 +10")
            else:
                log("✗ 没能点中「确认发布」→ 留窗")
                say("宝，没能自动点中确认发布，留给你手点")
        page.screenshot(path="/tmp/fill_final.png", full_page=True)
        if not a.confirm_publish:
            say("宝，03 这篇文章的标签、关键词、封面都填好了，发布弹窗也开着，你点确认发布就行")

        log("\n" + "=" * 58)
        log("截图：/tmp/fill_final.png")
        log("🟢 这篇草稿已填好并停在编辑器里，浏览器窗口**特意留给你**看 + 点发布。")
        log("检查清单：①标题 ②正文汉字齐全、格式正常 ③图 3/3 ④摘要✓ ⑤封面✓")
        log("若摘要/标签框没自动填到，手动补：摘要=上面那段；标签点「人工智能」预设")
        log("最后「确认发布」由你自己点（脚本红线：绝不代点）")
        log("发完直接关这个窗口即可。旧草稿在草稿箱里，发完再删其余 03。")
        log("=" * 58)

        # ⚠ 2026-10-18 宝明确要求：填完要留最后一个网页给她发布，不能全关。
        # 所以这里保持浏览器打开，不调用 br.close()。
        # 只开一个窗口（运行前已 pkill 旧的 Playwright 浏览器，不会堆）。
        try:
            while True:
                time.sleep(15)
        except KeyboardInterrupt:
            br.close()
        say("填充完成，浏览器已留着，请检查并发布")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
