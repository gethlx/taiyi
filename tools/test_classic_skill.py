#!/usr/bin/env python3
"""Validate the classic slice and model-facing source selection boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from analysis_contract import validate_committed_analysis


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    examples = json.loads((ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8"))
    example = next(item for item in examples["valid_records"] if item["example_id"] == "MC-P01")
    contract_errors = validate_committed_analysis(example["record"], example["authoritative"], workspace=ROOT)
    if contract_errors:
        errors.append(f"classic contract example failed: {contract_errors}")

    result = subprocess.run(
        [
            sys.executable, "-B", str(ROOT / "skill/taiyi-shuji/scripts/select_evidence.py"),
            "--result", str(ROOT / "tools/fixtures/classic/CI-01-evidence-result.json"),
            "--evidence-id", "EV-T01-YI-WS-63-63-3f1ea053e5fd", "--contains", "阳在下也",
        ],
        cwd=ROOT, text=True, capture_output=True,
    )
    if result.returncode:
        errors.append(f"source selection failed: {result.stderr.strip()}")
    else:
        packet = json.loads(result.stdout)
        if set(packet) != {"sources"} or len(packet["sources"]) != 1:
            errors.append("selector did not return one minimal sources package")
        else:
            source = packet["sources"][0]
            if set(source) != {"work_id", "title", "source_path", "start_line", "end_line", "excerpt"}:
                errors.append("model-facing source shape differs")
            if source["excerpt"] != "1. 潜龙勿用，阳在下也。":
                errors.append("selector did not preserve the chosen short original")
        if "evidence_id" in result.stdout or "body_sha256" in result.stdout:
            errors.append("selector exposed internal evidence identity")

    stitched = subprocess.run(
        [
            sys.executable, "-B", str(ROOT / "skill/taiyi-shuji/scripts/select_evidence.py"),
            "--result", str(ROOT / "tools/fixtures/classic/CI-01-evidence-result.json"),
            "--evidence-id", "EV-T01-YI-WS-80-80-c8fe9691bb2e",
            "--contains", "初九曰",
            "--contains", "乐则行之",
        ],
        cwd=ROOT, text=True, capture_output=True,
    )
    if stitched.returncode == 0 or "not contiguous" not in stitched.stderr:
        errors.append("selector accepted non-contiguous source units as one classic claim")

    if errors:
        print("FAILED: classic skill", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: classic record identity and anchored short-source boundaries validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
