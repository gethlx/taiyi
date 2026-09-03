#!/usr/bin/env python3
"""Validate complete upstream role transport and bounded role packets."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/taiyi-shuji/scripts/build_role_packet.py"
FREEZE = ROOT / "skill/taiyi-shuji/scripts/freeze_inputs.py"
EXAMPLES = ROOT / "spec/analysis_examples.json"


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def freeze(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(FREEZE), *args], cwd=ROOT, text=True, capture_output=True)


def main() -> int:
    errors: list[str] = []
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    source = next(item for item in examples["valid_records"] if item["example_id"] == "MC-P02")
    sourced = next(
        item
        for item in examples["valid_records"]
        if item["record"]["sources"]
    )
    record = source["record"]
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        auth = temp / "authoritative.json"
        empty_sources = temp / "empty-sources.json"
        role_sources = temp / "r2-sources.json"
        outcome = temp / "outcome.json"
        formulas = temp / "formulas.json"
        input_lock = temp / "input-lock.json"
        dump(auth, source["authoritative"])
        dump(empty_sources, [])
        dump(role_sources, [sourced["record"]["sources"][0]])
        dump(outcome, record["outcome"])
        dump(formulas, record["formulas"][1:])
        frozen = freeze(["--authoritative", str(auth), "--output", str(input_lock)])
        if frozen.returncode:
            errors.append(f"input freeze failed: {frozen.stderr.strip()}")
        role_paths: dict[str, Path] = {}
        for role in ("r0", "r1", "r2", "red_team"):
            path = temp / f"{role}.json"
            dump(path, record["reasoning"][role])
            role_paths[role] = path

        common = ["--authoritative", str(auth), "--input-lock", str(input_lock)]
        cases = [
            ("r0", [], []),
            ("r1", ["r0"], ["r0"]),
            ("r2", ["r0", "r1"], ["r0", "r1"]),
            ("red_team", ["r0", "r1", "r2"], ["r0", "r1", "r2"]),
            ("stage_c", ["r0", "r1", "r2", "red_team"], ["r0", "r1", "r2", "red_team"]),
        ]
        for role, priors, expected in cases:
            output = temp / f"{role}.md"
            current_sources = (
                role_sources
                if role in {"r2", "red_team", "stage_c"}
                else empty_sources
            )
            args = [
                "--role", role,
                *common,
                "--current-role-sources", str(current_sources),
                "--output", str(output),
            ]
            for prior in priors:
                args.extend(["--prior-result", f"{prior}={role_paths[prior]}"])
            if role in {"red_team", "stage_c"}:
                args.extend(["--candidate-outcome", str(outcome), "--generated-formulas", str(formulas)])
            result = run(args)
            if result.returncode:
                errors.append(f"{role} packet failed: {result.stderr.strip()}")
                continue
            text = output.read_text(encoding="utf-8")
            for prior in expected:
                full = record["reasoning"][prior]["text"]
                if full not in text:
                    errors.append(f"{role} omitted complete {prior} text")
            if '"evidence_id"' in text or '"body_sha256"' in text:
                errors.append(f"{role} exposed internal source identity")
            if "handoff" in text.lower():
                errors.append(f"{role} packet retained handoff transport")
            if "任务卡" in text:
                errors.append(f"{role} packet retained the removed runtime task card")
            if '"scope":' in text:
                errors.append(f"{role} packet exposed machine-only scope as medical input")
            source_excerpt = sourced["record"]["sources"][0]["excerpt"]
            if role in {"r0", "r1"} and source_excerpt in text:
                errors.append(f"{role} inherited a source not selected for its role")
            if role in {"r2", "red_team", "stage_c"} and source_excerpt not in text:
                errors.append(f"{role} omitted its explicitly selected current source")

        missing = run(["--role", "r2", *common, "--current-role-sources", str(role_sources), "--prior-result", f"r1={role_paths['r1']}", "--output", str(temp / "missing.md")])
        if missing.returncode == 0:
            errors.append("R2 accepted incomplete upstream results")
        bad_prior = temp / "bad-prior.json"
        dump(bad_prior, {"text": "正文", "handoff": "旧交接"})
        malformed = run(["--role", "r1", *common, "--current-role-sources", str(empty_sources), "--prior-result", f"r0={bad_prior}", "--output", str(temp / "bad.md")])
        if malformed.returncode == 0:
            errors.append("packet accepted an extra handoff field")
        no_candidate = run(["--role", "red_team", *common, "--current-role-sources", str(role_sources), "--prior-result", f"r0={role_paths['r0']}", "--output", str(temp / "red.md")])
        if no_candidate.returncode == 0:
            errors.append("red packet accepted a missing candidate outcome")
        premature_candidate = run([
            "--role", "r1", *common,
            "--current-role-sources", str(empty_sources),
            "--prior-result", f"r0={role_paths['r0']}",
            "--candidate-outcome", str(outcome),
            "--generated-formulas", str(formulas),
            "--output", str(temp / "premature-candidate.md"),
        ])
        if premature_candidate.returncode == 0:
            errors.append("subject role packet accepted audit-only candidate material")

        original_authoritative = auth.read_bytes()
        changed = source["authoritative"] | {
            "input": source["authoritative"]["input"] | {"raw_text": "冻结后被改动"}
        }
        dump(auth, changed)
        changed_packet = run([
            "--role", "r1", *common,
            "--current-role-sources", str(empty_sources),
            "--prior-result", f"r0={role_paths['r0']}",
            "--output", str(temp / "changed.md"),
        ])
        if changed_packet.returncode == 0:
            errors.append("packet accepted authoritative input changed after freeze")
        auth.write_bytes(original_authoritative)
        replaced_lock = freeze(["--authoritative", str(auth), "--output", str(input_lock)])
        if replaced_lock.returncode == 0:
            errors.append("freeze_inputs replaced an existing lock")
        sandbox_context = temp / "sandbox-context.json"
        sandbox_lock = temp / "sandbox-input-lock.json"
        dump(
            sandbox_context,
            {
                "schema_version": "1.1",
                "sandbox_id": "SANDBOX-NOT-A-FORMAL-PARENT",
                "formula": {"formula_id": "SANDBOX-NOT-A-FORMAL-PARENT", "role": "sandbox", "composition": []},
            },
        )
        frozen_sandbox = freeze([
            "--authoritative", str(auth),
            "--context-record", str(sandbox_context),
            "--output", str(sandbox_lock),
        ])
        if frozen_sandbox.returncode == 0:
            errors.append("freeze_inputs accepted a sandbox as formal context")

        followup = next(
            item for item in examples["valid_records"] if item["example_id"] == "MC-P04"
        )
        follow_auth = temp / "followup-authoritative.json"
        case_snapshot = temp / "case-snapshot.json"
        follow_lock = temp / "followup-input-lock.json"
        follow_outcome = temp / "followup-outcome.json"
        follow_formulas = temp / "followup-formulas.json"
        follow_authoritative = json.loads(
            json.dumps(followup["authoritative"], ensure_ascii=False)
        )
        follow_authoritative["input"]["raw_text"] = "CURRENT-RAW-MUST-STAY-FROZEN-ONLY"
        dump(follow_auth, follow_authoritative)
        dump(
            case_snapshot,
            {
                "schema_version": "1.0",
                "record_type": "case_snapshot",
                "case_id": "CASE-A",
                "turn_id": "CASE-A-T02",
                "parent_turn_id": "CASE-A-T01",
                "prior_final": {
                    "run_id": "RUN-PARENT",
                    "result_id": "RESULT-PARENT",
                    "outcome_identity": "r2_pending_physician_review",
                    "outcome_summary": "PARENT-OUTCOME-SUMMARY",
                    "day_progression": [
                        {
                            "day": day,
                            "identity": "case_prediction",
                            "text": f"PARENT-DAY-{day}",
                        }
                        for day in (1, 2, 3)
                    ],
                    "risks": ["PARENT-RISK"],
                    "minimum_questions": ["PARENT-QUESTION"],
                    "unresolved_boundaries": ["PARENT-BOUNDARY"],
                    "r0_summary": "PARENT-R0-FINAL-SUMMARY",
                    "r1_summary": "PARENT-R1-FINAL-HYPOTHESIS",
                    "comparison_to_previous": "PARENT-CHANGE-SUMMARY",
                    "formulas": [
                        {
                            "formula_id": "FORMULA-PARENT-FORMAL",
                            "role": "formal_recommendation",
                            "composition": [],
                        }
                    ],
                },
            },
        )
        dump(follow_outcome, followup["record"]["outcome"])
        dump(follow_formulas, [])
        frozen_followup = freeze([
            "--authoritative", str(follow_auth),
            "--context-record", str(case_snapshot),
            "--output", str(follow_lock),
        ])
        if frozen_followup.returncode:
            errors.append(f"followup input freeze failed: {frozen_followup.stderr.strip()}")
        follow_role_paths: dict[str, Path] = {}
        for role in ("r0", "r1", "r2"):
            path = temp / f"followup-{role}.json"
            dump(path, followup["record"]["reasoning"][role])
            follow_role_paths[role] = path
        follow_args_by_role: dict[str, list[str]] = {}
        for role, priors in (
            ("r0", ()),
            ("r1", ("r0",)),
            ("r2", ("r0", "r1")),
            ("red_team", ("r0", "r1", "r2")),
        ):
            follow_packet = temp / f"followup-{role}.md"
            follow_args = [
                "--role", role,
                "--authoritative", str(follow_auth),
                "--input-lock", str(follow_lock),
                "--context-record", str(case_snapshot),
                "--current-role-sources", str(empty_sources),
                "--output", str(follow_packet),
            ]
            for prior in priors:
                follow_args.extend(
                    ["--prior-result", f"{prior}={follow_role_paths[prior]}"]
                )
            if role == "red_team":
                follow_args.extend(
                    [
                        "--candidate-outcome",
                        str(follow_outcome),
                        "--generated-formulas",
                        str(follow_formulas),
                    ]
                )
            follow_args_by_role[role] = follow_args
            follow_result = run(follow_args)
            if follow_result.returncode:
                errors.append(
                    f"followup {role} packet failed: {follow_result.stderr.strip()}"
                )
                continue
            follow_text = follow_packet.read_text(encoding="utf-8")
            if "CURRENT-RAW-MUST-STAY-FROZEN-ONLY" in follow_text:
                errors.append(f"followup {role} packet exposed isolated raw text")
            if '"scope":' in follow_text:
                errors.append(f"followup {role} packet exposed machine scope")
            expected_markers = {
                "r0": {"PARENT-R0-FINAL-SUMMARY"},
                "r1": {
                    "PARENT-R1-FINAL-HYPOTHESIS",
                    "PARENT-OUTCOME-SUMMARY",
                    "PARENT-DAY-1",
                },
                "r2": {
                    "PARENT-OUTCOME-SUMMARY",
                    "PARENT-DAY-1",
                    "FORMULA-PARENT-FORMAL",
                },
                "red_team": {
                    "PARENT-R0-FINAL-SUMMARY",
                    "PARENT-R1-FINAL-HYPOTHESIS",
                    "PARENT-OUTCOME-SUMMARY",
                    "FORMULA-PARENT-FORMAL",
                },
            }[role]
            for marker in expected_markers:
                if marker not in follow_text:
                    errors.append(f"followup {role} packet omitted {marker}")
            forbidden_markers = {
                "r0": {
                    "PARENT-R1-FINAL-HYPOTHESIS",
                    "PARENT-OUTCOME-SUMMARY",
                    "FORMULA-PARENT-FORMAL",
                },
                "r1": {"PARENT-R0-FINAL-SUMMARY", "FORMULA-PARENT-FORMAL"},
                "r2": {"PARENT-R0-FINAL-SUMMARY", "PARENT-R1-FINAL-HYPOTHESIS"},
                "red_team": set(),
            }[role]
            for marker in forbidden_markers:
                if marker in follow_text:
                    errors.append(f"followup {role} packet leaked {marker}")

        follow_args = follow_args_by_role["red_team"]
        missing_parent_args = []
        skip_next = False
        for item in follow_args:
            if skip_next:
                skip_next = False
                continue
            if item == "--context-record":
                skip_next = True
                continue
            missing_parent_args.append(item)
        missing_parent = run(missing_parent_args)
        if missing_parent.returncode == 0:
            errors.append("followup packet accepted a missing case snapshot")

    if errors:
        print("FAILED: role packet", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: role packets bind frozen input, role-bounded case history, complete upstream text, and current-role sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
