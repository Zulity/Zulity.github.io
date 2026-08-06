# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt-text — macOS Vision OCR（免费、本地、零 API）。
对整页 PNG 批量提取文字，每条带像素坐标 [x0,y0,x1,y1]\t文字（左上角原点）。

用法:
  python3 ocr_pages.py <png目录> <输出txt>
  python3 ocr_pages.py <png目录> <输出txt> --lang zh-Hans   # 中文论文

依赖: pyobjc-framework-Vision pyobjc-framework-Quartz
      pip install pyobjc-framework-Vision
"""
import argparse
import os

import Quartz
import Vision


def ocr_page(path, lang="en-US"):
    url = Quartz.CFURLCreateWithFileSystemPath(
        None, path, Quartz.kCFURLPOSIXPathStyle, False)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return None, None, None
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cg is None:
        return None, None, None
    W = Quartz.CGImageGetWidth(cg)
    H = Quartz.CGImageGetHeight(cg)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    req.setRecognitionLanguages_([lang])
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        return None, W, H
    lines = []
    for obs in req.results():
        cand = obs.topCandidates_(1)[0]
        bb = obs.boundingBox()  # normalized, origin bottom-left
        x = int(bb.origin.x * W)
        y = int((1 - bb.origin.y - bb.size.height) * H)  # top-left origin
        w = int(bb.size.width * W)
        h = int(bb.size.height * H)
        lines.append(f"[{x},{y},{x + w},{y + h}]\t{cand.string()}")
    return lines, W, H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="整页 PNG 目录")
    ap.add_argument("out", help="输出 txt 路径")
    ap.add_argument("--lang", default="en-US", help="识别语言（en-US / zh-Hans）")
    ap.add_argument("--only", help="只处理文件名包含该子串的页（如 'Fig'）")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.dir) if f.endswith(".png"))
    if args.only:
        files = [f for f in files if args.only in f]
    all_text = []
    for f in files:
        lines, W, H = ocr_page(os.path.join(args.dir, f), args.lang)
        all_text.append(f"===== PAGE {f} ({W}x{H}) =====")
        if lines:
            all_text.extend(lines)
        else:
            all_text.append("(no text)")
        print(f"done {f} ({len(lines) if lines else 0} lines)", flush=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(all_text))
    print(f"OCR done -> {args.out}")


if __name__ == "__main__":
    main()
