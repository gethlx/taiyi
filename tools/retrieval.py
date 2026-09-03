#!/usr/bin/env python3
"""Command-line access to the contract-1.0 evidence port."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidence_service import (
    EvidencePort,
    EvidenceRequestError,
    validate_card_configuration,
)


def _read_request(path: str | None) -> dict[str, object]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("EvidenceRequest JSON root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "validate",
        help="validate cards, corpus checksums, schema, and the rebuildable index",
    )
    subparsers.add_parser(
        "index",
        help="print non-source metadata for the process-local locator index",
    )
    query_parser = subparsers.add_parser(
        "query",
        help="read an EvidenceRequest JSON object and print an EvidenceResult",
    )
    query_parser.add_argument(
        "--input",
        help="UTF-8 JSON file; when omitted the request is read from stdin",
    )
    query_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )
    query_parser.add_argument(
        "--output",
        type=Path,
        help="write EvidenceResult JSON to this file and print only a summary",
    )
    arguments = parser.parse_args()

    try:
        port = EvidencePort()
        if arguments.command == "validate":
            errors = validate_card_configuration(
                port.manifest, port.configuration
            )
            if errors:
                raise ValueError("; ".join(errors))
            summary = port.index_summary()
            print(
                "PASS: "
                f"{summary['work_count']} calling cards cover the manifest; "
                f"{summary['segment_count']} locators rebuild from kb/texts; "
                "cards and indexes remain non-evidence and outside the manifest"
            )
            return 0
        if arguments.command == "index":
            print(json.dumps(port.index_summary(), ensure_ascii=False, indent=2))
            return 0
        request = _read_request(arguments.input)
        result = port.locate(request)
        rendered = json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":") if arguments.compact else None,
            indent=None if arguments.compact else 2,
        )
        if arguments.output:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(rendered + "\n", encoding="utf-8")
            print(
                "PASS: "
                f"{len(result['source_evidence'])} evidence records written to "
                f"{arguments.output}"
            )
        else:
            print(rendered)
        return 0
    except (
        EvidenceRequestError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
