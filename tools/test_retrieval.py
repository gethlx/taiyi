#!/usr/bin/env python3
"""Run real stage-2 evidence fixtures against the current source corpus."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from evidence_service import (
    EvidencePort,
    EvidenceRequestError,
    normalize_text,
    validate_evidence_result,
)


WORKSPACE = Path(__file__).resolve().parents[1]
FIXTURE_PATH = WORKSPACE / "spec" / "retrieval_tests.json"
SCHEMA_PATH = WORKSPACE / "spec" / "evidence.schema.json"
EXPECTED_RESULT_KEYS = {
    "schema_version",
    "request_id",
    "task_id",
    "corpus_snapshot",
    "route_candidates",
    "source_evidence",
    "retrieval_assessments",
    "variant_candidates",
    "cross_work_candidates",
    "retrieval_trace",
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _contains(value: str, phrase: str) -> bool:
    return normalize_text(phrase) in normalize_text(value)


def _set_pointer(value: Any, pointer: str, replacement: Any) -> None:
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    cursor = value
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    final = parts[-1]
    if isinstance(cursor, list):
        cursor[int(final)] = replacement
    else:
        cursor[final] = replacement


def _is_subsequence(expected: list[str], actual: list[str]) -> bool:
    position = 0
    for item in actual:
        if position < len(expected) and item == expected[position]:
            position += 1
    return position == len(expected)


def _source_identity_errors(
    result: dict[str, Any],
    manifest: dict[str, Any],
    cards: dict[str, Any],
) -> list[str]:
    """Re-read every result without relying on the port's own validator."""

    errors: list[str] = []
    works = {item["work_id"]: item for item in manifest["works"]}
    cards_by_work = {item["work_id"]: item for item in cards["cards"]}
    for evidence in result["source_evidence"]:
        evidence_id = evidence["evidence_id"]
        work = works.get(evidence["work_id"])
        card = cards_by_work.get(evidence["work_id"])
        if work is None or card is None:
            errors.append(f"{evidence_id}: unknown work/card")
            continue
        expected_path = f"kb/{work['path']}"
        if evidence["source_path"] != expected_path:
            errors.append(f"{evidence_id}: source path differs")
            continue
        source = (WORKSPACE / expected_path).resolve()
        if not source.is_relative_to((WORKSPACE / "kb" / "texts").resolve()):
            errors.append(f"{evidence_id}: source escaped kb/texts")
            continue
        lines = source.read_text(encoding="utf-8").splitlines()
        locator = evidence["locator"]
        start, end = locator["start_line"], locator["end_line"]
        excerpt = "\n".join(lines[start - 1 : end]).strip()
        if evidence["excerpt"] != excerpt:
            errors.append(f"{evidence_id}: excerpt differs from source")
        if evidence["excerpt_sha256"] != _sha256_bytes(
            excerpt.encode("utf-8")
        ):
            errors.append(f"{evidence_id}: excerpt SHA differs")
        if evidence["body_sha256"] != _sha256_file(source):
            errors.append(f"{evidence_id}: body SHA differs")
        if evidence["body_sha256"] != work["sha256"]:
            errors.append(f"{evidence_id}: manifest SHA differs")
        if evidence["source_identity"] != work["source"]:
            errors.append(f"{evidence_id}: source identity differs")
        if evidence["kind"] != card["evidence_kind"]:
            errors.append(f"{evidence_id}: evidence kind differs")
        if evidence["authority_role"] != card["authority_role"]:
            errors.append(f"{evidence_id}: authority differs")
        if evidence["rechecked_from_source"] is not True:
            errors.append(f"{evidence_id}: readback marker missing")
    return errors


