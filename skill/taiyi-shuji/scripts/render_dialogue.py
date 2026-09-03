#!/usr/bin/env python3
"""Render the complete reader-facing text result from one canonical analysis."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}\n"


def _render(record: dict[str, Any]) -> str:
    outcome = record["outcome"]
    reasoning = record["reasoning"]
    subject = record["input"]["subject"]
    parts = [
        "# 太乙枢机分析结果\n",
        _section("正式结论", outcome["summary"]),
        _section("主对象", subject["label"]),
    ]

    role_labels = {
        "r0": "R0 元典关系",
        "r1": "R1 辨证求机",
        "r2": (
            "R2 治法方药（审计前候选）"
            if "red_team" in reasoning
            else "R2 治法方药"
        ),
        "red_team": "隔离红方",
        "stage_c": "Stage C 综合",
    }
    for role, label in role_labels.items():
        if role in reasoning:
            parts.append(_section(label, reasoning[role]["text"]))

    conflicts = reasoning["unresolved_conflicts"]
    if conflicts:
        body = "\n".join(f"- {item}" for item in conflicts)
        parts.append(_section("未解实质冲突", body))

    if outcome["risks"]:
        parts.append(
            _section("风险与边界", "\n".join(f"- {item}" for item in outcome["risks"]))
        )
    if outcome["day_progression"]:
        parts.append(
            _section(
                "三日条件观察",
                "\n\n".join(
                    f"### Day {item['day']}\n\n{item['text']}"
                    for item in outcome["day_progression"]
                ),
            )
        )
    if outcome["minimum_questions"]:
        parts.append(
            _section(
                "最小补问",
                "\n".join(
                    f"{index}. {item}"
                    for index, item in enumerate(outcome["minimum_questions"], 1)
                ),
            )
        )

    source_lines: list[str] = []
    for item in record["sources"]:
        source_lines.append(
            f"- 《{item['title']}》｜`{item['source_path']}:{item['start_line']}`\n\n"
            + "\n".join(f"  > {line}" for line in item["excerpt"].splitlines())
        )
    if source_lines:
        parts.append(_section("相关短原文与来源", "\n".join(source_lines)))
    parts.append(
        "如需同源移动端 H5 或图像解释，可以继续明确提出；本轮文字结果不依赖这些扩展。\n"
    )
    return "\n".join(parts).rstrip() + "\n"


def _write_atomic(path: Path, text: str) -> None:
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
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        record = _load_object(arguments.record)
        if record.get("record_type") != "committed_analysis":
            raise ValueError("record is not a committed analysis")
        _write_atomic(arguments.output, _render(record))
        print(f"PASS: rendered {arguments.output}")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
