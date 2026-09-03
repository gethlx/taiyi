#!/usr/bin/env python3
"""Validate deterministic structure and same-result binding for an H5 view model."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from validate_presentation_projection import validate_projection


LINK_KINDS = {"primary", "conditional", "unknown"}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def require_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def require_text(parent: dict[str, Any], key: str, prefix: str = "") -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}{key} must be a non-empty string")
    return value


def require_list(parent: dict[str, Any], key: str, prefix: str = "") -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{prefix}{key} must be an array")
    return value


def validate_text_list(items: list[Any], label: str, *, minimum: int = 0, maximum: int | None = None) -> None:
    if len(items) < minimum or (maximum is not None and len(items) > maximum):
        limit = f"{minimum}..{maximum}" if maximum is not None else f">={minimum}"
        raise ValueError(f"{label} length must be {limit}")
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{label} must contain only non-empty strings")


def validate_named_items(items: list[Any], label: str, detail_key: str) -> None:
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        title = require_text(item, "title", f"{label}[{index}].")
        if "?" in title or "？" in title:
            raise ValueError(f"{label}[{index}].title must be declarative")
        require_text(item, detail_key, f"{label}[{index}].")


def projection_texts(parent: dict[str, Any], key: str) -> list[str]:
    items = require_list(parent, key, f"{key}.")
    texts: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"projection {key}[{index}] must be an object")
        texts.append(require_text(item, "text", f"projection {key}[{index}]."))
    return texts


def validate_adapted_text_sequence(
    items: Any, expected_count: int, label: str, *, preserve_count: bool = False
) -> None:
    if not isinstance(items, list):
        raise ValueError(f"{label} must be an array")
    validate_text_list(items, label)
    if expected_count == 0 and items:
        raise ValueError(f"{label} is forbidden when the projection has no source items")
    if expected_count > 0 and not items:
        raise ValueError(f"{label} must represent its projection source items")
    if preserve_count and len(items) != expected_count:
        raise ValueError(f"{label} must preserve projection structure count {expected_count}")


def validate_projection_binding(
    model: dict[str, Any], projection: dict[str, Any], projection_sha256: str
) -> None:
    identity = require_object(model, "identity")
    projection_identity = require_object(projection, "identity")
    expected_identity = {
        "runId": projection_identity.get("run_id"),
        "resultId": projection_identity.get("result_id"),
        "taskType": projection_identity.get("task_type"),
        "resultIdentity": projection_identity.get("result_identity"),
        "projectionSchemaVersion": projection.get("schema_version"),
        "projectionSha256": projection_sha256,
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise ValueError(f"identity.{key} does not match the validated presentation projection")

    header = require_object(model, "header")
    projection_header = require_object(projection, "report_header")
    header_mapping = {"scopeLabel": "scope_label", "brandSignature": "brand_signature"}
    for view_key, projection_key in header_mapping.items():
        if header.get(view_key) != projection_header.get(projection_key):
            raise ValueError(f"header.{view_key} must be copied from presentation projection")
    require_text(header, "title", "header.")

    summary = require_object(projection, "reader_summary")
    overview = require_object(model, "overview")
    require_text(overview, "summary", "overview.")
    if overview.get("summary") != summary.get("key_message"):
        raise ValueError(
            "overview.summary must be copied from presentation projection key_message"
        )
    validate_adapted_text_sequence(
        header.get("flow"),
        len(require_list(summary, "key_relations")),
        "header.flow",
        preserve_count=True,
    )

    relationship_model = require_object(
        require_object(projection, "explanation_story"), "relationship_model"
    )
    projection_nodes = require_list(relationship_model, "nodes")
    model_nodes = require_list(overview, "nodes", "overview.")
    if len(model_nodes) != len(projection_nodes):
        raise ValueError("overview.nodes must preserve projection relationship node count")
    node_indexes = {
        node.get("node_id"): index for index, node in enumerate(projection_nodes) if isinstance(node, dict)
    }
    expected_links = [
        {"from": node_indexes.get(edge.get("from")), "to": node_indexes.get(edge.get("to")), "kind": edge.get("kind")}
        for edge in require_list(relationship_model, "edges")
        if isinstance(edge, dict)
    ]
    if overview.get("links") != expected_links:
        raise ValueError("overview.links must be copied from presentation projection relationship edges")

    fact_base = require_object(projection, "fact_base")
    facts = require_object(model, "facts")
    expected_confirmed = projection_texts(fact_base, "confirmed_facts")
    expected_unknown = projection_texts(fact_base, "ambiguous_facts") + projection_texts(
        fact_base, "missing_facts"
    )
    validate_adapted_text_sequence(facts.get("confirmed"), len(expected_confirmed), "facts.confirmed")
    validate_adapted_text_sequence(facts.get("unknown"), len(expected_unknown), "facts.unknown")

    professional = require_object(model, "professional")
    judgment = require_object(projection, "professional_judgment")
    r0 = require_object(judgment, "r0_relation")
    if professional.get("r0Excerpt") != r0.get("original_excerpt"):
        raise ValueError("professional.r0Excerpt must copy the projection professional excerpt")
    require_text(professional, "r0Explanation", "professional.")
    require_text(professional, "scope", "professional.")
    r1 = judgment.get("r1_pattern")
    if isinstance(r1, dict):
        if professional.get("r1Excerpt") != r1.get("original_excerpt"):
            raise ValueError("professional.r1Excerpt must copy the projection professional excerpt")
        require_text(professional, "r1Label", "professional.")
        require_text(professional, "r1Explanation", "professional.")
    elif any(key in professional for key in ("r1Label", "r1Excerpt", "r1Explanation")):
        raise ValueError("professional R1 fields are forbidden when presentation projection has no R1")

    expected_steps = require_list(require_object(projection, "explanation_story"), "causal_chain")
    validate_adapted_text_sequence(
        require_object(model, "mechanism").get("steps"),
        len(expected_steps),
        "mechanism.steps",
        preserve_count=True,
    )

    treatment_story = projection.get("treatment_story")
    treatment = model.get("treatment")
    if isinstance(treatment_story, dict):
        if not isinstance(treatment, dict):
            raise ValueError("treatment is required when presentation projection has treatment_story")
        require_text(treatment, "centerLabel", "treatment.")
        if len(require_list(treatment, "items", "treatment.")) != len(require_list(treatment_story, "goals")):
            raise ValueError("treatment.items must preserve projection treatment goal count")
    elif treatment is not None:
        raise ValueError("treatment is forbidden when presentation projection has no treatment_story")

    formula_story = projection.get("formula_story")
    formula = model.get("formula")
    if isinstance(formula_story, dict):
        if not isinstance(formula, dict):
            raise ValueError("formula is required when presentation projection has formula_story")
        expected_groups = require_list(formula_story, "responsibility_groups")
        expected_ingredients: list[str] = []
        expected_execution: list[str] = []
        for source_formula in require_list(formula_story, "formulas"):
            if not isinstance(source_formula, dict):
                continue
            expected_ingredients.extend(
                ingredient.get("raw_text")
                for ingredient in require_list(source_formula, "composition")
                if isinstance(ingredient, dict)
            )
            for key in ("preparation_text", "administration_text"):
                value = source_formula.get(key)
                if isinstance(value, str) and value.strip():
                    expected_execution.append(value)
        expected_execution.extend(require_list(formula_story, "execution_unknowns"))
        require_text(formula, "lead", "formula.")
        require_text(formula, "centerLabel", "formula.")
        if len(require_list(formula, "groups", "formula.")) != len(expected_groups):
            raise ValueError("formula.groups must preserve projection responsibility group count")
        if formula.get("ingredients") != expected_ingredients:
            raise ValueError("formula.ingredients must copy projection formula raw text in order")
        if formula.get("executionFacts") != expected_execution:
            raise ValueError("formula.executionFacts must copy projection execution facts in order")
    elif formula is not None:
        raise ValueError("formula is forbidden when presentation projection has no formula_story")

    observation_story = projection.get("observation_story")
    observation = model.get("observation")
    if isinstance(observation_story, dict):
        if not isinstance(observation, dict):
            raise ValueError("observation is required when presentation projection has observation_story")
        require_text(observation, "premise", "observation.")
        if len(require_list(observation, "stages", "observation.")) != len(
            require_list(observation_story, "progression")
        ):
            raise ValueError("observation.stages must preserve projection progression count")
    elif observation is not None:
        raise ValueError("observation is forbidden when presentation projection has no observation_story")

    projection_boundaries = require_object(projection, "boundaries")
    boundaries = require_object(model, "boundaries")
    expected_supported = projection_texts(projection_boundaries, "risks")
    expected_questions = projection_texts(projection_boundaries, "minimum_questions")
    validate_adapted_text_sequence(boundaries.get("supported"), len(expected_supported), "boundaries.supported")
    validate_adapted_text_sequence(boundaries.get("questions"), len(expected_questions), "boundaries.questions")
    audit_receipt = require_object(projection, "audit_receipt")
    if audit_receipt.get("performed"):
        require_text(boundaries, "auditSummary", "boundaries.")
    elif "auditTitle" in boundaries or "auditSummary" in boundaries:
        raise ValueError("H5 audit receipt is forbidden when red-team review was not performed")


def validate_view_model(
    model: dict[str, Any],
    record: dict[str, Any] | None,
    projection: dict[str, Any] | None,
    projection_sha256: str | None,
) -> None:
    if model.get("schemaVersion") != "1.0":
        raise ValueError("schemaVersion must be 1.0")

    identity = require_object(model, "identity")
    for key in (
        "runId",
        "resultId",
        "taskType",
        "resultIdentity",
        "projectionSchemaVersion",
        "projectionSha256",
    ):
        require_text(identity, key, "identity.")
    if record is not None:
        expected = {
            "runId": record.get("run_id"),
            "resultId": require_object(record, "outcome").get("result_id"),
            "taskType": record.get("task_type"),
            "resultIdentity": require_object(record, "outcome").get("identity"),
        }
        for key, value in expected.items():
            if identity[key] != value:
                raise ValueError(f"identity.{key} does not match committed analysis")
    if projection is not None and projection_sha256 is not None:
        validate_projection_binding(model, projection, projection_sha256)

    header = require_object(model, "header")
    for key in ("title", "scopeLabel", "brandSignature", "heroVisual", "heroAlt"):
        require_text(header, key, "header.")
    if "?" in header["title"] or "？" in header["title"]:
        raise ValueError("header.title must be declarative, not a question")
    flow = require_list(header, "flow", "header.")
    validate_text_list(flow, "header.flow", minimum=2, maximum=4)
    link_kinds = header.get("linkKinds", [])
    if not isinstance(link_kinds, list) or len(link_kinds) > len(flow) - 1:
        raise ValueError("header.linkKinds must be an array no longer than flow edges")
    if any(kind not in LINK_KINDS for kind in link_kinds):
        raise ValueError("header.linkKinds contains an unsupported relation kind")

    overview = require_object(model, "overview")
    require_text(overview, "summary", "overview.")
    nodes = require_list(overview, "nodes", "overview.")
    if not 2 <= len(nodes) <= 6:
        raise ValueError("overview.nodes length must be 2..6")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"overview.nodes[{index}] must be an object")
        require_text(node, "label", f"overview.nodes[{index}].")
        require_text(node, "detail", f"overview.nodes[{index}].")
    links = require_list(overview, "links", "overview.")
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            raise ValueError(f"overview.links[{index}] must be an object")
        if link.get("kind") not in LINK_KINDS:
            raise ValueError(f"overview.links[{index}].kind is unsupported")
        for endpoint in ("from", "to"):
            value = link.get(endpoint)
            if not isinstance(value, int) or not 0 <= value < len(nodes):
                raise ValueError(f"overview.links[{index}].{endpoint} is out of range")

    facts = require_object(model, "facts")
    validate_text_list(require_list(facts, "confirmed", "facts."), "facts.confirmed")
    validate_text_list(require_list(facts, "unknown", "facts."), "facts.unknown")

    professional = require_object(model, "professional")
    for key in ("r0Excerpt", "r0Explanation", "scope"):
        require_text(professional, key, "professional.")
    r1_values = [professional.get(key) for key in ("r1Label", "r1Excerpt", "r1Explanation")]
    if any(value is not None for value in r1_values):
        if any(not isinstance(value, str) or not value.strip() for value in r1_values):
            raise ValueError("professional R1 fields must be all present and non-empty")
        if "?" in professional["r1Label"] or "？" in professional["r1Label"]:
            raise ValueError("professional.r1Label must be declarative")

    mechanism = require_object(model, "mechanism")
    validate_text_list(require_list(mechanism, "steps", "mechanism."), "mechanism.steps", maximum=5)

    treatment = model.get("treatment")
    if treatment is not None:
        if not isinstance(treatment, dict):
            raise ValueError("treatment must be an object when present")
        require_text(treatment, "centerLabel", "treatment.")
        items = require_list(treatment, "items", "treatment.")
        if not 1 <= len(items) <= 6:
            raise ValueError("treatment.items length must be 1..6")
        validate_named_items(items, "treatment.items", "detail")

    formula = model.get("formula")
    if formula is not None:
        if not isinstance(formula, dict):
            raise ValueError("formula must be an object when present")
        for key in ("lead", "centerLabel"):
            require_text(formula, key, "formula.")
        groups = require_list(formula, "groups", "formula.")
        if not 1 <= len(groups) <= 6:
            raise ValueError("formula.groups length must be 1..6")
        validate_named_items(groups, "formula.groups", "detail")
        validate_text_list(require_list(formula, "ingredients", "formula."), "formula.ingredients", minimum=1)
        validate_text_list(require_list(formula, "executionFacts", "formula."), "formula.executionFacts")

    observation = model.get("observation")
    if observation is not None:
        if not isinstance(observation, dict):
            raise ValueError("observation must be an object when present")
        require_text(observation, "premise", "observation.")
        stages = require_list(observation, "stages", "observation.")
        if not 1 <= len(stages) <= 5:
            raise ValueError("observation.stages length must be 1..5")
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                raise ValueError(f"observation.stages[{index}] must be an object")
            for key in ("label", "positive", "contrary"):
                require_text(stage, key, f"observation.stages[{index}].")

    boundaries = require_object(model, "boundaries")
    validate_text_list(require_list(boundaries, "supported", "boundaries."), "boundaries.supported", minimum=1)
    validate_text_list(require_list(boundaries, "questions", "boundaries."), "boundaries.questions")
    audit_title = boundaries.get("auditTitle")
    audit_summary = boundaries.get("auditSummary")
    if audit_title is not None or audit_summary is not None:
        if not isinstance(audit_title, str) or not audit_title.strip():
            raise ValueError("boundaries.auditTitle must be non-empty when present")
        if not isinstance(audit_summary, str) or not audit_summary.strip():
            raise ValueError("boundaries.auditSummary must be non-empty when present")
        if "?" in audit_title or "？" in audit_title:
            raise ValueError("boundaries.auditTitle must be declarative")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--view-model", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model = load_object(args.view_model)
    record = load_object(args.record) if args.record else None
    projection_bytes = args.projection.read_bytes()
    projection = json.loads(projection_bytes.decode("utf-8"))
    if not isinstance(projection, dict):
        raise ValueError(f"JSON root must be an object: {args.projection}")
    projection_sha256 = hashlib.sha256(projection_bytes).hexdigest()
    validate_projection(projection, record)
    validate_view_model(model, record, projection, projection_sha256)
    identity = model["identity"]
    print(f"PASS: valid H5 view model for {identity['runId']}/{identity['resultId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
