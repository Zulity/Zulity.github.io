---
name: cxy-journal-club-ppt-text
description: CXY 定制 Journal Club / 文献汇报 PPT 生成器（OCR-first 文本优先版，代号 "PPT+text"）。核心思路：先用 macOS 自带 Vision 框架对整页 PNG/PDF 渲染页做免费 OCR（提取文字+像素坐标、排除页眉页脚、按从上到下/从左到右逻辑排序），把全部"读文字"任务交给 OCR+廉价文本模型（如 deepseek），再调度视觉专家（如 kimi-k3）只做"看图"任务（panel 定位 bbox、复合图 QC），在尽量节省视觉模型 token 的前提下保证图片质量。含精确 panel 边界裁剪、逐张 QC、30 slide 上限、正文 20pt/1.5 行距、备注逐 panel 总结、汇报人/日期必填。Use when the user asks for 文献汇报PPT, 组会PPT, journal club slides, paper presentation, or to explain a paper with PowerPoint, 尤其当论文只有整页 PNG/扫描件、或视觉 API 限流/昂贵时（先 OCR 后 vision 的降本流程）。
---

# CXY-journal-club-PPT+text — OCR-first 精确裁剪 Journal Club PPT

将科学论文（PDF 或整页 PNG/扫描件）转化为精确面板边界裁剪的组会汇报 PPT。
**本版相对 cxy-journal-club-ppt2 的核心升级：OCR-first 文本优先流水线**——
用 macOS 自带 Vision 框架（免费、本地、无 API 限流）先完成全部文字工作，
再把视觉模型（如 kimi-k3）的调用压缩到最少，在省 token 的同时保证图片质量。

适用场景：视觉 API 限流/超时/昂贵、论文只有整页 PNG 无文本层、需要批量处理。

## 硬约束（沿用 ppt2 + 新增）

1. **正文 20pt，标题 ≥22pt，全 slide 文字行距 1.5 倍；每页正文 ≤4 条要点。**
2. **Phase 0 必问汇报人姓名 + 汇报日期**，写入标题页与 slide 1 备注，不可占位符交付。
3. **精确 panel 边界复合裁剪**：≤6 panel 且 ≤2 行/图，1 slide=1 张复合图，命名与内容一致。
4. **只用论文主图**；不用 Supplementary/Extended Data/网络图/作者照片/logo/Graphical Abstract。
5. **先读论文再设计**：能陈述中心问题、知识缺口、假说、证据链、结论后才动手。
6. **含作者与背景介绍**，以 Strengths + Limitations + 讨论问题收尾。
7. **Result slide 备注 = 逐 panel 图示总结**（`Fig1A：…` 每行一条）。
8. **Slide ≤30**（含标题与讨论），超 30 才询问用户。
9. **OCR-first（新增硬约束）**：文本读取一律走免费 OCR + 廉价文本模型，
   视觉模型仅用于"看图"任务（panel bbox 定位、复合图 QC、渲染验收），不用于读文字。
10. **token 预算纪律（新增）**：视觉调用前先问"这个信息 OCR/聚类能不能拿到？"
    能则不用视觉；视觉定位用缩略图（≤1500px 宽）；QC 用拼图（contact sheet）批量检查。

## OCR-first 工作流总览

```
整页 PNG / PDF渲染页
  → [0] macOS Vision OCR（免费、本地、含像素坐标）→ ocr_text.txt
  → [1] 页眉页脚过滤 + 逻辑排序（从上到下、从左到右）→ clean_text.txt
  → [2] 廉价文本模型（如 deepseek）/ agent 提取 paper_logic + 关键数据
  → [3] OCR 文字坐标网格聚类 → panel 布局初判（grid_cluster）
  → [4] vision 只补缺口：panel bbox 精确定位（缩略图）+ 疑难区域确认
  → [5] numpy 精修 + whiteout/pre-whiteout 裁剪 → 复合图
  → [6] 程序化 QC（caption/页眉/截断）+ vision 拼图批量 QC
  → [7] deck outline + build_ppt → verify_ppt 终检 → 渲染验收
```

