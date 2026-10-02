#!/usr/bin/env python3
"""生成静态站：python site/build.py [--check] [--out site/dist]

  --check   只校验数据，不输出文件（新增/修改项目后先跑这个）
默认输出到 site/dist/：index.html、app.js、style.css、data/catalog.json、downloads/*.zip
依赖：pip install -r site/requirements.txt
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import ROOT, load_catalog  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="只校验，不输出文件")
    ap.add_argument("--out", default=str(HERE / "dist"), help="输出目录（默认 site/dist）")
    args = ap.parse_args(argv)

    catalog, errors, warnings, downloads = load_catalog(ROOT, build_downloads=not args.check)
    for w in warnings:
        print(f"警告  {w}")
    for e in errors:
        print(f"错误  {e}")
    n_mcp = sum(1 for i in catalog["items"] if i["type"] == "mcp")
    n_skill = len(catalog["items"]) - n_mcp
    if errors:
        print(f"\n校验失败：{len(errors)} 个错误，{len(warnings)} 个警告（{n_mcp} 个 MCP，{n_skill} 个 Skill）")
        return 1
    if args.check:
        print(f"校验通过：{n_mcp} 个 MCP，{n_skill} 个 Skill，{len(warnings)} 个警告")
        return 0

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    (out / "downloads").mkdir()
    for f in (HERE / "src").iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
    (out / "data" / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, blob in downloads.items():
        (out / "downloads" / name).write_bytes(blob)
    n_rec = sum(len(i["recordings"]) for i in catalog["items"])
    print(f"已生成 {out}：{n_mcp} 个 MCP，{n_skill} 个 Skill，{n_rec} 份录制，{len(downloads)} 个下载包，{len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    sys.exit(main())
