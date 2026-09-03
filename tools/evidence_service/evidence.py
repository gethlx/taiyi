"""Stage-2 evidence location without task or TCM reasoning semantics.

The port accepts a locating question already interpreted by a model stage.  It
uses calling cards and a process-local Markdown index to find candidates, then
re-opens the single declared source file before returning any excerpt.  It
does not decide what an excerpt proves, choose a reading, create a graph, or
produce model-generalized text.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


WORKSPACE = Path(__file__).resolve().parents[2]
MANIFEST_PATH = WORKSPACE / "kb" / "manifest.json"
CARDS_PATH = WORKSPACE / "spec" / "retrieval_cards.json"
EVIDENCE_SCHEMA_PATH = WORKSPACE / "spec" / "evidence.schema.json"

CARD_REQUIRED_KEYS = {
    "card_id",
    "work_id",
    "title",
    "aliases",
    "layers",
    "evidence_kind",
    "authority_role",
    "text_state",
    "priority",
    "topic_ids",
    "routing_terms",
    "call_when",
    "routing_scope",
    "must_not",
    "upstream_work_ids",
    "return_to_work_ids",
}
CARD_SOURCE_KEYS = {
    "excerpt",
    "original_text",
    "source_path",
    "locator",
    "source_lines",
}
AUTHORITY_BY_KIND = {
    "classic_original": {"main", "same_layer_reference", "conditional"},
    "commentary_reference": {"same_layer_reference", "annotation"},
}
ROUTE_BASIS_ORDER = {
    "target_work_id": 0,
    "title_or_alias": 1,
    "topic_hint": 2,
    "question_term": 3,
    "card_relation": 4,
    "full_corpus_fallback": 5,
}
GENERIC_QUESTION_PARTS = (
    "请定位",
    "请查找",
    "请检索",
    "请核对",
    "原文",
    "出处",
    "相关",
    "候选",
    "如何",
    "怎样",
    "是否",
    "有无",
    "哪一段",
    "在哪里",
    "本轮",
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ANCHOR_RE = re.compile(r'^<a\s+id="([^"]+)"></a>\s*$')
COMMENT_RE = re.compile(r"^\s*<!--.*?-->\s*$")
BOOK_TITLE_RE = re.compile(r"《([^》]{1,60})》")
EDITORIAL_PROPERTY_RE = re.compile(r"^属性：[（(]?\s*平按[∶:]")
PROPERTY_PREFIX_RE = re.compile(r"^属性：")
INLINE_WIKI_NOTE_RE = re.compile(
    r"[（(]维基文库注[：:].*?[）)]|〔维基文库[^〕]*〕"
)
INLINE_COLLATION_NOTE_RE = re.compile(
    r"平按[∶:：].*?(?:[）)]|$)",
    re.DOTALL,
)
INLINE_EDITOR_NOTE_RE = re.compile(
    rf"(?:{INLINE_WIKI_NOTE_RE.pattern}|{INLINE_COLLATION_NOTE_RE.pattern})",
    re.DOTALL,
)
INLINE_VARIANT_NOTE_RE = re.compile(
    r"(?:[〈<（(〔【]\s*)?一作(?:"
    r"[“「『'\"][^”」』'\"]{1,20}[”」』'\"]|"
    r"[\u3400-\u9fff□]{1,20}(?=[〉>）)〕】，,。；;\s])"
    r"(?:\s*[〉>）)〕】])?)"
)
VARIANT_MARKER_RE = re.compile(r"一作|别本作|一本作|原作|误作|或作")
FRAGMENT_RE = re.compile(r"□{2,}|原缺|卷[^，。；]{0,10}缺|残缺")
EDITORIAL_LINE_RE = re.compile(
    r"^(?:注[：:].*(?:缺字|排版|图像)|〔维基文库)"
)
SOURCE_METADATA_LINE_RE = re.compile(
    r"^据.{0,100}(?:出版社|第[0-9一二三四五六七八九十]+版)(?:[。.]?)$"
)
CLASSIC_RESUME_RE = re.compile(
    r"^(?:□{2,}|黄帝|岐伯|歧伯|雷公|少师|伯高|帝曰|问曰|答曰|"
    r"凡|故|夫|天地|阴阳|五脏|六腑|经脉|脉有|人之|"
    r"手太|手少|足太|足少|太阳|少阳|阳明|太阴|少阴|厥阴)"
)
VARIANT_PAIR_RE = re.compile(
    r"(?P<context>[\u3400-\u9fff]{1,24})"
    r"(?:[〈<（(〔【]\s*)?一作(?:"
    r"[“「『'\"](?P<quoted>[^”」』'\"]{1,20})[”」』'\"]|"
    r"(?P<plain>[\u3400-\u9fff□]{1,20})"
    r"(?=[〉>）)〕】，,。；;\s]))"
    r"(?:\s*[〉>）)〕】])?"
)
COLLATION_VARIANT_PAIR_RE = re.compile(
    r"(?P<context>[\u3400-\u9fff]{1,32})"
    r"《[^》]{1,30}》作"
    r"(?P<variant>[\u3400-\u9fff□]{1,20})"
    r"(?=[，,。；;、）)\s]|$)"
)

CHAR_NORMALIZATION = str.maketrans(
    {
        "陰": "阴",
        "陽": "阳",
        "氣": "气",
        "炁": "气",
        "臟": "脏",
        "經": "经",
        "絡": "络",
        "靈": "灵",
        "樞": "枢",
        "闔": "阖",
        "開": "开",
        "進": "进",
        "退": "退",
        "歸": "归",
        "復": "复",
        "變": "变",
        "證": "证",
        "診": "诊",
        "論": "论",
        "藥": "药",
        "醫": "医",
        "實": "实",
        "體": "体",
        "與": "与",
        "為": "为",
        "從": "从",
        "於": "于",
        "則": "则",
        "無": "无",
        "屬": "属",
        "營": "营",
        "衛": "卫",
        "後": "后",
        "間": "间",
        "讀": "读",
        "書": "书",
        "針": "针",
        "灸": "灸",
    }
)


class EvidenceRequestError(ValueError):
    """Raised when a locating request violates the evidence-port boundary."""


@dataclass(frozen=True)
class Work:
    work_id: str
    title: str
    source_path: str
    source_identity: str
    source_sha256: str


@dataclass(frozen=True)
class Segment:
    segment_id: str
    work_id: str
    headings: tuple[str, ...]
    anchor: str | None
    start_line: int
    end_line: int
    source_path: str
    source_identity: str
    source_sha256: str
    search_text: str
    normalized_search_text: str
    fragmentary: bool


@dataclass(frozen=True)
class Hit:
    segment: Segment
    score: float
    category: str
    basis: str


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(
        CHAR_NORMALIZATION
    )
    return "".join(
        character.lower()
        for character in normalized
        if character.isalnum()
        or "\u3400" <= character <= "\u9fff"
        or character == "□"
    )


def _semantic_line(value: str) -> str:
    value = PROPERTY_PREFIX_RE.sub("", value, count=1)
    value = INLINE_EDITOR_NOTE_RE.sub("", value)
    return value


def _is_content_line(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if COMMENT_RE.match(stripped) or ANCHOR_RE.match(stripped):
        return False
    if stripped.startswith(">"):
        return False
    if stripped.startswith("| ◄") or stripped.startswith("| ►"):
        return False
    if EDITORIAL_LINE_RE.match(stripped):
        return False
    if SOURCE_METADATA_LINE_RE.match(stripped):
        return False
    return True


def _parse_segments(work: Work, workspace: Path) -> list[Segment]:
    """Build locators from Markdown without persisting source excerpts."""

    source_file = workspace / work.source_path
    lines = source_file.read_text(encoding="utf-8").splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                body_start = index + 1
                break

    headings: list[str] = []
    active_anchor: str | None = None
    pending: list[tuple[int, str, str]] = []
    pending_characters = 0
    pending_fragment = False
    active_fragment = False
    skipping_editorial = False
    segments: list[Segment] = []

    def flush() -> None:
        nonlocal pending, pending_characters, active_fragment
        content = [
            (line_number, raw_line, search_line)
            for line_number, raw_line, search_line in pending
            if _is_content_line(raw_line)
        ]
        pending = []
        pending_characters = 0
        if not content:
            active_fragment = False
            return
        # Collation/editor notes regularly wrap across physical Markdown lines.
        # Remove them only after rejoining the segment so a continuation line
        # cannot become a false source hit.
        search_text = _semantic_line(
            "\n".join(item[1] for item in content)
        ).strip()
        if not normalize_text(search_text):
            active_fragment = False
            return
        start_line = content[0][0]
        end_line = content[-1][0]
        segment_id = f"{work.work_id}-S{len(segments) + 1:05d}"
        segments.append(
            Segment(
                segment_id=segment_id,
                work_id=work.work_id,
                headings=tuple(headings),
                anchor=active_anchor,
                start_line=start_line,
                end_line=end_line,
                source_path=work.source_path,
                source_identity=work.source_identity,
                source_sha256=work.source_sha256,
                search_text=search_text,
                normalized_search_text=normalize_text(
                    "\n".join((*headings, search_text))
                ),
                fragmentary=active_fragment
                or FRAGMENT_RE.search(search_text) is not None,
            )
        )
        active_fragment = False

    for zero_index, raw_line in enumerate(lines[body_start:], start=body_start):
        line_number = zero_index + 1
        stripped = raw_line.strip()
        anchor_match = ANCHOR_RE.match(stripped)
        if anchor_match:
            flush()
            active_anchor = anchor_match.group(1)
            skipping_editorial = False
            continue
        heading_match = HEADING_RE.match(raw_line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            headings[:] = headings[: max(0, level - 1)]
            headings.append(heading_match.group(2).strip())
            skipping_editorial = False
            continue
        if COMMENT_RE.match(stripped):
            continue
        if EDITORIAL_PROPERTY_RE.match(stripped):
            flush()
            pending_fragment = pending_fragment or bool(FRAGMENT_RE.search(stripped))
            skipping_editorial = True
            continue
        if skipping_editorial:
            if not stripped:
                skipping_editorial = False
                continue
            pending_fragment = pending_fragment or bool(FRAGMENT_RE.search(stripped))
            if not CLASSIC_RESUME_RE.match(stripped):
                continue
            skipping_editorial = False
        if not stripped:
            flush()
            continue
        if not pending:
            active_fragment = pending_fragment
            pending_fragment = False
        search_line = _semantic_line(raw_line)
        pending.append((line_number, raw_line, search_line))
        pending_characters += len(raw_line)
        if pending_characters >= 1800 and len(pending) > 1:
            flush()
    flush()

    # A source paragraph can sit immediately before the next sibling heading.
    # Markdown nesting alone would then falsely present the paragraph as part
    # of the previous sibling.  Do not guess that it belongs to the next
    # heading; conservatively retain only the common parent scope.
    bounded_segments: list[Segment] = []
    for index, segment in enumerate(segments):
        bounded_headings = segment.headings
        if index + 1 < len(segments):
            following = segments[index + 1]
            sibling_boundary = (
                len(segment.headings) >= 2
                and len(following.headings) == len(segment.headings)
                and segment.headings[:-1] == following.headings[:-1]
                and segment.headings[-1] != following.headings[-1]
                and following.start_line - segment.end_line <= 8
            )
            if sibling_boundary:
                bounded_headings = segment.headings[:-1]
        if bounded_headings != segment.headings:
            segment = replace(
                segment,
                headings=bounded_headings,
                normalized_search_text=normalize_text(
                    "\n".join((*bounded_headings, segment.search_text))
                ),
            )
        bounded_segments.append(segment)
    return bounded_segments


def _source_title(card_title: str, headings: tuple[str, ...]) -> str:
    parts = [card_title]
    for heading in headings[-2:]:
        if normalize_text(heading) != normalize_text(parts[-1]):
            parts.append(heading)
    return " · ".join(parts)


def validate_card_configuration(
    manifest: dict[str, Any], configuration: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    works = manifest.get("works", [])
    manifest_ids = {
        item.get("work_id") for item in works if isinstance(item, dict)
    }
    if configuration.get("schema_version") != "2.0":
        errors.append("retrieval cards must use schema 2.0")
    if configuration.get("source_of_truth") != "kb/manifest.json":
        errors.append("retrieval cards must resolve through kb/manifest.json")
    policy = configuration.get("policy", {})
    expected_policy = {
        "cards_are_routing_only": True,
        "cards_are_evidence": False,
        "index_is_rebuildable": True,
        "index_enters_manifest": False,
        "original_text_root": "kb/texts",
        "source_recheck_required": True,
    }
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            errors.append(f"retrieval card policy differs: {key}")
    concepts = configuration.get("concepts", [])
    concept_ids = {
        item.get("concept_id") for item in concepts if isinstance(item, dict)
    }
    if None in concept_ids or len(concept_ids) != len(concepts):
        errors.append("retrieval concept IDs must be unique and non-empty")
    cards = configuration.get("cards", [])
    card_ids = [
        item.get("card_id") for item in cards if isinstance(item, dict)
    ]
    work_ids = [
        item.get("work_id") for item in cards if isinstance(item, dict)
    ]
    if len(card_ids) != len(set(card_ids)) or None in card_ids:
        errors.append("retrieval card IDs must be unique and non-empty")
    if set(work_ids) != manifest_ids or len(work_ids) != len(set(work_ids)):
        errors.append("retrieval cards must cover each manifest work once")
    for card in cards:
        card_id = card.get("card_id", "<missing>")
        if set(card) != CARD_REQUIRED_KEYS:
            errors.append(f"retrieval card fields differ: {card_id}")
        if CARD_SOURCE_KEYS & set(card):
            errors.append(f"retrieval card contains source evidence: {card_id}")
        if not set(card.get("topic_ids", [])) <= concept_ids:
            errors.append(f"retrieval card has unknown topic ID: {card_id}")
        related_ids = set(card.get("upstream_work_ids", [])) | set(
            card.get("return_to_work_ids", [])
        )
        if not related_ids <= manifest_ids:
            errors.append(f"retrieval card has unknown related work: {card_id}")
        kind = card.get("evidence_kind")
        if card.get("authority_role") not in AUTHORITY_BY_KIND.get(kind, set()):
            errors.append(f"retrieval card authority is invalid: {card_id}")
        if card.get("text_state") not in {"complete", "fragmentary"}:
            errors.append(f"retrieval card text state is invalid: {card_id}")
        if (
            not isinstance(card.get("priority"), int)
            or isinstance(card.get("priority"), bool)
            or not 1 <= card["priority"] <= 4
        ):
            errors.append(f"retrieval card priority is invalid: {card_id}")
        for key in ("aliases", "layers", "routing_terms"):
            values = card.get(key)
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(value, str) and value.strip() for value in values)
            ):
                errors.append(f"retrieval card {key} is invalid: {card_id}")
        for key in ("call_when", "routing_scope", "must_not"):
            value = card.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"retrieval card {key} is empty: {card_id}")
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    for forbidden in (
        "retrieval_cards.json",
        "retrieval_tests.json",
        "retrieval_index",
    ):
        if forbidden in manifest_text:
            errors.append(f"derived retrieval artifact entered manifest: {forbidden}")
    for item in works:
        if not str(item.get("path", "")).startswith("texts/"):
            errors.append(f"manifest work is outside kb/texts: {item.get('work_id')}")
    return errors


FORBIDDEN_RESULT_KEYS = {
    "task_mode",
    "active_task",
    "pending_intents",
    "queued_task_ids",
    "requested_visuals",
    "current_inference",
    "supports",
    "supports_ids",
    "conflicts",
    "conflicts_ids",
    "supporting_evidence_ids",
    "evidence_links",
    "reasoning_order",
    "semantic_graph",
    "graph",
    "visuals",
    "mermaid",
    "final_explanation",
    "model_generalization",
    "completion_method",
    "trust_label",
    "continue_reasoning",
    "confidence",
}


def _nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(_nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_nested_keys(child))
    return keys


def validate_evidence_result(
    result: dict[str, Any],
    request: dict[str, Any],
    workspace: Path = WORKSPACE,
    manifest: dict[str, Any] | None = None,
    cards: dict[str, Any] | None = None,
) -> list[str]:
    """Independently recheck result identities and source readback.

    This validator does not judge relevance.  It protects the deterministic
    boundary even when a result was loaded from disk or returned by another
    process.
    """

    errors: list[str] = []
    workspace = workspace.resolve()
    manifest = manifest or _load_json(workspace / "kb" / "manifest.json")
    cards = cards or _load_json(workspace / "spec" / "retrieval_cards.json")
    works = {
        item["work_id"]: item
        for item in manifest.get("works", [])
        if isinstance(item, dict)
    }
    cards_by_work = {
        item["work_id"]: item
        for item in cards.get("cards", [])
        if isinstance(item, dict)
    }
    if result.get("request_id") != request.get("request_id"):
        errors.append("result.request_id_mismatch")
    if result.get("task_id") != request.get("task_id"):
        errors.append("result.task_id_mismatch")
    forbidden = _nested_keys(result) & FORBIDDEN_RESULT_KEYS
    if forbidden:
        errors.append("result.forbidden_keys:" + ",".join(sorted(forbidden)))

    snapshot = result.get("corpus_snapshot", {})
    manifest_path = workspace / "kb" / "manifest.json"
    if snapshot.get("manifest_sha256") != _sha256_file(manifest_path):
        errors.append("snapshot.manifest_sha_mismatch")
    expected_work_sha = {
        work_id: item["sha256"] for work_id, item in works.items()
    }
    if snapshot.get("work_sha256") != expected_work_sha:
        errors.append("snapshot.work_sha_map_mismatch")
    expected_snapshot_sha = _sha256_bytes(
        _canonical_json(
            {
                "manifest_sha256": _sha256_file(manifest_path),
                "work_sha256": expected_work_sha,
            }
        )
    )
    if snapshot.get("snapshot_sha256") != expected_snapshot_sha:
        errors.append("snapshot.identity_mismatch")

    route_ids: list[str] = []
    for candidate in result.get("route_candidates", []):
        work_id = candidate.get("work_id")
        route_ids.append(work_id)
        card = cards_by_work.get(work_id)
        if card is None:
            errors.append(f"route.unknown_work:{work_id}")
            continue
        for field in (
            "card_id",
            "title",
            "evidence_kind",
            "authority_role",
            "priority",
        ):
            if candidate.get(field) != card.get(field):
                errors.append(f"route.card_identity_mismatch:{work_id}:{field}")
    if len(route_ids) != len(set(route_ids)):
        errors.append("route.duplicate_work")

    evidence_items = result.get("source_evidence", [])
    if len(evidence_items) > request.get("max_evidence", 0):
        errors.append("evidence.max_exceeded")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    source_root = (workspace / "kb" / "texts").resolve()
    for item in evidence_items:
        evidence_id = item.get("evidence_id")
        if evidence_id in evidence_by_id:
            errors.append(f"evidence.duplicate_id:{evidence_id}")
        evidence_by_id[evidence_id] = item
        work_id = item.get("work_id")
        work = works.get(work_id)
        card = cards_by_work.get(work_id)
        if work is None or card is None:
            errors.append(f"evidence.unknown_work:{evidence_id}")
            continue
        expected_path = f"kb/{work['path']}"
        if item.get("source_path") != expected_path:
            errors.append(f"evidence.path_mismatch:{evidence_id}")
        source_file = (workspace / expected_path).resolve()
        if not source_file.is_relative_to(source_root) or not source_file.is_file():
            errors.append(f"evidence.path_escape_or_missing:{evidence_id}")
            continue
        actual_body_sha = _sha256_file(source_file)
        if (
            actual_body_sha != work["sha256"]
            or item.get("body_sha256") != work["sha256"]
        ):
            errors.append(f"evidence.body_sha_mismatch:{evidence_id}")
        if item.get("source_identity") != work["source"]:
            errors.append(f"evidence.source_identity_mismatch:{evidence_id}")
        if item.get("kind") != card["evidence_kind"]:
            errors.append(f"evidence.kind_mismatch:{evidence_id}")
        if item.get("authority_role") != card["authority_role"]:
            errors.append(f"evidence.authority_mismatch:{evidence_id}")
        locator = item.get("locator", {})
        start = locator.get("start_line")
        end = locator.get("end_line")
        lines = source_file.read_text(encoding="utf-8").splitlines()
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 1
            or end < start
            or end > len(lines)
        ):
            errors.append(f"evidence.line_range_invalid:{evidence_id}")
            continue
        expected_excerpt = "\n".join(lines[start - 1 : end]).strip()
        if item.get("excerpt") != expected_excerpt:
            errors.append(f"evidence.excerpt_mismatch:{evidence_id}")
        if item.get("excerpt_sha256") != _sha256_text(expected_excerpt):
            errors.append(f"evidence.excerpt_sha_mismatch:{evidence_id}")
        if item.get("rechecked_from_source") is not True:
            errors.append(f"evidence.readback_marker_missing:{evidence_id}")
        if not any(_is_content_line(line) for line in lines[start - 1 : end]):
            errors.append(f"evidence.non_body_excerpt:{evidence_id}")
        anchor = locator.get("anchor")
        expected_line_anchor = f"L{start}-L{end}"
        if anchor != expected_line_anchor and (
            not isinstance(anchor, str)
            or f'<a id="{anchor}"></a>' not in lines[:start]
        ):
            errors.append(f"evidence.anchor_mismatch:{evidence_id}")

    known_ids = set(evidence_by_id)
    variant_candidates = result.get("variant_candidates", [])
    variant_candidate_ids: set[str] = set()
    variant_source_ids: set[str] = set()
    for candidate in variant_candidates:
        candidate_id = candidate.get("candidate_id")
        if candidate_id in variant_candidate_ids:
            errors.append(f"variant.duplicate_id:{candidate_id}")
        variant_candidate_ids.add(candidate_id)
        evidence_id = candidate.get("evidence_id")
        if evidence_id not in known_ids:
            errors.append(f"variant.unknown_evidence:{candidate_id}")
        variant_source_ids.add(evidence_id)

    cross_candidate_ids: set[str] = set()
    cross_source_ids: set[str] = set()
    for candidate in result.get("cross_work_candidates", []):
        candidate_id = candidate.get("candidate_id")
        if candidate_id in cross_candidate_ids:
            errors.append(f"cross_work.duplicate_id:{candidate_id}")
        cross_candidate_ids.add(candidate_id)
        evidence_id = candidate.get("evidence_id")
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            errors.append(f"cross_work.unknown_evidence:{candidate_id}")
            continue
        cross_source_ids.add(evidence_id)
        if evidence.get("work_id") in set(candidate.get("from_target_work_ids", [])):
            errors.append(f"cross_work.same_as_target:{candidate_id}")

    expected_targets: list[str | None] = (
        list(request.get("target_work_ids", []))
        if request.get("target_work_ids")
        else [None]
    )
    assessments = result.get("retrieval_assessments", [])
    actual_targets = [item.get("target_work_id") for item in assessments]
    if actual_targets != expected_targets:
        errors.append("assessment.target_set_or_order_mismatch")
    assessment_ids: set[str] = set()
    for assessment in assessments:
        assessment_id = assessment.get("assessment_id")
        if assessment_id in assessment_ids:
            errors.append(f"assessment.duplicate_id:{assessment_id}")
        assessment_ids.add(assessment_id)
        if assessment.get("request_id") != request.get("request_id"):
            errors.append(f"assessment.request_mismatch:{assessment_id}")
        direct = assessment.get("direct_evidence_ids", [])
        related = assessment.get("related_candidate_evidence_ids", [])
        variants = assessment.get("variant_evidence_ids", [])
        for group_name, identifiers in (
            ("direct", direct),
            ("related", related),
            ("variant", variants),
        ):
            unknown = set(identifiers) - known_ids
            if unknown:
                errors.append(
                    f"assessment.{group_name}_unknown:{assessment_id}:"
                    + ",".join(sorted(unknown))
                )
        if set(direct) & set(related):
            errors.append(f"assessment.direct_related_overlap:{assessment_id}")
        target_work_id = assessment.get("target_work_id")
        if target_work_id is not None and any(
            evidence_by_id.get(evidence_id, {}).get("work_id") != target_work_id
            for evidence_id in direct
        ):
            errors.append(f"assessment.direct_target_mismatch:{assessment_id}")
        if not set(variants) <= variant_source_ids:
            errors.append(f"assessment.variant_identity_mismatch:{assessment_id}")
        state = assessment.get("state")
        direct_states = {
            evidence_by_id.get(evidence_id, {}).get("fragment_state")
            for evidence_id in direct
        }
        if state == "not_retrieved" and direct:
            errors.append(f"assessment.not_retrieved_has_direct:{assessment_id}")
        elif state == "complete" and (
            not direct or direct_states != {"complete"}
        ):
            errors.append(f"assessment.complete_invalid:{assessment_id}")
        elif state == "fragmentary" and (
            not direct or "fragmentary" not in direct_states
        ):
            errors.append(f"assessment.fragmentary_invalid:{assessment_id}")
        elif state == "conflicting" and (
            not direct or not variants
        ):
            errors.append(f"assessment.conflicting_invalid:{assessment_id}")
    return errors


class EvidencePort:
    """Process-local evidence locator bound to the current corpus snapshot."""

    def __init__(
        self,
        workspace: Path = WORKSPACE,
        manifest_path: Path | None = None,
        cards_path: Path | None = None,
        schema_path: Path | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.manifest_path = (
            manifest_path.resolve()
            if manifest_path is not None
            else self.workspace / "kb" / "manifest.json"
        )
        self.cards_path = (
            cards_path.resolve()
            if cards_path is not None
            else self.workspace / "spec" / "retrieval_cards.json"
        )
        self.schema_path = (
            schema_path.resolve()
            if schema_path is not None
            else self.workspace / "spec" / "evidence.schema.json"
        )
        self.manifest = _load_json(self.manifest_path)
        self.configuration = _load_json(self.cards_path)
        self.schema = _load_json(self.schema_path)
        Draft202012Validator.check_schema(self.schema)
        self.result_validator = Draft202012Validator(self.schema)
        self.request_validator = Draft202012Validator(
            {
                "$schema": self.schema["$schema"],
                "$defs": self.schema["$defs"],
                "$ref": "#/$defs/EvidenceRequest",
            }
        )
        card_errors = validate_card_configuration(
            self.manifest, self.configuration
        )
        if card_errors:
            raise ValueError("; ".join(card_errors))
        self.works = {
            item["work_id"]: Work(
                work_id=item["work_id"],
                title=item["title"],
                source_path=f"kb/{item['path']}",
                source_identity=item["source"],
                source_sha256=item["sha256"],
            )
            for item in self.manifest["works"]
        }
        self.cards = {
            item["work_id"]: item for item in self.configuration["cards"]
        }
        self.concepts = {
            item["concept_id"]: item for item in self.configuration["concepts"]
        }
        for work in self.works.values():
            self._verify_work(work)
        self.segments_by_work = {
            work_id: _parse_segments(work, self.workspace)
            for work_id, work in self.works.items()
        }
        self.segment_positions = {
            segment.segment_id: (work_id, index)
            for work_id, segments in self.segments_by_work.items()
            for index, segment in enumerate(segments)
        }
        self._snapshot = self._build_snapshot()

    def _verify_work(self, work: Work) -> None:
        source_file = (self.workspace / work.source_path).resolve()
        source_root = (self.workspace / "kb" / "texts").resolve()
        if not source_file.is_relative_to(source_root):
            raise ValueError(f"source is outside kb/texts: {work.work_id}")
        if not source_file.is_file():
            raise ValueError(f"source is missing: {work.source_path}")
        if _sha256_file(source_file) != work.source_sha256:
            raise ValueError(
                f"source checksum differs from kb/manifest.json: {work.work_id}"
            )

    def _build_snapshot(self) -> dict[str, Any]:
        work_sha256 = {
            work_id: work.source_sha256 for work_id, work in self.works.items()
        }
        manifest_sha256 = _sha256_file(self.manifest_path)
        snapshot_sha256 = _sha256_bytes(
            _canonical_json(
                {
                    "manifest_sha256": manifest_sha256,
                    "work_sha256": work_sha256,
                }
            )
        )
        return {
            "manifest_path": "kb/manifest.json",
            "manifest_sha256": manifest_sha256,
            "source_root": "kb/texts",
            "work_sha256": work_sha256,
            "snapshot_sha256": snapshot_sha256,
        }

    def index_summary(self) -> dict[str, Any]:
        return {
            "index_version": "gem-evidence-index-1.0",
            "built_from": "kb/manifest.json",
            "source_root": "kb/texts",
            "work_count": len(self.works),
            "segment_count": sum(
                len(segments) for segments in self.segments_by_work.values()
            ),
            "work_ids": list(self.works),
            "contains_original_excerpts": False,
            "persisted": False,
            "registered_in_manifest": False,
            "snapshot_sha256": self._snapshot["snapshot_sha256"],
        }

    def validate_request(self, request: dict[str, Any]) -> None:
        errors = sorted(
            self.request_validator.iter_errors(request),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            error = errors[0]
            path = "/".join(str(item) for item in error.absolute_path) or "$"
            raise EvidenceRequestError(f"invalid EvidenceRequest at {path}: {error.message}")
        unknown = set(request["target_work_ids"]) - set(self.works)
        if unknown:
            raise EvidenceRequestError(
                "EvidenceRequest has unknown target_work_ids: "
                + ", ".join(sorted(unknown))
            )

    def _matched_concepts(self, request: dict[str, Any]) -> dict[str, list[str]]:
        query = normalize_text(
            " ".join((request["question_text"], *request["topic_hints"]))
        )
        matched: dict[str, list[str]] = {}
        for concept in self.concepts.values():
            terms = [
                term
                for term in concept["terms"]
                if normalize_text(term) in query
                or any(
                    normalize_text(hint) in normalize_text(term)
                    or normalize_text(term) in normalize_text(hint)
                    for hint in request["topic_hints"]
                )
            ]
            if terms:
                matched[concept["concept_id"]] = list(dict.fromkeys(terms))
        return matched

    def _route(
        self, request: dict[str, Any]
    ) -> tuple[list[str], list[dict[str, Any]], set[str]]:
        normalized_question = normalize_text(request["question_text"])
        matched_concepts = self._matched_concepts(request)
        target_ids = list(request["target_work_ids"])
        scores: dict[str, float] = {}
        bases: dict[str, set[str]] = {}
        terms: dict[str, list[str]] = {}

        def add(
            work_id: str, score: float, basis: str, matched_terms: Iterable[str] = ()
        ) -> None:
            scores[work_id] = scores.get(work_id, 0.0) + score
            bases.setdefault(work_id, set()).add(basis)
            terms.setdefault(work_id, []).extend(matched_terms)

        for index, work_id in enumerate(target_ids):
            add(work_id, 1000.0 - index, "target_work_id")
        for card in self.configuration["cards"]:
            work_id = card["work_id"]
            alias_matches = [
                alias
                for alias in card["aliases"]
                if normalize_text(alias) in normalized_question
            ]
            if alias_matches:
                add(
                    work_id,
                    180.0 + max(len(normalize_text(item)) for item in alias_matches),
                    "title_or_alias",
                    alias_matches,
                )
            concept_matches = sorted(
                set(card["topic_ids"]) & set(matched_concepts)
            )
            if concept_matches:
                matched_terms = [
                    term
                    for concept_id in concept_matches
                    for term in matched_concepts[concept_id]
                ]
                add(
                    work_id,
                    20.0 * len(concept_matches),
                    "topic_hint",
                    matched_terms,
                )
            routing_matches = [
                term
                for term in card["routing_terms"]
                if normalize_text(term) in normalized_question
                or any(
                    normalize_text(term) in normalize_text(hint)
                    for hint in request["topic_hints"]
                )
            ]
            if routing_matches:
                add(
                    work_id,
                    sum(8.0 + len(normalize_text(term)) for term in routing_matches),
                    "question_term",
                    routing_matches,
                )

        seed_ids = list(dict.fromkeys((*target_ids, *scores.keys())))
        related_ids: set[str] = set()
        for work_id in seed_ids:
            card = self.cards[work_id]
            for related_id in (
                *card["upstream_work_ids"],
                *card["return_to_work_ids"],
            ):
                if related_id not in scores:
                    add(related_id, 5.0, "card_relation")
                else:
                    bases.setdefault(related_id, set()).add("card_relation")
                related_ids.add(related_id)
        if not scores:
            for card in self.configuration["cards"]:
                add(
                    card["work_id"],
                    float(5 - card["priority"]),
                    "full_corpus_fallback",
                )
        manifest_rank = {work_id: index for index, work_id in enumerate(self.works)}
        ordered = sorted(
            scores,
            key=lambda work_id: (
                0 if work_id in target_ids else 1,
                target_ids.index(work_id) if work_id in target_ids else 999,
                -scores[work_id],
                self.cards[work_id]["priority"],
                manifest_rank[work_id],
            ),
        )[:12]
        entries = [
            {
                "card_id": self.cards[work_id]["card_id"],
                "work_id": work_id,
                "title": self.cards[work_id]["title"],
                "evidence_kind": self.cards[work_id]["evidence_kind"],
                "authority_role": self.cards[work_id]["authority_role"],
                "priority": self.cards[work_id]["priority"],
                "candidate_basis": sorted(
                    bases[work_id], key=ROUTE_BASIS_ORDER.__getitem__
                ),
                "match_terms": list(dict.fromkeys(terms.get(work_id, []))),
                "rank": rank,
            }
            for rank, work_id in enumerate(ordered, start=1)
        ]
        return ordered, entries, related_ids

    def _query_terms(
        self,
        request: dict[str, Any],
        route_ids: list[str],
    ) -> list[str]:
        terms: set[str] = {
            hint for hint in request["topic_hints"] if len(normalize_text(hint)) >= 2
        }
        normalized_question = normalize_text(request["question_text"])
        for work_id in route_ids:
            card = self.cards[work_id]
            for term in card["routing_terms"]:
                if normalize_text(term) in normalized_question:
                    terms.add(term)
        reduced = request["question_text"]
        for part in GENERIC_QUESTION_PARTS:
            reduced = reduced.replace(part, "")
        reduced = BOOK_TITLE_RE.sub("", reduced)
        for run in re.findall(
            r"[\u3400-\u9fff□]{2,16}|[A-Za-z0-9_-]{2,}", reduced
        ):
            terms.add(run)
            normalized_run = normalize_text(run)
            if 5 <= len(normalized_run) <= 12:
                for width in (2, 3, 4):
                    for offset in range(len(normalized_run) - width + 1):
                        terms.add(normalized_run[offset : offset + width])
        return sorted(
            {
                term
                for term in terms
                if len(normalize_text(term)) >= 2
            },
            key=lambda term: (-len(normalize_text(term)), term),
        )

    @staticmethod
    def _phrase_matches(
        phrase: str,
        source_text: str,
        require_source_gap: bool = False,
    ) -> bool:
        semantic_text = INLINE_EDITOR_NOTE_RE.sub("", source_text)
        if not VARIANT_MARKER_RE.search(phrase):
            semantic_text = INLINE_VARIANT_NOTE_RE.sub("", semantic_text)
        normalized_phrase = normalize_text(phrase)
        if not normalized_phrase:
            return False
        if "□" not in normalized_phrase:
            return normalized_phrase in normalize_text(semantic_text)
        pieces = [
            re.escape(piece) for piece in re.split(r"□+", normalized_phrase)
        ]
        pattern = re.compile(r"(.{1,24})".join(pieces))
        for clause in re.split(r"[，,。；;！？!?\n\r]+", semantic_text):
            for match in pattern.finditer(normalize_text(clause)):
                if not require_source_gap or all(
                    "□" in captured for captured in match.groups()
                ):
                    return True
        return False

    def _score_segment(
        self,
        segment: Segment,
        exact_targets: list[str],
        query_terms: list[str],
        require_source_gap: bool,
    ) -> float:
        if exact_targets:
            matches = [
                phrase
                for phrase in exact_targets
                if self._phrase_matches(
                    phrase,
                    segment.search_text,
                    require_source_gap=require_source_gap,
                )
            ]
            if not matches:
                return 0.0
            return 500.0 + sum(len(normalize_text(item)) for item in matches)
        heading_text = normalize_text(" ".join(segment.headings))
        score = 0.0
        for term in query_terms:
            normalized = normalize_text(term)
            if normalized and normalized in segment.normalized_search_text:
                score += min(30.0, 2.0 + len(normalized) * 1.5)
                if normalized in heading_text:
                    score += 10.0
        return score

    def _search_works(
        self,
        work_ids: Iterable[str],
        exact_targets: list[str],
        query_terms: list[str],
        category: str,
        basis: str,
        target_ids: set[str],
    ) -> list[Hit]:
        hits: list[Hit] = []
        for work_id in work_ids:
            scored: list[Hit] = []
            for segment in self.segments_by_work[work_id]:
                score = self._score_segment(
                    segment,
                    exact_targets,
                    query_terms,
                    require_source_gap=work_id in target_ids,
                )
                if score > 0:
                    scored.append(
                        Hit(
                            segment=segment,
                            score=score,
                            category=category,
                            basis=basis,
                        )
                    )
            scored.sort(key=lambda hit: (-hit.score, hit.segment.start_line))
            hits.extend(scored[:3])
        return hits

    def _adjacent_hits(self, base_hits: list[Hit]) -> list[Hit]:
        adjacent: list[Hit] = []
        seen = {hit.segment.segment_id for hit in base_hits}
        for hit in base_hits[:8]:
            work_id, position = self.segment_positions[hit.segment.segment_id]
            segments = self.segments_by_work[work_id]
            for neighbor_position in (position - 1, position + 1):
                if not 0 <= neighbor_position < len(segments):
                    continue
                segment = segments[neighbor_position]
                if segment.segment_id in seen:
                    continue
                if segment.headings[:2] != hit.segment.headings[:2]:
                    continue
                seen.add(segment.segment_id)
                adjacent.append(
                    Hit(
                        segment=segment,
                        score=max(0.1, hit.score * 0.1),
                        category="adjacent_context",
                        basis="adjacent_context",
                    )
                )
        return adjacent

    def _readback(self, segment: Segment) -> tuple[str, str]:
        work = self.works[segment.work_id]
        self._verify_work(work)
        source_file = self.workspace / work.source_path
        lines = source_file.read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(
            lines[segment.start_line - 1 : segment.end_line]
        ).strip()
        if not excerpt:
            raise ValueError(f"empty source readback: {segment.segment_id}")
        return excerpt, _sha256_text(excerpt)

    @staticmethod
    def _evidence_id(segment: Segment, excerpt_sha256: str) -> str:
        return (
            f"EV-{segment.work_id}-{segment.start_line}-"
            f"{segment.end_line}-{excerpt_sha256[:12]}"
        )

    def _variant_pairs(
        self,
        excerpt: str,
        evidence_id: str,
        relevance_terms: list[str],
    ) -> list[dict[str, Any]]:
        normalized_relevance = [
            normalize_text(term) for term in relevance_terms if normalize_text(term)
        ]
        pairs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        semantic_excerpt = INLINE_WIKI_NOTE_RE.sub("", excerpt)
        for match in VARIANT_PAIR_RE.finditer(semantic_excerpt):
            variant = (match.group("quoted") or match.group("plain")).strip()
            context = match.group("context").strip()
            width = max(1, len(normalize_text(variant)))
            base = context[-width:].strip()
            normalized_pair = (normalize_text(base), normalize_text(variant))
            if (
                not normalized_pair[0]
                or not normalized_pair[1]
                or normalized_pair in seen
            ):
                continue
            if normalized_relevance and not any(
                normalized_pair[0] in term
                or normalized_pair[1] in term
                or term in normalized_pair[0]
                or term in normalized_pair[1]
                for term in normalized_relevance
            ):
                continue
            seen.add(normalized_pair)
            pairs.append(
                {
                    "candidate_id": f"VAR-{evidence_id}-{len(pairs) + 1:02d}",
                    "evidence_id": evidence_id,
                    "base_reading": base,
                    "variant_reading": variant,
                    "status": "unadjudicated",
                }
            )
        for match in COLLATION_VARIANT_PAIR_RE.finditer(semantic_excerpt):
            context = match.group("context").strip()
            variant = match.group("variant").strip()
            matching_terms = [
                term.strip()
                for term in relevance_terms
                if normalize_text(term)
                and normalize_text(term) in normalize_text(context)
            ]
            base = (
                max(matching_terms, key=lambda term: len(normalize_text(term)))
                if matching_terms
                else context
            )
            normalized_pair = (normalize_text(base), normalize_text(variant))
            if (
                not normalized_pair[0]
                or not normalized_pair[1]
                or normalized_pair in seen
            ):
                continue
            if normalized_relevance and not any(
                normalized_pair[0] in term
                or normalized_pair[1] in term
                or term in normalized_pair[0]
                or term in normalized_pair[1]
                for term in normalized_relevance
            ):
                continue
            seen.add(normalized_pair)
            pairs.append(
                {
                    "candidate_id": f"VAR-{evidence_id}-{len(pairs) + 1:02d}",
                    "evidence_id": evidence_id,
                    "base_reading": base,
                    "variant_reading": variant,
                    "status": "unadjudicated",
                }
            )
        return pairs

    def locate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.validate_request(request)
        route_ids, route_entries, related_ids = self._route(request)
        target_ids = set(request["target_work_ids"])
        query_terms = self._query_terms(request, route_ids)
        exact_targets = request["exact_quote_targets"]
        base_hits = self._search_works(
            route_ids,
            exact_targets,
            query_terms,
            category="direct_match",
            basis="exact_quote" if exact_targets else "topic_hint",
            target_ids=target_ids,
        )
        adjacent_hits = self._adjacent_hits(base_hits)
        cross_hits: list[Hit] = []
        if target_ids:
            remaining = [
                work_id for work_id in self.works if work_id not in target_ids
            ]
            if exact_targets:
                cross_hits = self._search_works(
                    remaining,
                    exact_targets,
                    query_terms,
                    category="cross_work_candidate",
                    basis="exact_quote",
                    target_ids=target_ids,
                )
            else:
                related_route = [
                    work_id
                    for work_id in route_ids
                    if work_id not in target_ids and work_id in related_ids
                ]
                cross_hits = self._search_works(
                    related_route,
                    [],
                    query_terms,
                    category="cross_work_candidate",
                    basis="card_relation",
                    target_ids=target_ids,
                )

        target_rank = {
            work_id: index for index, work_id in enumerate(request["target_work_ids"])
        }
        category_rank = {
            "direct_match": 0,
            "cross_work_candidate": 1,
            "adjacent_context": 2,
        }
        all_hits = sorted(
            (*base_hits, *cross_hits, *adjacent_hits),
            key=lambda hit: (
                category_rank[hit.category],
                0 if hit.segment.work_id in target_ids else 1,
                target_rank.get(hit.segment.work_id, 999),
                -hit.score,
                hit.segment.start_line,
            ),
        )
        selected: list[Hit] = []
        selected_segments: set[str] = set()
        for hit in all_hits:
            if len(selected) >= request["max_evidence"]:
                break
            if hit.segment.segment_id in selected_segments:
                continue
            selected_segments.add(hit.segment.segment_id)
            selected.append(hit)

        source_evidence: list[dict[str, Any]] = []
        hit_by_evidence_id: dict[str, Hit] = {}
        variant_candidates: list[dict[str, Any]] = []
        relevance_terms = [
            *exact_targets,
            *request["topic_hints"],
        ]
        for hit in selected:
            segment = hit.segment
            excerpt, excerpt_sha256 = self._readback(segment)
            evidence_id = self._evidence_id(segment, excerpt_sha256)
            variants = self._variant_pairs(
                excerpt, evidence_id, relevance_terms
            )
            fragment_state = (
                "variant"
                if variants
                else "fragmentary"
                if segment.fragmentary
                else "complete"
            )
            work = self.works[segment.work_id]
            card = self.cards[segment.work_id]
            source_evidence.append(
                {
                    "evidence_id": evidence_id,
                    "segment_id": segment.segment_id,
                    "work_id": segment.work_id,
                    "title": _source_title(card["title"], segment.headings),
                    "kind": card["evidence_kind"],
                    "authority_role": card["authority_role"],
                    "source_path": segment.source_path,
                    "source_identity": segment.source_identity,
                    "locator": {
                        "heading_path": list(segment.headings),
                        "anchor": segment.anchor
                        or f"L{segment.start_line}-L{segment.end_line}",
                        "start_line": segment.start_line,
                        "end_line": segment.end_line,
                    },
                    "excerpt": excerpt,
                    "body_sha256": work.source_sha256,
                    "excerpt_sha256": excerpt_sha256,
                    "fragment_state": fragment_state,
                    "rechecked_from_source": True,
                }
            )
            hit_by_evidence_id[evidence_id] = hit
            variant_candidates.extend(variants)

        evidence_ids_by_work: dict[str, list[str]] = {}
        for item in source_evidence:
            evidence_ids_by_work.setdefault(item["work_id"], []).append(
                item["evidence_id"]
            )
        cross_work_candidates: list[dict[str, Any]] = []
        for item in source_evidence:
            hit = hit_by_evidence_id[item["evidence_id"]]
            if not target_ids or item["work_id"] in target_ids:
                continue
            if hit.category == "adjacent_context":
                continue
            basis = (
                "exact_quote"
                if hit.basis == "exact_quote"
                else "card_relation"
                if hit.basis == "card_relation"
                else "topic_hint"
            )
            cross_work_candidates.append(
                {
                    "candidate_id": f"XW-{len(cross_work_candidates) + 1:03d}",
                    "evidence_id": item["evidence_id"],
                    "from_target_work_ids": list(request["target_work_ids"]),
                    "candidate_basis": basis,
                }
            )

        assessments: list[dict[str, Any]] = []
        assessment_targets: list[str | None] = (
            list(request["target_work_ids"])
            if request["target_work_ids"]
            else [None]
        )
        cross_ids = [
            item["evidence_id"] for item in cross_work_candidates
        ]
        for index, target_work_id in enumerate(assessment_targets, start=1):
            if target_work_id is None:
                direct_ids = [
                    item["evidence_id"]
                    for item in source_evidence
                    if hit_by_evidence_id[item["evidence_id"]].category
                    == "direct_match"
                ]
            else:
                direct_ids = [
                    item["evidence_id"]
                    for item in source_evidence
                    if item["work_id"] == target_work_id
                    and hit_by_evidence_id[item["evidence_id"]].category
                    == "direct_match"
                ]
            adjacent_ids = [
                item["evidence_id"]
                for item in source_evidence
                if (
                    target_work_id is None
                    or item["work_id"] == target_work_id
                )
                and hit_by_evidence_id[item["evidence_id"]].category
                == "adjacent_context"
            ]
            other_target_direct_ids = [
                item["evidence_id"]
                for item in source_evidence
                if target_work_id is not None
                and item["work_id"] != target_work_id
                and item["work_id"] in target_ids
                and hit_by_evidence_id[item["evidence_id"]].category
                == "direct_match"
            ]
            variant_evidence_ids = list(
                dict.fromkeys(
                    item["evidence_id"]
                    for item in variant_candidates
                    if item["evidence_id"] in direct_ids
                )
            )
            if not direct_ids:
                state = "not_retrieved"
            elif variant_evidence_ids:
                state = "conflicting"
            elif any(
                item["evidence_id"] in direct_ids
                and item["fragment_state"] == "fragmentary"
                for item in source_evidence
            ):
                state = "fragmentary"
            else:
                state = "complete"
            assessments.append(
                {
                    "assessment_id": f"ASSESS-{request['request_id']}-{index:02d}",
                    "request_id": request["request_id"],
                    "target_work_id": target_work_id,
                    "state": state,
                    "direct_evidence_ids": direct_ids,
                    "related_candidate_evidence_ids": list(
                        dict.fromkeys(
                            (
                                *adjacent_ids,
                                *other_target_direct_ids,
                                *cross_ids,
                            )
                        )
                    ),
                    "variant_evidence_ids": variant_evidence_ids,
                }
            )

        traces: list[dict[str, Any]] = []

        def trace(
            phase: str,
            work_ids: Iterable[str],
            segment_ids: Iterable[str],
            detail_code: str,
        ) -> None:
            traces.append(
                {
                    "trace_id": f"TRACE-{len(traces) + 1:03d}",
                    "phase": phase,
                    "work_ids": list(dict.fromkeys(work_ids)),
                    "segment_ids": list(dict.fromkeys(segment_ids)),
                    "detail_code": detail_code,
                }
            )

        route_basis = (
            "target_work"
            if request["target_work_ids"]
            else "card_match"
            if any(
                "full_corpus_fallback" not in item["candidate_basis"]
                for item in route_entries
            )
            else "corpus_fallback"
        )
        trace("card_route", route_ids, [], route_basis)
        trace(
            "exact_quote_search" if exact_targets else "lexical_search",
            [hit.segment.work_id for hit in base_hits],
            [hit.segment.segment_id for hit in base_hits],
            "exact_quote" if exact_targets else "search_terms",
        )
        if adjacent_hits:
            trace(
                "adjacent_expansion",
                [hit.segment.work_id for hit in adjacent_hits],
                [hit.segment.segment_id for hit in adjacent_hits],
                "same_heading_neighbor",
            )
        per_target_related_hits = [
            hit
            for hit in base_hits
            if len(target_ids) > 1 and hit.segment.work_id in target_ids
        ]
        if cross_hits or per_target_related_hits:
            trace(
                "cross_work_expansion",
                [
                    hit.segment.work_id
                    for hit in (*cross_hits, *per_target_related_hits)
                ],
                [
                    hit.segment.segment_id
                    for hit in (*cross_hits, *per_target_related_hits)
                ],
                "exact_quote"
                if exact_targets
                else "card_relationship",
            )
        trace(
            "source_readback",
            [item["work_id"] for item in source_evidence],
            [item["segment_id"] for item in source_evidence],
            "checksum_verified",
        )
        trace(
            "assessment",
            [
                item["target_work_id"]
                for item in assessments
                if item["target_work_id"] is not None
            ],
            [],
            "state_assigned",
        )

        result = {
            "schema_version": "1.0",
            "request_id": request["request_id"],
            "task_id": request["task_id"],
            "corpus_snapshot": dict(self._snapshot),
            "route_candidates": route_entries,
            "source_evidence": source_evidence,
            "retrieval_assessments": assessments,
            "variant_candidates": variant_candidates,
            "cross_work_candidates": cross_work_candidates,
            "retrieval_trace": traces,
        }
        schema_errors = sorted(
            self.result_validator.iter_errors(result),
            key=lambda error: list(error.absolute_path),
        )
        if schema_errors:
            error = schema_errors[0]
            path = "/".join(str(item) for item in error.absolute_path) or "$"
            raise ValueError(
                f"EvidenceResult violates schema at {path}: {error.message}"
            )
        invariant_errors = validate_evidence_result(
            result,
            request,
            workspace=self.workspace,
            manifest=self.manifest,
            cards=self.configuration,
        )
        if invariant_errors:
            raise ValueError(
                "EvidenceResult violates deterministic invariants: "
                + "; ".join(invariant_errors)
            )
        return result
