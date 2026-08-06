# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt-text — 复合图拼图（contact sheet）批量 QC 工具。
把多张复合图拼成一张网格图，一次 view_image 检查多张，大幅节省视觉模型 token。
典型：23 张图从 23 次调用降到 4-6 次拼图 + 失败项单独复查。

用法:
  python3 contact_sheet.py <fig_dir> [图名...]  # 无图名则全部
  # 输出 fig_dir/../qc_sheets/sheet_01.png 等，随后用 view_image 检查

拼图默认：3 列，每张缩到 640px 宽，白底网格，图上方标注文件名。
"""
import argparse
import os

from PIL import Image, ImageDraw


def make_sheet(files, out_path, cols=3, thumb_w=640):
    imgs = []
    for f in files:
        im = Image.open(f)
        w, h = im.size
        tw = thumb_w
        th = int(h * tw / w)
        im = im.resize((tw, th), Image.LANCZOS)
        imgs.append((os.path.basename(f), im))
    n = len(imgs)
    rows = (n + cols - 1) // cols
    label_h = 34
    cell_w = thumb_w
    cell_h = max((im.height for _, im in imgs), default=300) + label_h
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for i, (fname, im) in enumerate(imgs):
        r, c = divmod(i, cols)
        x, y = c * cell_w, r * cell_h
        sheet.paste(im, (x, y + label_h))
        draw.text((x + 8, y + 8), fname, fill=(0, 0, 0))
        draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline=(180, 180, 180))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sheet.save(out_path)
    print(f"{n} 张 -> {out_path} ({sheet.width}x{sheet.height})")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fig_dir")
    ap.add_argument("names", nargs="*", help="图名（不带 .png）；缺省=目录全部 png")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--thumb", type=int, default=640)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.names:
        files = [os.path.join(args.fig_dir, n if n.endswith(".png") else n + ".png") for n in args.names]
    else:
        files = sorted(os.path.join(args.fig_dir, f) for f in os.listdir(args.fig_dir) if f.endswith(".png"))
    files = [f for f in files if os.path.exists(f)]
    if not files:
        print("没有可拼图文件")
        return
    out_dir = args.out or os.path.join(os.path.dirname(args.fig_dir.rstrip("/")), "qc_sheets")
    out_path = os.path.join(out_dir, "sheet_01.png")
    make_sheet(files, out_path, args.cols, args.thumb)
    if len(files) > args.cols * 6:
        print(f"提示: {len(files)} 张建议拆多 sheet（每 sheet ≤{args.cols*6} 张）保证可读性；"
              f"可用 --names 指定子集。")


if __name__ == "__main__":
    main()
