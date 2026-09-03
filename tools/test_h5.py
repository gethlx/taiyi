#!/usr/bin/env python3
"""Validate optional same-record read-only H5 and atomic failure."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/taiyi-shuji/scripts/render_h5.py"


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render(record: Path, authoritative: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--record", str(record), "--authoritative", str(authoritative), "--output", str(output)],
        cwd=ROOT, text=True, capture_output=True,
    )


def main() -> int:
    errors: list[str] = []
    examples = json.loads((ROOT / "spec/analysis_examples.json").read_text(encoding="utf-8"))
    has_local_corpus = (ROOT / "kb/manifest.json").is_file()
    example_id = "MC-P01" if has_local_corpus else "MC-P02"
    source = next(item for item in examples["valid_records"] if item["example_id"] == example_id)
    with tempfile.TemporaryDirectory(dir=ROOT / "tools") as raw:
        temp = Path(raw)
        record = temp / "analysis.json"
        auth = temp / "authoritative.json"
        output = temp / "report.html"
        dump(record, source["record"])
        dump(auth, source["authoritative"])
        result = render(record, auth, output)
        if result.returncode:
            errors.append(f"H5 render failed: {(result.stderr or result.stdout).strip()}")
        else:
            body = output.read_text(encoding="utf-8")
            markers = [
                source["record"]["run_id"],
                source["record"]["outcome"]["result_id"],
                source["record"]["reasoning"]["r0"]["text"],
            ]
            if has_local_corpus:
                markers.extend(("潜龙勿用", "kb/texts/01_周易.md"))
            for marker in markers:
                if marker not in body:
                    errors.append(f"H5 omitted {marker}")
            lowered = body.lower()
            for forbidden in ("<form", "<input", "localstorage", "fetch(", "xmlhttprequest"):
                if forbidden in lowered:
                    errors.append(f"H5 contains forbidden surface {forbidden}")
            if "evidence_id" in body or "body_sha256" in body:
                errors.append("H5 exposed internal source identity")

        output.write_text("previous-report\n", encoding="utf-8")
        broken = copy.deepcopy(source["record"])
        if has_local_corpus:
            broken["sources"][0]["excerpt"] = "不存在的原文"
        else:
            broken["outcome"]["status"] = "invalid-status"
        bad = temp / "bad.json"
        dump(bad, broken)
        rejected = render(bad, auth, output)
        if rejected.returncode == 0 or output.read_text(encoding="utf-8") != "previous-report\n":
            errors.append("invalid H5 input overwrote the previous report")

    if errors:
        print("FAILED: optional read-only H5", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: optional H5 binds one committed run/result and remains read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
