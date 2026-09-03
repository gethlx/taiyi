#!/usr/bin/env python3
"""Exercise the reusable presentation projection contract across all task types."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/taiyi-shuji/scripts"))

from validate_presentation_projection import validate_projection  # noqa: E402
from validate_h5_view_model import validate_view_model  # noqa: E402


def make_record(task_type: str) -> dict[str, Any]:
    reasoning: dict[str, Any] = {
        "r0": {"text": "当前对象的最终关系判断。"},
        "unresolved_conflicts": [],
    }
    if task_type != "classic_interpretation":
        reasoning.update(
            {
                "r1": {"text": "与当前事实相连的最终辨证转译。"},
                "r2": {"text": "与当前判断相连的最终治疗方向。"},
                "red_team": {"text": "独立反向检验未发现改变主体结论的实质冲突。"},
            }
        )
    sources = (
        [
            {
                "work_id": "WORK-1",
                "title": "测试原文",
                "source_path": "kb/texts/test.md",
                "start_line": 1,
                "end_line": 1,
                "excerpt": "用于验证结构的短原文。",
            }
        ]
        if task_type == "classic_interpretation"
        else []
    )
    formulas: list[dict[str, Any]] = []
    day_progression: list[dict[str, Any]] = []
    if task_type == "formula_analysis":
        formulas = [
            {
                "formula_id": "FORMULA-1",
                "role": "input",
                "composition": [
                    {"raw_text": "甲药9g", "name": "甲药", "amount": 9, "unit": "g"},
                    {"raw_text": "乙药6g", "name": "乙药", "amount": 6, "unit": "g"},
                ],
                "preparation_text": "制备方式未提供。",
                "administration_text": "服用方式未提供。",
            }
        ]
        day_progression = [
            {
                "day": 1,
                "identity": "conditional_prediction",
                "text": "条件成立时观察正向变化与反向信号。",
            }
        ]
    record: dict[str, Any] = {
        "schema_version": "1.1",
        "record_type": "committed_analysis",
        "committed": True,
        "run_id": f"RUN-{task_type}",
        "task_type": task_type,
        "input": {
            "raw_text": "用于验证通用规则的中性输入。",
            "subject": {
                "subject_id": "SUBJECT-1",
                "kind": "classic" if task_type == "classic_interpretation" else "formula" if task_type == "formula_analysis" else "case",
                "label": "当前对象",
            },
            "confirmed_facts": ["已确认事实"],
            "ambiguous_facts": ["仍含混事实"],
            "scope": ["当前分析范围"],
        },
        "sources": sources,
        "outcome": {
            "result_id": f"RESULT-{task_type}",
            "identity": "classic_interpretation" if task_type == "classic_interpretation" else "conditional_r2",
            "summary": "当前正式结果摘要。",
            "risks": ["当前结果边界"],
            "minimum_questions": ["仍需补充的信息"],
            "day_progression": day_progression,
        },
        "calls": [],
        "formulas": formulas,
        "reasoning": reasoning,
    }
    if task_type in {"case_reasoning", "followup"}:
        record["case_context"] = {
            "case_id": "CASE-1",
            "turn_id": "TURN-2" if task_type == "followup" else "TURN-1",
            **({"parent_turn_id": "TURN-1"} if task_type == "followup" else {}),
        }
    return record


def make_projection(record: dict[str, Any]) -> dict[str, Any]:
    task_type = record["task_type"]
    projection: dict[str, Any] = {
        "schema_version": "1.0",
        "identity": {
            "run_id": record["run_id"],
            "result_id": record["outcome"]["result_id"],
            "task_type": task_type,
            "subject": copy.deepcopy(record["input"]["subject"]),
            "result_identity": record["outcome"]["identity"],
        },
        "report_header": {
            "primary_title": "当前对象分析报告",
            "scope_label": "当前范围",
            "brand_signature": "太乙枢机",
        },
        "reader_summary": {
            "key_message": "当前结果的患者向核心表达。",
            "key_relations": ["关系一", "关系二"],
            "current_concerns": ["当前关注点"],
            "pattern_explanation": "当前关系在成立范围内的清晰解释。",
        },
        "professional_judgment": {
            "r0_relation": {
                "title": "总体关系判断",
                "source_role": "r0",
                "original_excerpt": "当前对象的最终关系判断。",
                "plain_explanation": "面向读者的关系解释。",
            },
            "applicability_scope": "只在当前已知事实和边界内成立。",
        },
        "fact_base": {
            "confirmed_facts": [{"fact_id": "F-1", "text": "已确认事实", "source_indexes": [0]}],
            "ambiguous_facts": [{"fact_id": "A-1", "text": "仍含混事实", "source_indexes": [0]}],
            "missing_facts": [{"fact_id": "M-1", "text": "仍需补充的信息", "source_indexes": [0]}],
            "scope_items": [{"text": "当前分析范围", "source_indexes": [0]}],
        },
        "explanation_story": {
            "core_mechanism": "当前对象的关系核心。",
            "relationship_model": {
                "nodes": [
                    {"node_id": "N-1", "label": "关系一", "detail": "节点一", "status": "confirmed"},
                    {"node_id": "N-2", "label": "关系二", "detail": "节点二", "status": "conditional"},
                ],
                "edges": [{"from": "N-1", "to": "N-2", "kind": "conditional"}],
            },
            "causal_chain": [],
            "supporting_conditions": ["支持条件"],
            "contrary_conditions": ["反向条件"],
        },
        "boundaries": {
            "risks": [{"text": "当前结果边界", "source_indexes": [0]}],
            "minimum_questions": [{"text": "仍需补充的信息", "source_indexes": [0]}],
            "unresolved_conflicts": [],
        },
        "sources": copy.deepcopy(record["sources"]),
        "audit_receipt": {
            "performed": task_type != "classic_interpretation",
            "resolution": "not_performed" if task_type == "classic_interpretation" else "retained",
            "public_summary": "" if task_type == "classic_interpretation" else "独立反向检验后主体结论保留。",
        },
    }
    if task_type != "classic_interpretation":
        projection["professional_judgment"]["r1_pattern"] = {
            "title": "辨证结论",
            "source_role": "r1",
            "original_excerpt": "与当前事实相连的最终辨证转译。",
            "plain_explanation": "面向患者的辨证解释。",
        }
        projection["treatment_story"] = {
            "center_label": "治疗主轴",
            "goals": [{"title": "治疗方向", "detail": "对应当前判断的治疗目标。"}],
            "strategy": "围绕当前主轴安排治疗层次。",
            "why_it_matches": "治疗方向与当前最终判断相连。",
        }
    if task_type == "classic_interpretation":
        projection["classic_story"] = {
            "interpretation_focus": "解释当前原文的关系含义。",
            "source_passages": [
                {"source_index": 0, "excerpt": record["sources"][0]["excerpt"], "explanation": "说明原文的关系边界。"}
            ],
            "concepts": [{"title": "核心概念", "explanation": "概念层级说明。"}],
            "relationships": [],
        }
    if task_type == "formula_analysis":
        projection["formula_story"] = {
            "formulas": copy.deepcopy(record["formulas"]),
            "center_label": "方义主轴",
            "responsibility_groups": [
                {
                    "group_id": "G-1",
                    "title": "方药职责",
                    "detail": "覆盖当前方剂全部组成。",
                    "formula_id": "FORMULA-1",
                    "composition_indexes": [0, 1],
                }
            ],
            "collaboration": "各组成围绕当前方义协同。",
            "execution_unknowns": ["现实执行方式仍待确认。"],
        }
        projection["observation_story"] = {
            "premise": "只在正式前提成立时观察。",
            "progression": [
                {
                    "source_day_index": 0,
                    "stage": "第 1 日",
                    "identity": "conditional_prediction",
                    "positive": "正向变化",
                    "contrary": "反向信号",
                }
            ],
            "reassessment_trigger": "出现反向信号时重新核对。",
        }
    if task_type == "followup":
        projection["followup_story"] = {
            "case_id": record["case_context"]["case_id"],
            "turn_id": record["case_context"]["turn_id"],
            "parent_turn_id": record["case_context"]["parent_turn_id"],
            "comparison_summary": "本轮事实与上一轮的对照摘要。",
            "observed_changes": [{"text": "已确认事实", "status": "unchanged", "source_indexes": [0]}],
            "retained_judgment": "本轮仍保留的判断。",
            "current_adjustment": "本轮依据事实形成的调整。",
        }
    return projection


def expect_rejected(projection: dict[str, Any], record: dict[str, Any], label: str, errors: list[str]) -> None:
    try:
        validate_projection(projection, record)
    except ValueError:
        return
    errors.append(f"validator accepted {label}")


def make_h5_model(record: dict[str, Any], projection: dict[str, Any], digest: str) -> dict[str, Any]:
    relationship = projection["explanation_story"]["relationship_model"]
    indexes = {node["node_id"]: index for index, node in enumerate(relationship["nodes"])}
    formula_story = projection["formula_story"]
    source_formula = formula_story["formulas"][0]
    return {
        "schemaVersion": "1.0",
        "identity": {
            "runId": projection["identity"]["run_id"],
            "resultId": projection["identity"]["result_id"],
            "taskType": projection["identity"]["task_type"],
            "resultIdentity": projection["identity"]["result_identity"],
            "projectionSchemaVersion": projection["schema_version"],
            "projectionSha256": digest,
        },
        "header": {
            "title": projection["report_header"]["primary_title"],
            "scopeLabel": projection["report_header"]["scope_label"],
            "brandSignature": projection["report_header"]["brand_signature"],
            "heroVisual": "/assets/current-hero.webp",
            "heroAlt": "当前报告主题背景",
            "flow": projection["reader_summary"]["key_relations"],
            "linkKinds": ["conditional"],
        },
        "overview": {
            "summary": projection["reader_summary"]["key_message"],
            "nodes": [{"label": node["label"], "detail": node["detail"]} for node in relationship["nodes"]],
            "links": [
                {"from": indexes[edge["from"]], "to": indexes[edge["to"]], "kind": edge["kind"]}
                for edge in relationship["edges"]
            ],
        },
        "facts": {
            "confirmed": [item["text"] for item in projection["fact_base"]["confirmed_facts"]],
            "unknown": [
                item["text"]
                for key in ("ambiguous_facts", "missing_facts")
                for item in projection["fact_base"][key]
            ],
        },
        "professional": {
            "r0Excerpt": projection["professional_judgment"]["r0_relation"]["original_excerpt"],
            "r0Explanation": projection["professional_judgment"]["r0_relation"]["plain_explanation"],
            "r1Label": projection["professional_judgment"]["r1_pattern"]["title"],
            "r1Excerpt": projection["professional_judgment"]["r1_pattern"]["original_excerpt"],
            "r1Explanation": projection["professional_judgment"]["r1_pattern"]["plain_explanation"],
            "scope": projection["professional_judgment"]["applicability_scope"],
        },
        "mechanism": {"steps": []},
        "treatment": {
            "centerLabel": projection["treatment_story"]["center_label"],
            "items": [
                {"title": goal["title"], "detail": goal["detail"]}
                for goal in projection["treatment_story"]["goals"]
            ],
        },
        "formula": {
            "lead": formula_story["collaboration"],
            "centerLabel": formula_story["center_label"],
            "groups": [
                {"title": group["title"], "detail": group["detail"]}
                for group in formula_story["responsibility_groups"]
            ],
            "ingredients": [item["raw_text"] for item in source_formula["composition"]],
            "executionFacts": [
                source_formula["preparation_text"],
                source_formula["administration_text"],
                *formula_story["execution_unknowns"],
            ],
        },
        "observation": {
            "premise": projection["observation_story"]["premise"],
            "stages": [
                {"label": item["stage"], "positive": item["positive"], "contrary": item["contrary"]}
                for item in projection["observation_story"]["progression"]
            ],
        },
        "boundaries": {
            "supported": [item["text"] for item in projection["boundaries"]["risks"]],
            "questions": [item["text"] for item in projection["boundaries"]["minimum_questions"]],
            "auditTitle": "结论已经过独立复核",
            "auditSummary": projection["audit_receipt"]["public_summary"],
        },
    }


def main() -> int:
    errors: list[str] = []
    pairs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for task_type in ("classic_interpretation", "formula_analysis", "case_reasoning", "followup"):
        record = make_record(task_type)
        projection = make_projection(record)
        pairs[task_type] = (record, projection)
        try:
            validate_projection(projection, record)
        except ValueError as exc:
            errors.append(f"valid {task_type} projection was rejected: {exc}")

    formula_record, formula_projection = pairs["formula_analysis"]
    bad_title = copy.deepcopy(formula_projection)
    bad_title["report_header"]["primary_title"] = "这张方子如何起效？"
    expect_rejected(bad_title, formula_record, "question-form report title", errors)

    changed_formula = copy.deepcopy(formula_projection)
    changed_formula["formula_story"]["formulas"][0]["composition"][0]["raw_text"] = "甲药12g"
    expect_rejected(changed_formula, formula_record, "drifted formula composition", errors)

    missing_fact = copy.deepcopy(formula_projection)
    missing_fact["fact_base"]["confirmed_facts"] = []
    expect_rejected(missing_fact, formula_record, "unmapped confirmed fact", errors)

    corrected_record = copy.deepcopy(formula_record)
    corrected_record["reasoning"]["stage_c"] = {"text": "综合反向检验后的最终修正。"}
    corrected_projection = copy.deepcopy(formula_projection)
    corrected_projection["audit_receipt"]["resolution"] = "corrected"
    try:
        validate_projection(corrected_projection, corrected_record)
    except ValueError as exc:
        errors.append(f"valid Stage C receipt was rejected: {exc}")

    stale_receipt = copy.deepcopy(corrected_projection)
    stale_receipt["audit_receipt"]["resolution"] = "retained"
    expect_rejected(stale_receipt, corrected_record, "stale red-team receipt after Stage C", errors)

    digest = "a" * 64
    h5_model = make_h5_model(formula_record, formula_projection, digest)
    try:
        validate_view_model(h5_model, formula_record, formula_projection, digest)
    except ValueError as exc:
        errors.append(f"valid projection-bound H5 view model was rejected: {exc}")
    drifted_h5 = copy.deepcopy(h5_model)
    drifted_h5["overview"]["summary"] = "只在页面代码中修改过的另一版结论。"
    try:
        validate_view_model(drifted_h5, formula_record, formula_projection, digest)
    except ValueError:
        pass
    else:
        errors.append("H5 validator accepted copy drift outside the presentation projection")

    if errors:
        print("FAILED: reusable presentation projection", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: presentation projection generalizes across classic, formula, case, and followup tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
