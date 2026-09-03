#!/usr/bin/env python3
"""Validate patient-record activation, A-B-A isolation, and one sandbox."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/taiyi-shuji/scripts/case_state.py"


def dump(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def patient_record(case_id: str, label: str, turns: list[str]) -> dict[str, object]:
    visits = []
    for index, turn_id in enumerate(turns):
        visit: dict[str, object] = {
            "turn_id": turn_id,
            "raw_text": f"{label}第{index + 1}轮原话",
            "confirmed_facts": [f"{label}第{index + 1}轮事实"],
            "ambiguous_facts": [],
        }
        if index:
            visit["parent_turn_id"] = turns[index - 1]
        visits.append(visit)
    return {
        "schema_version": "1.0",
        "record_type": "patient_record",
        "case_id": case_id,
        "label": label,
        "visits": visits,
    }


def main() -> int:
    errors: list[str] = []
    examples = json.loads(
        (ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8")
    )
    case_example = next(
        item for item in examples["valid_records"] if item["example_id"] == "MC-P03"
    )

    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        state = temp / "state.json"
        record_a = temp / "case-a.patient.json"
        record_b = temp / "case-b.patient.json"
        analysis = temp / "analysis.json"
        authoritative = temp / "authoritative.json"
        dump(record_a, patient_record("CASE-A", "病例甲", ["CASE-A-T01", "CASE-A-T02"]))
        dump(record_b, patient_record("CASE-B", "病例乙", ["CASE-B-T01"]))
        dump(analysis, case_example["record"])
        dump(authoritative, case_example["authoritative"])

        if run(["init", "--state", str(state)]).returncode:
            errors.append("state init failed")
        registered_a = run(
            [
                "register",
                "--state",
                str(state),
                "--record",
                str(record_a),
                "--activate",
            ]
        )
        registered_b = run(
            [
                "register",
                "--state",
                str(state),
                "--record",
                str(record_b),
                "--activate",
            ]
        )
        if registered_a.returncode or registered_b.returncode:
            errors.append(
                "patient record registration failed: "
                f"{registered_a.stderr.strip()} {registered_b.stderr.strip()}"
            )
        if run(["activate", "--state", str(state), "--case-id", "CASE-A"]).returncode:
            errors.append("A→B→A activation failed")
        context = run(["context", "--state", str(state)])
        if context.returncode:
            errors.append(f"active context failed: {context.stderr.strip()}")
        else:
            payload = json.loads(context.stdout)
            if (
                payload["case_id"] != "CASE-A"
                or payload["latest_visit"]["turn_id"] != "CASE-A-T02"
                or Path(payload["record_path"]).resolve() != record_a.resolve()
            ):
                errors.append("active state did not restore the registered A record")

        created = run(
            [
                "sandbox-create",
                "--state",
                str(state),
                "--record",
                str(analysis),
                "--authoritative",
                str(authoritative),
                "--formula-id",
                "FORMULA-MC-P03-FORMAL",
            ]
        )
        if created.returncode:
            errors.append(f"sandbox create failed: {created.stderr.strip()}")
        stored = json.loads(state.read_text(encoding="utf-8"))
        if stored["schema_version"] != "2.0" or len(stored["cases"]) != 2:
            errors.append("minimal state identity differs")
        if any("turns" in case for case in stored["cases"].values()):
            errors.append("state duplicated patient turns instead of registering records")
        if (
            stored["sandbox"]["source_run_id"] != "RUN-MC-P03"
            or stored["sandbox"]["formula"]["role"] != "sandbox"
        ):
            errors.append("sandbox did not preserve source identity")

    if errors:
        print("FAILED: case state", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "PASS: state registers one factual record per case, preserves A→B→A "
        "isolation, and keeps one copy-on-write sandbox"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
