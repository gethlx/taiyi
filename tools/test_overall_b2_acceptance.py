#!/usr/bin/env python3
"""Aggregate the current text-mainline remediation machine acceptance."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from analysis_contract import validate_committed_analysis


ROOT = Path(__file__).resolve().parents[1]


def walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(walk_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(walk_keys(item) for item in value), set())
    return set()


def main() -> int:
    errors: list[str] = []
    examples = json.loads((ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8"))
    expected_tasks = {"classic_interpretation", "formula_analysis", "case_reasoning", "followup"}
    tasks: set[str] = set()
    for item in examples["valid_records"]:
        record = item["record"]
        tasks.add(record["task_type"])
        found = validate_committed_analysis(record, item["authoritative"], workspace=ROOT)
        if found:
            errors.append(f"{item['example_id']}: {found}")
        forbidden = walk_keys(record) & {"handoff", "evidence_id", "evidence_ids", "body_sha256", "projections"}
        if forbidden:
            errors.append(f"{item['example_id']}: forbidden active keys {sorted(forbidden)}")
        if record["task_type"] in {"formula_analysis", "case_reasoning", "followup"}:
            if "red_team" not in record["reasoning"]:
                errors.append(f"{item['example_id']}: mandatory red result missing")
        if record["reasoning"]["unresolved_conflicts"] and "stage_c" not in record["reasoning"]:
            errors.append(f"{item['example_id']}: conflict lacks Stage C")
    if tasks != expected_tasks:
        errors.append(f"task coverage differs: {sorted(tasks)}")

    active_runtime = [
        ROOT / "skill/taiyi-shuji/scripts/freeze_inputs.py",
        ROOT / "skill/taiyi-shuji/scripts/build_role_packet.py",
        ROOT / "skill/taiyi-shuji/scripts/commit_analysis.py",
        ROOT / "skill/taiyi-shuji/scripts/render_dialogue.py",
    ]
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in active_runtime)
    for forbidden in ("--handoff", "--projections", '"evidence_ids"'):
        if forbidden in runtime_text:
            errors.append(f"active runtime retains {forbidden}")
    if errors:
        print("FAILED: text-mainline remediation acceptance", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: four task identities, complete role text, mandatory red boundary, minimal sources, and optional H5 align")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