def _case_errors(
    case: dict[str, Any],
    result: dict[str, Any],
    result_validator: Draft202012Validator,
    port: EvidencePort,
) -> list[str]:
    errors: list[str] = []
    test_id = case["test_id"]
    if set(result) != EXPECTED_RESULT_KEYS:
        errors.append(f"{test_id}: EvidenceResult root fields differ")
    schema_errors = sorted(
        result_validator.iter_errors(result),
        key=lambda error: list(error.absolute_path),
    )
    if schema_errors:
        errors.append(f"{test_id}: result schema failed: {schema_errors[0].message}")
    invariant_errors = validate_evidence_result(
        result,
        case["request"],
        workspace=WORKSPACE,
        manifest=port.manifest,
        cards=port.configuration,
    )
    errors.extend(f"{test_id}: {item}" for item in invariant_errors)
    errors.extend(
        f"{test_id}: {item}"
        for item in _source_identity_errors(
            result, port.manifest, port.configuration
        )
    )

    evidence_by_id = {
        item["evidence_id"]: item for item in result["source_evidence"]
    }
    assessments = {
        item["target_work_id"]: item
        for item in result["retrieval_assessments"]
    }
    expected = case["expected"]
    for expected_assessment in expected.get("assessments", []):
        target = expected_assessment["target_work_id"]
        assessment = assessments.get(target)
        if assessment is None:
            errors.append(f"{test_id}: assessment missing for {target}")
            continue
        if assessment["state"] != expected_assessment["state"]:
            errors.append(
                f"{test_id}: {target} state {assessment['state']} "
                f"!= {expected_assessment['state']}"
            )
        direct_text = "\n".join(
            evidence_by_id[evidence_id]["excerpt"]
            for evidence_id in assessment["direct_evidence_ids"]
        )
        for phrase in expected_assessment.get(
            "required_direct_phrases", []
        ):
            if not _contains(direct_text, phrase):
                errors.append(
                    f"{test_id}: direct source for {target} lacks {phrase}"
                )
        related_work_ids = {
            evidence_by_id[evidence_id]["work_id"]
            for evidence_id in assessment["related_candidate_evidence_ids"]
        }
        for work_id in expected_assessment.get(
            "required_related_work_ids", []
        ):
            if work_id not in related_work_ids:
                errors.append(
                    f"{test_id}: related candidate lacks {work_id}"
                )
        if len(assessment["variant_evidence_ids"]) < expected_assessment.get(
            "minimum_variant_candidates", 0
        ):
            errors.append(f"{test_id}: too few direct variant candidates")

    for identity in expected.get("required_identities", []):
        if not any(
            item["work_id"] == identity["work_id"]
            and item["kind"] == identity["kind"]
            and item["authority_role"] == identity["authority_role"]
            for item in result["source_evidence"]
        ):
            errors.append(f"{test_id}: source identity missing {identity}")

    variant_readings = {
        normalize_text(reading)
        for item in result["variant_candidates"]
        for reading in (item["base_reading"], item["variant_reading"])
    }
    for reading in expected.get("required_variant_readings", []):
        if normalize_text(reading) not in variant_readings:
            errors.append(f"{test_id}: variant reading missing {reading}")

    if len(result["cross_work_candidates"]) < expected.get(
        "minimum_cross_work_candidates", 0
    ):
        errors.append(f"{test_id}: too few cross-work candidates")
    if len(result["source_evidence"]) > expected.get(
        "maximum_source_evidence", 10**9
    ):
        errors.append(f"{test_id}: too much source evidence")
    actual_phases = [item["phase"] for item in result["retrieval_trace"]]
    expected_phases = expected.get("required_trace_phases", [])
    if not _is_subsequence(expected_phases, actual_phases):
        errors.append(
            f"{test_id}: trace phases {actual_phases} do not contain "
            f"{expected_phases} in order"
        )
    return errors


def _probe_request(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": f"ER-{probe['probe_id']}",
        "task_id": "TASK-SEALED-PROBE",
        "origin_stage": "stage_a",
        "question_text": f"定位{probe['exact_quote_target']}",
        "target_work_ids": [probe["target_work_id"]],
        "exact_quote_targets": [probe["exact_quote_target"]],
        "topic_hints": probe.get("topic_hints", []),
        "max_evidence": 8,
    }


