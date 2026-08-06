# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt-text — OCR 文本清洗：页眉页脚过滤 + 逻辑排序。
输入 ocr_pages.py 的输出（[x0,y0,x1,y1]\t文字，按页分段），输出：
  1) clean_text.txt  — 按阅读顺序（自上而下、从左到右）排列的纯文本
  2) noise_report.txt — 被过滤掉的噪声条目（页眉/页脚/水印/页码）

用法:
  python3 sort_text_by_layout.py <ocr_text.txt> <输出目录>

页眉页脚黑名单按期刊调整：修改 NOISE_PATTERNS 与 PAGE_HEADER_ORIGIN。
"""
import argparse
import os
import re

# ---- 期刊页眉/页脚/水印黑名单（按需增删）----
NOISE_PATTERNS = [
    (r"^RESEARCH ARTICLE$", "期刊页眉"),
    (r"^Check for updates$", "页眉"),
    (r"^Science\s+\d+\s+\w+\s+\d{4}$", "页脚（期刊名+日期）"),
    (r"^\d+\s+of\s+\d+$", "页码"),
    (r"^Downloaded from", "水印"),
    (r"Tsinghua University|University on May|University$", "下载机构水印"),
    (r"^[A-Za-z]+\s+\d+,\s*\d{4}$", "日期行"),
    (r"^\d{4}$", "孤立年份"),
    (r"doi:\s*\S+|DOI:\s*\S+", "DOI 引用框"),
    (r"^10\.\d{4}/", "DOI 起始"),
]
# 页眉起点（页顶内容，通常 y<180 且靠左/靠右的小字）——由坐标判断，见 _is_header_footer

PAGE_SEP = re.compile(r"^===== PAGE (\S+) \((\d+)x(\d+)\) =====")


def parse_ocr(path):
    """返回 {filename: [(x0,y0,x1,y1,text), ...]} 保持原顺序。"""
    pages = {}
    cur = None
    for line in open(path, encoding="utf-8"):
        m = PAGE_SEP.match(line)
        if m:
            cur = m.group(1)
            pages[cur] = []
            continue
        mm = re.match(r"\[(\d+),(\d+),(\d+),(\d+)\]\t(.+)", line)
        if mm and cur is not None:
            pages[cur].append((int(mm[1]), int(mm[2]), int(mm[3]), int(mm[4]), mm[5]))
    return pages


def is_noise(x0, y0, x1, y1, text, H, x_center_gutter=None):
    """判断是否为页眉/页脚/水印/页码。text 已 strip。"""
    if not text:
        return True
    for pat, why in NOISE_PATTERNS:
        if re.match(pat, text):
            return True
    # 页码特征：短数字行靠近底部
    if re.match(r"^\d{1,3}$", text) and y0 > H * 0.93:
        return True
    # 顶部页眉：y<H*0.05 且字号小（高<40px）且文字短
    if y0 < H * 0.05 and (y1 - y0) < 45 and len(text) < 40:
        return True
    return False


def cluster_rows(boxes, gap=45):
    """按文字块 y 中心聚类成行，返回 [(行锚点y, [boxes...]), ...]（按锚点升序）。
    锚点 = 行内最小 y 中心（首个 box），不重算均值，保证行序单调。"""
    items = sorted(boxes, key=lambda b: (b[1] + b[3]) // 2)
    rows = []
    for b in items:
        cy = (b[1] + b[3]) // 2
        if rows and cy - rows[-1][0] <= gap:
            rows[-1][1].append(b)
        else:
            rows.append((cy, [b]))
    return rows


def sort_layout(page_boxes, W, H):
    """页内逻辑排序：检测双栏 → 栏内自上而下、行内从左到右。返回 [(text, x0,y0), ...]。"""
    # 双栏检测：右侧栏存在大量文字块 x 中心 > 0.5W（Science/NEJM 中缝≈页宽一半）
    right_blocks = [b for b in page_boxes if (b[0] + b[2]) / 2 > W * 0.5]
    left_blocks = [b for b in page_boxes if (b[0] + b[2]) / 2 <= W * 0.5]
    two_col = (len(right_blocks) > 5 and len(left_blocks) > 5
               and 0.3 < len(right_blocks) / max(len(left_blocks), 1) < 3.0)
    ordered = []
    if two_col:
        # 左栏自上而下 → 右栏自上而下（报纸式双栏阅读）
        for blocks in (left_blocks, right_blocks):
            for row in cluster_rows(blocks):
                row_boxes = sorted(row[1], key=lambda b: b[0])
                for b in row_boxes:
                    ordered.append((b[4], b[0], b[1]))
    else:
        for row in cluster_rows(page_boxes):
            row_boxes = sorted(row[1], key=lambda b: b[0])
            for b in row_boxes:
                ordered.append((b[4], b[0], b[1]))
    return ordered, two_col


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ocr_txt", help="ocr_pages.py 的输出")
    ap.add_argument("outdir", help="输出目录")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    pages = parse_ocr(args.ocr_txt)
    clean_lines = []
    noise_lines = []
    for fname, boxes in pages.items():
        # 用每页最大坐标估算 H/W（供页码/页眉坐标判断）
        W = max((b[2] for b in boxes), default=0)
        H = max((b[3] for b in boxes), default=0)
        keep, noise = [], []
        for b in boxes:
            if is_noise(b[0], b[1], b[2], b[3], b[4].strip(), H):
                noise.append(b)
            else:
                keep.append(b)
        ordered, two_col = sort_layout(keep, W, H)
        clean_lines.append(f"===== PAGE {fname} (clean, two_col={two_col}) =====")
        for text, x0, y0 in ordered:
            clean_lines.append(f"[{x0},{y0}]\t{text}")
        noise_lines.append(f"===== PAGE {fname} (noise removed: {len(noise)}) =====")
        for b in noise:
            noise_lines.append(f"[{b[0]},{b[1]},{b[2]},{b[3]}]\t{b[4]}")

    with open(os.path.join(args.outdir, "clean_text.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(clean_lines))
    with open(os.path.join(args.outdir, "noise_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(noise_lines))
    total_clean = sum(1 for l in clean_lines if l.startswith("["))
    total_noise = sum(1 for l in noise_lines if l.startswith("["))
    print(f"clean_text.txt: {total_clean} 行正文 | noise_report.txt: {total_noise} 行噪声已滤")


if __name__ == "__main__":
    main()
