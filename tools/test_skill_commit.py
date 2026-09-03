#!/usr/bin/env python3
"""Validate atomic 1.1 assembly and complete same-record text rendering."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMIT = ROOT / "skill/taiyi-shuji/scripts/commit_analysis.py"
FREEZE = ROOT / "skill/taiyi-shuji/scripts/freeze_inputs.py"
RENDER = ROOT / "skill/taiyi-shuji/scripts/render_dialogue.py"


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def execute(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(script), *args], cwd=ROOT, text=True, capture_output=True)


def main() -> int:
    errors: list[str] = []
    examples = json.loads((ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8"))
    source = next(item for item in examples["valid_records"] if item["example_id"] == "MC-P02")
    expected = source["record"]
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        paths: dict[str, Path] = {}
        fragments = {
            "authoritative": source["authoritative"],
            "sources": expected["sources"],
            "outcome": expected["outcome"],
            "calls": expected["calls"],
            "conflicts": expected["reasoning"]["unresolved_conflicts"],
            "generated": expected["formulas"][1:],
        }
        for name, value in fragments.items():
            paths[name] = temp / f"{name}.json"
            dump(paths[name], value)
        for role in ("r0", "r1", "r2", "red_team"):
            paths[role] = temp / f"{role}.json"
            dump(paths[role], expected["reasoning"][role])
        paths["input_lock"] = temp / "input-lock.json"
        frozen = execute(
            FREEZE,
            [
                "--authoritative", str(paths["authoritative"]),
                "--output", str(paths["input_lock"]),
            ],
        )
        if frozen.returncode:
            errors.append(f"input freeze failed: {frozen.stderr.strip()}")
        output = temp / "analysis.json"
        args = [
            "--authoritative", str(paths["authoritative"]),
            "--input-lock", str(paths["input_lock"]),
            "--run-id", expected["run_id"],
            "--task-type", expected["task_type"], "--sources", str(paths["sources"]),
            "--outcome", str(paths["outcome"]), "--calls", str(paths["calls"]),
            "--conflicts", str(paths["conflicts"]), "--generated-formulas", str(paths["generated"]),
            "--output", str(output),
        ]
        for role in ("r0", "r1", "r2", "red_team"):
            args.extend(["--role", f"{role}={paths[role]}"])
        result = execute(COMMIT, args)
        if result.returncode:
            errors.append(f"commit failed: {result.stderr.strip()}")
        elif json.loads(output.read_text(encoding="utf-8")) != expected:
            errors.append("assembled record differs from canonical example")

        dialogue = temp / "dialogue.md"
        rendered = execute(RENDER, ["--record", str(output), "--output", str(dialogue)])
        if rendered.returncode:
            errors.append(f"dialogue render failed: {rendered.stdout.strip()}")
        else:
            text = dialogue.read_text(encoding="utf-8")
            for role in ("r0", "r1", "r2", "red_team"):
                if expected["reasoning"][role]["text"] not in text:
                    errors.append(f"dialogue omitted complete {role} text")
            for marker in (expected["outcome"]["summary"], "Day 1", "Day 2", "Day 3", "可以继续明确提出"):
                if marker not in text:
                    errors.append(f"dialogue omitted {marker}")
            if "evidence_id" in text or "body_sha256" in text:
                errors.append("dialogue exposed an internal source identity")

        sentinel = temp / "sentinel.json"
        sentinel.write_text("do-not-overwrite\n", encoding="utf-8")

        if output.is_file():
            continued_outcome = copy.deepcopy(expected["outcome"])
            continued_outcome["result_id"] = "RESULT-MC-P02-CONTINUED"
            continued_outcome_path = temp / "continued-outcome.json"
            dump(continued_outcome_path, continued_outcome)
            continued_output = temp / "continued-analysis.json"
            continued_lock = temp / "continued-input-lock.json"
            frozen_continued = execute(
                FREEZE,
                [
                    "--authoritative", str(paths["authoritative"]),
                    "--context-record", str(output),
                    "--output", str(continued_lock),
                ],
            )
            if frozen_continued.returncode:
                errors.append(
                    f"continued input freeze failed: {frozen_continued.stderr.strip()}"
                )
            continued_args = list(args)
            continued_args[continued_args.index("--run-id") + 1] = "RUN-MC-P02-CONTINUED"
            continued_args[continued_args.index("--outcome") + 1] = str(continued_outcome_path)
            continued_args[continued_args.index("--output") + 1] = str(continued_output)
            continued_args[continued_args.index("--input-lock") + 1] = str(continued_lock)
            continued_args.extend(["--context-record", str(output)])
            continued = execute(COMMIT, continued_args)
            if continued.returncode:
                errors.append(
                    "continued formula commit failed: "
                    f"{continued.stderr.strip()}"
                )

            renamed_authoritative = copy.deepcopy(source["authoritative"])
            renamed_authoritative["input"]["subject"]["subject_id"] = (
                "FORMULA-MC-P02-RENAMED"
            )
            renamed_authoritative["source_formulas"][0]["formula_id"] = (
                "FORMULA-MC-P02-RENAMED"
            )
            renamed_authoritative_path = temp / "renamed-authoritative.json"
            dump(renamed_authoritative_path, renamed_authoritative)
            renamed_lock = temp / "renamed-input-lock.json"
            frozen_renamed = execute(
                FREEZE,
                [
                    "--authoritative", str(renamed_authoritative_path),
                    "--context-record", str(output),
                    "--output", str(renamed_lock),
                ],
            )
            if frozen_renamed.returncode:
                errors.append(
                    f"renamed input freeze failed: {frozen_renamed.stderr.strip()}"
                )
            renamed_args = list(continued_args)
            renamed_args[renamed_args.index("--authoritative") + 1] = str(
                renamed_authoritative_path
            )
            renamed_args[renamed_args.index("--input-lock") + 1] = str(renamed_lock)
            renamed_args[renamed_args.index("--output") + 1] = str(sentinel)
            renamed = execute(COMMIT, renamed_args)
            if (
                renamed.returncode == 0
                or "formula_identity.same_composition_requires_same_id"
                not in renamed.stderr
                or sentinel.read_text(encoding="utf-8") != "do-not-overwrite\n"
            ):
                errors.append(
                    "continued formula accepted a renamed formula_id or overwrote output"
                )

        original_authoritative = paths["authoritative"].read_bytes()
        changed_authoritative = copy.deepcopy(source["authoritative"])
        changed_authoritative["input"]["raw_text"] = "冻结后被修改"
        dump(paths["authoritative"], changed_authoritative)
        changed_args = [str(sentinel) if item == str(output) else item for item in args]
        changed_commit = execute(COMMIT, changed_args)
        if (
            changed_commit.returncode == 0
            or "authoritative input changed after freeze" not in changed_commit.stderr
            or sentinel.read_text(encoding="utf-8") != "do-not-overwrite\n"
        ):
            errors.append("commit accepted authoritative input changed after R0 freeze")
        paths["authoritative"].write_bytes(original_authoritative)

        parent_example = next(
            item for item in examples["valid_records"] if item["example_id"] == "MC-P03"
        )
        followup_example = next(
            item for item in examples["valid_records"] if item["example_id"] == "MC-P04"
        )
        followup_record = followup_example["record"]
        parent_record = parent_example["record"]
        parent_result_formula_id = parent_record["outcome"].get("result_formula_id")
        case_snapshot = {
            "schema_version": "1.0",
            "record_type": "case_snapshot",
            "case_id": "CASE-A",
            "turn_id": "CASE-A-T02",
            "parent_turn_id": "CASE-A-T01",
            "prior_final": {
                "run_id": parent_record["run_id"],
                "result_id": parent_record["outcome"]["result_id"],
                "outcome_identity": parent_record["outcome"]["identity"],
                "outcome_summary": parent_record["outcome"]["summary"],
                "day_progression": parent_record["outcome"]["day_progression"],
                "risks": parent_record["outcome"]["risks"],
                "minimum_questions": parent_record["outcome"]["minimum_questions"],
                "unresolved_boundaries": parent_record["reasoning"][
                    "unresolved_conflicts"
                ],
                "r0_summary": "父轮最终 R0 纵向摘要",
                "r1_summary": "父轮最终 R1 纵向摘要",
                "formulas": [
                    formula
                    for formula in parent_record["formulas"]
                    if formula["role"] == "input"
                    or (
                        formula["role"] == "formal_recommendation"
                        and formula["formula_id"] == parent_result_formula_id
                    )
                ],
            },
        }
        followup_paths: dict[str, Path] = {}
        followup_fragments = {
            "authoritative": followup_example["authoritative"],
            "sources": followup_record["sources"],
            "outcome": followup_record["outcome"],
            "calls": followup_record["calls"],
            "conflicts": followup_record["reasoning"]["unresolved_conflicts"],
            "generated": [
                item
                for item in followup_record["formulas"]
                if item["role"] in {"candidate", "formal_recommendation", "sandbox"}
            ],
            "parent": case_snapshot,
        }
        for name, value in followup_fragments.items():
            followup_paths[name] = temp / f"followup-{name}.json"
            dump(followup_paths[name], value)
        followup_roles = [
            role
            for role in ("r0", "r1", "r2", "red_team", "stage_c")
            if role in followup_record["reasoning"]
        ]
        for role in followup_roles:
            followup_paths[role] = temp / f"followup-{role}.json"
            dump(followup_paths[role], followup_record["reasoning"][role])
        followup_lock = temp / "followup-commit-lock.json"
        frozen_followup = execute(
            FREEZE,
            [
                "--authoritative", str(followup_paths["authoritative"]),
                "--context-record", str(followup_paths["parent"]),
                "--output", str(followup_lock),
            ],
        )
        if frozen_followup.returncode:
            errors.append(f"followup freeze failed: {frozen_followup.stderr.strip()}")
        followup_output = temp / "followup-analysis.json"
        followup_args = [
            "--authoritative", str(followup_paths["authoritative"]),
            "--input-lock", str(followup_lock),
            "--context-record", str(followup_paths["parent"]),
            "--run-id", followup_record["run_id"],
            "--task-type", "followup",
            "--sources", str(followup_paths["sources"]),
            "--outcome", str(followup_paths["outcome"]),
            "--calls", str(followup_paths["calls"]),
            "--conflicts", str(followup_paths["conflicts"]),
            "--generated-formulas", str(followup_paths["generated"]),
            "--output", str(followup_output),
        ]
        for role in followup_roles:
            followup_args.extend(["--role", f"{role}={followup_paths[role]}"])
        followup_commit = execute(COMMIT, followup_args)
        if followup_commit.returncode:
            errors.append(f"followup commit failed: {followup_commit.stderr.strip()}")

        no_parent_lock = temp / "followup-no-parent-lock.json"
        frozen_no_parent = execute(
            FREEZE,
            [
                "--authoritative", str(followup_paths["authoritative"]),
                "--output", str(no_parent_lock),
            ],
        )
        if frozen_no_parent.returncode:
            errors.append(f"no-parent freeze failed: {frozen_no_parent.stderr.strip()}")
        no_parent_args = []
        skip_next = False
        for item in followup_args:
            if skip_next:
                skip_next = False
                continue
            if item == "--context-record":
                skip_next = True
                continue
            no_parent_args.append(item)
        no_parent_args[no_parent_args.index("--input-lock") + 1] = str(no_parent_lock)
        no_parent_args[no_parent_args.index("--output") + 1] = str(sentinel)
        no_parent_commit = execute(COMMIT, no_parent_args)
        if (
            no_parent_commit.returncode == 0
            or "followup commit requires one frozen case snapshot"
            not in no_parent_commit.stderr
            or sentinel.read_text(encoding="utf-8") != "do-not-overwrite\n"
        ):
            errors.append("followup commit accepted a missing case snapshot")

        bad_role = temp / "bad-role.json"
        dump(bad_role, {"text": "正文", "handoff": "旧交接"})
        bad_args = list(args)
        index = bad_args.index(f"r0={paths['r0']}")
        bad_args[index] = f"r0={bad_role}"
        bad_args[bad_args.index(str(output))] = str(sentinel)
        failed = execute(COMMIT, bad_args)
        if failed.returncode == 0 or sentinel.read_text(encoding="utf-8") != "do-not-overwrite\n":
            errors.append("invalid role payload overwrote the previous result")

        broken_sources = copy.deepcopy(expected["sources"])
        broken_sources.append({"work_id": "T01-YI-WS", "title": "周易", "source_path": "kb/texts/01_周易.md", "start_line": 40, "end_line": 40, "excerpt": "不存在的短句"})
        dump(paths["sources"], broken_sources)
        source_args = [str(sentinel) if item == str(output) else item for item in args]
        rejected = execute(COMMIT, source_args)
        if rejected.returncode == 0 or sentinel.read_text(encoding="utf-8") != "do-not-overwrite\n":
            errors.append("invalid source overwrote the previous result")

    if errors:
        print("FAILED: skill commit", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: 1.1 commit verifies frozen input and case snapshot while preserving atomic canonical text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