## Phase 0 — 汇报人元数据（最先执行）

先问用户 ① 汇报人姓名 ② 汇报日期；写入 `deck_outline.md` 元信息区与标题页
（`汇报人：XXX　|　汇报日期：YYYY年M月D日`）+ slide 1 备注。不可占位符交付。

## Phase 1 — OCR 文字提取（免费、本地、零 API）

### 1.1 整页 PNG 直接 OCR

用 `scripts/ocr_pages.py`（pyobjc 调用 macOS Vision 框架，本地运行）：
- 输入：整页 PNG 目录（如 2475×3150 扫描页）
- 输出：每页 `[x0,y0,x1,y1]\t文字` 逐条记录（**像素坐标**，左上角原点）
- 依赖：`pip install pyobjc-framework-Vision pyobjc-framework-Quartz`

### 1.2 PDF 先渲染再 OCR

若输入是 PDF：先用 PyMuPDF 渲染每页 200-300 DPI 整页 PNG
（`page.get_pixmap(dpi=250)`），再走 1.1。不要直接 OCR PDF。

### 1.3 页眉页脚过滤（黑名单模式）

对 OCR 输出按坐标 + 正则过滤非正文内容（本 skill 内置默认黑名单）：
- 期刊页眉/页眉：`RESEARCH ARTICLE`、期刊名（`Science`、`Cancer Cell` 等）、`Check for updates`
- 页脚：`Science 1 MAY 2025`、页码（`x of y`、孤立数字行）
- 水印：`Downloaded from`、下载机构（`Tsinghua University` 等）
- 版权/DOI 引用框、二维码标记
过滤规则见 `scripts/sort_text_by_layout.py` 的 `NOISE_PATTERNS`，按期刊调整。

### 1.4 逻辑排序（从上到下、从左到右）

用 `scripts/sort_text_by_layout.py`：
1. **行聚类**：按文字块 y 中心聚类成行（gap 阈值可调，默认 45px）
2. **行内排序**：同一行按 x 中心从左到右排序
3. **双栏期刊**：先按 x 中缝分成左右栏，栏内再自上而下（Science/NEJM 双栏版式）
输出 `clean_text.txt`：按阅读顺序排列的纯文本 + 坐标附件。

### 1.5 关键数据与逻辑提取（廉价文本模型协助）

- 将 `clean_text.txt` 交给**廉价文本模型**（如 deepseek 系列）或当前 agent 直接提炼：
  标题/作者/单位/DOI → 中心问题 → 知识缺口 → 假说 → 系统与数据 → 实验设计
  → 证据链（Result 1→N 映射 Figure）→ 结论 → 边界 → **关键数字清单**。
- 产出 `paper/paper_logic.md` + `paper/key_numbers.md`（供三方一致性核查）。
- 若环境有可调用的文本模型连接器（deepseek 等），优先用于这一步；否则 agent 自读。

## Phase 2 — 作者与背景（纯文本）

从 OCR 的标题/作者/单位/讨论部分提取；作者 slide 1 张、背景 1-2 张。
不要为作者/背景调用视觉模型。

## Phase 3 — figure_ledger（OCR 辅助盘点）

建立 `docs/figure_ledger.csv`，逐 panel 一行：
`figure_id, page, panel_id, panel_summary, composite_group, include, qc_status`。
- panel 位置初判来自 OCR 坐标聚类（Phase 4 的 grid_cluster 输出）
- panel_summary 来自 caption OCR（图注文字本身是文本！）
- **只用 caption/正文文本确定 panel 含义，不调用视觉**

## Phase 4 — panel 布局与裁剪（vision 只补缺口）

### 4.1 OCR 网格聚类（零视觉初判）

`scripts/grid_cluster.py`：对 figure 页做行聚类 + 每行列聚类，输出 panel 网格 bbox
初判 + 格子内文字摘要。**先跑它**——多数 panel 边界（尤其多列柱状图/散点图）
可从轴标签/图例文字的坐标直接推断，根本不需要视觉模型。

