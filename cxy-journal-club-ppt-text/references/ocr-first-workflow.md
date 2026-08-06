# OCR-first 工作流实战经验手册（cxy-journal-club-ppt-text）

本文件沉淀自 SuYan Science（Science 388, eadp5540, 2025）Journal Club PPT 制作全过程：
**输入只有 13 张整页 PNG（2475×3150 扫描页，无 PDF 文本层）**，且会话期间视觉 API
长时间限流/超时——最终靠"OCR-first + 极少 vision"完成 23 张复合图全部过 QC、
30 页 PPT 交付。以下经验按流程顺序整理。

## 1. 为什么 OCR-first 值得做

| 对比 | macOS Vision OCR（pyobjc） | 视觉模型（kimi-k3 等） |
|---|---|---|
| 成本 | 免费、本地、无 API 限流 | 按 token 计费、可能限流/超时 |
| 文字提取 | 精确到像素坐标，可程序化过滤/排序 | 会吞细节、无稳定坐标 |
| 图表理解 | 不能 | 擅长 |
| 定位精度 | ±0px（但仅文字） | ±20px（bbox 需换算） |

**分工原则：一切"读文字"交给 OCR；视觉只做"看图"**（panel bbox 精定位、
复合图质量 QC、渲染验收）。本案例中 90% 的 panel 布局信息来自 OCR 文字坐标聚类，
视觉调用被压缩到 ~8 次（含拼图 QC）。

## 2. OCR 环境搭建（macOS）

```bash
pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz
# 验证
python3 -c "import Vision, Quartz; print('OK')"
```
- **不要用 `swift` 命令行编译**：本机 CommandLineTools 模块损坏会报大量
  swiftinterface 错误（实测踩坑），pyobjc 更稳。
- 输出格式必须含像素坐标：`[x0,y0,x1,y1]\t文字`，这是后续聚类/过滤的基础。

## 3. 页眉页脚过滤（黑名单实测）

SuYan Science 页面的噪声与对应正则：

| 噪声 | 正则（示例） |
|---|---|
| 期刊页眉 | `^RESEARCH ARTICLE$` |
| 页眉链接 | `^Check for updates$` |
| 页脚 | `^Science\s+\d+\s+MAY` / `^\d+\s+of\s+\d+$` |
| 下载水印 | `^Downloaded from` / `Tsinghua University` |
| DOI 引用框 | `^10\.\d{4}/` |

坐标辅助规则：`y0 < H*0.05 且高<45px 且短文本` → 页眉；`y0 > H*0.93 且纯数字` → 页码。
**不同期刊黑名单不同**（Cell 系是 CellPress logo + DOI 框；Nature 系有页眉刊名），
交付前跑 `noise_report.txt` 人工扫一眼，避免误删正文。

## 4. 逻辑排序（从上到下、从左到右）

- 行聚类：按文字块 y 中心，gap 默认 45px（Science 正文行距≈40px）
- 行内排序：同 row 按 x 中心升序
- **双栏检测**：右侧栏文字块数 >5 且占比 30%-75% → 报纸式（左栏自上而下→右栏）
- 输出带 `[x,y]` 前缀，便于回溯坐标

## 5. 用 OCR 坐标推断 panel 布局（零视觉核心）

`grid_cluster.py` 对 figure 页做 行聚类 + 每行列聚类，直接得到：
- panel 标签（A/B/C…）与轴标签/图例的格子 bbox
- 行/列数（判断 panel 网格结构）
- 每个格子内文字摘要（判断 panel 内容）

**实战验证**：Fig2（page6）4 行×3-4 列网格、Fig3（page7）的 PLS-DA/VIP 布局、
Fig5（page10）的组织分布图 E/F 分界，全部可由 OCR 坐标推断，vision 只做确认。

## 6. vision 调用省 token 清单（核心经验）

1. **缩略图定位**：定位 bbox 用 ≤1500px 宽缩略图（`PIL thumbnail`），
   换算回整页坐标再 numpy 精修。token 省 60%+。
2. **拼图 QC（contact_sheet）**：4-9 张复合图拼一张（每张 640px 宽、3 列），
   一次 `view_image` 检查多张。23 张图从 23 次调用 → 4-6 次。
3. **prompt 紧凑化**：定位 prompt 要求"JSON 输出 bbox"而非长描述；
   QC prompt 用"逐项简短回答"而非叙述。
