# 一键发稿机 🖨️

**一篇 Markdown，三个平台，全自动发出去。**

腾讯云开发者社区 + 掘金 + 小红书，无头浏览器真跑通。不是 demo，是我自己每天在用的流水线——**40+ 篇文章靠它发的，踩过的 18 个坑全部内置规避**。

## 为什么造这个

我让 AI 帮我自动发文，第一天它造了 4 个空白草稿；第三天我信了文件名上的"待发布"标记，一天发出 9 篇重复、被平台驳回 6 篇、删了 16 篇。
这些坑没有一篇教程写过，因为没人把无头发布跑到这个深度。坑全部修完之后，就成了这个包。

## 三个平台的硬骨头（全部已啃完）

| 平台 | 坑 | 本包的解法 |
|---|---|---|
| 腾讯云 | 标签必填+下拉点选、弹窗状态不持久、封面校验 | 一次弹窗填完 + 失败照发模式 |
| 掘金 | byte-select 拦截 pointer、popup 捕获 | 键盘直注 + expect_page |
| 小红书 | 发布按钮闭包 shadow DOM、tiptap 字数虚高 | 红色像素质心定位 + innerText 校准 |

**防重复铁律**：发前强制拉线上清单核对标题。这条纪律是用 16 篇删稿换的。

## 快速开始

```bash
pip install playwright pillow && playwright install chromium
export FMJ_BASE=$(pwd)
python3 scripts/persist_login.py 腾讯云     # 扫码一次，长期免登录
python3 scripts/tc_publish.py --title "标题" --body 稿件.md --tag 人工智能
```

跨智能体可用：豆包 / Claude / CodeBuddy / WorkBuddy，把 `SKILL.md` 喂给你的 Agent 即可。

## 真实战绩

- 30+ 天连续使用，40+ 篇三平台发布
- 审核→自动发布→改名归档全链路无人值守
- 2026-10-24 事故后强化查重，重复率归零

## License

MIT。觉得有用点个 ⭐，比什么都实在。
