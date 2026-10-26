#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""永久自动化发布器（腾讯云）。
只处理带「审核通过」标记的文章：内容运营/ 下所有 *腾讯云版__审核通过.md。
逐篇调 tc_publish.py 全自动发布（headless、自动点确认发布、校验发布成功）；
发布成功后把文件名 __审核通过.md 改名为 __已发布.md（避免重复发布）。
未带标记的文章一律不动。后台静默运行。
"""
import os
import subprocess, time, re
from pathlib import Path

BASE = Path(os.environ.get("FMJ_BASE", os.getcwd()) + "")
FIGDIR = BASE / "配图"
PY = str(Path.home()) + "/.workbuddy/binaries/python/envs/default/bin/python"
PUB = BASE / "scripts" / "tc_publish.py"
PER_ARTICLE_TIMEOUT = 240

def title_of(md):
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            return t if "#WorkBuddy#" in t else t + " #WorkBuddy#"
    return md.stem + " #WorkBuddy#"

def figs_of(md):
    m = re.match(r"(\d+)-", md.name)
    if not m:
        return []
    prefix = m.group(1)
    return sorted(p.name for p in FIGDIR.glob(f"{prefix}__fig*.png"))

def pub_one(md):
    title = title_of(md)
    figs = figs_of(md)
    cmd = [PY, str(PUB), "--title", title, "--body", md.name, "--tag", "人工智能"]
    if figs:
        cmd += ["--figs"] + figs
    print(f"[auto] 发布：{md.name} 配图={len(figs)}", flush=True)
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=str(BASE))
    try:
        rc = proc.wait(timeout=PER_ARTICLE_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"[auto] ⚠ 超时回收 {md.name} ({time.time()-t0:.0f}s)", flush=True)
        return "TIMEOUT"
    print(f"[auto] tc_publish rc={rc} ({time.time()-t0:.0f}s)", flush=True)
    return rc

def main():
    arts = sorted(BASE.glob("*腾讯云版__审核通过.md"))
    if not arts:
        print("[auto] 无审核通过待发文章，静默退出", flush=True)
        return
    print(f"[auto] 发现 {len(arts)} 篇审核通过，开始自动发布", flush=True)
    for md in arts:
        rc = pub_one(md)
        if rc == 0:
            new = md.with_name(md.name.replace("__审核通过.md", "__已发布.md"))
            md.rename(new)
            print(f"[auto] ✅ 已发布并标记：{new.name}", flush=True)
        else:
            print(f"[auto] ❌ 发布失败 rc={rc}，保留待重试：{md.name}", flush=True)
        subprocess.run("pkill -f headless_shell 2>/dev/null", shell=True)
        time.sleep(2)
    print("[auto] 本轮结束", flush=True)

if __name__ == "__main__":
    main()
