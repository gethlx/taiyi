# 对外展示纯净版标准

本文件规定如何为任一当前正式结果生成媒介中立的 `presentation_projection`。
H5、纯图片套图及后续视觉作品只能从该工件派生，不得各自重新整理完整分析。

纯净版已经决定患者需要理解什么、信息主次、阅读顺序和语义基线。H5 和纯图片共用同一
份专业判断、患者解释、关系、治法、方药、观察和边界；下游不再提取新的“患者理解任务”，
但可以按媒介压缩、拆分、标签化和调整文字层级，不得补充第二套医学内容。

## 目录

1. 权威性与边界
2. 固定生成顺序
3. 来源优先级
4. 通用字段契约
5. 四类任务适配
6. 患者向文案标准
7. 关系语义标准
8. 红方与 Stage C
9. 工件与下游绑定
10. 验收

## 1. 权威性与边界

纯净版只接受当次通过机器契约的 `committed_analysis` 和同一权威输入。它是同一
`run_id`／`result_id` 的对外表达投影，不创建新的医学结果、病例状态或方剂身份。

每个案例都从当次正式记录重新生成。不得把历史纯净版、旧 H5 数据、旧图片提示词、
样例药群、固定证机链或视觉主题作为新案例的内容来源。历史作品只能帮助验证规则
是否泛化。

纯净版负责回答“最终要向患者或读者表达什么”，不包含网页、图片或排版方案。
以下内容不得进入纯净版：

- 红方攻击全文、审计前候选、被 Stage C 排除的结论；
- R0／R1／R2 的工作过程、角色说明、调用状态和施工说明；
- “H5 中展示”“本模块”“布局测试”“建议图形”“图片使用”等媒介指令；
- 页面高度、折叠、Tab、SVG、画幅、动效、配色、材质或生图提示词；
- 为填满栏目而补造的症状、病位、因果、药群、观察、经典关系或身体定位。

媒介中立不等于信息未整理。纯净版必须已经形成可直接交给 H5 和纯图片生成器的完整患者
表达；若下游仍需补足医学解释、重新决定结论主次或另造摘要内容，说明纯净版尚未完成。
仅为适应标题长度、卡片层级、图注、节点标签或画幅而进行的媒介改写属于下游职责。

允许的媒介适配包括：缩短陈述式标题、把长句拆成节点或图注、合并重复解释、改为列表和
标签、调整同一模块内的呈现顺序。不得改写的内容包括：身份、方剂原文、药味顺序、剂量、
炮制煎服、专业直接引文、来源、关系拓扑和状态类型。任何适配都不得新增症状、病位、因果、
药性、疗效、人体落点或服用许可，也不得删去会改变成立范围的条件、未知、风险和退出信号。

## 2. 固定生成顺序

1. 校验 committed analysis 与权威输入，冻结 run/result、任务、主对象和结果身份。
2. 读取当次权威事实、最终 R0／R1／R2、红方、必要 Stage C、outcome、方剂与来源。
3. 先吸收 Stage C 的保留、修改、排除和未解项，形成唯一可公开语义。
4. 将输入事实、风险、补问、观察和方剂建立可追溯映射，不先写标题或摘要。
5. 选择仍然成立的 R0／R1 专业原句；受 Stage C 修改时只引用修正后仍成立的原句，
   或直接引用 Stage C 的最终关系句并标明来源角色。
6. 按当前任务形成患者／读者顺序，不照搬 R0→R1→R2 章节。
7. 形成陈述式标题、核心消息、患者解释、关系语义和可选任务模块。
8. 运行确定性校验，再进行语义复核；两者均通过后才允许生成 H5 或图片。

## 3. 来源优先级

发生冲突时按以下顺序处理：

1. **权威输入**：主对象、确认／含混事实、方剂组成、炮制、煎服和病例时间身份；
2. **Stage C**：存在时决定哪些主体语义保留、修改、排除或仍未解决；
3. **最终 outcome**：结果身份、最终摘要、风险、最小补问和正式观察条目；
4. **最终 R0／R1／R2**：只取未被 Stage C 修改或排除的专业判断与解释依据；
5. **红方**：只决定公开回执和需要保留的边界，不直接成为患者主叙事；
6. **sources**：只保留正式记录实际采用的短原文与出处。

