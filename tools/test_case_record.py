#!/usr/bin/env python3
"""Validate patient facts, immutable bindings, and bounded follow-up snapshots."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/taiyi-shuji/scripts/case_record.py"


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


def main() -> int:
    errors: list[str] = []
    examples = json.loads(
        (ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8")
    )
    by_id = {item["example_id"]: item for item in examples["valid_records"]}
    initial = by_id["MC-P03"]
    followup = by_id["MC-P04"]

    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        record = temp / "patient-record.json"
        initial_visit = temp / "initial-visit.json"
        corrected_visit = temp / "corrected-visit.json"
        followup_visit = temp / "followup-visit.json"
        bad_visit = temp / "bad-visit.json"
        initial_analysis = temp / "initial-analysis.json"
        initial_authoritative = temp / "initial-authoritative.json"
        followup_analysis = temp / "followup-analysis.json"
        followup_authoritative = temp / "followup-authoritative.json"
        initial_evolution = temp / "initial-evolution.json"
        followup_evolution = temp / "followup-evolution.json"
        snapshot = temp / "case-snapshot.json"

        initialized = run(
            [
                "init",
                "--record",
                str(record),
                "--case-id",
                "CASE-A",
                "--label",
                "病例甲",
            ]
        )
        if initialized.returncode:
            errors.append(f"patient record init failed: {initialized.stderr.strip()}")

        visit_one = {
            "turn_id": "CASE-A-T01",
            "raw_text": initial["record"]["input"]["raw_text"],
            "confirmed_facts": initial["record"]["input"]["confirmed_facts"],
            "ambiguous_facts": initial["record"]["input"]["ambiguous_facts"],
            "external_context": ["用户主动提供的体系外信息，仅留档"],
            "clinician_opinions": ["医者既有判断，仅作历史意见"],
        }
        dump(initial_visit, visit_one)
        appended = run(
            ["append-visit", "--record", str(record), "--visit", str(initial_visit)]
        )
        if appended.returncode:
            errors.append(f"initial visit append failed: {appended.stderr.strip()}")

        corrected = dict(visit_one)
        corrected["confirmed_facts"] = [*visit_one["confirmed_facts"], "更正后的直接事实"]
        corrected["corrections"] = ["补记一项用户已经明确的直接事实"]
        dump(corrected_visit, corrected)
        correction = run(
            ["correct-visit", "--record", str(record), "--visit", str(corrected_visit)]
        )
        if correction.returncode:
            errors.append(f"unbound visit correction failed: {correction.stderr.strip()}")

        initial_record_payload = copy.deepcopy(initial["record"])
        initial_authoritative_payload = copy.deepcopy(initial["authoritative"])
        initial_record_payload["input"]["confirmed_facts"] = corrected[
            "confirmed_facts"
        ]
        initial_authoritative_payload["input"]["confirmed_facts"] = corrected[
            "confirmed_facts"
        ]
        dump(initial_analysis, initial_record_payload)
        dump(initial_authoritative, initial_authoritative_payload)
        dump(
            initial_evolution,
            {
                "r0_summary": "父轮最终 R0 纵向摘要",
                "r1_summary": "父轮最终 R1 纵向摘要",
                "unresolved_boundaries": [],
            },
        )
        bound = run(
            [
                "bind-analysis",
                "--record",
                str(record),
                "--turn-id",
                "CASE-A-T01",
                "--analysis",
                str(initial_analysis),
                "--authoritative",
                str(initial_authoritative),
                "--evolution",
                str(initial_evolution),
            ]
        )
        if bound.returncode:
            errors.append(f"initial analysis bind failed: {bound.stderr.strip()}")

        rejected_correction = run(
            ["correct-visit", "--record", str(record), "--visit", str(corrected_visit)]
        )
        if rejected_correction.returncode == 0:
            errors.append("bound visit was corrected in place")

        visit_two = {
            "turn_id": "CASE-A-T02",
            "parent_turn_id": "CASE-A-T01",
            "raw_text": followup["record"]["input"]["raw_text"],
            "confirmed_facts": [
                *corrected["confirmed_facts"],
                *followup["record"]["input"]["confirmed_facts"],
            ],
            "ambiguous_facts": followup["record"]["input"]["ambiguous_facts"],
            "treatment_response": ["精神稍好"],
        }
        dump(followup_visit, visit_two)
        appended_followup = run(
            ["append-visit", "--record", str(record), "--visit", str(followup_visit)]
        )
        if appended_followup.returncode:
            errors.append(f"follow-up visit append failed: {appended_followup.stderr.strip()}")

        snapped = run(
            [
                "snapshot",
                "--record",
                str(record),
                "--turn-id",
                "CASE-A-T02",
                "--output",
                str(snapshot),
            ]
        )
        if snapped.returncode:
            errors.append(f"case snapshot failed: {snapped.stderr.strip()}")
        else:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            if (
                payload["case_id"],
                payload["turn_id"],
                payload["parent_turn_id"],
            ) != ("CASE-A", "CASE-A-T02", "CASE-A-T01"):
                errors.append("case snapshot lineage differs")
            serialized = json.dumps(payload, ensure_ascii=False)
            if "父轮最终 R0 纵向摘要" not in serialized or "父轮最终 R1 纵向摘要" not in serialized:
                errors.append("case snapshot omitted final R0/R1 evolution")
            if initial["record"]["reasoning"]["r0"]["text"] in serialized:
                errors.append("case snapshot copied full parent R0 text")
            if initial["record"]["reasoning"]["r1"]["text"] in serialized:
                errors.append("case snapshot copied full parent R1 text")
            if "用户主动提供的体系外信息" in serialized:
                errors.append("case snapshot leaked isolated external context")

        followup_record_payload = copy.deepcopy(followup["record"])
        followup_authoritative_payload = copy.deepcopy(followup["authoritative"])
        followup_record_payload["input"]["confirmed_facts"] = visit_two[
            "confirmed_facts"
        ]
        followup_authoritative_payload["input"]["confirmed_facts"] = visit_two[
            "confirmed_facts"
        ]
        dump(followup_analysis, followup_record_payload)
        dump(followup_authoritative, followup_authoritative_payload)
        dump(
            followup_evolution,
            {
                "r0_summary": "本轮最终 R0 纵向摘要",
                "r1_summary": "本轮最终 R1 纵向摘要",
                "comparison_to_previous": "本轮相对父轮的收敛变化",
                "unresolved_boundaries": ["方向仍待下一轮事实确认"],
            },
        )
        bound_followup = run(
            [
                "bind-analysis",
                "--record",
                str(record),
                "--turn-id",
                "CASE-A-T02",
                "--analysis",
                str(followup_analysis),
                "--authoritative",
                str(followup_authoritative),
                "--evolution",
                str(followup_evolution),
            ]
        )
        if bound_followup.returncode:
            errors.append(f"follow-up analysis bind failed: {bound_followup.stderr.strip()}")

        bad = dict(visit_two)
        bad["turn_id"] = "CASE-A-T03"
        bad["parent_turn_id"] = "CASE-A-T01"
        dump(bad_visit, bad)
        before = record.read_bytes()
        rejected_parent = run(
            ["append-visit", "--record", str(record), "--visit", str(bad_visit)]
        )
        if rejected_parent.returncode == 0 or record.read_bytes() != before:
            errors.append("invalid parent lineage changed the patient record")

        final_record = json.loads(record.read_text(encoding="utf-8"))
        if len(final_record["visits"]) != 2:
            errors.append("patient record visit count differs")
        if final_record["visits"][0]["external_context"] != [
            "用户主动提供的体系外信息，仅留档"
        ]:
            errors.append("patient record did not preserve isolated external context")

    if errors:
        print("FAILED: patient record", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "PASS: patient facts, corrections, formal bindings, and bounded follow-up "
        "snapshots remain separate and atomic"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
