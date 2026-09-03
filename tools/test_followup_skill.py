#!/usr/bin/env python3
"""Validate same-case follow-up lineage and reserved-opinion boundaries."""

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
    example = next(item for item in examples["valid_records"] if item["example_id"] == "MC-P04")
    record = example["record"]
    found = validate_committed_analysis(record, example["authoritative"], workspace=ROOT)
    if found:
        errors.append(f"follow-up contract example failed: {found}")
    context = record["case_context"]
    if (context["case_id"], context["turn_id"], context["parent_turn_id"]) != ("CASE-A", "CASE-A-T02", "CASE-A-T01"):
        errors.append("follow-up lineage differs")
    if record["outcome"]["identity"] != "reserved_opinion" or "result_formula_id" in record["outcome"]:
        errors.append("reserved follow-up acquired a formal formula identity")
    if [item["identity"] for item in record["outcome"]["day_progression"]] != ["followup_prediction"] * 3:
        errors.append("follow-up Day identities differ")

    crossed = copy.deepcopy(record)
    crossed["case_context"]["case_id"] = "CASE-B"
    rejected = validate_committed_analysis(crossed, example["authoritative"], workspace=ROOT)
    if not any(item.startswith("case_context.changed") for item in rejected):
        errors.append("cross-case mutation was accepted")

    if errors:
        print("FAILED: follow-up skill", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: follow-up slice preserves explicit parent context, fact/prediction identity, and reserved status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