不得用 outcome 摘要反向覆盖权威输入，也不得因 R0／R1／R2 中仍保留旧句而恢复
Stage C 已排除的内容。

## 4. 通用字段契约

规范工件为 UTF-8 JSON，字段名固定使用 snake_case：

```text
presentation_projection
├── schema_version                固定 1.0
├── identity
│   ├── run_id
│   ├── result_id
│   ├── task_type
│   ├── subject                   与正式记录完全相同
│   └── result_identity
├── report_header
│   ├── primary_title             陈述式内容标题
│   ├── scope_label               病例／方剂／复察／经典范围
│   └── brand_signature           太乙枢机，仅作署名
├── reader_summary
│   ├── key_message               一句话核心结论
│   ├── key_relations[]           2—4 个首要关系短语
│   ├── current_concerns[]
│   ├── pattern_explanation
│   ├── treatment_strategy?
│   ├── formula_summary?
│   └── observation_summary?
├── professional_judgment
│   ├── r0_relation
│   │   ├── title
│   │   ├── source_role           r0 或 stage_c
│   │   ├── original_excerpt      正式记录中的连续原句
│   │   └── plain_explanation
│   ├── r1_pattern?
│   │   ├── title
│   │   ├── source_role           r1 或 stage_c
│   │   ├── original_excerpt
│   │   └── plain_explanation
│   └── applicability_scope
├── fact_base
│   ├── confirmed_facts[]         {fact_id, text, source_indexes[]}
│   ├── ambiguous_facts[]         {fact_id, text, source_indexes[]}
│   ├── missing_facts[]           {fact_id, text, source_indexes[]}，映射 minimum_questions
│   └── scope_items[]             {text, source_indexes[]}
├── explanation_story
│   ├── core_mechanism
│   ├── relationship_model
│   │   ├── nodes[]               {node_id, label, detail, status}
│   │   └── edges[]               {from, to, kind, label?}
│   ├── causal_chain[]            {label, detail, status}；无可靠顺序时为空
│   ├── supporting_conditions[]
│   └── contrary_conditions[]
├── treatment_story?
│   ├── center_label
│   ├── goals[]                   {title, detail, role?}
│   ├── strategy
│   └── why_it_matches
├── formula_story?
│   ├── formulas[]                从正式记录逐字段复制
│   ├── center_label
│   ├── responsibility_groups[]   {group_id, title, detail, formula_id, composition_indexes[]}
│   ├── collaboration
│   └── execution_unknowns[]
├── observation_story?
│   ├── premise
│   ├── progression[]             {source_day_index, stage, identity, positive, contrary}
│   └── reassessment_trigger
├── classic_story?                仅经典解释
│   ├── interpretation_focus
│   ├── source_passages[]         {source_index, excerpt, explanation}
│   ├── concepts[]                {title, explanation}
│   └── relationships[]           {from, to, relation, boundary}
├── followup_story?               仅同案复察
│   ├── case_id
│   ├── turn_id
│   ├── parent_turn_id
│   ├── comparison_summary
│   ├── observed_changes[]        {text, status, source_indexes[]}
│   ├── retained_judgment
│   └── current_adjustment
├── boundaries
│   ├── risks[]                   {text, source_indexes[]}
│   ├── minimum_questions[]       {text, source_indexes[]}
│   └── unresolved_conflicts[]    {text, source_indexes[]}
├── sources[]                     与正式记录采用来源完全相同
└── audit_receipt
    ├── performed
    ├── resolution                not_performed／retained／corrected／unresolved
    └── public_summary
```

