# 个人病历、激活与单沙盘

本文件服务个人病历的事实写入、同案激活、复察快照和一个写时复制沙盘。只读、
新增或纠正病历时不运行医学主链。

## 病历内容

每个病例只有一份结构化 `patient_record`。每轮保存：

- 用户原话和当前可用事实的完整快照；
- 含混事实；
- 用户主动提供但不进入中医角色的 `external_context`；
- 只作历史意见的 `clinician_opinions`；
- 实际方、治疗反应和明确更正；
- 正式分析链接，以及审计后最终 R0／R1 纵向摘要。

完整角色正文不复制进病历。已绑定正式结果的轮次不可原地改事实；后续纠正另建
新 `turn_id` 并指向上一轮。模型或提交失败时事实可以保留，但不产生分析绑定。

## 病历命令

新建、查看和追加本轮事实：

```bash
python3 -B scripts/case_record.py init \
  --record /absolute/path/to/patient-record.json \
  --case-id CASE-ID --label "病例标签"
python3 -B scripts/case_record.py show \
  --record /absolute/path/to/patient-record.json
python3 -B scripts/case_record.py append-visit \
  --record /absolute/path/to/patient-record.json \
  --visit /absolute/path/to/visit.json
```

`visit.json` 至少含 `turn_id`、`raw_text`、`confirmed_facts`、
`ambiguous_facts`。非首轮必须用 `parent_turn_id` 指向同案紧邻上一轮；实际方使用
`actual_formulas`，角色固定为 `input`。事实列表由宿主依据本轮对话形成，脚本不
用关键词抽取或补造。

最新且尚未绑定分析的轮次可以原子更正。完整替换文件必须保持同一 turn/parent，
保留旧 `corrections` 并追加一条更正说明：

```bash
python3 -B scripts/case_record.py correct-visit \
  --record /absolute/path/to/patient-record.json \
  --visit /absolute/path/to/corrected-visit.json
```

正式分析完成后，宿主在同一上下文形成 `final-evolution.json`，只含
`r0_summary`、`r1_summary`、可选 `comparison_to_previous` 和
`unresolved_boundaries`。绑定前脚本核对病历事实与权威输入、case/turn、
run/result 及正式分析有效性：

```bash
python3 -B scripts/case_record.py bind-analysis \
  --record /absolute/path/to/patient-record.json \
  --turn-id TURN-ID \
  --analysis /absolute/path/to/analysis.json \
  --authoritative /absolute/path/to/authoritative.json \
  --evolution /absolute/path/to/final-evolution.json
```

复察进入 R0 前，从当前未绑定轮次及其已绑定父轮生成一次有限快照：

```bash
python3 -B scripts/case_record.py snapshot \
  --record /absolute/path/to/patient-record.json \
  --turn-id CURRENT-TURN-ID \
  --output /absolute/path/to/case-snapshot.json
```

## 激活状态

状态文件只登记病历路径、当前活动病例和一个沙盘，不复制轮次与分析文件：

```bash
python3 -B scripts/case_state.py init --state /absolute/path/to/state.json
python3 -B scripts/case_state.py register \
  --state /absolute/path/to/state.json \
  --record /absolute/path/to/patient-record.json --activate
python3 -B scripts/case_state.py activate \
  --state /absolute/path/to/state.json --case-id CASE-ID
python3 -B scripts/case_state.py context --state /absolute/path/to/state.json
```

病例切换必须由用户明确提出；工具不按症状、方名或相似度猜病例。

## 单沙盘

沙盘只复制指定正式记录中的方剂，不改变病历。宿主根据用户明确指令形成完整
`sandbox` 方对象，再由工具逐值保存；Python 不理解改方指令或补药：

```bash
python3 -B scripts/case_state.py sandbox-create \
  --state /absolute/path/to/state.json \
  --record /absolute/path/to/analysis.json \
  --authoritative /absolute/path/to/authoritative.json \
  --formula-id FORMULA-ID
python3 -B scripts/case_state.py sandbox-update \
  --state /absolute/path/to/state.json \
  --formula-json /absolute/path/to/sandbox-formula.json
python3 -B scripts/case_state.py sandbox-clear \
  --state /absolute/path/to/state.json
```

全局同时只有一个沙盘。新建沙盘替换旧沙盘，但不覆盖来源记录、病历或正式方。
