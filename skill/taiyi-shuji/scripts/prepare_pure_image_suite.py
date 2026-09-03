#!/usr/bin/env python3
"""Validate an image-suite plan and compile deterministic Image 2 prompts.

This script does not choose medical meaning or visual metaphors. It binds an existing
patient-facing suite plan to one validated presentation projection, turns display_text
into the only allowed visible-copy whitelist, and creates batches of at most three pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any


MODES = {"exact", "condensed", "label"}
PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
NUMBER_TOKEN = re.compile(r"(?:R|Day\s*)?\d+(?:\.\d+)?(?:mg|g|ml|%|日|剂|服|次)?", re.IGNORECASE)


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_text(parent: dict[str, Any], key: str, label: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return value


def resolve_path(root: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("projection field path must be a non-empty string")
    current = root
    consumed = ""
    for match in PATH_TOKEN.finditer(path):
        key, index = match.groups()
        separator = path[len(consumed):match.start()]
        if key is not None:
            expected_separator = "." if consumed else ""
        else:
            expected_separator = ""
        if separator != expected_separator:
            raise ValueError(f"unsupported projection field path: {path}")
        if key is not None:
            if not isinstance(current, dict) or key not in current:
                raise ValueError(f"projection field does not exist: {path}")
            current = current[key]
            consumed = path[:match.end()]
        else:
            if not isinstance(current, list):
                raise ValueError(f"projection field is not an array at [{index}]: {path}")
            numeric_index = int(index)
            if not 0 <= numeric_index < len(current):
                raise ValueError(f"projection field index is out of range: {path}")
            current = current[numeric_index]
            consumed = path[:match.end()]
    if consumed != path:
        raise ValueError(f"unsupported projection field path: {path}")
    return current


def preserved_strings(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(preserved_strings(item))
        return result
    if isinstance(value, dict):
        for key in ("raw_text", "original_excerpt", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return [candidate]
    return []


def validate_exact_text(display: str, source: Any, label: str) -> None:
    candidates = preserved_strings(source)
    if isinstance(source, str):
        if display != source:
            raise ValueError(f"{label} exact text must equal its projection source")
        return
    cursor = 0
    for candidate in candidates:
        position = display.find(candidate, cursor)
        if position < 0:
            raise ValueError(f"{label} exact text does not preserve source item {candidate!r}")
        cursor = position + len(candidate)


def unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def atomic_write(path: Path, text: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"output already exists; use --force to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def validate_brand_profile(profile: dict[str, Any]) -> None:
    if profile.get("profile_version") != "1.0":
        raise ValueError("brand profile_version must be 1.0")
    for key in ("name", "art_direction", "typography"):
        require_text(profile, key, "brand_profile")
    for key in ("materials", "palette", "stable_rules", "avoid"):
        value = profile.get(key)
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"brand_profile.{key} must be a non-empty string array")


def render_prompt(
    page: dict[str, Any],
    projection: dict[str, Any],
    visual_system: dict[str, Any],
    brand_profile: dict[str, Any],
) -> str:
    display_items = page["display_text"]
    allowed_text = [item["text"] for item in display_items]
    allowed_numbers = unique_in_order(
        token
        for text in allowed_text
        for token in NUMBER_TOKEN.findall(text)
    )
    source_context = {
        field: resolve_path(projection, field) for field in page["projection_fields"]
    }

    brand_lines = [brand_profile.get("art_direction", "")]
    for key in ("materials", "palette", "stable_rules"):
        values = brand_profile.get(key, [])
        if isinstance(values, list):
            brand_lines.extend(str(value) for value in values)
    plan_lines: list[str] = []
    for key, value in visual_system.items():
        if key == "avoid":
            continue
        if isinstance(value, str) and value.strip():
            plan_lines.append(f"{key}: {value}")
    avoid = []
    for values in (brand_profile.get("avoid", []), visual_system.get("avoid", [])):
        if isinstance(values, list):
            avoid.extend(str(value) for value in values)

    copy_lines = "\n".join(
        f'- [{item["mode"]}] "{item["text"]}"' for item in display_items
    )
    number_line = " / ".join(f'"{value}"' for value in allowed_numbers) or "无"
    context_json = json.dumps(source_context, ensure_ascii=False, indent=2)
    brand_text = "\n- ".join(line for line in brand_lines if line)
    plan_text = "\n- ".join(plan_lines)
    avoid_text = "\n- ".join(unique_in_order(avoid))

    return f"""Create one finished high-resolution portrait Chinese patient-facing visual report page.
This is page {page['index']} of one image suite. It is not a website, H5 screenshot, wireframe, or plain text poster.

PAGE TYPE
{page['type']}

PAGE PURPOSE AND VISUAL EMPHASIS
{page['emphasis']}

BRAND MOTHER
- {brand_text}
- typography: {brand_profile.get('typography', '')}

CURRENT R0 / REPORT FUSION
- {plan_text}

SOURCE CONTEXT — use for understanding only; do not print JSON keys or field paths
{context_json}

VISIBLE TEXT WHITELIST — these are the only readable strings allowed anywhere in the image
{copy_lines}

TEXT POLICY
- Render Simplified Chinese with crisp, legible typography and no garbled characters.
- Do not render mode names, JSON keys, source paths, prompt instructions, or any other readable text.
- Props, seals, books, packets, instruments, diagrams, icons, and decorative marks must remain unlabeled unless their text is explicitly whitelisted above.
- The first whitelist item is the patient-facing page title. Keep it declarative and visually primary.
- Preserve every [exact] item verbatim. [condensed] and [label] are already finalized display copy; do not rewrite them.
- No English or pinyin unless it appears in the whitelist.

