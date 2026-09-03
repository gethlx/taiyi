#!/usr/bin/env python3
"""Validate one Taiyi Shuji analysis record against its intake snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = PROJECT_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from analysis_contract import validate_committed_analysis  # noqa: E402


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--authoritative", required=True, type=Path)
    parser.add_argument(
        "--context-record",
        type=Path,
        help="formal context record used by a formula continuation or followup",
    )
    arguments = parser.parse_args()

    try:
        record = _load_object(arguments.record)
        authoritative = _load_object(arguments.authoritative)
        context_record = (
            _load_object(arguments.context_record)
            if arguments.context_record
            else None
        )
        if record.get("task_type") == "followup" and context_record is not None:
            current = record.get("case_context", {})
            if (
                context_record.get("record_type") != "case_snapshot"
                or context_record.get("case_id") != current.get("case_id")
                or context_record.get("turn_id") != current.get("turn_id")
                or context_record.get("parent_turn_id")
                != current.get("parent_turn_id")
            ):
                raise ValueError(
                    "case snapshot does not match case_id, turn_id, and parent_turn_id"
                )
        errors = validate_committed_analysis(
            record,
            authoritative,
            workspace=PROJECT_ROOT,
            previous_record=(
                context_record
                if record.get("task_type") == "formula_analysis"
                else None
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("FAILED: analysis record", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"PASS: {record['run_id']} is a valid committed analysis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
