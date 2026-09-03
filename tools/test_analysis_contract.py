#!/usr/bin/env python3
"""Exercise positive, negative, and hard-boundary machine-contract examples."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from analysis_contract import (
    authoritative_snapshot,
    validate_committed_analysis,
    validate_run_failure,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "analysis.schema.json"
EXAMPLES_PATH = ROOT / "spec" / "analysis_examples.json"


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _set_pointer(value: Any, pointer: str, replacement: Any) -> None:
    parts = [
        part.replace("~1", "/").replace("~0", "~")
        for part in pointer.split("/")[1:]
    ]
    cursor = value
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    final = parts[-1]
    if isinstance(cursor, list):
        cursor[int(final)] = replacement
    else:
        cursor[final] = replacement


def main() -> int:
    errors: list[str] = []
    try:
        schema = _load_object(SCHEMA_PATH)
        examples = _load_object(EXAMPLES_PATH)
        Draft202012Validator.check_schema(schema)

        if examples.get("schema_version") != "1.1":
            errors.append("analysis examples must use schema_version 1.1")
        valid_records = examples.get("valid_records", [])
        valid_failures = examples.get("valid_failures", [])
        mutations = examples.get("mutations", [])
        if len(valid_records) != 4:
            errors.append("exactly four task examples are required")
        if len(valid_failures) != 1:
            errors.append("exactly one failure example is required")
        if len(mutations) != 14:
            errors.append("exactly fourteen hard-boundary mutations are required")

        bases: dict[str, dict[str, Any]] = {}
        authoritative: dict[str, dict[str, Any]] = {}
        for example in valid_records:
            example_id = example["example_id"]
            bases[example_id] = example["record"]
            authoritative[example_id] = example["authoritative"]
            result_errors = validate_committed_analysis(
                example["record"],
                example["authoritative"],
                workspace=ROOT,
                schema=schema,
            )
            if result_errors:
                errors.append(f"{example_id}: {result_errors}")

        for example in valid_failures:
            example_id = example["example_id"]
            bases[example_id] = example["record"]
            result_errors = validate_run_failure(
                example["record"],
                schema=schema,
            )
            if result_errors:
                errors.append(f"{example_id}: {result_errors}")

        identifiers = list(bases)
        if len(identifiers) != len(set(identifiers)):
            errors.append("duplicate positive example IDs")
        mutation_ids = [item["mutation_id"] for item in mutations]
        if len(mutation_ids) != len(set(mutation_ids)):
            errors.append("duplicate mutation IDs")

        for mutation in mutations:
            mutation_id = mutation["mutation_id"]
            base_id = mutation["base_id"]
            mutated = copy.deepcopy(bases[base_id])
            _set_pointer(mutated, mutation["path"], copy.deepcopy(mutation["value"]))
            if mutated["record_type"] == "committed_analysis":
                result_errors = validate_committed_analysis(
                    mutated,
                    authoritative[base_id],
                    workspace=ROOT,
                    schema=schema,
                )
            else:
                result_errors = validate_run_failure(mutated, schema=schema)
            prefix = mutation["expected_error_prefix"]
            if not any(item.startswith(prefix) for item in result_errors):
                errors.append(
                    f"{mutation_id}: expected {prefix}, got {result_errors}"
                )

        host_badcase = copy.deepcopy(bases["MC-P03"])
        host_badcase["outcome"]["identity"] = "r1_confirmed_pending_further_facts"
        host_badcase["outcome"]["result_formula_id"] = None
        host_badcase["outcome"]["minimum_questions"] = [
            {"question": "这是错误的对象形状"}
        ]
        host_errors = validate_committed_analysis(
            host_badcase,
            authoritative["MC-P03"],
            workspace=ROOT,
            schema=schema,
        )
        expected_host_paths = {
            "schema.outcome.identity",
            "schema.outcome.minimum_questions.0",
            "schema.outcome.result_formula_id",
        }
        actual_host_paths = {
            item.split(":", 1)[0]
            for item in host_errors
            if item.startswith("schema.")
        }
        missing_host_paths = expected_host_paths - actual_host_paths
        if missing_host_paths:
            errors.append(
                "host badcase lacks targeted schema paths: "
                f"{sorted(missing_host_paths)} from {host_errors}"
            )
        if any(item.startswith("schema.root") for item in host_errors):
            errors.append(
                "host badcase collapsed into an unhelpful oneOf root error"
            )

        orphan_call = copy.deepcopy(bases["MC-P02"])
        orphan_call["calls"].append(
            {
                "call_id": "CALL-ORPHAN-STAGE-C",
                "responsibilities": ["stage_c"],
                "status": "succeeded",
            }
        )
        orphan_call_errors = validate_committed_analysis(
            orphan_call,
            authoritative["MC-P02"],
            workspace=ROOT,
            schema=schema,
        )
        if "calls.responsibility_without_reasoning:stage_c" not in orphan_call_errors:
            errors.append(
                "successful Stage C call without saved result was accepted"
            )

        orphan_reasoning = copy.deepcopy(bases["MC-P02"])
        orphan_reasoning["reasoning"]["stage_c"] = copy.deepcopy(
            orphan_reasoning["reasoning"]["r2"]
        )
        orphan_reasoning_errors = validate_committed_analysis(
            orphan_reasoning,
            authoritative["MC-P02"],
            workspace=ROOT,
            schema=schema,
        )
        if (
            "calls.reasoning_without_succeeded_responsibility:stage_c"
            not in orphan_reasoning_errors
        ):
            errors.append(
                "saved Stage C result without successful call responsibility was accepted"
            )

        skipped_red = copy.deepcopy(bases["MC-P02"])
        skipped_red["reasoning"].pop("red_team")
        skipped_red["calls"] = [
            call
            for call in skipped_red["calls"]
            if "red_team" not in call["responsibilities"]
        ]
        skipped_red_errors = validate_committed_analysis(
            skipped_red,
            authoritative["MC-P02"],
            workspace=ROOT,
            schema=schema,
        )
        if not any(
            item.startswith("reasoning.required_roles_missing:")
            and "red_team" in item
            for item in skipped_red_errors
        ):
            errors.append(
                "complete formula analysis without an actual red result was accepted"
            )

        retried_red = copy.deepcopy(bases["MC-P02"])
        retried_red["calls"].insert(
            1,
            {
                "call_id": "CALL-MC-P02-RED-FAILED",
                "responsibilities": ["red_team"],
                "status": "failed",
                "error_code": "interrupted",
            },
        )
        retried_red_errors = validate_committed_analysis(
            retried_red,
            authoritative["MC-P02"],
            workspace=ROOT,
            schema=schema,
        )
        if retried_red_errors:
            errors.append(
                "truthful failed red attempt followed by a successful retry was rejected: "
                f"{retried_red_errors}"
            )

        ingredient_level_administration = copy.deepcopy(bases["MC-P02"])
        ingredient_level_administration["formulas"][0]["composition"][0][
            "administration_text"
        ] = "先煎"
        ingredient_level_errors = validate_committed_analysis(
            ingredient_level_administration,
            authoritative["MC-P02"],
            workspace=ROOT,
            schema=schema,
        )
        if not any(
            item.startswith("schema.formulas.0.composition.0")
            for item in ingredient_level_errors
        ):
            errors.append(
                "ingredient-level administration field was accepted instead of "
                f"formula-level text: {ingredient_level_errors}"
            )

        previous_formula = bases["MC-P02"]
        continued_formula = copy.deepcopy(previous_formula)
        continued_formula["run_id"] = "RUN-MC-P02-CONTINUED"
        continued_formula["outcome"]["result_id"] = "RESULT-MC-P02-CONTINUED"
        continued_formula["input"]["raw_text"] += " 补充：桂枝切片，汤剂，每日两服。"
        continued_formula["input"]["confirmed_facts"].extend(
            ["桂枝切片", "剂型为汤剂", "每日两服"]
        )
        continued_input = next(
            item
            for item in continued_formula["formulas"]
            if item["role"] == "input"
        )
        continued_input["composition"][0]["raw_text"] = "桂枝三两（切片）"
        continued_input["composition"][0]["preparation"] = "切片"
        continued_input["preparation_text"] = "汤剂"
        continued_input["administration_text"] = "每日两服"
        continued_authoritative = authoritative_snapshot(continued_formula)
        continued_errors = validate_committed_analysis(
            continued_formula,
            continued_authoritative,
            workspace=ROOT,
            schema=schema,
            previous_record=previous_formula,
        )
        if continued_errors:
            errors.append(
                "same formula with added preparation or administration was rejected: "
                f"{continued_errors}"
            )

        stale_run_result = copy.deepcopy(continued_formula)
        stale_run_result["run_id"] = previous_formula["run_id"]
        stale_run_result["outcome"]["result_id"] = previous_formula["outcome"][
            "result_id"
        ]
        stale_errors = validate_committed_analysis(
            stale_run_result,
            authoritative_snapshot(stale_run_result),
            workspace=ROOT,
            schema=schema,
            previous_record=previous_formula,
        )
        for expected_error in (
            "formula_identity.continuation_requires_new_run_id",
            "formula_identity.continuation_requires_new_result_id",
        ):
            if expected_error not in stale_errors:
                errors.append(
                    f"continued formula reused identity without {expected_error}: "
                    f"{stale_errors}"
                )

        renamed_formula = copy.deepcopy(continued_formula)
        renamed_formula["input"]["subject"]["subject_id"] = "FORMULA-MC-P02-RENAMED"
        renamed_input = next(
            item
            for item in renamed_formula["formulas"]
            if item["role"] == "input"
        )
        renamed_input["formula_id"] = "FORMULA-MC-P02-RENAMED"
        renamed_errors = validate_committed_analysis(
            renamed_formula,
            authoritative_snapshot(renamed_formula),
            workspace=ROOT,
            schema=schema,
            previous_record=previous_formula,
        )
        if "formula_identity.same_composition_requires_same_id" not in renamed_errors:
            errors.append(
                "same composition with a new formula_id was accepted: "
                f"{renamed_errors}"
            )

        changed_formula = copy.deepcopy(continued_formula)
        changed_input = next(
            item
            for item in changed_formula["formulas"]
            if item["role"] == "input"
        )
        changed_input["composition"][0]["raw_text"] = "桂枝四两（切片）"
        changed_input["composition"][0]["amount"] = "四"
        changed_errors = validate_committed_analysis(
            changed_formula,
            authoritative_snapshot(changed_formula),
            workspace=ROOT,
            schema=schema,
            previous_record=previous_formula,
        )
        if "formula_identity.changed_composition_requires_new_id" not in changed_errors:
            errors.append(
                "changed composition retained the previous formula_id: "
                f"{changed_errors}"
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"test harness failed: {exc}")

    if errors:
        print("FAILED: minimal machine contract", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "PASS: 4 task records, 1 failure envelope, and "
        "14 hard-boundary mutations plus formula identity transitions validate the minimal machine contract"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