`source_indexes` 使用对应正式数组的零基索引；`missing_facts` 映射 outcome 的
`minimum_questions`，其余字段映射同名正式数组。允许一条患者文案合并多个来源
项，但所有正式确认事实、含混事实、scope、风险、最小补问和未解冲突都必须至少
被映射一次。映射只提供追溯，不能用代码判断患者化改写是否语义正确。

`formulas[]` 必须逐项复制正式记录的完整方剂数组，不得筛除或改写组成。
职责群使用 `formula_id + composition_indexes` 指向药味，不复制一套可能漂移的药名。

### 模块存在条件

| 正式记录状态 | 纯净版要求 |
|---|---|
| 任意任务 | identity、header、summary、R0、fact_base、explanation、boundaries、sources、audit 必须存在 |
| 存在最终 R1 | `r1_pattern` 必须存在；没有 R1 时禁止补造 |
| 存在最终 R2 | `treatment_story` 必须存在；没有 R2 时禁止补造 |
| `formulas` 非空 | `formula_story` 必须存在并完整复制全部方剂；为空时禁止生成 |
| `day_progression` 非空 | `observation_story` 必须逐条覆盖；为空时禁止生成 |
| classic_interpretation | 专项字段只生成 `classic_story`，不得生成 `followup_story` |
| followup | 专项字段只生成 `followup_story`，并绑定正式 case/turn/parent identity |

“必须存在”不等于套用固定结论。字段内容仍由当次正式结果决定；不适用的可选模块
必须省略，而不是写“暂无”来占位。

## 5. 四类任务适配

### classic_interpretation

- 主标题命名原文、概念或关系问题，不患者化为病因；
- 使用 `classic_story` 保存原文问题、概念层级和跨书关系；
- R1、治法、方药和观察没有正式内容时全部省略。

### formula_analysis

- 标题命名方剂对象、方义主轴或结构与适用条件；
- 方剂对象、组成、剂量、炮制、煎服和身份必须完整保留；正式输入若同时含有明确的
  上下文事实，也必须进入 fact_base，并保留其条件性用途，不得因“纯方剂”标签删去；
- R1 明确标为条件性方证／证机，不写现实患者诊断；
- 不生成“您的症状”“您的病因”、身体病位或已发生疗效；
- Day 条目保留正式共同前提和条件预测身份。

### case_reasoning

- 标题围绕已确认主诉与当前判断，不把条件写成确诊；
- 已确认症状、舌脉、病程与实施事实进入 fact_base；
- R0→R1 关系必须与事实相连，治法和方药只取最终 R2；
- 没有正式方剂或观察时省略相应模块。

### followup

- `followup_story` 区分上一轮判断、本轮已发生变化和本轮新判断；
- 已发生变化与未来观察不得混写；预测只能进入 observation_story；
- 方药差异只记录真实保留、调整、增减或替换；
- 守、调、转、辨的方向必须来自本轮最终结论，不为版式补齐。

## 6. 患者向文案标准

- `report_header.primary_title` 使用“患者所见对象＋整体判断／处置方向／观察范围”的
  陈述式命名，不使用问句，不堆叠 R0／R1 术语；
- `professional_judgment.r0_relation.title` 与 `r1_pattern.title` 保留专业判断的正式命名，
  不因患者化而删除；H5 模块标题和纯图片页标题另用 `label` 做患者向适配，专业标题进入
  正文层。专业标题本身已经清楚易懂时才可直接复用；
- 患者向页面或模块标题命名“这一页告诉患者什么”，不写“关系如何形成”“治法落在哪里”
  等教学问句，也不写“R0 总体判断”“R1 辨证分型”“条件性四轴”等内部章节名；
- 模块内容使用结论、事实、证机、治法、方药、观察和边界语言，不使用教学提问；
- 太乙枢机只进入 `brand_signature`，不抢占主标题；
- `original_excerpt` 保留必要专业术语，`plain_explanation` 再使用患者语言解释；
- 避免“系统认为、模型发现、经过多轮修复、我们将展示”等过程性叙述；
- 每段只表达一个患者理解任务，删除重复摘要和同义路标；
- 条件、未知、未解和结果身份不能为了简洁而消失；
- 不使用认证、批准服用、保证疗效、概率、评分或未经正式结果支持的轻重判断。

