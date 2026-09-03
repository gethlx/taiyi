#!/usr/bin/env python3
"""Validate actual-case identity, formal-result, and conflict boundaries."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from analysis_contract import validate_committed_analysis


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    examples = json.loads((ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8"))
    example = next(item for item in examples["valid_records"] if item["example_id"] == "MC-P03")
    record = example["record"]
    found = validate_committed_analysis(record, example["authoritative"], workspace=ROOT)
    if found:
        errors.append(f"case contract example failed: {found}")
    if record["case_context"] != {"case_id": "CASE-A", "turn_id": "CASE-A-T01"}:
        errors.append("initial case identity differs")
    if [item["identity"] for item in record["outcome"]["day_progression"]] != ["case_prediction"] * 3:
        errors.append("case Day identities differ")

    conflicted = copy.deepcopy(record)
    conflicted["reasoning"]["unresolved_conflicts"] = ["仍有实质冲突。"]
    rejected = validate_committed_analysis(conflicted, example["authoritative"], workspace=ROOT)
    if not any(item.startswith("outcome.unresolved_conflict_forbids_formal_r2") for item in rejected):
        errors.append("unresolved conflict still allowed a formal detailed result")

    if errors:
        print("FAILED: case skill", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: case slice preserves identity and blocks formal results with unresolved conflict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