def _source_probe_errors(
    probe: dict[str, Any], result: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    probe_id = probe["probe_id"]
    assessment = result["retrieval_assessments"][0]
    evidence_by_id = {
        item["evidence_id"]: item for item in result["source_evidence"]
    }
    if assessment["state"] != probe["expected_state"]:
        errors.append(
            f"{probe_id}: state {assessment['state']} "
            f"!= {probe['expected_state']}"
        )
    all_excerpts = "\n".join(
        item["excerpt"] for item in result["source_evidence"]
    )
    for phrase in probe.get("forbidden_excerpt_phrases", []):
        if _contains(all_excerpts, phrase):
            errors.append(f"{probe_id}: editorial/non-source phrase returned")

    required_related = probe.get("required_related_work_id")
    if required_related:
        related_works = {
            evidence_by_id[evidence_id]["work_id"]
            for evidence_id in assessment["related_candidate_evidence_ids"]
        }
        if required_related not in related_works:
            errors.append(
                f"{probe_id}: required related work {required_related} missing"
            )
    direct_items = [
        evidence_by_id[evidence_id]
        for evidence_id in assessment["direct_evidence_ids"]
    ]
    if "expected_kind" in probe and not any(
        item["kind"] == probe["expected_kind"] for item in direct_items
    ):
        errors.append(f"{probe_id}: direct evidence kind differs")
    if "expected_authority_role" in probe and not any(
        item["authority_role"] == probe["expected_authority_role"]
        for item in direct_items
    ):
        errors.append(f"{probe_id}: direct authority differs")

    direct_variant_ids = set(assessment["variant_evidence_ids"])
    readings = {
        normalize_text(reading)
        for item in result["variant_candidates"]
        if item["evidence_id"] in direct_variant_ids
        for reading in (item["base_reading"], item["variant_reading"])
    }
    expected_readings = {
        normalize_text(item)
        for item in probe.get("expected_variant_readings", [])
    }
    if expected_readings and not expected_readings <= readings:
        errors.append(
            f"{probe_id}: variant readings differ: "
            f"{sorted(readings)}"
        )
    if "expected_variant_readings" in probe and not expected_readings and readings:
        errors.append(f"{probe_id}: unrelated variant polluted direct target")
    return errors


def _checksum_drift_errors(
    probe: dict[str, Any],
    fixture: dict[str, Any],
    port: EvidencePort,
) -> list[str]:
    errors: list[str] = []
    work_id = probe["target_work_id"]
    work = next(item for item in port.manifest["works"] if item["work_id"] == work_id)
    card = copy.deepcopy(port.cards[work_id])
    card["upstream_work_ids"] = []
    card["return_to_work_ids"] = []
    matching_case = next(
        item
        for item in fixture["cases"]
        if work_id in item["request"]["target_work_ids"]
        and item["request"]["exact_quote_targets"]
    )
    request = copy.deepcopy(matching_case["request"])
    request["request_id"] = f"ER-{probe['probe_id']}"
    request["task_id"] = "TASK-CHECKSUM-DRIFT"
    request["target_work_ids"] = [work_id]

    with tempfile.TemporaryDirectory(prefix="gem-evidence-drift-") as directory:
        root = Path(directory)
        source = root / "kb" / work["path"]
        source.parent.mkdir(parents=True)
        shutil.copy2(WORKSPACE / "kb" / work["path"], source)
        manifest = {
            "manifest_version": port.manifest["manifest_version"],
            "updated_at": port.manifest["updated_at"],
            "rule": port.manifest["rule"],
            "work_count": 1,
            "asset_count": 0,
            "works": [work],
            "assets": [],
        }
        cards = {
            "schema_version": "2.0",
            "product_contract_version": "1.0",
            "updated_at": port.configuration["updated_at"],
            "source_of_truth": "kb/manifest.json",
            "policy": port.configuration["policy"],
            "concepts": port.configuration["concepts"],
            "cards": [card],
        }
        spec_dir = root / "spec"
        spec_dir.mkdir()
        manifest_path = root / "kb" / "manifest.json"
        cards_path = spec_dir / "retrieval_cards.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        cards_path.write_text(
            json.dumps(cards, ensure_ascii=False), encoding="utf-8"
        )
        temp_port = EvidencePort(
            workspace=root,
            manifest_path=manifest_path,
            cards_path=cards_path,
            schema_path=SCHEMA_PATH,
        )
        source.write_text(
            source.read_text(encoding="utf-8") + "\n漂移",
            encoding="utf-8",
        )
        try:
            temp_port.locate(request)
        except ValueError as exc:
            if "checksum differs" not in str(exc):
                errors.append(f"{probe['probe_id']}: wrong drift failure: {exc}")
        else:
            errors.append(f"{probe['probe_id']}: live drift did not fail closed")
        try:
            EvidencePort(
                workspace=root,
                manifest_path=manifest_path,
                cards_path=cards_path,
                schema_path=SCHEMA_PATH,
            )
        except ValueError as exc:
            if "checksum differs" not in str(exc):
                errors.append(f"{probe['probe_id']}: wrong init failure: {exc}")
        else:
            errors.append(f"{probe['probe_id']}: init drift did not fail closed")
    return errors