标题、摘要和解释的语义复核必须由当前宿主完成。正则、词表或长度阈值只能发现
表面问题，不能替代患者语言、医学边界或 Stage C 吸收判断。

## 7. 关系语义标准

`relationship_model` 是媒介中立语义，不保存坐标、颜色、图形或构图：

- `status` 使用 `confirmed`、`conditional` 或 `unknown`；
- `kind` 使用 `primary`、`conditional` 或 `unknown`；
- 节点和边只取最终公开语义，不能从药名或关键词自动推断；
- 因果顺序明确时才填写 `causal_chain`；否则使用相互影响、并列或开放关系；
- R0 的五行、卦象和开阖升降只保存实际成立的关系，不固定映射脏腑或颜色；
- R1 才保存与事实相连的医学转译；纯方剂不得借节点制造患者病位；
- 没有量化数据时不生成比例、概率、严重度或疗效趋势语义。

H5 和图片可以用不同画法表达同一模型，但不得改变节点、边、状态和成立范围。

## 8. 红方与 Stage C

- 未执行红方：`performed=false`、`resolution=not_performed`，下游不显示回执；
- 红方无实质冲突：`resolution=retained`，公开说明独立反向检验后主体结论保留；
- Stage C 已收敛：`resolution=corrected`，公开说明已经综合修正，正文只给修正后结果；
- 仍有未解项：`resolution=unresolved`，未解项必须进入 boundaries。

公开回执说明检验状态，不代表安全认证、医师审核或服用批准。

## 9. 工件与下游绑定

每次明确请求 H5 或图片时，在当前 run 目录形成唯一规范文件：

```text
presentation/presentation-projection.json
```

先运行：

```bash
python3 -B scripts/validate_presentation_projection.py \
  --projection /absolute/path/to/presentation-projection.json \
  --record /absolute/path/to/analysis.json
```

校验通过后，H5 view model 或图片计划必须保存 `projection_schema_version` 和该 JSON
文件的 SHA-256。下游不得直接读取完整 analysis 补内容。媒介适配只能从纯净版字段形成；
若要改变医学含义、事实、主次关系或边界，先更新纯净版并重新校验，再重新生成下游作品。

下游可以按照画幅和信息量把一个模块拆成多页，或把语义连续的模块合并为一页；这种
编排只能引用纯净版现有字段，不生成新的患者任务或医学关系。同一字段进入 H5 与纯图片
时语义、事实和状态保持一致，表层文字可以因媒介不同而压缩或标签化。

## 10. 验收

### 确定性检查

- run/result、任务、主对象和结果身份同源；
- fact_base 的来源索引合法并覆盖正式输入数组；
- 方剂对象、组成顺序、raw_text、剂量、炮制、煎服完全守恒；
- 专业原句真实存在于声明的最终角色正文中；
- 关系节点 ID 唯一、边引用有效、状态值固定；
- 观察条目覆盖 outcome 的正式 progression，实况与预测身份不混；
- 风险、补问、未解冲突和 sources 完整映射；
- 红方／Stage C 回执状态与正式记录一致。

### 语义复核

- Stage C 的修改、排除和未解项已被吸收；
- 标题、摘要、模块内容均为面向患者／读者的正式报告语言；
- 无施工说明、内部角色过程、旧候选或媒介方案；
- 专业原文、患者解释、关系语义和成立范围互不冲突；
- `reader_summary`、专业判断及各 story 已共同完成患者理解任务，下游无需补造医学内容；
- 同一纯净版可直接供 H5 与纯图片使用，表层文案可以适配，但结论、事实、关系、状态与
  边界不会不同；
- 纯方剂、病例、复察和经典没有互相借用不适用模块；
- 换成不同 R0、无方病例、无五行卦象或经典解释时仍可按本标准生成。

确定性校验通过不等于语义复核完成。只有两者都完成，纯净版才可供 H5 或图片使用。
