#!/usr/bin/env python3
"""Emit selected source units without printing an unselected full source line."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


UNIT_PATTERN = re.compile(r"[^。！？；\n]+[。！？；]?")
ROOT = Path(__file__).resolve().parents[3]


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _units(text: str) -> list[str]:
    return [match.group(0).strip() for match in UNIT_PATTERN.finditer(text) if match.group(0).strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--contains", required=True, action="append")
    arguments = parser.parse_args()

    try:
        result = _load_object(arguments.result)
        evidence = next(
            item
            for item in result["source_evidence"]
            if item["evidence_id"] == arguments.evidence_id
        )
        source_units = _units(evidence["excerpt"])
        selected_indices: list[int] = []
        for target in arguments.contains:
            matches = [
                index
                for index, unit in enumerate(source_units)
                if target in unit
            ]
            if not matches:
                raise ValueError(
                    f"{arguments.evidence_id} has no source unit containing {target!r}"
                )
            if len(matches) != 1:
                raise ValueError(
                    f"{target!r} matches more than one source unit; use a more exact substring"
                )
            if matches[0] not in selected_indices:
                selected_indices.append(matches[0])
        selected_indices.sort()
        if selected_indices != list(
            range(selected_indices[0], selected_indices[-1] + 1)
        ):
            raise ValueError(
                "selected source units are not contiguous; do not stitch them into one claim"
            )
        selected_excerpt = "".join(
            source_units[index] for index in selected_indices
        )
        manifest = _load_object(ROOT / "kb" / "manifest.json")
        works = {
            item["work_id"]: item
            for item in manifest.get("works", [])
            if isinstance(item, dict) and "work_id" in item
        }
        work = works.get(evidence["work_id"])
        if work is None:
            raise ValueError(f"unknown work_id: {evidence['work_id']}")
        packet = {
            "sources": [
                {
                    "work_id": evidence["work_id"],
                    "title": work["title"],
                    "source_path": evidence["source_path"],
                    "start_line": evidence["locator"]["start_line"],
                    "end_line": evidence["locator"]["end_line"],
                    "excerpt": selected_excerpt,
                }
            ],
        }
        print(json.dumps(packet, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, StopIteration, json.JSONDecodeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
