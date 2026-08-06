# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt-text — 复合图程序化 QC（零视觉，先做）。
检查：1) caption/页眉/水印侵入  2) 边缘截断（提示）  3) 区内 OCR 文字量
用法:
  python3 qc_programmatic.py <fig_dir> <ocr_text.txt> --groups crop_figures_config.py
"""
import argparse
import importlib.util
import os
import re
import sys

import numpy as np
from PIL import Image

NOISE_PATTERNS = [
    (r"^Fig\.?\s*\d+", "caption"),
    (r"RESEARCH ARTICLE", "期刊页眉"),
    (r"Science\s+\d+\s+MAY", "页脚"),
    (r"Downloaded from", "水印"),
    (r"Check for updates", "页眉"),
    (r"^\d+\s+of\s+\d+$", "页码"),
]


def load_groups(py_path):
    spec = importlib.util.spec_from_file_location("cropcfg", py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.GROUPS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fig_dir")
    ap.add_argument("ocr_txt")
    ap.add_argument("--groups", help="含 GROUPS 的配置 .py（含 panel bbox 与页号）")
    args = ap.parse_args()

    groups = load_groups(args.groups) if args.groups else None
    if not groups:
        print("需要 --groups 配置文件（GROUPS 含 输出名,页号,panels[,whiteout][,pre]）")
        sys.exit(2)

    ocr_cache = {}
    fails, warns = [], []

    def page_ocr(pn):
        if pn not in ocr_cache:
            txt = open(args.ocr_txt, encoding="utf-8").read()
            m = re.search(rf"===== PAGE page_{pn:02d}\.png \(\d+x\d+\) =====(.*?)(?===== PAGE |\Z)", txt, re.S)
            body = m.group(1) if m else ""
            ocr_cache[pn] = [(int(a), int(b), int(c), int(d), t)
                             for a, b, c, d, t in re.findall(r"\[(\d+),(\d+),(\d+),(\d+)\]\t(.+)", body)]
        return ocr_cache[pn]

    for entry in groups:
        name, pn = entry[0], entry[1]
        panels = entry[2]
        path = os.path.join(args.fig_dir, f"{name}.png")
        if not os.path.exists(path):
            fails.append(f"{name}: 文件缺失")
            continue
        im = Image.open(path)
        # 1) caption/页眉/水印：用整页 OCR 反查裁剪区（需 page 与 bbox 推断裁剪区）
        # 简化：对裁剪图直接再跑一次轻量 OCR 不可行（需 pyobjc），改用区域交叉法：
        # 若提供 --groups 的 bbox，检查 bbox 周围 30px 内是否有 caption 关键词。
        xs0 = [p[1][0] for p in panels]
        ys0 = [p[1][1] for p in panels]
        xs1 = [p[1][2] for p in panels]
        ys1 = [p[1][3] for p in panels]
        x0, x1 = min(xs0), max(xs1)
        y0, y1 = min(ys0), max(ys1)
        pad = 30
        zone_ocr = [(a, b, c, d, t) for (a, b, c, d, t) in page_ocr(pn)
                    if a >= x0 - pad and c <= x1 + pad and b >= y0 - pad and d <= y1 + pad]
        joined = " ".join(t for *_, t in zone_ocr)
        for pat, label in NOISE_PATTERNS:
            if re.search(pat, joined, re.M):
                hit = next((t for t in [t for *_, t in zone_ocr] if re.match(pat, t)), "")
                fails.append(f"{name}: 疑似含 {label} -> {hit[:50]}")
        # 2) 文字量
        if len(zone_ocr) < 3:
            warns.append(f"{name}: 区内 OCR 文字过少({len(zone_ocr)})，检查裁剪是否错误")
        # 3) 边缘暗像素（提示）
        arr = np.asarray(im.convert("L"))
        h, w = arr.shape
        edge_sum = sum((arr[0:6, :] < 120).sum(), (arr[h-6:h, :] < 120).sum(),
                       (arr[:, 0:6] < 120).sum(), (arr[:, w-6:w] < 120).sum())
        if edge_sum > 800:
            warns.append(f"{name}: 边缘暗像素较高({edge_sum})，建议人工复核或裁白边")
        print(f"{name:<14} 区内OCR {len(zone_ocr):<4} 边缘 {edge_sum}")

    print("\n" + ("ALL CLEAR" if not fails else f"{len(fails)} FAIL"))
    for f in fails:
        print("  FAIL -", f)
    for w in warns:
        print("  WARN -", w)


if __name__ == "__main__":
    main()
