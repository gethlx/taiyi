#!/usr/bin/env python3
"""Validate deterministic structure and source conservation for a presentation projection.

This validator proves structural and identity binding only. Patient-language quality,
medical meaning, and correct absorption of Stage C still require semantic review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


RELATION_STATES = {"confirmed", "conditional", "unknown"}
RELATION_KINDS = {"primary", "conditional", "unknown"}
AUDIT_RESOLUTIONS = {"not_performed", "retained", "corrected", "unresolved"}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def require_object(parent: dict[str, Any], key: str, prefix: str = "") -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{prefix}{key} must be an object")
    return value


def optional_object(parent: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object when present")
    return value


def require_text(parent: dict[str, Any], key: str, prefix: str = "") -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}{key} must be a non-empty string")
    return value


def require_declarative_text(parent: dict[str, Any], key: str, prefix: str = "") -> str:
    value = require_text(parent, key, prefix)
    if "?" in value or "？" in value:
        raise ValueError(f"{prefix}{key} must be declarative, not a question")
    return value


def require_list(parent: dict[str, Any], key: str, prefix: str = "") -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{prefix}{key} must be an array")
    return value


def source_list(parent: dict[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"committed analysis {key} must be an array or null")
    return value


def validate_text_list(
    items: list[Any], label: str, *, minimum: int = 0, maximum: int | None = None
) -> None:
    if len(items) < minimum or (maximum is not None and len(items) > maximum):
        limit = f"{minimum}..{maximum}" if maximum is not None else f">={minimum}"
        raise ValueError(f"{label} length must be {limit}")
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{label} must contain only non-empty strings")


def validate_mapped_items(
    items: list[Any], source: list[Any], label: str, *, require_id: bool = True
) -> None:
    covered: set[int] = set()
    ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        if require_id:
            item_id = require_text(item, "fact_id", f"{label}[{index}].")
            if item_id in ids:
                raise ValueError(f"{label} contains duplicate fact_id {item_id!r}")
            ids.add(item_id)
        require_text(item, "text", f"{label}[{index}].")
        indexes = require_list(item, "source_indexes", f"{label}[{index}].")
        if not indexes:
            raise ValueError(f"{label}[{index}].source_indexes must not be empty")
        for source_index in indexes:
            if not isinstance(source_index, int) or not 0 <= source_index < len(source):
                raise ValueError(f"{label}[{index}].source_indexes contains an invalid index")
            covered.add(source_index)
    expected = set(range(len(source)))
    if covered != expected:
        raise ValueError(f"{label} must cover every committed source item with valid indexes")


def validate_professional_item(
    item: dict[str, Any], record: dict[str, Any], label: str, allowed_roles: set[str]
) -> None:
    require_declarative_text(item, "title", f"{label}.")
    role = require_text(item, "source_role", f"{label}.")
    excerpt = require_text(item, "original_excerpt", f"{label}.")
    require_text(item, "plain_explanation", f"{label}.")
    if role not in allowed_roles:
        raise ValueError(f"{label}.source_role must be one of {sorted(allowed_roles)}")
    role_output = require_object(require_object(record, "reasoning"), role, "reasoning.")
    role_text = require_text(role_output, "text", f"reasoning.{role}.")
    if excerpt not in role_text:
        raise ValueError(f"{label}.original_excerpt is not a continuous excerpt of reasoning.{role}.text")


def validate_relationship_model(story: dict[str, Any]) -> None:
    model = require_object(story, "relationship_model", "explanation_story.")
    nodes = require_list(model, "nodes", "explanation_story.relationship_model.")
    if not 2 <= len(nodes) <= 6:
        raise ValueError("relationship_model.nodes length must be 2..6")
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"relationship_model.nodes[{index}] must be an object")
        node_id = require_text(node, "node_id", f"relationship_model.nodes[{index}].")
        require_declarative_text(node, "label", f"relationship_model.nodes[{index}].")
        require_text(node, "detail", f"relationship_model.nodes[{index}].")
        if node.get("status") not in RELATION_STATES:
            raise ValueError(f"relationship_model.nodes[{index}].status is unsupported")
        if node_id in node_ids:
            raise ValueError(f"relationship_model.nodes contains duplicate node_id {node_id!r}")
        node_ids.add(node_id)

    edges = require_list(model, "edges", "explanation_story.relationship_model.")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"relationship_model.edges[{index}] must be an object")
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            raise ValueError(f"relationship_model.edges[{index}] references an unknown node")
        if edge.get("kind") not in RELATION_KINDS:
            raise ValueError(f"relationship_model.edges[{index}].kind is unsupported")
        if "label" in edge and (not isinstance(edge["label"], str) or not edge["label"].strip()):
            raise ValueError(f"relationship_model.edges[{index}].label must be non-empty when present")

    chain = require_list(story, "causal_chain", "explanation_story.")
    if len(chain) > 5:
        raise ValueError("explanation_story.causal_chain length must be 0..5")
    for index, step in enumerate(chain):
        if not isinstance(step, dict):
            raise ValueError(f"explanation_story.causal_chain[{index}] must be an object")
        require_declarative_text(step, "label", f"explanation_story.causal_chain[{index}].")
        require_text(step, "detail", f"explanation_story.causal_chain[{index}].")
        if step.get("status") not in RELATION_STATES:
            raise ValueError(f"explanation_story.causal_chain[{index}].status is unsupported")


def validate_treatment_story(projection: dict[str, Any]) -> None:
    story = optional_object(projection, "treatment_story")
    if story is None:
        return
    require_text(story, "center_label", "treatment_story.")
    require_text(story, "strategy", "treatment_story.")
    require_text(story, "why_it_matches", "treatment_story.")
    goals = require_list(story, "goals", "treatment_story.")
    if not 1 <= len(goals) <= 6:
        raise ValueError("treatment_story.goals length must be 1..6")
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            raise ValueError(f"treatment_story.goals[{index}] must be an object")
        require_declarative_text(goal, "title", f"treatment_story.goals[{index}].")
        require_text(goal, "detail", f"treatment_story.goals[{index}].")
        if "role" in goal and (not isinstance(goal["role"], str) or not goal["role"].strip()):
            raise ValueError(f"treatment_story.goals[{index}].role must be non-empty when present")


def validate_formula_story(projection: dict[str, Any], record: dict[str, Any]) -> None:
    record_formulas = source_list(record, "formulas")
    story = optional_object(projection, "formula_story")
    if not record_formulas:
        if story is not None:
            raise ValueError("formula_story must be absent when committed analysis has no formulas")
        return
    if story is None:
        raise ValueError("formula_story is required when committed analysis has formulas")
    formulas = require_list(story, "formulas", "formula_story.")
    if formulas != record_formulas:
        raise ValueError("formula_story.formulas must exactly preserve committed formulas and order")
    require_text(story, "center_label", "formula_story.")
    require_text(story, "collaboration", "formula_story.")
    validate_text_list(
        require_list(story, "execution_unknowns", "formula_story."),
        "formula_story.execution_unknowns",
    )

    formula_by_id: dict[str, dict[str, Any]] = {}
    for formula in record_formulas:
        if not isinstance(formula, dict):
            raise ValueError("committed formulas must contain objects")
        formula_id = require_text(formula, "formula_id", "formulas[].")
        formula_by_id[formula_id] = formula

    group_ids: set[str] = set()
    groups = require_list(story, "responsibility_groups", "formula_story.")
    if not groups:
        raise ValueError("formula_story.responsibility_groups must not be empty")
    covered_composition: dict[str, set[int]] = {formula_id: set() for formula_id in formula_by_id}
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"formula_story.responsibility_groups[{index}] must be an object")
        group_id = require_text(group, "group_id", f"formula_story.responsibility_groups[{index}].")
        require_declarative_text(group, "title", f"formula_story.responsibility_groups[{index}].")
        require_text(group, "detail", f"formula_story.responsibility_groups[{index}].")
        formula_id = require_text(group, "formula_id", f"formula_story.responsibility_groups[{index}].")
        if group_id in group_ids:
            raise ValueError(f"formula_story contains duplicate group_id {group_id!r}")
        group_ids.add(group_id)
        if formula_id not in formula_by_id:
            raise ValueError(f"formula_story group references unknown formula_id {formula_id!r}")
        composition = source_list(formula_by_id[formula_id], "composition")
        indexes = require_list(
            group, "composition_indexes", f"formula_story.responsibility_groups[{index}]."
        )
        if not indexes:
            raise ValueError(f"formula_story.responsibility_groups[{index}].composition_indexes is empty")
        for composition_index in indexes:
            if not isinstance(composition_index, int) or not 0 <= composition_index < len(composition):
                raise ValueError(
                    f"formula_story.responsibility_groups[{index}].composition_indexes contains an invalid index"
                )
            covered_composition[formula_id].add(composition_index)
    for formula_id, formula in formula_by_id.items():
        expected_indexes = set(range(len(source_list(formula, "composition"))))
        if covered_composition[formula_id] != expected_indexes:
            raise ValueError(
                f"formula_story.responsibility_groups must cover every composition item in {formula_id}"
            )


def validate_observation_story(projection: dict[str, Any], outcome: dict[str, Any]) -> None:
    source_progression = source_list(outcome, "day_progression")
    story = optional_object(projection, "observation_story")
    if not source_progression:
        if story is not None:
            raise ValueError("observation_story must be absent when outcome has no day_progression")
        return
    if story is None:
        raise ValueError("observation_story is required when outcome has day_progression")
    require_text(story, "premise", "observation_story.")
    require_text(story, "reassessment_trigger", "observation_story.")
    progression = require_list(story, "progression", "observation_story.")
    seen: set[int] = set()
    for index, stage in enumerate(progression):
        if not isinstance(stage, dict):
            raise ValueError(f"observation_story.progression[{index}] must be an object")
        source_index = stage.get("source_day_index")
        if not isinstance(source_index, int) or not 0 <= source_index < len(source_progression):
            raise ValueError(f"observation_story.progression[{index}].source_day_index is invalid")
        if source_index in seen:
            raise ValueError("observation_story.progression contains a duplicate source_day_index")
        seen.add(source_index)
        for key in ("stage", "identity", "positive", "contrary"):
            require_text(stage, key, f"observation_story.progression[{index}].")
        expected_identity = source_progression[source_index].get("identity")
        if stage["identity"] != expected_identity:
            raise ValueError(f"observation_story.progression[{index}].identity does not match outcome")
    if seen != set(range(len(source_progression))):
        raise ValueError("observation_story.progression must cover every committed day_progression item")


def validate_classic_story(projection: dict[str, Any], record: dict[str, Any]) -> None:
    story = optional_object(projection, "classic_story")
    task_type = record.get("task_type")
    if task_type != "classic_interpretation":
        if story is not None:
            raise ValueError("classic_story is only allowed for classic_interpretation")
        return
    if story is None:
        raise ValueError("classic_story is required for classic_interpretation")
    require_text(story, "interpretation_focus", "classic_story.")
    sources = source_list(record, "sources")
    passages = require_list(story, "source_passages", "classic_story.")
    seen: set[int] = set()
    for index, passage in enumerate(passages):
        if not isinstance(passage, dict):
            raise ValueError(f"classic_story.source_passages[{index}] must be an object")
        source_index = passage.get("source_index")
        if not isinstance(source_index, int) or not 0 <= source_index < len(sources):
            raise ValueError(f"classic_story.source_passages[{index}].source_index is invalid")
        if source_index in seen:
            raise ValueError("classic_story.source_passages contains a duplicate source_index")
        seen.add(source_index)
        excerpt = require_text(passage, "excerpt", f"classic_story.source_passages[{index}].")
        require_text(passage, "explanation", f"classic_story.source_passages[{index}].")
        if excerpt != sources[source_index].get("excerpt"):
            raise ValueError(f"classic_story.source_passages[{index}].excerpt must copy its source")
    if seen != set(range(len(sources))):
        raise ValueError("classic_story.source_passages must cover every committed source")

    concepts = require_list(story, "concepts", "classic_story.")
    if not 1 <= len(concepts) <= 6:
        raise ValueError("classic_story.concepts length must be 1..6")
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            raise ValueError(f"classic_story.concepts[{index}] must be an object")
        require_declarative_text(concept, "title", f"classic_story.concepts[{index}].")
        require_text(concept, "explanation", f"classic_story.concepts[{index}].")

    relationships = require_list(story, "relationships", "classic_story.")
    for index, relation in enumerate(relationships):
        if not isinstance(relation, dict):
            raise ValueError(f"classic_story.relationships[{index}] must be an object")
        for key in ("from", "to", "relation", "boundary"):
            require_text(relation, key, f"classic_story.relationships[{index}].")


def validate_followup_story(projection: dict[str, Any], record: dict[str, Any]) -> None:
    story = optional_object(projection, "followup_story")
    task_type = record.get("task_type")
    if task_type != "followup":
        if story is not None:
            raise ValueError("followup_story is only allowed for followup")
        return
    if story is None:
        raise ValueError("followup_story is required for followup")
    case_context = require_object(record, "case_context")
    for key in ("case_id", "turn_id", "parent_turn_id"):
        if story.get(key) != case_context.get(key):
            raise ValueError(f"followup_story.{key} does not match committed case_context")
    for key in ("comparison_summary", "retained_judgment", "current_adjustment"):
        require_text(story, key, "followup_story.")
    source_facts = source_list(require_object(record, "input"), "confirmed_facts")
    changes = require_list(story, "observed_changes", "followup_story.")
    if source_facts and not changes:
        raise ValueError("followup_story.observed_changes must not be empty when confirmed facts exist")
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            raise ValueError(f"followup_story.observed_changes[{index}] must be an object")
        require_text(change, "text", f"followup_story.observed_changes[{index}].")
        if change.get("status") not in {"improved", "worsened", "unchanged", "uncertain"}:
            raise ValueError(f"followup_story.observed_changes[{index}].status is unsupported")
        indexes = require_list(change, "source_indexes", f"followup_story.observed_changes[{index}].")
        if not indexes:
            raise ValueError(f"followup_story.observed_changes[{index}].source_indexes is empty")
        for source_index in indexes:
            if not isinstance(source_index, int) or not 0 <= source_index < len(source_facts):
                raise ValueError(
                    f"followup_story.observed_changes[{index}].source_indexes contains an invalid index"
                )


def validate_audit_receipt(projection: dict[str, Any], record: dict[str, Any]) -> None:
    receipt = require_object(projection, "audit_receipt")
    if not isinstance(receipt.get("performed"), bool):
        raise ValueError("audit_receipt.performed must be a boolean")
    resolution = receipt.get("resolution")
    if resolution not in AUDIT_RESOLUTIONS:
        raise ValueError("audit_receipt.resolution is unsupported")
    public_summary = receipt.get("public_summary")
    if not isinstance(public_summary, str):
        raise ValueError("audit_receipt.public_summary must be a string")

    reasoning = require_object(record, "reasoning")
    red_team = reasoning.get("red_team")
    stage_c = reasoning.get("stage_c")
    unresolved = source_list(reasoning, "unresolved_conflicts")
    has_red_team = isinstance(red_team, dict)
    has_stage_c = isinstance(stage_c, dict)
    if receipt["performed"] != has_red_team:
        raise ValueError("audit_receipt.performed does not match committed red_team state")
    expected_resolution = (
        "unresolved" if unresolved else "corrected" if has_stage_c else "retained" if has_red_team else "not_performed"
    )
    if resolution != expected_resolution:
        raise ValueError("audit_receipt.resolution does not match committed red_team/Stage C state")
    if has_red_team and not public_summary.strip():
        raise ValueError("audit_receipt.public_summary is required after red-team review")
    if not has_red_team and public_summary.strip():
        raise ValueError("audit_receipt.public_summary must be empty when red-team review was not performed")


def validate_projection(projection: dict[str, Any], record: dict[str, Any]) -> None:
    if projection.get("schema_version") != "1.0":
        raise ValueError("schema_version must be 1.0")
    if record.get("committed") is not True:
        raise ValueError("record must be a committed analysis")

    identity = require_object(projection, "identity")
    outcome = require_object(record, "outcome")
    expected_identity = {
        "run_id": record.get("run_id"),
        "result_id": outcome.get("result_id"),
        "task_type": record.get("task_type"),
        "subject": require_object(record, "input").get("subject"),
        "result_identity": outcome.get("identity"),
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise ValueError(f"identity.{key} does not match committed analysis")

    header = require_object(projection, "report_header")
    for key in ("primary_title", "scope_label", "brand_signature"):
        require_text(header, key, "report_header.")
    require_declarative_text(header, "primary_title", "report_header.")
    if header["primary_title"].strip() == header["brand_signature"].strip():
        raise ValueError("brand_signature must not replace the report's content title")

    summary = require_object(projection, "reader_summary")
    require_text(summary, "key_message", "reader_summary.")
    validate_text_list(
        require_list(summary, "key_relations", "reader_summary."),
        "reader_summary.key_relations",
        minimum=2,
        maximum=4,
    )
    validate_text_list(
        require_list(summary, "current_concerns", "reader_summary."),
        "reader_summary.current_concerns",
    )
    require_text(summary, "pattern_explanation", "reader_summary.")
    for optional_key in ("treatment_strategy", "formula_summary", "observation_summary"):
        if optional_key in summary and (
            not isinstance(summary[optional_key], str) or not summary[optional_key].strip()
        ):
            raise ValueError(f"reader_summary.{optional_key} must be non-empty when present")

    professional = require_object(projection, "professional_judgment")
    validate_professional_item(
        require_object(professional, "r0_relation", "professional_judgment."),
        record,
        "professional_judgment.r0_relation",
        {"r0", "stage_c"},
    )
    r1_pattern = optional_object(professional, "r1_pattern")
    has_r1 = isinstance(require_object(record, "reasoning").get("r1"), dict)
    if has_r1 and r1_pattern is None:
        raise ValueError("professional_judgment.r1_pattern is required when final R1 exists")
    if not has_r1 and r1_pattern is not None:
        raise ValueError("professional_judgment.r1_pattern is forbidden when final R1 is absent")
    if r1_pattern is not None:
        validate_professional_item(
            r1_pattern,
            record,
            "professional_judgment.r1_pattern",
            {"r1", "stage_c"},
        )
    require_text(professional, "applicability_scope", "professional_judgment.")

    input_data = require_object(record, "input")
    fact_base = require_object(projection, "fact_base")
    validate_mapped_items(
        require_list(fact_base, "confirmed_facts", "fact_base."),
        source_list(input_data, "confirmed_facts"),
        "fact_base.confirmed_facts",
    )
    validate_mapped_items(
        require_list(fact_base, "ambiguous_facts", "fact_base."),
        source_list(input_data, "ambiguous_facts"),
        "fact_base.ambiguous_facts",
    )
    validate_mapped_items(
        require_list(fact_base, "missing_facts", "fact_base."),
        source_list(outcome, "minimum_questions"),
        "fact_base.missing_facts",
    )
    validate_mapped_items(
        require_list(fact_base, "scope_items", "fact_base."),
        source_list(input_data, "scope"),
        "fact_base.scope_items",
        require_id=False,
    )

    explanation = require_object(projection, "explanation_story")
    require_text(explanation, "core_mechanism", "explanation_story.")
    validate_relationship_model(explanation)
    validate_text_list(
        require_list(explanation, "supporting_conditions", "explanation_story."),
        "explanation_story.supporting_conditions",
    )
    validate_text_list(
        require_list(explanation, "contrary_conditions", "explanation_story."),
        "explanation_story.contrary_conditions",
    )

    treatment_story = optional_object(projection, "treatment_story")
    has_r2 = isinstance(require_object(record, "reasoning").get("r2"), dict)
    if has_r2 and treatment_story is None:
        raise ValueError("treatment_story is required when final R2 exists")
    if not has_r2 and treatment_story is not None:
        raise ValueError("treatment_story is forbidden when final R2 is absent")
    validate_treatment_story(projection)
    validate_formula_story(projection, record)
    validate_observation_story(projection, outcome)
    validate_classic_story(projection, record)
    validate_followup_story(projection, record)

    boundaries = require_object(projection, "boundaries")
    validate_mapped_items(
        require_list(boundaries, "risks", "boundaries."),
        source_list(outcome, "risks"),
        "boundaries.risks",
        require_id=False,
    )
    validate_mapped_items(
        require_list(boundaries, "minimum_questions", "boundaries."),
        source_list(outcome, "minimum_questions"),
        "boundaries.minimum_questions",
        require_id=False,
    )
    validate_mapped_items(
        require_list(boundaries, "unresolved_conflicts", "boundaries."),
        source_list(require_object(record, "reasoning"), "unresolved_conflicts"),
        "boundaries.unresolved_conflicts",
        require_id=False,
    )

    if require_list(projection, "sources") != source_list(record, "sources"):
        raise ValueError("sources must exactly preserve committed analysis sources and order")
    validate_audit_receipt(projection, record)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    projection_bytes = args.projection.read_bytes()
    projection = json.loads(projection_bytes.decode("utf-8"))
    if not isinstance(projection, dict):
        raise ValueError(f"JSON root must be an object: {args.projection}")
    record = load_object(args.record)
    validate_projection(projection, record)
    digest = hashlib.sha256(projection_bytes).hexdigest()
    identity = projection["identity"]
    print(
        f"PASS: valid presentation projection for {identity['run_id']}/{identity['result_id']} "
        f"sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