### 4.2 vision 精确定位（缩略图，省 token）

仅当聚类结果不够精确（如嵌套图、重叠 panel、通栏图）才调用视觉模型：
- **用缩略图**（≤1500px 宽，`PIL thumbnail`）而非原图，token 可省 60%+
- prompt 固定模板（`references/ocr-first-workflow.md` 提供）：要求 JSON 输出
  `panel字母 -> [x0,y0,x1,y1]`，并注明"左上角原点、宽高、含坐标轴/图例的外接矩形"
- 得到缩略图坐标后 × 缩放系数换算回整页坐标（±20px，后续 numpy 精修）

### 4.3 numpy 精修 + 裁剪（沿用 ppt2）

`scripts/crop_composite.py`（泛化自 crop_suyan.py）：
- bbox 四周留白 15px → numpy 暗像素扫描精修上下边界 → 额外留白
- **whiteout**（第 4 元素）：裁剪画布内坐标填白，处理 y 重叠 x 分离的相邻 panel
- **pre-whiteout**（第 5 元素）：整页坐标、**精修前**涂白，避免残留干扰边界精修
  （本次实战新增：Fig3_FG 顶部残留导致 refine 反复失败，pre-whiteout 一次解决）
- 统一扩展 20px 白边，输出 `figures/v3_final/Fig{N}_{panels}.png`

### 4.4 命名规范

`Fig1_AB.png`、`Fig2_CDE.png`：文件名 panel 字母 = 实际包含集合，QC 校验。

## Phase 5 — QC（程序化优先 + vision 拼图批量）

### 5.1 程序化 QC（零视觉，先做）

`scripts/qc_programmatic.py`：
- caption/页眉/水印检查（复用 NOISE_PATTERNS）
- 边缘截断检查（四边 6px 暗像素密度，仅提示不阻断）
- 裁剪区内 OCR 文字量检查（<3 条判异常）
- 图片存在性与尺寸检查

### 5.2 vision 拼图批量 QC（省 token 关键技巧）

**不要逐张调用视觉模型**。把 4-9 张复合图拼成 contact sheet
（PIL `Image.new` + `paste`，每张缩到 ~600px 宽，2-3 列网格），一次 `view_image`
检查多张，prompt 用统一清单（panel 完整、无页眉/caption、命名一致、无截断）。
- 通过项不再单独复查
- 失败项单独放大复查 → 修 → 重拼复检
- 典型节省：23 张图从 23 次调用降到 4-6 次拼图 + 若干次单查

### 5.3 QC 清单（沿用 ppt2 Phase 5）

panel 标签完整 / ≤6 panel 且 ≤2 行 / 命名一致 / 轴标签可读 / legend 完整 /
P 值完整 / scale bar 清晰 / 无截断 / 无页眉 / 无 caption / 无邻 panel 侵入。

## Phase 6-9 — 大纲、生成、终检、验收（沿用 ppt2）

- **Phase 6**：`deck_outline.md`（含汇报人/日期）+ 23 张复合图 → ≤30 slide
- **Phase 7**：`build_ppt.py` 生成（16:9、配色 #142D4F/#215F8F/#D9EAF5/#D48B2C/
  #555555/#8899AA、标题页深色+金色汇报行、Result 标题 `FigX:` 开头）
- **Phase 8**：`verify_ppt.py` 终检（slide≤30、字号、行距 1.5、备注逐 panel、图片嵌入）
- **Phase 9**：PowerPoint（AppleScript）导出 PDF → PyMuPDF 110DPI PNG → vision 抽查
  标题页（汇报人/日期）+ 代表性 Result slide + 文字页

## Phase 10 — 个性化讲稿生成（PPT 交付后自动产出）

讲稿是 Journal Club 交付物的一部分（汇报人逐页讲稿），**默认生成**，除非用户明确不要。
输出 `results/reports/journal_club_讲稿_<汇报人>.md`。

### 10.1 输入

- `deck_outline.md`（每页标题）+ `build_ppt.py` 的 RESULTS 备注（逐 panel 要点）
- `paper/paper_logic.md` + `paper/key_numbers.md`（数据来源，防编造）

