#!/usr/bin/env python3
"""Validate Taiyi Shuji committed records without producing medical semantics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "analysis.schema.json"
SOURCE_FORMULA_ROLES = {"input", "reference", "mentioned"}
CASE_TASKS = {"case_reasoning", "followup"}
FULL_REASONING_TASKS = {"formula_analysis", "case_reasoning", "followup"}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _schema_errors(
    record: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    record_type = record.get("record_type")
    definition = {
        "committed_analysis": "CommittedAnalysis",
        "run_failure": "RunFailure",
    }.get(record_type)
    validation_schema = schema
    if definition is not None:
        # Validate the selected envelope directly. The top-level oneOf is useful
        # to consumers, but its default error collapses a malformed record into
        # one enormous "not valid under any schema" message. A task host needs
        # the exact field path in order to fail closed before commit.
        validation_schema = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        }
    validator = Draft202012Validator(validation_schema)
    return [
        "schema."
        + (".".join(str(part) for part in error.absolute_path) or "root")
        + f": {error.message}"
        for error in sorted(
            validator.iter_errors(record),
            key=lambda item: list(item.absolute_path),
        )
    ]


def _duplicates(values: list[Any]) -> set[Any]:
    return {value for value in values if values.count(value) > 1}


def _source_formulas(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        formula
        for formula in record.get("formulas", [])
        if formula.get("role") in SOURCE_FORMULA_ROLES
    ]


def _subject_input_formula(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the formula owned by a formula subject, if one is present."""

    subject = record.get("input", {}).get("subject", {})
    subject_id = subject.get("subject_id")
    if subject.get("kind") != "formula" or not isinstance(subject_id, str):
        return None
    return next(
        (
            formula
            for formula in record.get("formulas", [])
            if formula.get("role") == "input"
            and formula.get("formula_id") == subject_id
        ),
        None,
    )


def _explicit_composition_identity(formula: dict[str, Any]) -> tuple[Any, ...]:
    """Compare names, order, amounts, and units while allowing added preparation."""

    return tuple(
        (
            ingredient.get("name"),
            ingredient.get("amount"),
            ingredient.get("unit"),
        )
        for ingredient in formula.get("composition", [])
    )


def validate_formula_identity_transition(
    previous_record: dict[str, Any],
    current_record: dict[str, Any],
) -> list[str]:
    """Check one explicitly continued formula without adding lineage fields."""

    if (
        previous_record.get("record_type") != "committed_analysis"
        or previous_record.get("task_type") != "formula_analysis"
    ):
        return ["formula_identity.previous_record_invalid"]
    if current_record.get("task_type") != "formula_analysis":
        return ["formula_identity.current_record_not_formula_analysis"]
    previous_formula = _subject_input_formula(previous_record)
    current_formula = _subject_input_formula(current_record)
    if previous_formula is None or current_formula is None:
        return ["formula_identity.input_formula_missing"]

    same_composition = _explicit_composition_identity(
        previous_formula
    ) == _explicit_composition_identity(current_formula)
    same_id = previous_formula["formula_id"] == current_formula["formula_id"]
    errors: list[str] = []
    if previous_record.get("run_id") == current_record.get("run_id"):
        errors.append("formula_identity.continuation_requires_new_run_id")
    if previous_record.get("outcome", {}).get("result_id") == current_record.get(
        "outcome", {}
    ).get("result_id"):
        errors.append("formula_identity.continuation_requires_new_result_id")
    if same_composition and not same_id:
        errors.append("formula_identity.same_composition_requires_same_id")
    if not same_composition and same_id:
        errors.append("formula_identity.changed_composition_requires_new_id")
    return errors


def authoritative_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    """Extract the intake-owned values that later model output cannot rewrite."""

    snapshot: dict[str, Any] = {
        "input": record.get("input"),
        "source_formulas": _source_formulas(record),
    }
    if "case_context" in record:
        snapshot["case_context"] = record["case_context"]
    return snapshot


