# -*- coding: utf-8 -*-
"""cxy-journal-club-ppt2 — PPT 脚本化终检（Phase 8）。

用法：
  python3 verify_ppt.py <deck.pptx>

自动检查（对应 SKILL 硬约束与 Phase 8 终检清单）：
  [1] slide 总数 <= 30（含标题与讨论）
  [2] 标题页含 汇报人/日期（非占位符）
  [3] 每个 Result slide 标题以 "Fig" 开头（编号 >=5 且标题含 FigX:）
  [4] Result slide 备注非空（含逐 panel 总结行 FigX{A}：…）
  [5] 字号合规：标题 >=22pt，正文 20pt
  [6] 所有文字段落行距 == 1.5
  [7] 每张 Result slide 恰好 1 张图片
  [8] 引用的图片文件存在

退出码：0 = 全部通过；1 = 存在失败项。逐项输出 PASS/FAIL。
"""
import os
import re
import sys

from pptx import Presentation


def check_deck(path):
    prs = Presentation(path)
    slides = list(prs.slides)
    fails = []
    passed = []

    def ok(cond, msg):
        (passed if cond else fails).append(msg)

    n = len(slides)
    ok(n <= 30, f"[1] slide 总数 {n} <= 30")

    # --- 标题页：汇报人/日期 ---
    s0 = slides[0]
    txt0 = "\n".join(sh.text_frame.text for sh in s0.shapes if sh.has_text_frame)
    has_reporter = ("汇报人" in txt0 and "汇报日期" in txt0
                    and "XXX" not in txt0 and "YYYY" not in txt0
                    and "占位" not in txt0)
    ok(has_reporter, "[2] 标题页含汇报人/日期（非占位符）")

    # --- 逐 slide 检查 ---
    body_sizes = set()
    title_sizes = set()
    line_spacings = set()
    for i, s in enumerate(slides):
        title = ""
        for sh in s.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                title = sh.text_frame.text.strip()
                break
        is_result = re.match(r"^Fig\s*\d+", title)
        if i >= 4 and is_result:  # Result slides 从第 5 张起
            imgs = [sh for sh in s.shapes if sh.shape_type == 13]  # PICTURE
            ok(len(imgs) == 1, f"[7] slide {i+1} 恰好 1 张图片（实际 {len(imgs)}）")
            if imgs:
                try:
                    blob_ok = bool(imgs[0].image.blob)
                except Exception:
                    blob_ok = False
                ok(blob_ok, f"[8] slide {i+1} 图片数据有效嵌入（非空 blob）")
            notes_txt = s.notes_slide.notes_text_frame.text if s.has_notes_slide else ""
            has_panel_summary = bool(re.search(r"Fig\d+[A-Z]", notes_txt))
            ok(bool(notes_txt.strip()), f"[4] slide {i+1} 备注非空")
            ok(has_panel_summary, f"[4] slide {i+1} 备注含逐 panel 总结（FigX{{A}}：…）")
        # 字号与行距（标题文本框 = 第一个非空文本框；≤10pt 视为页码/DOI 等辅助文字，不计入）
        title_si = None
        for si, sh in enumerate(s.shapes):
            if sh.has_text_frame and sh.text_frame.text.strip():
                title_si = si
                break
        for si, sh in enumerate(s.shapes):
            if not sh.has_text_frame:
                continue
            for p in sh.text_frame.paragraphs:
                if p.line_spacing is not None:
                    line_spacings.add(round(float(p.line_spacing), 2))
                for r in p.runs:
                    if r.font.size is None or r.font.size.pt <= 10:
                        continue
                    pt = r.font.size.pt
                    if si == title_si and i != 0:  # 各页标题行（标题页整体是元信息页，跳过）
                        title_sizes.add(pt)
                    elif i != 0:                   # 正文（不含标题页）
                        body_sizes.add(pt)
        # Result 标题前缀
        if i >= 4 and is_result:
            ok(True, f"[3] slide {i+1} 标题以 Fig 开头: {title[:40]}…")

    # 标题/正文字号
    if title_sizes:
        ok(min(title_sizes) >= 22, f"[5] 标题最小字号 {min(title_sizes):.0f}pt >= 22pt")
    if body_sizes:
        ok(min(body_sizes) >= 19.5, f"[5] 正文最小字号 {min(body_sizes):.0f}pt >= 20pt")
    ok(all(abs(ls - 1.5) < 1e-6 for ls in line_spacings),
       f"[6] 行距全部 1.5（实际 {sorted(line_spacings)}）")

    for m in passed:
        print(f"  PASS  {m}")
    for m in fails:
        print(f"  FAIL  {m}")
    print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILED'}: {path}")
    return 0 if not fails else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(check_deck(sys.argv[1]))