4. **失败才放大**：拼图不过的项才单独放大复查，避免逐张高分辨率调用。
5. **不重复确认**：通过项不再回看；只有改过 bbox 的图才重检。
6. **OCR 能解决的绝不调视觉**：作者、背景、caption 含义、数据数字全是文本。

### vision 定位 prompt 模板

```
这是论文 Figure N 的高清渲染图，左上角为像素原点(0,0)，宽约 Wpx，高约 Hpx。
请逐一定位每个 panel 标签（A、B、…）所在 panel 的完整内容外接矩形
（含坐标轴/标题/图例），JSON 输出：键为 panel 字母，值为 [x0,y0,x1,y1]（±20px）。
若某 panel 内容超出画布边界，请说明。
```

### vision 拼图 QC prompt 模板

```
这是 N 张复合图拼成的 contact sheet（3 列，每张左上角有文件名标注）。
请逐张检查：1) panel 标签完整；2) 面板数 ≤6 且 ≤2 行；3) 命名与内容一致；
4) 无期刊页眉/caption 侵入；5) 无内容截断；6) 白色覆盖区域自然。
只报告有问题的文件名与具体问题，通过的图不必描述。
```

## 7. numpy 精修 + whiteout / pre-whiteout

- 精修：暗像素行扫描定内容上下界（阈值 <150，行暗像素 ≥3）
- **whiteout（裁剪后）**：处理"y 重叠 x 分离"的相邻 panel（如 Fig4 的 L 与 P）
- **pre-whiteout（裁剪前，本次新增）**：整页坐标、refine 之前涂白。
  实战场景：Fig3_FG 顶部有上一行（Fig3_DE）的 x 轴标签残片，
  refine 每次都把残片扫进来导致顶边界错误——pre-whiteout 一次解决。
- 残留定位技巧：对裁剪图做连通域分析（BFS 找 <500px 的暗簇），
  把碎片坐标换算回整页再加 whiteout。注意**别误删正常内容**
  （Fig4_IJK 曾把 I 面板设计图的竖线当残留误盖，靠放大复查发现）。

## 8. OCR 误读处理（关键数据核对）

| 现象 | 实例 | 处理 |
|---|---|---|
| µ 读成 p | IC50 "7.89 pM" → 正文 μM | 以正文为准，图注 OCR 不可信 |
| Kd 单位存疑 | "9.20 pM"（pM 太小不合理） | 讲稿不采用，标注存疑 |
| 数字串错误 | "1 300"、"1650=7.89" | 结合上下文修正 |
| 菌名/酶名乱码 | "Cerso*/fl" = Cers6^fl/fl | 用领域知识还原 |

**原则**：PPT/讲稿只写"正文 OCR 多页一致"或"合理可解释"的数字；
存疑数值宁可不写。交付前做三方核查（原文 OCR vs PPT vs 讲稿）。

## 9. deepseek（廉价文本模型）协助提示词

若环境提供文本模型连接器/可调 API，把 `clean_text.txt` 交给它：

```
你是生物医学论文分析助手。以下是 Science 论文的 OCR 清洗文本（按阅读顺序）。
请提取并输出 JSON：
{title, authors, corresponding, journal_year_doi, central_problem,
 knowledge_gap, hypothesis, system_data, design, evidence_chain:["R1:...","R2:..."],
 conclusion, boundaries, key_numbers:[{name, value, source_page}]}
不要编造 OCR 中没有的信息；数字仅转录。
```

之后由 agent 校验 key_numbers 与 PPT 一致性。无 deepseek 时 agent 自己完成同样提取。

## 10. 稳定性建议（限流/超时场景）

- 视觉 API 429 是滑动窗口限流：**每次失败后等待窗口重置再试**，不要密集重试
  （每次重试都会把 reset 时间推后）。
- 备选：先跑完整 OCR-first 流程（文本全免费），把视觉需求压缩到最少，
  等窗口恢复后一次性完成"定位确认 + 拼图 QC"。
- 长 sleep 用 `run_in_context` 提交（shell 工具 60s 超时会中断）。

## 11. 本次实战数据（供估算）

- 13 页 2475×3150 PNG：OCR 约 60 秒完成（本地），输出 ~1700 条文字
- panel 布局 90% 由 OCR 聚类推断；vision 共调用 ~8 次完成 23 图 QC
- 23 张复合图 20+ 轮裁剪修复（vision 逐张 QC 与 whiteout 迭代）
- 最终 30 页 PPT：verify_ppt ALL PASS，PowerPoint 渲染验收通过
