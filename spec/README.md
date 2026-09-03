# 太乙枢机规范目录

本目录保存公开运行所需的角色提示、机器契约、Schema 和确定性测试数据。它不
保存典籍正文，也不把 Schema 当作中医推理器。

## 主要文件

- [`THEORY_PROMPTS.md`](THEORY_PROMPTS.md)：共同、R0、R1、R2、红方与 Stage C 指令。
- [`MACHINE_CONTRACT.md`](MACHINE_CONTRACT.md)：正式分析与失败信封的承载范围。
- [`analysis.schema.json`](analysis.schema.json)：`committed_analysis / run_failure 1.1`。
- [`analysis_examples.json`](analysis_examples.json)：四类任务、失败信封和硬边界变异。
- [`PATIENT_RECORD.md`](PATIENT_RECORD.md)：个人病历的事实层、解释层和写入顺序。
- [`case_record.schema.json`](case_record.schema.json)：`patient_record / case_snapshot 1.0`。
- [`RETRIEVAL.md`](RETRIEVAL.md)：证据定位、选择、回读与模型可见边界。
- [`evidence.schema.json`](evidence.schema.json)：证据服务内部请求与结果契约。
- [`retrieval_cards.json`](retrieval_cards.json)：候选路由与调用权卡，不含典籍正文。
- [`retrieval_tests.json`](retrieval_tests.json)：检索夹具、探针和契约变异。

## 机器边界

机器契约负责验证用户原话、主对象、显式组成、病例与轮次身份、方剂角色、来源
锚点、冲突和结果绑定。它不判断阴阳、病机、方义、药性、治法或答案是否唯一。

病例完整原话、用户主动提供的体系外信息和医者历史意见可以留档，但不会自动
进入中医角色上下文。复察只从明确父轮生成一次有限 `case_snapshot`，再按 R0、
R1、R2 和红方职责裁剪。

公开仓库随附 Skill 必需的处理后典籍知识库。`kb/manifest.json`、其登记正文或
结构化资产缺失、被替换或哈希不符时，完整校验失败，直接来源回读不会跳过。
典籍目录约定见 [`../kb/README.md`](../kb/README.md)。
