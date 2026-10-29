# -*- coding: utf-8 -*-
"""生成小红书封面（1080x1440 文字卡片）。"""
import os
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "/配图")
FONT = "/System/Library/Fonts/STHeiti Light.ttc"

def font(sz, idx=4):
    try:
        return ImageFont.truetype(FONT, sz, index=idx)
    except Exception:
        return ImageFont.truetype(FONT, sz)

def wrap(draw, text, f, maxw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=f) <= maxw:
            cur += ch
        else:
            lines.append(cur); cur = ch
    if cur: lines.append(cur)
    return lines

def cover(name, big_lines, sub, accent=(255, 36, 66), bg=(255, 249, 244)):
    W, H = 1080, 1440
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    # 顶部色条
    d.rectangle([0, 0, W, 18], fill=accent)
    # 主标题
    f_big = font(96)
    y = 300
    for ln in big_lines:
        for wl in wrap(d, ln, f_big, W - 200):
            d.text((100, y), wl, font=f_big, fill=(30, 30, 30))
            y += 130
    # 红色下划线
    d.rectangle([100, y + 20, 100 + 260, y + 34], fill=accent)
    y += 120
    # 副标题
    f_sub = font(52)
    for wl in wrap(d, sub, f_sub, W - 240):
        d.text((100, y), wl, font=f_sub, fill=(120, 120, 120))
        y += 78
    # 底部署名
    f_ft = font(40)
    d.text((100, H - 160), "球球线 · 实测笔记", font=f_ft, fill=(180, 180, 180))
    p = OUT / name
    im.save(p)
    print("封面已生成:", p)

cover("08__xhs封面.png",
      ["不懂技术，", "但我用三个大佬的脑子", "避开了亏钱的坑"],
      "马斯克 · 芒格 · 巴菲特的筛法")
cover("09__xhs封面.png",
      ["让 AI 上网找资料", "就抓瞎？", "给它装双眼睛"],
      "AgentReach 从 0 到 1 实测")
cover("10__xhs封面.png",
      ["给大脑请了个智囊团", "乔布斯/马斯克/芒格", "给你打工"],
      "NUWA.skill 从 0 到 1 实测")
cover("11__xhs封面.png",
      ["别被忽悠！", "2 万赞的 Muse 方法", "根本是坑"],
      "开源平替 OpenMuse 实测避雷")
