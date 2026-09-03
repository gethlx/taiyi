#!/usr/bin/env python3
"""Maintain one minimal Taiyi patient record and frozen follow-up snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "spec" / "case_record.schema.json"


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _schema() -> dict[str, Any]:
    return load_object(SCHEMA_PATH)


def _validate_definition(value: dict[str, Any], definition: str) -> None:
    schema = _schema()
    validator = Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        }
    )
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
    if errors:
        rendered = []
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "root"
            rendered.append(f"{location}: {error.message}")
        raise ValueError(f"{definition} validation failed: " + "; ".join(rendered))


def validate_patient_record(record: dict[str, Any]) -> None:
    _validate_definition(record, "PatientRecord")
    seen: set[str] = set()
    previous_turn_id: str | None = None
    for visit in record["visits"]:
        turn_id = visit["turn_id"]
        if turn_id in seen:
            raise ValueError(f"duplicate turn_id: {turn_id}")
        seen.add(turn_id)
        parent_turn_id = visit.get("parent_turn_id")
        if previous_turn_id is None:
            if parent_turn_id is not None:
                raise ValueError("first visit must not have parent_turn_id")
        elif parent_turn_id != previous_turn_id:
            raise ValueError("each later visit must name the immediately previous turn")
        previous_turn_id = turn_id


def validate_case_snapshot(snapshot: dict[str, Any]) -> None:
    _validate_definition(snapshot, "CaseSnapshot")
    if snapshot["turn_id"] == snapshot["parent_turn_id"]:
        raise ValueError("case snapshot requires a new turn_id")


def _atomic_json(path: Path, value: dict[str, Any], *, kind: str) -> None:
    if kind == "record":
        validate_patient_record(value)
    elif kind == "snapshot":
        validate_case_snapshot(value)
    else:
        raise ValueError(f"unknown atomic JSON kind: {kind}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_name = handle.name
        os.replace(temporary_name, path)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _visit(record: dict[str, Any], turn_id: str) -> dict[str, Any]:
    for visit in record["visits"]:
        if visit["turn_id"] == turn_id:
            return visit
    raise ValueError(f"turn does not exist: {turn_id}")


def _relative_to_record(record_path: Path, target: Path) -> str:
    return os.path.relpath(target.resolve(), record_path.parent.resolve())


def _resolve_from_record(record_path: Path, stored: str) -> Path:
    path = Path(stored)
    if path.is_absolute():
        return path
    return (record_path.parent / path).resolve()


def _validate_committed_analysis(
    analysis: dict[str, Any], authoritative: dict[str, Any]
) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.analysis_contract import validate_committed_analysis

    errors = validate_committed_analysis(
        analysis,
        authoritative,
        workspace=ROOT,
    )
    if errors:
        raise ValueError("analysis validation failed: " + "; ".join(errors))


def cmd_init(args: argparse.Namespace) -> None:
    if args.record.exists():
        existing = load_object(args.record)
        validate_patient_record(existing)
        if existing["case_id"] != args.case_id or existing["label"] != args.label:
            raise ValueError("existing patient record identity differs")
        print(f"PASS: patient record already valid at {args.record}")
        return
    record = {
        "schema_version": "1.0",
        "record_type": "patient_record",
        "case_id": args.case_id,
        "label": args.label,
        "visits": [],
    }
    _atomic_json(args.record, record, kind="record")
    print(f"PASS: initialized patient record {args.case_id}")


def cmd_show(args: argparse.Namespace) -> None:
    record = load_object(args.record)
    validate_patient_record(record)
    print(json.dumps(record, ensure_ascii=False, indent=2))


def cmd_append_visit(args: argparse.Namespace) -> None:
    record = load_object(args.record)
    validate_patient_record(record)
    visit = load_object(args.visit)
    if "analysis_binding" in visit:
        raise ValueError("a new visit cannot arrive with an analysis binding")
    turn_ids = {item["turn_id"] for item in record["visits"]}
    if visit.get("turn_id") in turn_ids:
        raise ValueError(f"turn already exists: {visit.get('turn_id')}")
    updated = json.loads(json.dumps(record, ensure_ascii=False))
    updated["visits"].append(visit)
    _atomic_json(args.record, updated, kind="record")
    print(f"PASS: appended {record['case_id']}/{visit['turn_id']}")


def cmd_correct_visit(args: argparse.Namespace) -> None:
    record = load_object(args.record)
    validate_patient_record(record)
    replacement = load_object(args.visit)
    if not record["visits"]:
        raise ValueError("patient record has no visit to correct")
    current = record["visits"][-1]
    if current["turn_id"] != replacement.get("turn_id"):
        raise ValueError("only the latest visit can be corrected in place")
    if "analysis_binding" in current:
        raise ValueError("a bound visit is immutable; append a correction turn instead")
    if replacement.get("parent_turn_id") != current.get("parent_turn_id"):
        raise ValueError("correction cannot change parent_turn_id")
    if "analysis_binding" in replacement:
        raise ValueError("correction cannot add an analysis binding")
    old_notes = current.get("corrections", [])
    new_notes = replacement.get("corrections", [])
    if new_notes[: len(old_notes)] != old_notes or len(new_notes) <= len(old_notes):
        raise ValueError("correction must preserve prior notes and append one new note")
    updated = json.loads(json.dumps(record, ensure_ascii=False))
    updated["visits"][-1] = replacement
    _atomic_json(args.record, updated, kind="record")
    print(f"PASS: corrected unbound visit {record['case_id']}/{current['turn_id']}")


def cmd_bind_analysis(args: argparse.Namespace) -> None:
    record = load_object(args.record)
    validate_patient_record(record)
    visit = _visit(record, args.turn_id)
    analysis = load_object(args.analysis)
    authoritative = load_object(args.authoritative)
    evolution = load_object(args.evolution)
    _validate_definition(evolution, "FinalEvolution")
    _validate_committed_analysis(analysis, authoritative)
    context = analysis.get("case_context", {})
    if analysis.get("task_type") not in {"case_reasoning", "followup"}:
        raise ValueError("only case or follow-up analysis can bind to a patient record")
    if context.get("case_id") != record["case_id"] or context.get("turn_id") != args.turn_id:
        raise ValueError("analysis case_id or turn_id differs from the patient record")
    if visit.get("parent_turn_id") != context.get("parent_turn_id"):
        raise ValueError("analysis parent_turn_id differs from the patient record")
    analysis_input = analysis.get("input", {})
    if (
        analysis_input.get("raw_text") != visit.get("raw_text")
        or analysis_input.get("confirmed_facts") != visit.get("confirmed_facts")
        or analysis_input.get("ambiguous_facts") != visit.get("ambiguous_facts")
    ):
        raise ValueError("analysis facts differ from the patient record visit")
    if not isinstance(analysis.get("reasoning", {}).get("red_team"), dict):
        raise ValueError("case analysis lacks the required red-team result")

    actual_formulas = visit.get("actual_formulas", [])
    analysis_inputs = [
        formula for formula in analysis.get("formulas", []) if formula.get("role") == "input"
    ]
    if actual_formulas:
        indexed = {formula.get("formula_id"): formula for formula in analysis_inputs}
        for formula in actual_formulas:
            if indexed.get(formula["formula_id"]) != formula:
                raise ValueError("visit actual formula differs from the committed input formula")

    binding = {
        "run_id": analysis["run_id"],
        "result_id": analysis["outcome"]["result_id"],
        "outcome_identity": analysis["outcome"]["identity"],
        "analysis_file": _relative_to_record(args.record, args.analysis),
        "final_evolution": evolution,
    }
    if "analysis_binding" in visit:
        if visit["analysis_binding"] == binding:
            print(f"PASS: analysis already bound to {record['case_id']}/{args.turn_id}")
            return
        raise ValueError("visit is already bound to a different formal result")
    updated = json.loads(json.dumps(record, ensure_ascii=False))
    _visit(updated, args.turn_id)["analysis_binding"] = binding
    _atomic_json(args.record, updated, kind="record")
    print(f"PASS: bound {analysis['run_id']} to {record['case_id']}/{args.turn_id}")


def cmd_snapshot(args: argparse.Namespace) -> None:
    record = load_object(args.record)
    validate_patient_record(record)
    current = _visit(record, args.turn_id)
    parent_turn_id = current.get("parent_turn_id")
    if parent_turn_id is None:
        raise ValueError("initial visit has no follow-up parent snapshot")
    parent = _visit(record, parent_turn_id)
    binding = parent.get("analysis_binding")
    if not isinstance(binding, dict):
        raise ValueError("parent visit has no committed analysis binding")
    analysis_path = _resolve_from_record(args.record, binding["analysis_file"])
    analysis = load_object(analysis_path)
    context = analysis.get("case_context", {})
    outcome = analysis.get("outcome", {})
    if (
        analysis.get("record_type") != "committed_analysis"
        or analysis.get("committed") is not True
        or context.get("case_id") != record["case_id"]
        or context.get("turn_id") != parent_turn_id
        or analysis.get("run_id") != binding["run_id"]
        or outcome.get("result_id") != binding["result_id"]
    ):
        raise ValueError("bound parent analysis identity differs")
    result_formula_id = outcome.get("result_formula_id")
    formulas = [
        formula
        for formula in analysis.get("formulas", [])
        if formula.get("role") == "input"
        or (
            formula.get("role") == "formal_recommendation"
            and formula.get("formula_id") == result_formula_id
        )
    ]
    final_evolution = binding["final_evolution"]
    prior_final = {
        "run_id": binding["run_id"],
        "result_id": binding["result_id"],
        "outcome_identity": binding["outcome_identity"],
        "outcome_summary": outcome["summary"],
        "day_progression": outcome.get("day_progression", []),
        "risks": outcome.get("risks", []),
        "minimum_questions": outcome.get("minimum_questions", []),
        "unresolved_boundaries": final_evolution["unresolved_boundaries"],
        "r0_summary": final_evolution["r0_summary"],
        "r1_summary": final_evolution["r1_summary"],
        "formulas": formulas,
    }
    if "comparison_to_previous" in final_evolution:
        prior_final["comparison_to_previous"] = final_evolution[
            "comparison_to_previous"
        ]
    snapshot = {
        "schema_version": "1.0",
        "record_type": "case_snapshot",
        "case_id": record["case_id"],
        "turn_id": args.turn_id,
        "parent_turn_id": parent_turn_id,
        "prior_final": prior_final,
    }
    _atomic_json(args.output, snapshot, kind="snapshot")
    print(f"PASS: wrote case snapshot for {record['case_id']}/{args.turn_id}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    command = sub.add_parser("init")
    command.add_argument("--record", required=True, type=Path)
    command.add_argument("--case-id", required=True)
    command.add_argument("--label", required=True)
    command.set_defaults(handler=cmd_init)

    command = sub.add_parser("show")
    command.add_argument("--record", required=True, type=Path)
    command.set_defaults(handler=cmd_show)

    for name, handler in (
        ("append-visit", cmd_append_visit),
        ("correct-visit", cmd_correct_visit),
    ):
        command = sub.add_parser(name)
        command.add_argument("--record", required=True, type=Path)
        command.add_argument("--visit", required=True, type=Path)
        command.set_defaults(handler=handler)

    command = sub.add_parser("bind-analysis")
    command.add_argument("--record", required=True, type=Path)
    command.add_argument("--turn-id", required=True)
    command.add_argument("--analysis", required=True, type=Path)
    command.add_argument("--authoritative", required=True, type=Path)
    command.add_argument("--evolution", required=True, type=Path)
    command.set_defaults(handler=cmd_bind_analysis)

    command = sub.add_parser("snapshot")
    command.add_argument("--record", required=True, type=Path)
    command.add_argument("--turn-id", required=True)
    command.add_argument("--output", required=True, type=Path)
    command.set_defaults(handler=cmd_snapshot)
    return root


def main() -> int:
    args = parser().parse_args()
    args.record = args.record.resolve()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