### 10.2 每页格式（吸收用户定制规范）

```
### 第X页：[PPT标题]
**核心概念**：1 句话解释关键名词（面向不熟悉该领域的同学）
**讲稿**：自然口语段落（默认版 60-80 字/页；30 分钟版 140-170 字/页）
  = 自然过渡语 + 关键数据点 + 图表描述（有图时：横轴/纵轴/趋势）+ 方法贡献句
**提问引导**：以"大家思考一下…"或"这里值得留意的是…"收尾
```

### 10.3 附加要求（硬性）

1. **导师追问预案**：在相关页插入 `**【导师可能追问】**` 标记，格式
   "如果导师问xxx，回答是：yyy"（预判 8-15 处，覆盖模型/对照/统计/转化问题）。
2. **方法贡献句**：讲完方法后插入"这个方法的主要贡献在于…"（每篇 3-5 处）。
3. **数据高亮**：全文数字/单位/关键词/大写缩写/特殊符号加粗（markdown `**`）。
4. **三方一致性核查**：文末附表对照【文献原文 OCR】vs【PPT】vs【讲稿】，
   逐项核对关键数字与结论；发现偏差立即修正讲稿（OCR 误读按正文为准，
   存疑数值宁可不写，禁止编造原文没有的数据）。
5. **时长适配**：按用户指定时长选模板（10-15 分钟版 60-80 字/页、
   30 分钟版 140-170 字/页）；无指定默认 30 分钟版，并在文首标注预估时长。
6. 避免过于口语化的语气词，保持自然节奏；讲稿数据只来自 key_numbers/PPT，不编造。

### 10.4 模板

`references/script-template.md` 提供完整格式模板（含讲稿示例页与一致性核查表）。
生成时：按每页标题填核心概念句 + 讲稿 + 提问引导；数据从 key_numbers 转录；
图表描述根据该页复合图 panel 内容写（横轴/纵轴/趋势）。

## 交付物

- `paper/paper_logic.md` + `paper/key_numbers.md`（OCR 提取 + 文本模型提炼）
- `paper/ocr_text.txt` + `paper/clean_text.txt`（OCR 原文 + 排序后）
- `docs/deck_outline.md`、`docs/figure_ledger.csv`
- `figures/v3_final/`（复合图，全部过 QC）
- `ppt/journal_club_ppt_<name>.pptx`（≤30 slides）
- `results/reports/journal_club_讲稿_<汇报人>.md`（**个性化讲稿，默认生成**，
  含核心概念句/提问引导/【导师可能追问】预案/方法贡献句/数据高亮/三方一致性核查表）
- `scripts/`（可复现：ocr_pages / sort_text_by_layout / grid_cluster /
  crop_composite / qc_programmatic / build_ppt / verify_ppt）

## 自检清单（交付前）

- [ ] OCR 文本已过滤页眉页脚并按阅读顺序排序
- [ ] paper_logic + key_numbers 已产出（含关键数字清单）
- [ ] 视觉模型只用于看图任务；文本任务全部 OCR/文本模型完成
- [ ] 复合图 ≤6 panel/≤2 行、命名一致、全部过 QC
- [ ] Slide ≤30；标题页含汇报人/日期；备注逐 panel
- [ ] verify_ppt.py ALL PASS；渲染验收抽查通过
- [ ] 三方一致性核查（原文 OCR vs PPT vs 讲稿）关键数字无偏差
- [ ] **讲稿已生成**：每页含核心概念句 + 讲稿 + 提问引导；含【导师可能追问】预案
  与方法贡献句；数字/缩写已高亮；文末附三方一致性核查表

## 参考

- `references/ocr-first-workflow.md`：本次实战完整经验（OCR 排序细节、页眉黑名单、
  token 节省清单、vision prompt 模板、OCR 误读处理如 pM/μM、deepseek 协助提示词）
- 裁剪-QC 详细经验沿用 `cxy-journal-club-ppt2/references/cropping-qc.md`