def _validate_sources(
    sources: list[dict[str, Any]],
    *,
    workspace: Path,
) -> list[str]:
    """Read each selected short source once and verify its document anchor."""

    errors: list[str] = []
    if not sources:
        return errors
    manifest = _load_object(workspace / "kb" / "manifest.json")
    works = {
        item["work_id"]: item
        for item in manifest.get("works", [])
        if isinstance(item, dict) and "work_id" in item
    }
    source_root = (workspace / "kb" / "texts").resolve()
    body_cache: dict[Path, tuple[bytes, list[str]]] = {}
    identities: list[tuple[str, str, int, int, str]] = []

    for index, item in enumerate(sources):
        identity = (
            item["work_id"],
            item["source_path"],
            item["start_line"],
            item["end_line"],
            item["excerpt"],
        )
        identities.append(identity)
        work = works.get(item["work_id"])
        if work is None:
            errors.append(f"source.{index}.work_id_unknown")
            continue
        expected_path = f"kb/{work['path']}"
        if item["source_path"] != expected_path or item["title"] != work["title"]:
            errors.append(f"source.{index}.work_path_mismatch")
            continue
        source = (workspace / item["source_path"]).resolve()
        if not source.is_relative_to(source_root) or not source.is_file():
            errors.append(f"source.{index}.source_path_invalid")
            continue
        if source not in body_cache:
            body = source.read_bytes()
            body_cache[source] = (body, body.decode("utf-8").splitlines())
            if hashlib.sha256(body).hexdigest() != work["sha256"]:
                errors.append(f"source.{index}.file_integrity_mismatch")
        _, lines = body_cache[source]
        start, end = item["start_line"], item["end_line"]
        if end < start or end > len(lines):
            errors.append(f"source.{index}.locator_invalid")
            continue
        located_text = "\n".join(lines[start - 1 : end]).strip()
        if item["excerpt"] not in located_text:
            errors.append(f"source.{index}.excerpt_mismatch")

    for duplicate in _duplicates(identities):
        errors.append(f"sources.duplicate:{duplicate!r}")
    return errors


