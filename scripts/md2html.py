"""
Markdown → 腾讯云编辑器可用的富文本 HTML。

腾讯云的 Markdown 编辑器不认 `##`、`**`、`---` 这类语法，
必须转成HTML 后用剪贴板粘贴，才能得到正确的标题层级、加粗与分割线。
"""

import html
import re


def md_to_html(md: str) -> str:
    """把 Markdown 转成编辑器可粘贴的 HTML。"""
    lines = md.splitlines()
    out = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf = []

    def flush_code():
        nonlocal code_buf, code_lang
        if code_buf:
            cls = f' class="language-{code_lang}"' if code_lang else ""
            body = html.escape("\n".join(code_buf))
            out.append(f"<pre><code{cls}>{body}\n</code></pre>")
            code_buf = []
            code_lang = ""

    while i < len(lines):
        ln = lines[i].rstrip()

        # 代码块
        if ln.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lang = ln[3:].strip()
            i += 1
            continue
        if in_code:
            code_buf.append(ln)
            i += 1
            continue

        # 分割线
        if ln.strip() in ("---", "***", "___") and len(ln.strip()) >= 3:
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl = min(len(m.group(1)), 4)
            txt = inline(m.group(2))
            out.append(f"<h{lvl}>{txt}</h{lvl}>")
            i += 1
            continue

        # 引用块
        if ln.startswith(">"):
            out.append("<blockquote>")
            while i < len(lines) and lines[i].startswith(">"):
                t = lines[i].lstrip(">").strip()
                if t:
                    out.append(f"<p>{inline(t)}</p>")
                i += 1
            out.append("</blockquote>")
            continue

        # 表格：当前行有 |，且下一行是分隔行
        if "|" in ln and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += [f"<th>{inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # 列表
        if re.match(r"^\s*[-*+]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*+]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*+]\s+", "", lines[i]).strip())
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        if re.match(r"^\s*\d+\.\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]).strip())
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue

        # 空行
        if not ln.strip():
            i += 1
            continue

        # 普通段落（连续行合并）
        para = [ln]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^\s*(#{1,6}\s|[-*+]\s|\d+\.\s|>|\||```)", lines[i]
        ):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")

    flush_code()
    return "".join(out)


def inline(t: str) -> str:
    """行内格式：代码、加粗、斜体。"""
    t = html.escape(t, quote=False)
    # 行内代码
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # 加粗（避免与行内代码冲突，先占位）
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    return t


def to_plain_html_file(md_path: str, out_path: str) -> str:
    """生成可直接粘贴的 HTML 文件。"""
    md = open(md_path, encoding="utf-8").read()
    # 去掉开头给自己看的标签说明行
    lines = md.splitlines()
    if len(lines) > 2 and lines[2].startswith("> 标签："):
        del lines[2]
        md = "\n".join(lines)
    # 去掉首行 H1（标题已在标题框单独填）
    if md.lstrip().startswith("# "):
        md = md.lstrip()[2:]
        md = md.split("\n", 1)[1] if "\n" in md else ""
    body = md_to_html(md)
    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        f'<body>{body}</body></html>'
    )
    open(out_path, "w", encoding="utf-8").write(page)
    return out_path


if __name__ == "__main__":
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else "01-读本机图片六个坑-腾讯云版__待发布.md"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/tc_body.html"
    p = to_plain_html_file(src, dst)
    import os

    print(f"已生成 {p}  {os.path.getsize(p):,} 字节")
