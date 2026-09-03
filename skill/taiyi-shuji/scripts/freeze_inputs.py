#!/usr/bin/env python3
"""Freeze one Taiyi authoritative input and optional continuation context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from case_record import validate_case_snapshot


LOCK_VERSION = "1.0"
LOCK_FIELDS = {
    "lock_version",
    "authoritative_sha256",
    "context_record_sha256",
}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_input_lock(
    lock_path: Path,
    authoritative_path: Path,
    context_record_path: Path | None = None,
) -> None:
    """Verify that current bytes still match the one frozen input set."""

    lock = _load_object(lock_path)
    if set(lock) != LOCK_FIELDS or lock.get("lock_version") != LOCK_VERSION:
        raise ValueError("input lock shape is invalid")
    if lock["authoritative_sha256"] != _sha256(authoritative_path):
        raise ValueError("authoritative input changed after freeze")
    expected_context = (
        _sha256(context_record_path) if context_record_path is not None else None
    )
    if lock["context_record_sha256"] != expected_context:
        raise ValueError("context record changed or differs from the frozen input")


def _write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(
            "input lock already exists; start a fresh attempt instead of replacing it"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o444)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative", required=True, type=Path)
    parser.add_argument(
        "--context-record",
        type=Path,
        help="one continued formula record or generated follow-up case snapshot",
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        _load_object(arguments.authoritative)
        if arguments.context_record is not None:
            context = _load_object(arguments.context_record)
            record_type = context.get("record_type")
            committed_analysis = (
                record_type == "committed_analysis"
                and context.get("committed") is True
            )
            case_snapshot = (
                record_type == "case_snapshot"
                and context.get("schema_version") == "1.0"
            )
            if not committed_analysis and not case_snapshot:
                raise ValueError(
                    "context record must be one committed analysis or case snapshot"
                )
            if case_snapshot:
                validate_case_snapshot(context)
        lock = {
            "lock_version": LOCK_VERSION,
            "authoritative_sha256": _sha256(arguments.authoritative),
            "context_record_sha256": (
                _sha256(arguments.context_record)
                if arguments.context_record is not None
                else None
            ),
        }
        _write_new(arguments.output, lock)
        print(f"PASS: froze authoritative input at {arguments.output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
