#!/usr/bin/env python3
"""Register and activate patient records plus one copy-on-write formula sandbox."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from case_record import load_object, validate_patient_record


ROOT = Path(__file__).resolve().parents[3]
STATE_VERSION = "2.0"


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_VERSION,
        "active_case_id": None,
        "cases": {},
        "sandbox": None,
    }


def validate_state(state: dict[str, Any]) -> None:
    if set(state) != {"schema_version", "active_case_id", "cases", "sandbox"}:
        raise ValueError("state shape is invalid")
    if state["schema_version"] != STATE_VERSION:
        raise ValueError("state schema_version differs")
    if not isinstance(state["cases"], dict):
        raise ValueError("state cases must be an object")
    active = state["active_case_id"]
    if active is not None and active not in state["cases"]:
        raise ValueError("active case does not exist")
    for case_id, case in state["cases"].items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("case id is invalid")
        if not isinstance(case, dict) or set(case) != {"label", "record_file"}:
            raise ValueError(f"case {case_id} shape is invalid")
        if not isinstance(case["label"], str) or not case["label"]:
            raise ValueError(f"case {case_id} label is invalid")
        if not isinstance(case["record_file"], str) or not case["record_file"]:
            raise ValueError(f"case {case_id} record file is invalid")
    sandbox = state["sandbox"]
    if sandbox is not None:
        required = {
            "sandbox_id",
            "source_run_id",
            "source_result_id",
            "source_formula",
            "formula",
            "revision",
        }
        if not isinstance(sandbox, dict) or set(sandbox) != required:
            raise ValueError("sandbox shape is invalid")
        if sandbox["formula"].get("role") != "sandbox":
            raise ValueError("sandbox formula role differs")
        if sandbox["formula"].get("formula_id") != sandbox["sandbox_id"]:
            raise ValueError("sandbox formula id differs")
        if not isinstance(sandbox["revision"], int) or sandbox["revision"] < 0:
            raise ValueError("sandbox revision is invalid")


def load_state(path: Path) -> dict[str, Any]:
    state = load_object(path)
    validate_state(state)
    return state


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    validate_state(value)
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


def validate_committed_record(
    record: dict[str, Any], authoritative: dict[str, Any]
) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.analysis_contract import validate_committed_analysis

    errors = validate_committed_analysis(record, authoritative, workspace=ROOT)
    if errors:
        raise ValueError("record validation failed: " + "; ".join(errors))


def validate_formula(formula: dict[str, Any]) -> None:
    allowed = {
        "formula_id",
        "role",
        "name",
        "composition",
        "preparation_text",
        "administration_text",
    }
    if set(formula) - allowed or not {"formula_id", "role", "composition"}.issubset(
        formula
    ):
        raise ValueError("formula shape is invalid")
    if formula["role"] != "sandbox":
        raise ValueError("updated formula must use sandbox role")
    if not isinstance(formula["formula_id"], str) or not formula["formula_id"]:
        raise ValueError("sandbox formula_id is invalid")
    if not isinstance(formula["composition"], list):
        raise ValueError("sandbox composition is invalid")
    ingredient_allowed = {"raw_text", "name", "amount", "unit", "preparation"}
    for item in formula["composition"]:
        if (
            not isinstance(item, dict)
            or set(item) - ingredient_allowed
            or not {"raw_text", "name"}.issubset(item)
            or not isinstance(item["raw_text"], str)
            or not item["raw_text"]
            or not isinstance(item["name"], str)
            or not item["name"]
        ):
            raise ValueError("sandbox ingredient is invalid")


def _relative_to_state(state_path: Path, target: Path) -> str:
    return os.path.relpath(target.resolve(), state_path.parent.resolve())


def _record_path(state_path: Path, entry: dict[str, Any]) -> Path:
    stored = Path(entry["record_file"])
    if stored.is_absolute():
        return stored
    return (state_path.parent / stored).resolve()


def cmd_init(args: argparse.Namespace) -> None:
    if args.state.exists():
        validate_state(load_state(args.state))
        print(f"PASS: state already valid at {args.state}")
        return
    atomic_json(args.state, empty_state())
    print(f"PASS: initialized {args.state}")


def cmd_show(args: argparse.Namespace) -> None:
    print(json.dumps(load_state(args.state), ensure_ascii=False, indent=2))


def cmd_register(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    record = load_object(args.record)
    validate_patient_record(record)
    case_id = record["case_id"]
    entry = {
        "label": record["label"],
        "record_file": _relative_to_state(args.state, args.record),
    }
    existing = state["cases"].get(case_id)
    if existing is not None and existing != entry:
        raise ValueError("case id is already registered to another patient record")
    state["cases"][case_id] = entry
    if args.activate:
        state["active_case_id"] = case_id
    atomic_json(args.state, state)
    print(f"PASS: registered patient record {case_id}")


def cmd_activate(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    if args.case_id not in state["cases"]:
        raise ValueError(f"case does not exist: {args.case_id}")
    state["active_case_id"] = args.case_id
    atomic_json(args.state, state)
    print(f"PASS: activated {args.case_id}")


def cmd_context(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    case_id = state["active_case_id"]
    if case_id is None:
        raise ValueError("no active case")
    entry = state["cases"][case_id]
    record_path = _record_path(args.state, entry)
    record = load_object(record_path)
    validate_patient_record(record)
    if record["case_id"] != case_id:
        raise ValueError("registered patient record identity differs")
    latest_visit = record["visits"][-1] if record["visits"] else None
    context: dict[str, Any] = {
        "case_id": case_id,
        "label": entry["label"],
        "record_path": str(record_path),
        "latest_visit": latest_visit,
    }
    if latest_visit and isinstance(latest_visit.get("analysis_binding"), dict):
        stored = Path(latest_visit["analysis_binding"]["analysis_file"])
        analysis_path = stored if stored.is_absolute() else record_path.parent / stored
        context["latest_analysis_path"] = str(analysis_path.resolve())
    print(json.dumps(context, ensure_ascii=False, indent=2))


def cmd_sandbox_create(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    record = load_object(args.record)
    authoritative = load_object(args.authoritative)
    validate_committed_record(record, authoritative)
    formulas = {formula["formula_id"]: formula for formula in record.get("formulas", [])}
    if args.formula_id not in formulas:
        raise ValueError(f"formula does not exist: {args.formula_id}")
    source_formula = formulas[args.formula_id]
    sandbox_id = f"SANDBOX-{record['run_id']}"
    formula = json.loads(json.dumps(source_formula, ensure_ascii=False))
    formula["formula_id"] = sandbox_id
    formula["role"] = "sandbox"
    validate_formula(formula)
    state["sandbox"] = {
        "sandbox_id": sandbox_id,
        "source_run_id": record["run_id"],
        "source_result_id": record["outcome"]["result_id"],
        "source_formula": source_formula,
        "formula": formula,
        "revision": 0,
    }
    atomic_json(args.state, state)
    print(f"PASS: created {sandbox_id} from {args.formula_id}")


def cmd_sandbox_update(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    if state["sandbox"] is None:
        raise ValueError("sandbox does not exist")
    formula = load_object(args.formula_json)
    validate_formula(formula)
    if formula["formula_id"] != state["sandbox"]["sandbox_id"]:
        raise ValueError("updated formula_id differs from the active sandbox")
    state["sandbox"]["formula"] = formula
    state["sandbox"]["revision"] += 1
    atomic_json(args.state, state)
    print(
        f"PASS: updated {formula['formula_id']} to revision "
        f"{state['sandbox']['revision']}"
    )


def cmd_sandbox_clear(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    state["sandbox"] = None
    atomic_json(args.state, state)
    print("PASS: cleared sandbox")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("init", cmd_init),
        ("show", cmd_show),
        ("context", cmd_context),
        ("sandbox-clear", cmd_sandbox_clear),
    ):
        command = sub.add_parser(name)
        command.add_argument("--state", type=Path, required=True)
        command.set_defaults(handler=handler)
    command = sub.add_parser("register")
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--record", type=Path, required=True)
    command.add_argument("--activate", action="store_true")
    command.set_defaults(handler=cmd_register)
    command = sub.add_parser("activate")
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--case-id", required=True)
    command.set_defaults(handler=cmd_activate)
    command = sub.add_parser("sandbox-create")
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--record", type=Path, required=True)
    command.add_argument("--authoritative", type=Path, required=True)
    command.add_argument("--formula-id", required=True)
    command.set_defaults(handler=cmd_sandbox_create)
    command = sub.add_parser("sandbox-update")
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--formula-json", type=Path, required=True)
    command.set_defaults(handler=cmd_sandbox_update)
    return root


def main() -> int:
    args = parser().parse_args()
    args.state = args.state.resolve()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