def validate_committed_analysis(
    record: dict[str, Any],
    authoritative: dict[str, Any],
    *,
    workspace: Path = ROOT,
    schema: dict[str, Any] | None = None,
    previous_record: dict[str, Any] | None = None,
) -> list[str]:
    """Check deterministic identity, source, and commit boundaries."""

    active_schema = schema or _load_object(SCHEMA_PATH)
    errors = _schema_errors(record, active_schema)
    if errors:
        return errors
    if record["record_type"] != "committed_analysis":
        return ["record.not_committed_analysis"]

    expected_keys = {"input", "source_formulas"}
    if record["task_type"] in CASE_TASKS:
        expected_keys.add("case_context")
    if set(authoritative) != expected_keys:
        errors.append("authoritative_snapshot.shape_invalid")
    else:
        if record["input"] != authoritative["input"]:
            errors.append("input.snapshot_changed")
        if _source_formulas(record) != authoritative["source_formulas"]:
            errors.append("formulas.source_snapshot_changed")
        if record["task_type"] in CASE_TASKS:
            if record.get("case_context") != authoritative["case_context"]:
                errors.append("case_context.changed")

    task_type = record["task_type"]
    subject = record["input"]["subject"]
    context = record.get("case_context")
    if task_type in CASE_TASKS and context is None:
        errors.append("case_context.required")
    if task_type not in CASE_TASKS and context is not None:
        errors.append("case_context.forbidden")
    if context is not None and subject["subject_id"] != context["case_id"]:
        errors.append("case_context.subject_mismatch")
    if task_type == "followup" and context is not None and "parent_turn_id" not in context:
        errors.append("case_context.followup_parent_required")
    if task_type == "formula_analysis" and subject["kind"] != "formula":
        errors.append("subject.kind_mismatch")
    if task_type in CASE_TASKS and subject["kind"] != "case":
        errors.append("subject.kind_mismatch")
    if task_type == "classic_interpretation" and subject["kind"] != "classic":
        errors.append("subject.kind_mismatch")

    formulas = record["formulas"]
    formula_ids = [item["formula_id"] for item in formulas]
    for duplicate in sorted(_duplicates(formula_ids)):
        errors.append(f"formulas.duplicate_id:{duplicate}")
    formulas_by_id = {item["formula_id"]: item for item in formulas}
    if subject["kind"] == "formula":
        subject_formula = formulas_by_id.get(subject["subject_id"])
        if subject_formula is None or subject_formula["role"] != "input":
            errors.append("subject.formula_not_input")

    reasoning = record["reasoning"]
    required_roles = {"r0"}
    if task_type in FULL_REASONING_TASKS:
        required_roles.update({"r1", "r2", "red_team"})
    missing_roles = sorted(required_roles - set(reasoning))
    if missing_roles:
        errors.append(f"reasoning.required_roles_missing:{missing_roles}")

    outcome = record["outcome"]
    allowed_identities = {
        "classic_interpretation": {
            "classic_interpretation",
            "facts_or_evidence_insufficient",
            "reserved_opinion",
        },
        "formula_analysis": {
            "formula_analysis",
            "conditional_r2",
            "facts_or_evidence_insufficient",
            "reserved_opinion",
        },
        "case_reasoning": {
            "conditional_r2",
            "r2_pending_physician_review",
            "facts_or_evidence_insufficient",
            "reserved_opinion",
        },
        "followup": {
            "conditional_r2",
            "r2_pending_physician_review",
            "facts_or_evidence_insufficient",
            "reserved_opinion",
        },
    }
    if outcome["identity"] not in allowed_identities[task_type]:
        errors.append("outcome.identity_task_mismatch")

    result_formula_id = outcome.get("result_formula_id")
    if result_formula_id is not None:
        result_formula = formulas_by_id.get(result_formula_id)
        if result_formula is None:
            errors.append("outcome.result_formula_missing")
        elif result_formula["role"] in {"input", "reference", "mentioned", "sandbox"}:
            errors.append("outcome.result_formula_role_invalid")
        elif (
            outcome["identity"] == "r2_pending_physician_review"
            and result_formula["role"] != "formal_recommendation"
        ):
            errors.append("outcome.formal_result_requires_formal_formula")
    if (
        outcome["identity"] == "r2_pending_physician_review"
        and reasoning["unresolved_conflicts"]
    ):
        errors.append("outcome.unresolved_conflict_forbids_formal_r2")
    if reasoning["unresolved_conflicts"] and any(
        formula["role"] == "formal_recommendation" for formula in formulas
    ):
        errors.append("formulas.unresolved_conflict_forbids_formal_recommendation")

    day_items = outcome["day_progression"]
    if task_type == "classic_interpretation":
        if day_items:
            errors.append("outcome.classic_forbids_day_progression")
    else:
        if [item["day"] for item in day_items] != [1, 2, 3]:
            errors.append("outcome.day_progression_must_be_1_2_3")
        expected_identity = {
            "formula_analysis": "conditional_prediction",
            "case_reasoning": "case_prediction",
            "followup": "followup_prediction",
        }[task_type]
        if any(item["identity"] != expected_identity for item in day_items):
            errors.append("outcome.day_identity_task_mismatch")

    errors.extend(_validate_sources(record["sources"], workspace=workspace))

    call_ids = [item["call_id"] for item in record["calls"]]
    for duplicate in sorted(_duplicates(call_ids)):
        errors.append(f"calls.duplicate_id:{duplicate}")
    role_names = {"r0", "r1", "r2", "red_team", "stage_c"}
    succeeded_responsibilities = {
        responsibility
        for item in record["calls"]
        if item["status"] == "succeeded"
        for responsibility in item["responsibilities"]
        if responsibility in role_names
    }
    saved_role_results = role_names & set(reasoning)
    for role in sorted(succeeded_responsibilities - saved_role_results):
        errors.append(f"calls.responsibility_without_reasoning:{role}")
    for role in sorted(saved_role_results - succeeded_responsibilities):
        errors.append(f"calls.reasoning_without_succeeded_responsibility:{role}")
    if previous_record is not None:
        errors.extend(validate_formula_identity_transition(previous_record, record))
    return errors


def validate_run_failure(
    record: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a failure envelope that cannot contain a medical result."""

    active_schema = schema or _load_object(SCHEMA_PATH)
    errors = _schema_errors(record, active_schema)
    if errors:
        return errors
    if record["record_type"] != "run_failure":
        return ["record.not_run_failure"]
    return []
