#!/usr/bin/env python3
"""Atomically assemble and validate one canonical Taiyi Shuji analysis."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from freeze_inputs import verify_input_lock


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = PROJECT_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from analysis_contract import validate_committed_analysis  # noqa: E402


ROLE_NAMES = {"r0", "r1", "r2", "red_team", "stage_c"}
ROLE_RESULT_FIELDS = ("text",)
GENERATED_FORMULA_ROLES = {"candidate", "formal_recommendation", "sandbox"}
TASK_TYPES = {
    "classic_interpretation",
    "formula_analysis",
    "case_reasoning",
    "followup",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_object(path: Path) -> dict[str, Any]:
    value = _load(path)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _load_array(path: Path, label: str) -> list[Any]:
    value = _load(path)
    if not isinstance(value, list):
        raise ValueError(f"{label} JSON root must be an array: {path}")
    return value


def _validate_fragments(
    *,
    sources: list[Any],
    outcome: dict[str, Any],
    calls: list[Any],
) -> None:
    result_id = outcome.get("result_id")
    if not isinstance(result_id, str) or not result_id:
        raise ValueError("outcome.result_id must be a non-empty string")
    for index, item in enumerate(sources):
        if not isinstance(item, dict):
            raise ValueError(f"sources[{index}] must be an object")
    if not all(isinstance(item, dict) for item in calls):
        raise ValueError("calls entries must be objects")


def _parse_role(argument: str) -> tuple[str, Path]:
    role, separator, raw_path = argument.partition("=")
    if not separator or role not in ROLE_NAMES or not raw_path:
        raise ValueError(
            "--role must use r0|r1|r2|red_team|stage_c=/absolute/path.json"
        )
    return role, Path(raw_path)


def _role_result(path: Path) -> dict[str, Any]:
    source = _load_object(path)
    if set(source) != {"text"}:
        raise ValueError(f"role result must contain only text: {path}")
    result = {
        field: source[field]
        for field in ROLE_RESULT_FIELDS
        if field in source
    }
    if not isinstance(result.get("text"), str) or not result["text"].strip():
        raise ValueError(f"role text is missing: {path}")
    return result


def _check_role_transport(
    roles: dict[str, dict[str, Any]],
) -> None:
    for role, result in roles.items():
        if "\ufffd" in result["text"]:
            raise ValueError(f"{role}.text contains replacement character")


def _validate_context_record(
    task_type: str,
    authoritative: dict[str, Any],
    context_record: dict[str, Any] | None,
) -> None:
    case_context = authoritative.get("case_context", {})
    if task_type == "followup":
        if context_record is None:
            raise ValueError("followup commit requires one frozen case snapshot")
        if (
            context_record.get("record_type") != "case_snapshot"
            or context_record.get("case_id") != case_context.get("case_id")
            or context_record.get("turn_id") != case_context.get("turn_id")
            or context_record.get("parent_turn_id")
            != case_context.get("parent_turn_id")
        ):
            raise ValueError(
                "case snapshot does not match case_id, turn_id, and parent_turn_id"
            )
        if context_record.get("parent_turn_id") == case_context.get("turn_id"):
            raise ValueError("followup requires a new turn_id")
        return
    if task_type == "formula_analysis" and context_record is not None:
        if (
            context_record.get("record_type") != "committed_analysis"
            or context_record.get("task_type") != "formula_analysis"
        ):
            raise ValueError("formula continuation context must be a committed formula analysis")
        return
    if context_record is not None:
        raise ValueError("formal context record is not allowed for this task")


def _write_atomic(path: Path, record: dict[str, Any]) -> None:
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
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative", required=True, type=Path)
    parser.add_argument("--input-lock", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-type", required=True, choices=sorted(TASK_TYPES))
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--calls", required=True, type=Path)
    parser.add_argument(
        "--context-record",
        type=Path,
        help="one frozen formula continuation or follow-up case snapshot",
    )
    parser.add_argument("--role", action="append", default=[])
    parser.add_argument("--conflicts", type=Path)
    parser.add_argument(
        "--generated-formulas",
        type=Path,
        help=(
            "JSON array of candidate, formal_recommendation, or sandbox formulas "
            "produced by this run"
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        authoritative = _load_object(arguments.authoritative)
        context_record = (
            _load_object(arguments.context_record)
            if arguments.context_record
            else None
        )
        verify_input_lock(
            arguments.input_lock,
            arguments.authoritative,
            arguments.context_record,
        )
        if set(authoritative) not in (
            {"input", "source_formulas"},
            {"input", "source_formulas", "case_context"},
        ):
            raise ValueError("authoritative snapshot shape is invalid")
        sources = _load_array(arguments.sources, "sources")
        outcome = _load_object(arguments.outcome)
        calls = _load_array(arguments.calls, "calls")
        _validate_context_record(
            arguments.task_type,
            authoritative,
            context_record,
        )
        _validate_fragments(
            sources=sources,
            outcome=outcome,
            calls=calls,
        )

        roles: dict[str, dict[str, Any]] = {}
        for raw_role in arguments.role:
            role, path = _parse_role(raw_role)
            if role in roles:
                raise ValueError(f"duplicate role: {role}")
            roles[role] = _role_result(path)
        _check_role_transport(roles)
        conflicts = _load(arguments.conflicts) if arguments.conflicts else []
        if not isinstance(conflicts, list):
            raise ValueError("conflicts JSON root must be an array")
        generated_formulas = (
            _load(arguments.generated_formulas)
            if arguments.generated_formulas
            else []
        )
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
        formula_ids = [
            formula.get("formula_id")
            for formula in [*authoritative["source_formulas"], *generated_formulas]
        ]
        if any(not isinstance(formula_id, str) or not formula_id for formula_id in formula_ids):
            raise ValueError("formula_id must be a non-empty string")
        if len(formula_ids) != len(set(formula_ids)):
            raise ValueError("duplicate formula_id across source and generated formulas")

        record = {
            "schema_version": "1.1",
            "record_type": "committed_analysis",
            "committed": True,
            "run_id": arguments.run_id,
            "task_type": arguments.task_type,
            "input": authoritative["input"],
            "sources": sources,
            "outcome": outcome,
            "calls": calls,
        }
        if "case_context" in authoritative:
            record["case_context"] = authoritative["case_context"]
        record["formulas"] = [
            *authoritative["source_formulas"],
            *generated_formulas,
        ]
        record["reasoning"] = {
            **roles,
            "unresolved_conflicts": conflicts,
        }
        errors = validate_committed_analysis(
            record,
            authoritative,
            workspace=PROJECT_ROOT,
            previous_record=(
                context_record
                if arguments.task_type == "formula_analysis"
                else None
            ),
        )
        if errors:
            raise ValueError("; ".join(errors))
        _write_atomic(arguments.output, record)
        print(f"PASS: committed {record['run_id']} to {arguments.output}")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
