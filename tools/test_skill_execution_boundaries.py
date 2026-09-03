#!/usr/bin/env python3
"""Check deterministic Skill packaging and one-role prompt transport."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skill/taiyi-shuji"
LOADER = SKILL_ROOT / "scripts/load_role_prompt.py"
ROLE_HEADINGS = {
    "r0": "R0 角色指令",
    "r1": "R1 角色指令",
    "r2": "R2 角色指令",
    "red_team": "红方角色指令",
    "stage_c": "Stage C 角色指令",
}


def load(role: str) -> str:
    result = subprocess.run(
        [sys.executable, "-B", str(LOADER), "--role", role],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def main() -> int:
    errors: list[str] = []
    try:
        prompts = {role: load(role) for role in ROLE_HEADINGS}
    except RuntimeError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    for role, prompt in prompts.items():
        if prompt.count("## 共同指令") != 1:
            errors.append(f"{role} did not receive exactly one common instruction")
        own_heading = f"## {ROLE_HEADINGS[role]}"
        if prompt.count(own_heading) != 1:
            errors.append(f"{role} did not receive exactly one own-role instruction")
        for other_role, heading in ROLE_HEADINGS.items():
            if other_role != role and f"## {heading}" in prompt:
                errors.append(f"{role} received unrelated {other_role} instructions")

    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    linked_resources = set(
        re.findall(r"\((references/[^)]+\.md|scripts/[^)]+\.py)\)", skill_text)
    )
    for relative in linked_resources:
        if not (SKILL_ROOT / relative).is_file():
            errors.append(f"Skill links a missing resource: {relative}")

    packet_builder = SKILL_ROOT / "scripts/build_role_packet.py"
    packet_text = packet_builder.read_text(encoding="utf-8")
    if "--task-card" in packet_text or "当前职责任务卡" in packet_text:
        errors.append("runtime packet builder accepts a host-authored task card")

    for script in (SKILL_ROOT / "scripts").glob("*.py"):
        for module in imported_modules(script):
            if module == "legacy" or module.startswith("legacy."):
                errors.append(f"active Skill script imports legacy code: {script.name}")

    if errors:
        print("FAILED: Skill execution boundaries", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "PASS: role prompts load one responsibility, Skill links resolve, "
        "and active scripts do not import legacy code"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
