#!/usr/bin/env python3
"""Validate a final pure-image suite manifest, files, PNG dimensions, and hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise ValueError(f"not a valid PNG with IHDR header: {path}")
    return struct.unpack(">II", header[16:24])


def resolve_path(root: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("projection field path must be a non-empty string")
    current = root
    consumed = ""
    for match in PATH_TOKEN.finditer(path):
        key, index = match.groups()
        separator = path[len(consumed):match.start()]
        expected_separator = "." if key is not None and consumed else ""
        if separator != expected_separator:
            raise ValueError(f"unsupported projection field path: {path}")
        if key is not None:
            if not isinstance(current, dict) or key not in current:
                raise ValueError(f"projection field does not exist: {path}")
            current = current[key]
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--final-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_object(args.manifest)
    projection_bytes = args.projection.read_bytes()
    projection = json.loads(projection_bytes.decode("utf-8"))
    if not isinstance(projection, dict) or not isinstance(projection.get("identity"), dict):
        raise ValueError("projection must contain identity")
    projection_sha256 = hashlib.sha256(projection_bytes).hexdigest()

    if manifest.get("schema_version") != "1.0":
        raise ValueError("manifest schema_version must be 1.0")
    binding = manifest.get("projection")
    if not isinstance(binding, dict):
        raise ValueError("manifest.projection must be an object")
    expected_binding = {
        "schema_version": projection.get("schema_version"),
        "sha256": projection_sha256,
        "run_id": projection["identity"].get("run_id"),
        "result_id": projection["identity"].get("result_id"),
    }
    for key, value in expected_binding.items():
        if binding.get(key) != value:
            raise ValueError(f"manifest.projection.{key} does not match projection")

    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("manifest.pages must be a non-empty array")
    expected_files = {args.manifest.name}
    for expected_index, page in enumerate(pages, start=1):
        if not isinstance(page, dict) or page.get("index") != expected_index:
            raise ValueError("manifest page indexes must be sequential and start at 1")
        file_name = page.get("file")
        if not isinstance(file_name, str) or Path(file_name).name != file_name:
            raise ValueError(f"manifest page {expected_index} has an invalid filename")
        if not file_name.lower().endswith(".png") or file_name in expected_files:
            raise ValueError(f"manifest page {expected_index} has a duplicate or non-PNG filename")
        expected_files.add(file_name)
        image_path = args.final_dir / file_name
        if not image_path.is_file():
            raise ValueError(f"manifest image is missing: {image_path}")
        width, height = png_dimensions(image_path)
        if page.get("width") != width or page.get("height") != height:
            raise ValueError(f"manifest dimensions do not match: {file_name}")
        if page.get("bytes") != image_path.stat().st_size:
            raise ValueError(f"manifest byte size does not match: {file_name}")
        if page.get("sha256") != file_sha256(image_path):
            raise ValueError(f"manifest SHA-256 does not match: {file_name}")
        fields = page.get("projection_fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError(f"manifest projection_fields are missing: {file_name}")
        if len(fields) != len(set(fields)):
            raise ValueError(f"manifest projection_fields contain duplicates: {file_name}")
        for field in fields:
            resolve_path(projection, field)

    actual_files = {path.name for path in args.final_dir.iterdir() if path.is_file()}
    if actual_files != expected_files:
        extra = sorted(actual_files - expected_files)
        missing = sorted(expected_files - actual_files)
        raise ValueError(f"final directory mismatch; extra={extra}, missing={missing}")

    print(
        f"PASS: validated {len(pages)} final pure-image pages for "
        f"{projection['identity'].get('run_id')}/{projection['identity'].get('result_id')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
