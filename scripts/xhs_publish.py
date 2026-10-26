# -*- coding: utf-8 -*-
"""小红书图文发布（试发 05）：传图→标题→正文→发布。
用法: xhs_publish.py <md文件> <图1> <图2> ... 或 --recon 只摸结构不发布
"""
import os
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
CK = BASE / ".publish-state" / "小红书.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

def log(*a): print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)

TITLES = {
    "05": "14万字塞给AI，它反而开始瞎编了",
    "08": "用三个大佬的脑子，避开亏钱的坑",
    "09": "让AI上网找资料？给它装双眼睛",
    "10": "请了个智囊团：乔布斯芒格给你打工",
    "11": "别被忽悠！2万赞的Muse方法是坑",
    "12": "25天17万星！Rust复刻全家桶",
}
TAGS = {
    "05": "#AI工具 #人工智能 #AI避坑",
    "08": "#AI赚钱 #普通人搞钱 #避坑指南",
    "09": "#AI工具 #打工人效率 #AgentReach",
    "10": "#AI工具 #效率提升 #AI顾问",
    "11": "#避雷 #AI工具 #开源项目",
    "12": "#GitHub #Rust #开源软件 #程序员 #效率工具",
}

def parse_md(md_path, title_override=None):
    """返回 (title<=20字, body<=1000字)。去掉标题行/引用块/图片行/加粗。"""
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    body_lines = []
    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            body_lines.append("")
            continue
        if s.startswith("# "):      # 主标题
            continue
        if s.startswith(">"):       # 引用块（系列说明等）
            m = re.search(r"标签[:：]\s*(.+)$", s)
            continue
        if s.startswith("---"):
            continue
        if re.match(r"!\[.*\]\(.*\)", s):  # 图片行
            continue
        s = s.replace("**", "")
        body_lines.append(s)
    # 压缩多余空行
    text = "\n".join(body_lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text

def short_title(md_path):
    first = ""
    for ln in Path(md_path).read_text(encoding="utf-8").splitlines():
        if ln.startswith("# "):
            first = ln[2:].strip()
            break
    first = re.sub(r"（小红书版）|\(小红书版\)|^11 ·\s*", "", first)
    first = re.sub(r"\s+", "", first)
    return first[:20]

def run(md_path, figs, do_publish=True):
    text = parse_md(md_path)
    key = Path(md_path).name[:2]
    if key in TAGS and TAGS[key] not in text:
        text = text + "\n\n" + TAGS[key]
    if len(text) > 1000:
        text = text[:997] + "…"
    title = TITLES.get(key) or short_title(md_path)
    log(f"标题({len(title)}字): {title}")
    log(f"正文({len(text)}字)，图 {len(figs)} 张")

    with sync_playwright() as p:
        br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(user_agent=UA, viewport={"width":1400,"height":1800}, locale="zh-CN")
        ctx.add_init_script("()=>{Object.defineProperty(navigator,'webdriver',{get:()=>undefined});}")
        ctx.add_cookies(json.loads(CK.read_text(encoding="utf-8")))
        pg = ctx.new_page()
        pg.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded", timeout=45000)
        time.sleep(8)
        if "/login" in pg.url:
            log("❌ 登录态失效"); br.close(); return 2
        # 切图文 tab
        pg.evaluate("""()=>{
          const t=[...document.querySelectorAll('.creator-tab')].find(e=>(e.textContent||'').trim()==='上传图文');
          t.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));
        }""")
        time.sleep(4)
        # 传图
        pg.set_input_files("input.upload-input", figs)
        log("已提交图片文件，等待上传 ...")
        for _ in range(30):
            time.sleep(2)
            n = pg.evaluate("""()=>document.querySelectorAll('img[src*="sns-img"],img[src*="fe-image"],.img-container img,[class*=thumb] img').length""")
            if n >= len(figs):
                break
        time.sleep(2)
        log("上传区缩略图数:", pg.evaluate("""()=>document.querySelectorAll('img[src*="sns-img"],img[src*="fe-image"],.img-container img,[class*=thumb] img').length"""))
        # 关掉可能的提示
        try:
            pg.locator("button:has-text('我知道了')").first.click(timeout=2000)
            log("已关提示弹窗")
        except Exception:
            pass
        # 标题
        ti = pg.locator('input[placeholder*="填写标题"]').first
        ti.click(); ti.fill(title)
        time.sleep(1)
        # 正文（tiptap）
        ed = pg.locator(".tiptap.ProseMirror").first
        ed.click()
        time.sleep(1)
        pg.keyboard.insert_text(text)
        time.sleep(2)
        got = pg.evaluate("()=>{const e=document.querySelector('.tiptap.ProseMirror');return e?e.innerText.length:0}")
        log("正文已填字数:", got)
        if not do_publish:
            pg.screenshot(path="/tmp/xhs_preflight.png")
            log("预检截图 /tmp/xhs_preflight.png，未发布")
            br.close(); return 0
        # 发布：按钮是自定义元素 <xhs-publish-btn>（闭包 shadow DOM），
        # 文本不可见 → 截宿主区域找红色像素质心 → 真实鼠标点击
        import io
        from PIL import Image
        host = pg.locator("xhs-publish-btn").first
        try:
            host.scroll_into_view_if_needed(timeout=8000)
        except Exception:
            pass
        box = host.bounding_box()
        if not box:
            log("❌ 找不到 xhs-publish-btn 宿主")
            br.close(); return 3
        time.sleep(1)
        shot = pg.screenshot(clip={"x": box["x"], "y": box["y"],
                                   "width": box["width"], "height": box["height"]})
        im = Image.open(io.BytesIO(shot)).convert("RGB")
        w, h = im.size
        px = im.load()
        xs, ys = [], []
        for yy in range(0, h, 2):
            for xx in range(0, w, 2):
                r, g, b = px[xx, yy]
                if r > 200 and g < 90 and b < 110:
                    xs.append(xx); ys.append(yy)
        if not xs:
            pg.screenshot(path="/tmp/xhs_nobtn.png")
            log("❌ 宿主区域内没找到红色发布按钮像素")
            br.close(); return 3
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        log(f"红色按钮质心: 宿主内({cx:.0f},{cy:.0f}) 页面({box['x']+cx:.0f},{box['y']+cy:.0f})")
        pg.mouse.click(box["x"] + cx, box["y"] + cy)
        log("已点击发布")
        # 校验
        ok = False
        for _ in range(15):
            time.sleep(2)
            u = pg.url
            t = pg.evaluate("()=>document.body.innerText.slice(0,3000)")
            if "发布成功" in t or "publish/success" in u or ("成功" in t and "发布" in t):
                ok = True; break
        log("发布校验:", ok, "URL =", pg.url)
        pg.screenshot(path="/tmp/xhs_after.png")
        br.close()
        return 0 if ok else 4

if __name__ == "__main__":
    args = sys.argv[1:]
    recon = "--recon" in args
    args = [a for a in args if a != "--recon"]
    md = args[0]; figs = args[1:]
    sys.exit(run(md, figs, do_publish=not recon))
