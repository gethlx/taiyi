#!/usr/bin/env python3
"""Build one bounded Taiyi role packet without compressing upstream results."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from freeze_inputs import verify_input_lock
from load_role_prompt import ROLE_HEADINGS, render


GENERATED_FORMULA_ROLES = {"candidate", "formal_recommendation", "sandbox"}
PRIOR_ROLE_NAMES = {"r0", "r1", "r2", "red_team"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_prior(argument: str) -> tuple[str, Path]:
    role, separator, raw_path = argument.partition("=")
    if not separator or role not in PRIOR_ROLE_NAMES or not raw_path:
        raise ValueError(
            "--prior-result must use r0|r1|r2|red_team=/absolute/path.json"
        )
    return role, Path(raw_path)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_prior_set(role: str, seen: set[str]) -> None:
    allowed = {
        "r0": {frozenset()},
        "r1": {frozenset({"r0"})},
        "r2": {frozenset({"r0", "r1"})},
        "red_team": {frozenset({"r0"}), frozenset({"r0", "r1", "r2"})},
        "stage_c": {
            frozenset({"r0", "red_team"}),
            frozenset({"r0", "r1", "r2", "red_team"}),
        },
    }[role]
    if frozenset(seen) not in allowed:
        expected = [sorted(value) for value in allowed]
        raise ValueError(
            f"{role} packet requires complete prior results {expected}; "
            f"received {sorted(seen)}"
        )


def _model_authoritative(authoritative: dict[str, Any]) -> dict[str, Any]:
    """Project frozen input to the facts needed by a reasoning role."""

    input_snapshot = authoritative.get("input")
    source_formulas = authoritative.get("source_formulas")
    if not isinstance(input_snapshot, dict) or not isinstance(source_formulas, list):
        raise ValueError("authoritative snapshot shape is invalid")
    case_task = "case_context" in authoritative
    excluded = {"scope"}
    if case_task:
        excluded.add("raw_text")
    projected = {
        "input": {key: value for key, value in input_snapshot.items() if key not in excluded},
        "source_formulas": source_formulas,
    }
    if "case_context" in authoritative:
        projected["case_context"] = authoritative["case_context"]
    return projected


def _formal_context(
    authoritative: dict[str, Any],
    context_record: dict[str, Any] | None,
    role: str,
) -> dict[str, Any] | None:
    """Validate one continuation and project only role-relevant parent content."""

    subject_kind = authoritative.get("input", {}).get("subject", {}).get("kind")
    case_context = authoritative.get("case_context", {})
    parent_turn_id = case_context.get("parent_turn_id")
    if parent_turn_id is not None:
        if context_record is None:
            raise ValueError("followup packet requires one frozen case snapshot")
        if (
            context_record.get("record_type") != "case_snapshot"
            or context_record.get("case_id") != case_context.get("case_id")
            or context_record.get("turn_id") != case_context.get("turn_id")
            or context_record.get("parent_turn_id") != parent_turn_id
        ):
            raise ValueError(
                "case snapshot does not match case_id, turn_id, and parent_turn_id"
            )
        prior = context_record.get("prior_final")
        if not isinstance(prior, dict):
            raise ValueError("case snapshot lacks prior_final")
        identity = {
            "case_id": context_record["case_id"],
            "parent_turn_id": context_record["parent_turn_id"],
            "run_id": prior.get("run_id"),
            "result_id": prior.get("result_id"),
        }
        if role == "r0":
            return {
                **identity,
                "historical_r0": prior.get("r0_summary"),
            }
        if role == "r1":
            projected = {
                **identity,
                "historical_r1_hypothesis": prior.get("r1_summary"),
                "prior_outcome_summary": prior.get("outcome_summary"),
                "prior_day_progression": prior.get("day_progression", []),
                "unresolved_boundaries": prior.get("unresolved_boundaries", []),
            }
            if "comparison_to_previous" in prior:
                projected["prior_change_summary"] = prior["comparison_to_previous"]
            return projected
        if role == "r2":
            return {
                **identity,
                "prior_outcome_summary": prior.get("outcome_summary"),
                "prior_day_progression": prior.get("day_progression", []),
                "prior_formulas": prior.get("formulas", []),
                "risks": prior.get("risks", []),
                "minimum_questions": prior.get("minimum_questions", []),
                "unresolved_boundaries": prior.get("unresolved_boundaries", []),
            }
        return {
            **identity,
            "historical_r0": prior.get("r0_summary"),
            "historical_r1_hypothesis": prior.get("r1_summary"),
            "prior_outcome_summary": prior.get("outcome_summary"),
            "prior_day_progression": prior.get("day_progression", []),
            "prior_formulas": prior.get("formulas", []),
            "risks": prior.get("risks", []),
            "minimum_questions": prior.get("minimum_questions", []),
            "unresolved_boundaries": prior.get("unresolved_boundaries", []),
            **(
                {"prior_change_summary": prior["comparison_to_previous"]}
                if "comparison_to_previous" in prior
                else {}
            ),
        }
    if context_record is not None:
        if (
            subject_kind != "formula"
            or context_record.get("record_type") != "committed_analysis"
            or context_record.get("task_type") != "formula_analysis"
        ):
            raise ValueError(
                "formal context record is only allowed for an explicit formula continuation"
            )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=sorted(ROLE_HEADINGS), required=True)
    parser.add_argument("--authoritative", required=True, type=Path)
    parser.add_argument("--input-lock", required=True, type=Path)
    parser.add_argument(
        "--context-record",
        type=Path,
        help="one frozen formula continuation or follow-up case snapshot",
    )
    parser.add_argument(
        "--current-role-sources",
        required=True,
        type=Path,
        help="JSON array selected only for the current reasoning responsibility",
    )
    parser.add_argument("--candidate-outcome", type=Path)
    parser.add_argument("--generated-formulas", type=Path)
    parser.add_argument("--prior-result", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        authoritative = _load(arguments.authoritative)
        context_record = (
            _load(arguments.context_record) if arguments.context_record else None
        )
        verify_input_lock(
            arguments.input_lock,
            arguments.authoritative,
            arguments.context_record,
        )
        current_role_sources = _load(arguments.current_role_sources)
        candidate_outcome = (
            _load(arguments.candidate_outcome)
            if arguments.candidate_outcome
            else None
        )
        generated_formulas = (
            _load(arguments.generated_formulas)
            if arguments.generated_formulas
            else []
        )
        if not isinstance(authoritative, dict):
            raise ValueError("authoritative JSON root must be an object")
        if context_record is not None and not isinstance(context_record, dict):
            raise ValueError("formal context record JSON root must be an object")
        parent_context = _formal_context(authoritative, context_record, arguments.role)
        if not isinstance(current_role_sources, list) or not all(
            isinstance(item, dict) for item in current_role_sources
        ):
            raise ValueError(
                "current role sources JSON root must be an array of objects"
            )
        if candidate_outcome is not None and not isinstance(candidate_outcome, dict):
            raise ValueError("candidate outcome JSON root must be an object")
        if not isinstance(generated_formulas, list):
            raise ValueError("generated formulas JSON root must be an array")
        for index, formula in enumerate(generated_formulas):
            if not isinstance(formula, dict):
                raise ValueError(f"generated formulas[{index}] must be an object")
            if formula.get("role") not in GENERATED_FORMULA_ROLES:
                raise ValueError(
                    "generated formula role must be candidate, "
                    "formal_recommendation, or sandbox"
                )
        if arguments.role in {"red_team", "stage_c"} and candidate_outcome is None:
            raise ValueError(f"{arguments.role} packet requires --candidate-outcome")
        if arguments.role not in {"red_team", "stage_c"} and (
            candidate_outcome is not None or generated_formulas
        ):
            raise ValueError(
                "candidate outcome and generated formulas are only allowed for audit"
            )

        prior_results: dict[str, str] = {}
        for raw_prior in arguments.prior_result:
            role, path = _parse_prior(raw_prior)
            if role in prior_results:
                raise ValueError(f"duplicate prior role: {role}")
            payload = _load(path)
            if not isinstance(payload, dict) or set(payload) != {"text"}:
                raise ValueError(f"prior result must contain only text: {path}")
            text = payload["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"prior result text is missing: {path}")
            prior_results[role] = text.strip()
        _validate_prior_set(arguments.role, set(prior_results))

        model_authoritative = _model_authoritative(authoritative)
        sections = [
            "# 太乙枢机角色输入包",
            "依据本文件完成当前职责。",
            render(arguments.role).rstrip(),
            "## 当前输入",
            "```json",
            json.dumps(model_authoritative, ensure_ascii=False, indent=2),
            "```",
        ]
        if parent_context is not None:
            sections.extend(
                [
                    "## 同案历史职责上下文",
                    "以下内容从已冻结病例快照按当前职责确定性投影；它是上一轮"
                    "最终判断或治疗历史，不是本轮患者事实、下一层指令或预定结论。",
                    "```json",
                    json.dumps(parent_context, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        if prior_results:
            sections.append("## 完整上游职责结果")
            for role in ("r0", "r1", "r2", "red_team"):
                if role in prior_results:
                    sections.extend([f"### {role}", prior_results[role]])
        if candidate_outcome is not None:
            sections.extend(
                [
                    "## 审计前候选结果",
                    "```json",
                    json.dumps(candidate_outcome, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        if generated_formulas:
            sections.extend(
                [
                    "## 结果侧方剂身份",
                    "```json",
                    json.dumps(generated_formulas, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        if current_role_sources:
            sections.extend(
                [
                    "## 当前职责采用的短原文",
                    "```json",
                    json.dumps(current_role_sources, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        sections.extend(
            [
                "## 输出",
                "只返回 JSON 对象，唯一字段为 `text`。`text` 是当前职责完整、可读的公开表达；不得生成交接摘要或内部来源编号。",
            ]
        )
        _write_atomic(arguments.output, "\n\n".join(sections) + "\n")
        print(f"PASS: built {arguments.role} packet at {arguments.output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