def _import_boundary_errors() -> list[str]:
    errors: list[str] = []
    paths = [
        WORKSPACE / "tools" / "evidence_service" / "__init__.py",
        WORKSPACE / "tools" / "evidence_service" / "evidence.py",
        WORKSPACE / "tools" / "retrieval.py",
    ]
    forbidden_roots = {
        "gem_kernel",
        "gem_runtime",
        "legacy_retrieval_contract",
        "core",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in forbidden_roots:
                        errors.append(
                            f"{path.relative_to(WORKSPACE)} imports {alias.name}"
                        )
            if module and module.split(".", 1)[0] in forbidden_roots:
                errors.append(
                    f"{path.relative_to(WORKSPACE)} imports {module}"
                )
    return errors


def _adjacent_heading_boundary_errors(port: EvidencePort) -> list[str]:
    """A paragraph before a sibling heading must not inherit the old sibling."""

    request = {
        "request_id": "ER-ADJACENT-HEADING-BOUNDARY",
        "task_id": "TASK-ADJACENT-HEADING-BOUNDARY",
        "origin_stage": "stage_a",
        "question_text": "定位少阴病二三日不已至四五日真武汤主之",
        "target_work_ids": ["T04-GL"],
        "exact_quote_targets": [
            "少阴病二三日不已，至四五日",
            "真武汤主之",
        ],
        "topic_hints": ["少阴", "水气"],
        "max_evidence": 4,
    }
    try:
        result = port.locate(request)
    except (EvidenceRequestError, ValueError) as exc:
        return [f"adjacent heading boundary locate failed: {exc}"]
    matching = [
        item
        for item in result["source_evidence"]
        if item["locator"]["start_line"] == 5807
    ]
    if len(matching) != 1:
        return ["adjacent heading boundary source was not uniquely returned"]
    item = matching[0]
    if "白通加猪胆汁汤方" in item["title"]:
        return ["adjacent paragraph inherited the previous sibling title"]
    if "白通加猪胆汁汤方" in item["locator"]["heading_path"]:
        return ["adjacent paragraph inherited the previous sibling heading"]
    if item["locator"]["heading_path"] != [
        "桂林古本伤寒杂病论",
        "伤寒杂病论卷第十一",
    ]:
        return ["adjacent paragraph did not retain the common parent scope"]
    return []


def main() -> int:
    errors: list[str] = []
    try:
        fixture = _load_json(FIXTURE_PATH)
        schema = _load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
        result_validator = Draft202012Validator(schema)

        if fixture.get("schema_version") != "1.0":
            errors.append("retrieval fixture schema_version must be 1.0")
        if len(fixture.get("cases", [])) != 14:
            errors.append("exactly 14 real evidence fixtures are required")
        if len(fixture.get("adversarial_probes", [])) != 52:
            errors.append("exactly 52 evidence probes are required")
        if len(fixture.get("contract_mutations", [])) != 8:
            errors.append("exactly 8 invariant mutations are required")
        for key, id_key in (
            ("cases", "test_id"),
            ("adversarial_probes", "probe_id"),
            ("contract_mutations", "mutation_id"),
        ):
            identifiers = [item[id_key] for item in fixture[key]]
            if len(identifiers) != len(set(identifiers)):
                errors.append(f"duplicate IDs in {key}")

        port = EvidencePort()
        cached_results: dict[str, dict[str, Any]] = {}
        for case in fixture["cases"]:
            try:
                result = port.locate(case["request"])
            except (EvidenceRequestError, ValueError) as exc:
                errors.append(f"{case['test_id']}: locate failed: {exc}")
                continue
            cached_results[case["test_id"]] = result
            errors.extend(
                _case_errors(case, result, result_validator, port)
            )

        base_case = fixture["cases"][0]
        base_result = cached_results.get(base_case["test_id"])
        for probe in fixture["adversarial_probes"]:
            kind = probe["kind"]
            if kind == "source_query":
                request = _probe_request(probe)
                try:
                    result = port.locate(request)
                except (EvidenceRequestError, ValueError) as exc:
                    errors.append(f"{probe['probe_id']}: locate failed: {exc}")
                    continue
                errors.extend(_source_probe_errors(probe, result))
                errors.extend(
                    f"{probe['probe_id']}: {item}"
                    for item in validate_evidence_result(
                        result,
                        request,
                        workspace=WORKSPACE,
                        manifest=port.manifest,
                        cards=port.configuration,
                    )
                )
            elif kind == "request_extra_field":
                request = copy.deepcopy(base_case["request"])
                request["request_id"] = f"ER-{probe['probe_id']}"
                request[probe["field"]] = copy.deepcopy(probe["value"])
                try:
                    port.validate_request(request)
                except EvidenceRequestError:
                    pass
                else:
                    errors.append(
                        f"{probe['probe_id']}: extra request field was accepted"
                    )
            elif kind == "result_forbidden_key":
                if base_result is None:
                    errors.append(
                        f"{probe['probe_id']}: base result unavailable"
                    )
                    continue
                mutated = copy.deepcopy(base_result)
                mutated[probe["field"]] = copy.deepcopy(probe["value"])
                if not list(result_validator.iter_errors(mutated)):
                    errors.append(
                        f"{probe['probe_id']}: schema accepted forbidden result key"
                    )
                invariant_errors = validate_evidence_result(
                    mutated,
                    base_case["request"],
                    workspace=WORKSPACE,
                    manifest=port.manifest,
                    cards=port.configuration,
                )
                if not any(
                    item.startswith("result.forbidden_keys")
                    for item in invariant_errors
                ):
                    errors.append(
                        f"{probe['probe_id']}: invariant gate missed forbidden key"
                    )
            elif kind == "source_checksum_drift":
                errors.extend(
                    _checksum_drift_errors(probe, fixture, port)
                )
            else:
                errors.append(
                    f"{probe['probe_id']}: unknown probe kind {kind}"
                )

        if base_result is None:
            errors.append("contract mutations need RT-01 result")
        else:
            for mutation in fixture["contract_mutations"]:
                mutated = copy.deepcopy(base_result)
                _set_pointer(
                    mutated,
                    mutation["path"],
                    copy.deepcopy(mutation["value"]),
                )
                invariant_errors = validate_evidence_result(
                    mutated,
                    base_case["request"],
                    workspace=WORKSPACE,
                    manifest=port.manifest,
                    cards=port.configuration,
                )
                if not any(
                    item.startswith(mutation["expected_error_prefix"])
                    for item in invariant_errors
                ):
                    errors.append(
                        f"{mutation['mutation_id']}: expected "
                        f"{mutation['expected_error_prefix']}, got "
                        f"{invariant_errors}"
                    )
        errors.extend(_adjacent_heading_boundary_errors(port))
        errors.extend(_import_boundary_errors())
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        errors.append(f"test harness failed: {exc}")

    if errors:
        print("FAILED: stage-2 evidence tests", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "PASS: 14 real evidence fixtures, 52 evidence probes, and "
        "8 invariant mutations pass across "
        f"{len(port.works)} source works and "
        f"{port.index_summary()['segment_count']} rebuildable locators"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
