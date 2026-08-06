# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt-text — OCR 文字网格聚类 → panel 布局初判（零视觉）。
对 figure 页做：行聚类 → 每行列聚类 → 输出格子 bbox + 格子内文字摘要。
用于 Phase 4.1：多数 panel 边界可从轴标签/图例文字坐标推断，无需视觉模型。

用法:
  python3 grid_cluster.py <ocr_text.txt> <page_no> <y_lo> <y_hi> [x_lo] [x_hi]
示例:
  python3 grid_cluster.py ocr_text.txt 6 160 2460
"""
import argparse
import re

OCR = "paper/ocr_text.txt"


def ocr_boxes(ocr_path, pn):
    txt = open(ocr_path, encoding="utf-8").read()
    m = re.search(rf"===== PAGE page_{pn:02d}\.png \(\d+x\d+\) =====(.*?)(?===== PAGE |\Z)", txt, re.S)
    body = m.group(1) if m else ""
    out = []
    for mm in re.finditer(r"\[(\d+),(\d+),(\d+),(\d+)\]\t(.+)", body):
        x0, y0, x1, y1 = int(mm[1]), int(mm[2]), int(mm[3]), int(mm[4])
        out.append((x0, y0, x1, y1, mm[5]))
    return out


def cluster(values, gap):
    if not values:
        return []
    groups = [[values[0]]]
    for v in values[1:]:
        if v - groups[-1][-1] > gap:
            groups.append([v])
        else:
            groups[-1].append(v)
    return [(g[0], g[-1], g) for g in groups]


def analyze_page(ocr_path, pn, y_lo, y_hi, x_lo=155, x_hi=2318):
    boxes = [b for b in ocr_boxes(ocr_path, pn) if y_lo <= b[1] <= y_hi and x_lo <= b[3] <= x_hi]
    boxes.sort(key=lambda b: (b[1], b[0]))
    rows = cluster(sorted(set((b[1] + b[3]) // 2 for b in boxes)), gap=45)
    print(f"===== page {pn}: {len(rows)} rows =====")
    for ri, (ry0, ry1, _) in enumerate(rows):
        rboxes = [b for b in boxes if ry0 <= (b[1] + b[3]) // 2 <= ry1]
        cols = cluster(sorted(set((b[0] + b[2]) // 2 for b in rboxes)), gap=60)
        print(f"  row{ri} y={ry0}-{ry1}: {len(cols)} cols")
        for ci, (cx0, cx1, _) in enumerate(cols):
            cboxes = [b for b in rboxes if cx0 <= (b[0] + b[2]) // 2 <= cx1]
            x0 = min(b[0] for b in cboxes) - 10
            y0 = min(b[1] for b in cboxes) - 10
            x1 = max(b[2] for b in cboxes) + 10
            y1 = max(b[3] for b in cboxes) + 10
            texts = " | ".join(b[4] for b in sorted(cboxes, key=lambda b: (b[1], b[0]))[:8])
            print(f"    col{ci} bbox=({x0},{y0},{x1},{y1})  texts: {texts[:110]}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ocr_txt", help="ocr_pages.py 输出")
    ap.add_argument("page", type=int)
    ap.add_argument("y_lo", type=int)
    ap.add_argument("y_hi", type=int)
    ap.add_argument("x_lo", type=int, nargs="?", default=155)
    ap.add_argument("x_hi", type=int, nargs="?", default=2318)
    args = ap.parse_args()
    analyze_page(args.ocr_txt, args.page, args.y_lo, args.y_hi, args.x_lo, args.x_hi)


if __name__ == "__main__":
    main()
