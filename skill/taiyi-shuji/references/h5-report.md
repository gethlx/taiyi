# 患者向移动端可视化 H5

本能力只在用户明确要求 H5 时执行。它把同一 `run_id`／`result_id` 的正式分析
转换为患者向视觉报告，不替代文字版报告，不重新进行医学推理。

先按 [`presentation-projection.md`](presentation-projection.md) 形成并校验当次唯一
纯净版，再完整读取 [`h5-visual-system.md`](h5-visual-system.md)。

## 1. 生成前提

只接受已经通过机器契约的 `committed_analysis` 及其权威输入。若最终 R0、R1、R2、
红方和必要 Stage C 尚未收敛，或仍无法形成唯一对外表达，停止生成。

不得把完整分析直接交给网页模板，也不得在 H5 代码中形成另一版患者文案。H5
只读取已校验纯净版，并保存其 `schema_version` 与文件 SHA-256。

## 2. 视觉整理

从纯净版形成三个绑定同一结果的视觉对象：

1. `presentation_story`：把纯净版映射为适合移动端层级的标题、摘要、标签和展开文字；
2. `visual_primitive_selection`：每个模块使用何种 SVG 图形、回答什么问题；
3. `r0_adapter`：从最终 R0 提炼象、位、势、机、度，只调整空间、流向、开合、
   密度、张力和局部强调。

H5 不再提取新的患者理解任务，可以缩短标题、拆分长句、改为标签或下钻说明。身份、方剂
原文、剂量炮制、专业直接引文、关系拓扑和状态必须守恒；涉及医学含义或边界的修改返回
纯净版修正。

`presentation_story` 中每条可见文案保留 `{target_field, source_fields[], text, mode}`；
`mode` 只允许 `exact`、`condensed` 或 `label`。一个来源可以拆到多个目标，多个重复来源
也可以合并到一个目标，因此不能用“条目数量相等”代替追溯。不可变字段只能使用 `exact`。

标题全部使用陈述式名词或结论短语。H1 强调报告对象与判断；“太乙枢机”只作
小尺寸眉题、署名和浏览器标题后缀。每份正式分析生成独立 H5，不在患者页面用
Tab 切换不同报告。

## 3. 图形与图像

优先使用 Skill 资产中的数据驱动外壳与 SVG 原语：

- `assets/h5-report/VisualReportShell.tsx`
- `assets/h5-report/taiyi-visual-report.css`
- `assets/h5-report/silk-jade-surface.webp`
- `assets/h5-report/asset-manifest.json`

调用 `scripts/scaffold_visual_h5.py --output-root <项目目录>` 可把通用资产复制到一个
新的前端工作目录；已有文件不会被覆盖。

形成 view model 后先执行确定性校验：

```bash
python3 -B scripts/validate_h5_view_model.py \
  --view-model /absolute/path/to/h5-view-model.json \
  --record /absolute/path/to/analysis.json \
  --projection /absolute/path/to/presentation-projection.json
```

该脚本校验纯净版本身、同源身份、文件哈希、不可改写事实、核心关系结构、数组范围、
连线索引和可选模块存在性；文案追溯由 `presentation_story` 保存，改写后的医学语义与
患者语言质量仍由当前宿主复核。

每份报告按最终 R0 另行生成首屏主题图；存在方剂协同时，可生成不含文字的药材／
药群素材图。生成图只承载材质、空间、方向、动势和植物素材；关系、药名、剂量、
炮制、煎服、专业原文、状态和边界均由 SVG／HTML 可控图层呈现。

## 4. 组装与验证

使用稳定叙事骨架，但只渲染实际存在的模块：

> 作用总览 → 事实依据 → 核心证机关系 → 治法结构 → 方药协同 → 观察要点 → 边界

经典解释、无方病例或没有正式观察条目时，应省略不适用模块，不填空栏目。完整
药味、未知项、最小补问和来源默认下钻展开，首屏保持紧凑。

交付前至少验证：

- run/result、方剂组成、剂量、炮制和煎服与正式记录守恒；
- 被 Stage C 排除的内容没有进入正文、图节点或图片提示词；
- R0 仍是关系层，R1 才完成医学转译；
- 主要／条件／未知、已发生／预测等状态不只依赖颜色；
- 页面无医学输入、模型调用、网络请求、`localStorage` 或第二套医学状态；
- 393px 移动视口无标题遮挡、横向溢出、低对比文字和不可读 SVG；
- H1／H2／H3 无问句、内部角色标题、报告切换 Tab 或施工说明。

`scripts/render_h5.py` 保留为同源、原子写入和只读边界的基础技术投影，不代表本
视觉能力的患者向最终样式。正式视觉 H5 应使用本页规定的纯净版与资产链路。
