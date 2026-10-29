---
name: yi-jian-fa-gao-ji
description: 一键发稿机——把一篇 Markdown 自动发到腾讯云开发者社区、掘金、小红书三个平台的无头发布流水线。真实使用 30+ 天、发布 40+ 篇的实战版，内置验证码/弹窗/标签/查重等全部踩坑规避逻辑。当用户要批量发布文章、管理多平台内容、自动发文时使用。
---

# 一键发稿机（Auto Publisher）

三个平台、一条流水线，全部无头浏览器（Playwright）真跑通，不是概念稿。

## 它解决什么

手动发文到 3 个平台，一篇要 15-30 分钟：登录、贴正文、传图、填标签、点弹窗、等审核。
本技能包把这些全部自动化，并内置了 40+ 篇真实发布踩出来的规避逻辑：

- 腾讯云：文章标签必填且下拉必须点选（空着点发布无反应）、发布弹窗状态不持久必须一次填完、孤儿草稿自动清理
- 掘金：byte-select 标签控件 pointer 拦截、popup 窗口捕获、发布成功判据
- 小红书：shadow DOM 发布按钮（文字摸不到，用像素质心定位）、tiptap 正文注入、字数虚高修正
- **防重复铁律**：发前强制拉线上清单核对标题——文件名状态不可信，重复发布会被平台驳回

## 目录

| 模块 | 脚本 | 说明 |
|---|---|---|
| 腾讯云发布 | `scripts/tc_publish.py` | headless 全自动，含封面尽力/失败照发 |
| 腾讯云清单 | `scripts/tc_list.py` | 拉后台全清单（标题/状态/日期/ID），查重用 |
| 腾讯云删除 | `scripts/tc_delete.py` | 进回收站可恢复 |
| 掘金发布 | `scripts/juejin_publish.py` | 全自动无扫码（cookie 复用） |
| 掘金清单/删除 | `scripts/juejin_list.py` / `juejin_delete.py` | 主页清单 + 下架 |
| 小红书发布 | `scripts/xhs_publish.py` | 无头全自动，成功判据 URL 跳转 |
| 小红书封面 | `scripts/xhs_covers.py` | 1080x1440 文字卡片 |
| 审核过自动发 | `scripts/auto_pub_approved_tc.py` | 只发带 `__审核通过` 标记的文件 |
| 登录态持久化 | `scripts/persist_login.py` | 扫码一次，cookie 长期复用 |

## 快速开始

```bash
pip install playwright pillow && playwright install chromium
export FMJ_BASE=$(pwd)          # 工作目录（稿件/图/cookie 都在这）
python3 scripts/persist_login.py 腾讯云    # 首次扫码，之后长期免登录
python3 scripts/tc_publish.py --title "你的标题" --body 稿件.md --figs 图1.png --tag 人工智能
python3 scripts/juejin_publish.py 稿件.md  # 改脚本顶部配置即可
```

## 硬纪律（血泪换来的，勿绕过）

1. **发布前必须拉线上清单核对标题**（tc_list.py / juejin_list.py）——2026-10-24 只信文件名后缀，一天造出 9 篇重复、删了 16 篇。
2. cookie 放 `FMJ_BASE/.publish-state/`，失效就重新扫码，不硬试。
3. 发布成功的唯一判据是平台自己的成功信号（URL 跳转/页面状态），不是脚本没报错。

## 依赖

Python 3.10+ / Playwright / Pillow。详见 `references/踩坑实录.md`。
