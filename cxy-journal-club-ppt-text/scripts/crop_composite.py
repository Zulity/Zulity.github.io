# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt-text — 精确 panel 边界复合裁剪（含 whiteout / pre-whiteout）。

用法:
  1. 复制本文件为项目内 crop_figures_<paper>.py
  2. 配置 PAGE_DIR / OUT / GROUPS：
     GROUPS 每项 = (输出名, 页号, [(panel, (x0,y0,x1,y1)), ...], [whiteout...], [pre_whiteout...])
       - 坐标均为整页像素（ocr/grid_cluster/vision 定位结果）
       - whiteout:     裁剪画布内坐标（脚本自动换算），处理 y 重叠 x 分离的相邻 panel
       - pre_whiteout: 整页坐标，**精修前**涂白（避免残留干扰边界精修——本次实战新增）
  3. python3 crop_figures_<paper>.py
  4. 逐张 vision 拼图 QC（见 qc_programmatic.py + contact_sheet.py）
"""
import argparse
import os

import numpy as np
from PIL import Image

MARGIN = 15          # bbox 四周留白（整页像素）
PAD = 20             # 输出统一白边


def refine_y(im, x0, x1, y0, y1, thresh=150, min_dark=3, pad=3):
    """numpy 精修：区域内内容实际上下边界（暗像素扫描）。"""
    gray = np.asarray(im.convert("L"))
    dark = gray[y0:y1, x0:x1] < thresh
    rowsum = dark.sum(axis=1)
    ys = np.where(rowsum >= min_dark)[0]
    if len(ys) == 0:
        return y0, y1
    return y0 + ys.min() - pad, y0 + ys.max() + pad + 1


def render_composites(page_dir, groups, out_dir, dpi_note=True):
    os.makedirs(out_dir, exist_ok=True)
    pages = {}
    report = []
    for entry in groups:
        name, pn, panels = entry[0], entry[1], entry[2]
        whiteout = entry[3] if len(entry) > 3 else []
        pre_whiteout = entry[4] if len(entry) > 4 else []
        if pn not in pages:
            pages[pn] = Image.open(os.path.join(page_dir, f"page_{pn:02d}.png")).convert("RGB")
        im = pages[pn]
        # pre-whiteout：整页坐标，refine 前涂白
        if pre_whiteout:
            pim = im.load()
            for (wx0, wy0, wx1, wy1) in pre_whiteout:
                for yy in range(max(0, wy0), min(wy1, im.height)):
                    for xx in range(max(0, wx0), min(wx1, im.width)):
                        pim[xx, yy] = (255, 255, 255)
        xs0 = [p[1][0] for p in panels]
        ys0 = [p[1][1] for p in panels]
        xs1 = [p[1][2] for p in panels]
        ys1 = [p[1][3] for p in panels]
        x0 = max(0, min(xs0) - MARGIN)
        x1 = min(im.width, max(xs1) + MARGIN)
        y0 = max(0, min(ys0) - MARGIN)
        y1 = min(im.height, max(ys1) + MARGIN)
        ny0, ny1 = refine_y(im, x0, x1, y0, y1)
        if ny1 - ny0 < 0.5 * (y1 - y0):  # 防过度收缩
            ny0, ny1 = y0, y1
        y0, y1 = max(0, ny0 - 12), min(im.height, ny1 + 12)
        x0, x1 = max(0, x0 - 20), min(im.width, x1 + 20)
        crop = im.crop((x0, y0, x1, y1))
        # whiteout：裁剪画布内坐标（偏移 = x0, y0）
        if whiteout:
            px = crop.load()
            for (wx0, wy0, wx1, wy1) in whiteout:
                cx0, cy0 = max(0, wx0 - x0), max(0, wy0 - y0)
                cx1, cy1 = min(crop.width, wx1 - x0), min(crop.height, wy1 - y0)
                for yy in range(cy0, cy1):
                    for xx in range(cx0, cx1):
                        px[xx, yy] = (255, 255, 255)
        canvas = Image.new("RGB", (crop.width + 2 * PAD, crop.height + 2 * PAD), (255, 255, 255))
        canvas.paste(crop, (PAD, PAD))
        path = os.path.join(out_dir, f"{name}.png")
        canvas.save(path)
        panels_str = "".join(p for p, _ in panels)
        report.append((name, pn, panels_str, canvas.width, canvas.height,
                       f"y={ny0}-{ny1} x={x0}-{x1}"))
    print(f"{'name':<14} {'pg':<4} {'panels':<10} {'px_w':<6} {'px_h':<6} region")
    for r in report:
        print(f"{r[0]:<14} {r[1]:<4} {r[2]:<10} {r[3]:<6} {r[4]:<6} {r[5]}")
    print(f"\nTotal {len(report)} composite crops -> {out_dir}/  (下一步: qc_programmatic + vision 拼图 QC)")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="可选：GROUPS 配置的 .py 文件（默认读本文件底部 GROUPS 变量）")
    args = ap.parse_args()
    # 典型用法：复制本文件后直接改底部 GROUPS / PAGE_DIR / OUT 再运行
    from importlib import import_module
    mod = import_module("crop_figures_config") if args.config else None
    if mod:
        render_composites(mod.PAGE_DIR, mod.GROUPS, mod.OUT)
    else:
        print("请先配置 PAGE_DIR / OUT / GROUPS（复制本文件为 crop_figures_<paper>.py 后修改），"
              "或在脚本内直接设置全局变量后调用 render_composites()")


if __name__ == "__main__":
    main()
