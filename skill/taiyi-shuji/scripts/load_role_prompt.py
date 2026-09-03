#!/usr/bin/env python3
"""Load confirmed Taiyi role instructions verbatim for one model context."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROMPTS_PATH = ROOT / "spec" / "THEORY_PROMPTS.md"
ROLE_HEADINGS = {
    "r0": "R0 角色指令",
    "r1": "R1 角色指令",
    "r2": "R2 角色指令",
    "red_team": "红方角色指令",
    "stage_c": "Stage C 角色指令",
}


def _block(document: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\n\n```text\n(.*?)\n```$",
        re.MULTILINE | re.DOTALL,
    )
    matches = pattern.findall(document)
    if len(matches) != 1:
        raise ValueError(f"expected one fenced text block under heading: {heading}")
    return matches[0]


def render(role: str) -> str:
    document = PROMPTS_PATH.read_text(encoding="utf-8")
    sections = [
        ("共同指令", _block(document, "共同指令")),
        (ROLE_HEADINGS[role], _block(document, ROLE_HEADINGS[role])),
    ]
    return "\n\n".join(f"## {heading}\n\n{text}" for heading, text in sections) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print confirmed common and current-role instructions verbatim."
    )
    parser.add_argument("--role", choices=sorted(ROLE_HEADINGS), required=True)
    args = parser.parse_args()
    print(render(args.role), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