NUMBER WHITELIST
Only these Arabic-letter/number tokens may appear: {number_line}
Do not invent any other dose, total, day number, score, percentage, probability, severity, efficacy value, or page marker.

VISUAL FREEDOM
Choose the most direct content-bearing combination of human silhouette, meridian-like flow, botanical or prepared-herb material, preparation scene, mechanism scene, sequential storyboard, relationship field, or high-density factual atlas. The primary imagery must explain the page instead of decorating text. Do not create a second medical conclusion.

AVOID
- {avoid_text}
"""


def validate_plan(plan: dict[str, Any], projection: dict[str, Any], projection_sha256: str) -> list[dict[str, Any]]:
    if plan.get("schema_version") != "1.0":
        raise ValueError("image suite plan schema_version must be 1.0")
    binding = plan.get("projection")
    if not isinstance(binding, dict):
        raise ValueError("plan.projection must be an object")
    identity = projection.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("projection.identity must be an object")
    expected = {
        "schema_version": projection.get("schema_version"),
        "sha256": projection_sha256,
        "run_id": identity.get("run_id"),
        "result_id": identity.get("result_id"),
    }
    for key, value in expected.items():
        if binding.get(key) != value:
            raise ValueError(f"plan.projection.{key} does not match presentation projection")

    visual_system = plan.get("visual_system")
    if not isinstance(visual_system, dict):
        raise ValueError("plan.visual_system must be an object")
    pages = plan.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("plan.pages must be a non-empty array")

    files: set[str] = set()
    for position, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise ValueError(f"pages[{position - 1}] must be an object")
        if page.get("index") != position:
            raise ValueError("page indexes must be sequential and start at 1")
        file_name = require_text(page, "file", f"pages[{position - 1}]")
        if Path(file_name).name != file_name or not file_name.lower().endswith(".png"):
            raise ValueError(f"pages[{position - 1}].file must be a PNG basename")
        if file_name in files:
            raise ValueError(f"duplicate output file: {file_name}")
        files.add(file_name)
        require_text(page, "type", f"pages[{position - 1}]")
        require_text(page, "emphasis", f"pages[{position - 1}]")

        projection_fields = page.get("projection_fields")
        if not isinstance(projection_fields, list) or not projection_fields:
            raise ValueError(f"pages[{position - 1}].projection_fields must be non-empty")
        for field in projection_fields:
            resolve_path(projection, field)

        display_items = page.get("display_text")
        if not isinstance(display_items, list) or not display_items:
            raise ValueError(f"pages[{position - 1}].display_text must be non-empty")
        for item_index, item in enumerate(display_items):
            if not isinstance(item, dict):
                raise ValueError(f"pages[{position - 1}].display_text[{item_index}] must be an object")
            source_field = require_text(
                item, "source_field", f"pages[{position - 1}].display_text[{item_index}]"
            )
            text = require_text(item, "text", f"pages[{position - 1}].display_text[{item_index}]")
            mode = item.get("mode")
            if mode not in MODES:
                raise ValueError(f"pages[{position - 1}].display_text[{item_index}].mode is unsupported")
            source = resolve_path(projection, source_field)
            if mode == "exact":
                validate_exact_text(text, source, f"pages[{position - 1}].display_text[{item_index}]")
        title = display_items[0]["text"]
        if "?" in title or "？" in title:
            raise ValueError(f"pages[{position - 1}] patient-facing title must be declarative")
    return pages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--brand-profile",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "assets"
        / "pure-image-report"
        / "brand-visual-profile.json",
    )
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.batch_size <= 3:
        raise ValueError("batch size must be 1..3; validated production maximum is 3")
    plan = load_object(args.plan)
    projection_bytes = args.projection.read_bytes()
    projection = json.loads(projection_bytes.decode("utf-8"))
    if not isinstance(projection, dict):
        raise ValueError("projection root must be an object")
    projection_sha256 = sha256_bytes(projection_bytes)
    brand_profile = load_object(args.brand_profile)
    validate_brand_profile(brand_profile)
    pages = validate_plan(plan, projection, projection_sha256)
    visual_system = plan["visual_system"]

    output_paths = [
        args.output_dir / f"{page['index']:02d}-{Path(page['file']).stem}.prompt.md"
        for page in pages
    ]
    output_paths.append(args.output_dir / "generation-batches.json")
    if not args.force:
        existing = [str(path) for path in output_paths if path.exists()]
        if existing:
            raise ValueError(
                "outputs already exist; use --force to replace: " + ", ".join(existing)
            )

    batch_pages: list[dict[str, Any]] = []
    for page in pages:
        prompt_name = f"{page['index']:02d}-{Path(page['file']).stem}.prompt.md"
        prompt_path = args.output_dir / prompt_name
        atomic_write(
            prompt_path,
            render_prompt(page, projection, visual_system, brand_profile),
            force=args.force,
        )
        batch_pages.append(
            {
                "index": page["index"],
                "prompt": prompt_name,
                "output_file": page["file"],
            }
        )

    batches = [
        batch_pages[index:index + args.batch_size]
        for index in range(0, len(batch_pages), args.batch_size)
    ]
    batch_manifest = {
        "schema_version": "1.0",
        "projection_sha256": projection_sha256,
        "batch_size": args.batch_size,
        "batches": batches,
    }
    atomic_write(
        args.output_dir / "generation-batches.json",
        json.dumps(batch_manifest, ensure_ascii=False, indent=2) + "\n",
        force=args.force,
    )
    print(
        f"PASS: prepared {len(pages)} prompts in {len(batches)} batches at {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
