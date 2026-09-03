#!/usr/bin/env python3
"""Validate formula-specific identities, prompts, and generalized boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from analysis_contract import validate_committed_analysis


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    examples = json.loads((ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8"))
    example = next(item for item in examples["valid_records"] if item["example_id"] == "MC-P02")
    record = example["record"]
    found = validate_committed_analysis(record, example["authoritative"], workspace=ROOT)
    if found:
        errors.append(f"formula contract example failed: {found}")
    if [item["identity"] for item in record["outcome"]["day_progression"]] != ["conditional_prediction"] * 3:
        errors.append("formula Day identities differ")
    if record["outcome"]["result_formula_id"] != "FORMULA-MC-P02-CANDIDATE":
        errors.append("formula result identity is not the candidate")
    input_formula = next(item for item in record["formulas"] if item["role"] == "input")
    if "preparation_text" in input_formula or "administration_text" in input_formula:
        errors.append("MC-P02 unexpectedly contains complete preparation or administration")
    if record["outcome"]["identity"] != "conditional_r2":
        errors.append("formula without execution details is not conditional_r2")

    if errors:
        print("FAILED: formula skill", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: formula identities, conditional output, and Day boundaries validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
