#!/usr/bin/env python3
"""Inspect and validate the textual grammar reconstructed from Tangye Jingfa Tu.

This tool verifies source anchors, graph invariants, and curated Jingfang
counterexamples. It validates the Tangye rule layer and does not itself run the
GEM diagnostic, scoring, or prescription workflow.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
RULES_PATH = WORKSPACE / "kb" / "assets" / "辅行诀" / "经法规则.json"
GRAPH_PATH = WORKSPACE / "kb" / "assets" / "辅行诀" / "汤液图.json"
RULES_MD_PATH = WORKSPACE / "kb" / "assets" / "辅行诀" / "经法规则.md"
ANCHOR_RE = re.compile(r'^<a id="([^"]+)"></a>$')
HEADING_RE = re.compile(r"^###\s+(.+?)(?:方)?$")
FLAVORS = {"辛", "咸", "甘", "酸", "苦"}
ELEMENTS = {"木", "火", "土", "金", "水"}


def compact(text: str) -> str:
    """Normalize formatting while preserving Chinese characters."""
    return re.sub(r"[\s（）()，。、；：‘’“”\"'<>/=_—+、·-]+", "", text)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_anchor_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        match = ANCHOR_RE.fullmatch(line.strip())
        if match:
            starts.append((match.group(1), index))
    blocks: dict[str, str] = {}
    for position, (anchor, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        blocks[anchor] = "\n".join(lines[start + 1 : end]).strip()
    return blocks


def heading_from_block(block: str) -> str | None:
    for line in block.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def unordered_pair(values: list[str]) -> frozenset[str]:
    return frozenset(values)


def validate_pair_space(rules: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pair_space = rules.get("pair_space", {})
    flavors = pair_space.get("flavors", [])
    if set(flavors) != FLAVORS or len(flavors) != 5:
        errors.append("pair-space flavors must be the five unique Jingfa flavors")

    transformations = pair_space.get("transformations", [])
    eliminations = pair_space.get("eliminations", [])
    if len(transformations) != 5 or len(eliminations) != 5:
        errors.append("pair space must contain five transformations and five eliminations")

    transform_pairs = [unordered_pair(item.get("inputs", [])) for item in transformations]
    elimination_pairs = [unordered_pair(item.get("inputs", [])) for item in eliminations]
    all_expected = {
        frozenset(pair) for pair in itertools.combinations(FLAVORS, 2)
    }
    if any(len(pair) != 2 for pair in transform_pairs + elimination_pairs):
        errors.append("every graph relation must contain two distinct flavors")
    if len(set(transform_pairs)) != 5 or len(set(elimination_pairs)) != 5:
        errors.append("transformation or elimination pairs are duplicated")
    if set(transform_pairs) & set(elimination_pairs):
        errors.append("transformation and elimination pair sets must be disjoint")
    if set(transform_pairs) | set(elimination_pairs) != all_expected:
        errors.append("five transformations plus five eliminations must cover all ten pairs")
    if pair_space.get("expected_unordered_distinct_pair_count") != 10:
        errors.append("pair-space expected count must be ten")

    for relation_name, pairs in (
        ("transformations", transform_pairs),
        ("eliminations", elimination_pairs),
    ):
        counts = {flavor: sum(flavor in pair for pair in pairs) for flavor in FLAVORS}
        if set(counts.values()) != {2}:
            errors.append(f"every flavor must occur twice in {relation_name}: {counts}")

    acid_sweet = [
        item for item in eliminations
        if unordered_pair(item.get("inputs", [])) == frozenset({"酸", "甘"})
    ]
    if len(acid_sweet) != 1:
        errors.append("acid-sweet elimination relation must occur exactly once")
    else:
        item = acid_sweet[0]
        if item.get("effect") is not None:
            errors.append("acid-sweet effect must remain inactive, not be silently selected")
        if item.get("certainty") != "B" or item.get("reading") != "酸甘除□":
            errors.append("acid-sweet relation must retain the transcribed blank and boundary status")

    graph_transforms = {
        (unordered_pair(item.get("inputs", [])), item.get("output"))
        for item in graph.get("flavor_transformations", [])
    }
    rule_transforms = {
        (unordered_pair(item.get("inputs", [])), item.get("output"))
        for item in transformations
    }
    if graph_transforms != rule_transforms:
        errors.append("core transformation rules differ from graph transcription")

    graph_eliminations = {
        unordered_pair(item.get("inputs", [])): item.get("effect")
        for item in graph.get("elimination_pairs", [])
    }
    rule_eliminations = {
        unordered_pair(item.get("inputs", [])): item.get("effect")
        for item in eliminations
    }
    if graph_eliminations != rule_eliminations:
        errors.append("core elimination rules differ from graph transcription")
    return errors


def validate_organs_and_matrix(rules: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_organs = {
        "肝": ("木", "辛", "酸", "甘"),
        "心": ("火", "咸", "苦", "酸"),
        "脾": ("土", "甘", "辛", "苦"),
        "肺": ("金", "酸", "咸", "辛"),
        "肾": ("水", "苦", "甘", "咸"),
    }
    actual_organs = {
        item.get("organ"): (
            item.get("element"),
            item.get("use_tonify"),
            item.get("body_drain"),
            item.get("transform"),
        )
        for item in rules.get("organ_relations", [])
    }
    if actual_organs != expected_organs:
        errors.append("organ use/body/transform relations differ from the five-organ text")

    graph_organs = {
        item.get("脏"): (item.get("五行"), item.get("用"), item.get("体"), item.get("化"))
        for item in graph.get("zang_relations", [])
    }
    if graph_organs != expected_organs:
        errors.append("graph transcription differs from core organ relations")

    matrix = rules.get("twenty_five_drug_matrix", [])
    if len(matrix) != 5 or {item.get("flavor") for item in matrix} != FLAVORS:
        errors.append("twenty-five-drug matrix must contain five flavor rows")
        return errors
    drugs: list[str] = []
    for row in matrix:
        positions = row.get("by_nested_element", {})
        if set(positions) != ELEMENTS:
            errors.append(f"matrix row {row.get('flavor')} must contain all five elements")
            continue
        if positions.get(row.get("primary_element")) != row.get("master"):
            errors.append(f"matrix master does not occupy its primary element: {row.get('flavor')}")
        drugs.extend(positions.values())
    if len(drugs) != 25 or len(set(drugs)) != 25:
        errors.append("twenty-five-drug matrix must contain 25 unique positions")
    return errors


def validate_direct_evidence(rules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source_specs = rules.get("sources", {})
    source_texts: dict[str, str] = {}
    source_blocks: dict[str, dict[str, str]] = {}
    for key in ("fuxingjue", "shennong_bencao"):
        path = WORKSPACE / source_specs.get(key, {}).get("path", "")
        if not path.is_file():
            errors.append(f"missing direct-evidence source: {key}")
            continue
        source_texts[key] = path.read_text(encoding="utf-8")
        source_blocks[key] = parse_anchor_blocks(source_texts[key])

    evidence_ids: set[str] = set()
    for item in rules.get("direct_evidence", []):
        evidence_id = item.get("id")
        if not evidence_id or evidence_id in evidence_ids:
            errors.append(f"missing or duplicated direct-evidence ID: {evidence_id}")
            continue
        evidence_ids.add(evidence_id)
        source_key = item.get("source")
        source_text = source_texts.get(source_key, "")
        anchor = item.get("anchor")
        if anchor:
            source_text = source_blocks.get(source_key, {}).get(anchor, "")
            if not source_text:
                errors.append(f"missing direct-evidence anchor {anchor} for {evidence_id}")
                continue
        needle = item.get("contains", "")
        if not needle or compact(needle) not in compact(source_text):
            errors.append(f"direct-evidence text absent for {evidence_id}")
    return errors


def validate_formula_cases(rules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    corpus_path = WORKSPACE / rules.get("sources", {}).get("jingfang", {}).get("path", "")
    if not corpus_path.is_file():
        return ["missing Jingfang corpus"]
    blocks = parse_anchor_blocks(corpus_path.read_text(encoding="utf-8"))
    cases = rules.get("validation_cases", [])
    if len(cases) != 12:
        errors.append("validation set must contain twelve formula instances")
    if rules.get("validation_summary", {}).get("formula_instance_count") != len(cases):
        errors.append("validation summary formula count differs")

    matrix_map: dict[str, str] = {}
    for row in rules.get("twenty_five_drug_matrix", []):
        for drug in row.get("by_nested_element", {}).values():
            matrix_map[drug] = row.get("flavor")

    expected_rule_ids = {f"TG-{number:02d}" for number in range(1, 11)}
    rule_ids = {item.get("id") for item in rules.get("textual_rules", [])}
    if rule_ids != expected_rule_ids:
        errors.append("textual rule IDs must be TG-01 through TG-10")

    allowed_results = {
        "supports", "negative_control", "rejects_overextension",
        "boundary_signal", "supports_with_limit", "indirect_support",
    }
    case_ids: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        if not case_id or case_id in case_ids:
            errors.append(f"missing or duplicated case ID: {case_id}")
            continue
        case_ids.add(case_id)
        formula_anchor = case.get("formula_anchor")
        formula_block = blocks.get(formula_anchor, "")
        if not formula_block:
            errors.append(f"missing formula anchor for {case_id}: {formula_anchor}")
        else:
            actual_heading = heading_from_block(formula_block)
            expected_heading = case.get("source_heading_name", case.get("name"))
            if actual_heading != expected_heading:
                errors.append(
                    f"formula heading differs for {case_id}: expected {expected_heading}, got {actual_heading}"
                )

        indication_text = "\n".join(blocks.get(anchor, "") for anchor in case.get("indication_anchors", []))
        if not indication_text or any(anchor not in blocks for anchor in case.get("indication_anchors", [])):
            errors.append(f"missing indication evidence for {case_id}")
        elif compact(case.get("name", "")) not in compact(indication_text):
            errors.append(f"formula name absent from indication for {case_id}")

        composition_text = "\n".join(blocks.get(anchor, "") for anchor in case.get("composition_anchors", []))
        if not composition_text or any(anchor not in blocks for anchor in case.get("composition_anchors", [])):
            errors.append(f"missing composition evidence for {case_id}")
        for ingredient in case.get("mapped_ingredients", []):
            herb = ingredient.get("herb", "")
            matrix_token = ingredient.get("matrix_token", "")
            flavor = ingredient.get("flavor")
            if compact(herb) not in compact(composition_text):
                errors.append(f"mapped ingredient {herb} absent from composition for {case_id}")
            if matrix_map.get(matrix_token) != flavor:
                errors.append(f"matrix flavor differs for {case_id}: {matrix_token} -> {flavor}")
        for test in case.get("tests", []):
            if test.get("rule_id") not in rule_ids:
                errors.append(f"unknown rule in {case_id}: {test.get('rule_id')}")
            if test.get("result") not in allowed_results:
                errors.append(f"unknown test result in {case_id}: {test.get('result')}")

    if case_ids != {f"JF-{number:02d}" for number in range(1, 13)}:
        errors.append("validation case IDs must be JF-01 through JF-12")
    return errors


def validate_documents(rules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if rules.get("rule_set_id") != "tangye-graph-textual-grammar-v1":
        errors.append("active Tangye rule-set ID differs")
    if rules.get("status") != "current":
        errors.append("active Tangye rule set must have current status")
    if not RULES_MD_PATH.is_file():
        errors.append("missing Tangye textual-rule document")
    else:
        markdown = RULES_MD_PATH.read_text(encoding="utf-8")
        for token in ("五化", "五除", "TG-01", "TG-10", "经方辨错验证", "酸甘除□"):
            if token not in markdown:
                errors.append(f"Tangye rule document lacks required section token: {token}")
    return errors


def collect_errors(rules: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    return (
        validate_documents(rules)
        + validate_pair_space(rules, graph)
        + validate_organs_and_matrix(rules, graph)
        + validate_direct_evidence(rules)
        + validate_formula_cases(rules)
    )


def validate_or_exit(rules: dict[str, Any], graph: dict[str, Any]) -> None:
    errors = collect_errors(rules, graph)
    if errors:
        print(f"FAILED: {len(errors)} Tangye graph-rule error(s)")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(
        "PASS: five organ triads, all ten flavor pairs, 25 matrix positions, "
        "10 textual rules, direct evidence, and 12 Jingfang tests validated"
    )


def show_pairs(rules: dict[str, Any]) -> None:
    pair_space = rules["pair_space"]
    for item in pair_space["transformations"]:
        print(f"化\t{'+'.join(item['inputs'])}\t{item['output']}\t{item['organ']}")
    for item in pair_space["eliminations"]:
        effect = item.get("effect") or "□"
        print(f"除\t{'+'.join(item['inputs'])}\t{effect}\t{item['certainty']}")


def show_case(rules: dict[str, Any], case_id: str) -> None:
    cases = {item["case_id"]: item for item in rules["validation_cases"]}
    case = cases.get(case_id)
    if case is None:
        raise SystemExit(f"unknown case ID: {case_id}")
    print(f"{case['case_id']}\t{case['name']}")
    print("味位：" + "，".join(f"{item['herb']}={item['flavor']}" for item in case["mapped_ingredients"]))
    for test in case["tests"]:
        print(f"{test['rule_id']}\t{test['result']}\t{test['reason']}")
    print("边界：本命令只显示既有方例验证；完整组方须进入 GEM Stage A—C。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate graph invariants and source-backed tests")
    subparsers.add_parser("pairs", help="list the five transformation and five elimination pairs")
    case_parser = subparsers.add_parser("case", help="show one curated Jingfang test")
    case_parser.add_argument("case_id")
    args = parser.parse_args()

    rules = load_json(RULES_PATH)
    graph = load_json(GRAPH_PATH)
    if args.command == "validate":
        validate_or_exit(rules, graph)
    elif args.command == "pairs":
        show_pairs(rules)
    elif args.command == "case":
        show_case(rules, args.case_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
