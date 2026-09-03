#!/usr/bin/env python3
"""Validate the public Taiyi Shuji source tree."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"
TOOLS = ROOT / "tools"
KB = ROOT / "kb"

REQUIRED_FILES = {
    "README.md",
    "README.en.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "RULES.md",
    "THEORY_CORE.md",
    "PRODUCT.md",
    "ARCHITECTURE.md",
    "requirements.txt",
    "kb/README.md",
    "spec/README.md",
    "spec/MACHINE_CONTRACT.md",
    "spec/PATIENT_RECORD.md",
    "spec/RETRIEVAL.md",
    "spec/THEORY_PROMPTS.md",
    "spec/analysis.schema.json",
    "spec/analysis_examples.json",
    "spec/case_record.schema.json",
    "spec/evidence.schema.json",
    "spec/retrieval_cards.json",
    "spec/retrieval_tests.json",
    "skill/taiyi-shuji/SKILL.md",
    "skill/taiyi-shuji/agents/openai.yaml",
    "skill/taiyi-shuji/references/classic-interpretation.md",
    "skill/taiyi-shuji/references/case-reasoning.md",
    "skill/taiyi-shuji/references/formula-analysis.md",
    "skill/taiyi-shuji/references/followup.md",
    "skill/taiyi-shuji/references/presentation-projection.md",
    "skill/taiyi-shuji/references/h5-report.md",
    "skill/taiyi-shuji/references/case-state.md",
    "skill/taiyi-shuji/scripts/select_evidence.py",
    "skill/taiyi-shuji/scripts/render_h5.py",
    "skill/taiyi-shuji/scripts/validate_presentation_projection.py",
    "skill/taiyi-shuji/scripts/case_state.py",
    "skill/taiyi-shuji/scripts/case_record.py",
    "skill/taiyi-shuji/scripts/freeze_inputs.py",
    "skill/taiyi-shuji/scripts/build_role_packet.py",
    "skill/taiyi-shuji/scripts/commit_analysis.py",
    "skill/taiyi-shuji/scripts/load_role_prompt.py",
    "skill/taiyi-shuji/scripts/render_dialogue.py",
    "skill/taiyi-shuji/scripts/validate_analysis.py",
    "tools/evidence_service/__init__.py",
    "tools/evidence_service/evidence.py",
    "tools/import_public.py",
    "tools/analysis_contract.py",
    "tools/retrieval.py",
    "tools/tangye.py",
    "tools/test_analysis_contract.py",
    "tools/test_classic_skill.py",
    "tools/fixtures/classic/CI-01-evidence-result.json",
    "tools/test_case_skill.py",
    "tools/test_case_state.py",
    "tools/test_case_record.py",
    "tools/test_formula_skill.py",
    "tools/test_followup_skill.py",
    "tools/test_h5.py",
    "tools/test_presentation_projection.py",
    "tools/test_overall_b2_acceptance.py",
    "tools/test_retrieval.py",
    "tools/test_role_packet.py",
    "tools/test_skill_commit.py",
    "tools/validate.py",
    "docs/images/formula-analysis-overview.png",
    "docs/images/qi-transformation-r0.png",
    "docs/images/conditional-pattern-r1.png",
    "docs/images/case-pattern-mechanism.png",
    "docs/images/formula-groups.png",
}

ACTIVE_SPEC_FILES = {
    "README.md",
    "MACHINE_CONTRACT.md",
    "PATIENT_RECORD.md",
    "RETRIEVAL.md",
    "THEORY_PROMPTS.md",
    "analysis.schema.json",
    "analysis_examples.json",
    "case_record.schema.json",
    "evidence.schema.json",
    "retrieval_cards.json",
    "retrieval_tests.json",
}

FORBIDDEN_ACTIVE_NAMES = {
    "gem.py",
    "gem_kernel",
    "gem_runtime",
    "model.schema.json",
    "reasoning_contract.json",
    "runtime_envelope.schema.json",
    "acceptance.json",
    "contract_tests.json",
    "runtime_tests.json",
    "retrieval_agent_acceptance.json",
}

DOCS_WITH_LINKS = {
    "README.md",
    "README.en.md",
    "THIRD_PARTY_NOTICES.md",
    "RULES.md",
    "THEORY_CORE.md",
    "PRODUCT.md",
    "ARCHITECTURE.md",
    "kb/README.md",
    "spec/README.md",
    "spec/MACHINE_CONTRACT.md",
    "spec/PATIENT_RECORD.md",
    "spec/RETRIEVAL.md",
    "spec/THEORY_PROMPTS.md",
    "skill/taiyi-shuji/SKILL.md",
    "skill/taiyi-shuji/references/presentation-projection.md",
    "skill/taiyi-shuji/references/h5-report.md",
    "skill/taiyi-shuji/references/h5-visual-system.md",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path, errors: list[str]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)}: JSON root must be an object")
        return {}
    return value


def check_layout(errors: list[str]) -> None:
    for relative in sorted(REQUIRED_FILES):
        if not (ROOT / relative).is_file():
            errors.append(f"missing active file: {relative}")

    allowed_roots = {
        ".DS_Store",
        ".git",
        ".gitignore",
        ".workbuddy",
        "ARCHITECTURE.md",
        "cases",
        "docs",
        "LICENSE",
        "PRODUCT.md",
        "README.md",
        "README.en.md",
        "RULES.md",
        "THEORY_CORE.md",
        "kb",
        "legacy",
        "refs",
        "requirements.txt",
        "runs",
        "skill",
        "spec",
        "tools",
        "THIRD_PARTY_NOTICES.md",
    }
    unexpected = sorted(item.name for item in ROOT.iterdir() if item.name not in allowed_roots)
    if unexpected:
        errors.append(f"unexpected project-root entries: {unexpected}")

    actual_spec = {
        item.name
        for item in SPEC.iterdir()
        if item.is_file() and item.name != ".DS_Store"
    }
    if not ACTIVE_SPEC_FILES.issubset(actual_spec):
        errors.append(
            "public spec file set differs: "
            f"missing={sorted(ACTIVE_SPEC_FILES - actual_spec)}"
        )

    for name in FORBIDDEN_ACTIVE_NAMES:
        if (TOOLS / name).exists() or (SPEC / name).exists() or (ROOT / name).exists():
            errors.append(f"legacy name remains active: {name}")

def check_utf8(errors: list[str]) -> None:
    paths = [ROOT / item for item in DOCS_WITH_LINKS]
    paths.extend(SPEC.glob("*.json"))
    paths.extend((ROOT / "skill").rglob("*.md"))
    paths.extend((ROOT / "skill").rglob("*.yaml"))
    paths.extend(path for path in TOOLS.rglob("*.py") if "__pycache__" not in path.parts)
    for path in sorted(set(paths)):
        if "failed-artifacts" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: not readable UTF-8: {exc}")
            continue
        if "\ufffd" in text:
            errors.append(f"{path.relative_to(ROOT)}: contains replacement character")


def check_manifest(errors: list[str]) -> None:
    manifest = load_object(KB / "manifest.json", errors)
    works = manifest.get("works", [])
    assets = manifest.get("assets", [])
    if not isinstance(works, list) or not isinstance(assets, list):
        errors.append("kb/manifest.json: works and assets must be arrays")
        return
    if manifest.get("work_count") != len(works):
        errors.append("kb/manifest.json: work_count differs")
    if manifest.get("asset_count") != len(assets):
        errors.append("kb/manifest.json: asset_count differs")

    work_ids: set[str] = set()
    declared_texts: set[Path] = set()
    for item in works:
        if not isinstance(item, dict):
            errors.append("kb/manifest.json: invalid work entry")
            continue
        work_id = item.get("work_id")
        relative = item.get("path")
        expected_sha = item.get("sha256")
        source = item.get("source")
        if not all(isinstance(value, str) for value in (work_id, relative, expected_sha, source)):
            errors.append("kb/manifest.json: incomplete work identity")
            continue
        if work_id in work_ids:
            errors.append(f"kb/manifest.json: duplicate work_id {work_id}")
        work_ids.add(work_id)
        path = (KB / relative).resolve()
        text_root = (KB / "texts").resolve()
        if not path.is_relative_to(text_root) or path.suffix != ".md":
            errors.append(f"{work_id}: source is not one Markdown under kb/texts")
            continue
        declared_texts.add(path)
        if not path.is_file():
            errors.append(f"{work_id}: missing {relative}")
        elif sha256(path) != expected_sha:
            errors.append(f"{work_id}: SHA differs")

    actual_texts = {path.resolve() for path in (KB / "texts").glob("*.md")}
    if actual_texts != declared_texts:
        errors.append(
            "kb/texts differs from manifest: "
            f"unlisted={sorted(path.name for path in actual_texts - declared_texts)}, "
            f"missing={sorted(path.name for path in declared_texts - actual_texts)}"
        )

    for item in assets:
        if not isinstance(item, dict):
            errors.append("kb/manifest.json: invalid asset entry")
            continue
        relative = item.get("path")
        expected_sha = item.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_sha, str):
            errors.append("kb/manifest.json: incomplete asset entry")
            continue
        path = (KB / relative).resolve()
        if not path.is_relative_to((KB / "assets").resolve()):
            errors.append(f"asset escaped kb/assets: {relative}")
        elif not path.is_file():
            errors.append(f"missing asset: {relative}")
        elif sha256(path) != expected_sha:
            errors.append(f"asset SHA differs: {relative}")


def check_evidence_assets(errors: list[str]) -> None:
    schema = load_object(SPEC / "evidence.schema.json", errors)
    cards = load_object(SPEC / "retrieval_cards.json", errors)
    fixtures = load_object(SPEC / "retrieval_tests.json", errors)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # jsonschema reports a structured validation error
        errors.append(f"spec/evidence.schema.json: invalid Draft 2020-12 schema: {exc}")

    card_items = cards.get("cards", [])
    card_work_ids = {
        item["work_id"] for item in card_items if isinstance(item, dict) and "work_id" in item
    }
    if len(card_work_ids) != len(card_items):
        errors.append("retrieval cards must contain unique work identities")
    for item in card_items:
        if isinstance(item, dict) and any(key in item for key in ("excerpt", "original_text", "source_path")):
            errors.append(f"calling card contains source text: {item.get('work_id', '?')}")

    if fixtures.get("schema_version") != "1.0":
        errors.append("retrieval_tests schema_version must be 1.0")
    expected_counts = {"cases": 14, "adversarial_probes": 52, "contract_mutations": 8}
    for key, count in expected_counts.items():
        value = fixtures.get(key)
        if not isinstance(value, list) or len(value) != count:
            errors.append(f"retrieval_tests {key} must contain {count} items")


def check_analysis_contract(errors: list[str]) -> None:
    schema = load_object(SPEC / "analysis.schema.json", errors)
    case_schema = load_object(SPEC / "case_record.schema.json", errors)
    examples = load_object(SPEC / "analysis_examples.json", errors)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        errors.append(f"spec/analysis.schema.json: invalid Draft 2020-12 schema: {exc}")
    try:
        Draft202012Validator.check_schema(case_schema)
    except Exception as exc:
        errors.append(
            f"spec/case_record.schema.json: invalid Draft 2020-12 schema: {exc}"
        )
    if examples.get("schema_version") != "1.1":
        errors.append("analysis_examples schema_version must be 1.1")
    expected_counts = {"valid_records": 4, "valid_failures": 1, "mutations": 14}
    for key, count in expected_counts.items():
        value = examples.get(key)
        if not isinstance(value, list) or len(value) != count:
            errors.append(f"analysis_examples {key} must contain {count} items")


def check_skill_package(errors: list[str]) -> None:
    skill_root = ROOT / "skill" / "taiyi-shuji"
    expected_files = {
        "SKILL.md",
        "agents/openai.yaml",
        "references/classic-interpretation.md",
        "references/case-reasoning.md",
        "references/formula-analysis.md",
        "references/followup.md",
        "references/presentation-projection.md",
        "references/h5-report.md",
        "references/h5-visual-system.md",
        "references/case-state.md",
        "references/pure-image-report.md",
        "assets/h5-report/VisualReportShell.tsx",
        "assets/h5-report/asset-manifest.json",
        "assets/h5-report/silk-jade-surface.webp",
        "assets/h5-report/taiyi-visual-report.css",
        "assets/pure-image-report/brand-visual-profile.json",
        "assets/pure-image-report/image-suite-plan.schema.json",
        "scripts/case_record.py",
        "scripts/case_state.py",
        "scripts/freeze_inputs.py",
        "scripts/build_role_packet.py",
        "scripts/commit_analysis.py",
        "scripts/load_role_prompt.py",
        "scripts/render_dialogue.py",
        "scripts/render_h5.py",
        "scripts/scaffold_visual_h5.py",
        "scripts/validate_presentation_projection.py",
        "scripts/validate_h5_view_model.py",
        "scripts/select_evidence.py",
        "scripts/validate_analysis.py",
        "scripts/prepare_pure_image_suite.py",
        "scripts/validate_pure_image_manifest.py",
    }
    actual_files = {
        str(path.relative_to(skill_root))
        for path in skill_root.rglob("*")
        if path.is_file() and path.name != ".DS_Store"
    }
    if actual_files != expected_files:
        errors.append(
            "taiyi-shuji Skill file set differs: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
        return

    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    parts = skill_text.split("---", 2)
    if len(parts) != 3:
        errors.append("taiyi-shuji SKILL.md frontmatter is malformed")
    else:
        frontmatter_lines = [
            line for line in parts[1].strip().splitlines() if line.strip()
        ]
        keys = [line.split(":", 1)[0] for line in frontmatter_lines if ":" in line]
        if keys != ["name", "description"]:
            errors.append("taiyi-shuji SKILL.md frontmatter must contain name and description")
        if "name: taiyi-shuji" not in frontmatter_lines:
            errors.append("taiyi-shuji SKILL.md name differs")
    if "TODO" in skill_text:
        errors.append("taiyi-shuji SKILL.md contains TODO placeholder")

    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    required_metadata = (
        'display_name: "太乙枢机"',
        "short_description:",
        'default_prompt: "使用 $taiyi-shuji ',
    )
    for marker in required_metadata:
        if marker not in metadata:
            errors.append(f"taiyi-shuji openai.yaml missing {marker}")
    if "TODO" in metadata:
        errors.append("taiyi-shuji openai.yaml contains TODO placeholder")


def check_import_boundary(errors: list[str]) -> None:
    forbidden = {"gem_kernel", "gem_runtime", "legacy"}
    active_python = list(TOOLS.rglob("*.py"))
    active_python.extend((ROOT / "skill").rglob("*.py"))
    for path in active_python:
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: cannot parse: {exc}")
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                if module.split(".", 1)[0] in forbidden:
                    errors.append(f"{path.relative_to(ROOT)} imports legacy module {module}")


def check_links(errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for relative in sorted(DOCS_WITH_LINKS):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        for raw_target in pattern.findall(text):
            target = raw_target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{relative}: broken link {raw_target}")


def run_command(command: list[str], errors: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode:
        errors.append(f"{' '.join(command)} failed:\n{output}")
    elif output:
        print(output)


def main() -> int:
    errors: list[str] = []
    check_layout(errors)
    check_utf8(errors)
    has_local_corpus = (KB / "manifest.json").is_file()
    if has_local_corpus:
        check_manifest(errors)
    check_evidence_assets(errors)
    check_analysis_contract(errors)
    check_skill_package(errors)
    check_import_boundary(errors)
    check_links(errors)

    if not errors:
        if has_local_corpus:
            run_command([sys.executable, "-B", "tools/retrieval.py", "validate"], errors)
            run_command([sys.executable, "-B", "tools/test_retrieval.py"], errors)
            run_command([sys.executable, "-B", "tools/tangye.py", "validate"], errors)
            run_command([sys.executable, "-B", "tools/test_analysis_contract.py"], errors)
        run_command([sys.executable, "-B", "tools/test_role_packet.py"], errors)
        run_command([sys.executable, "-B", "tools/test_skill_commit.py"], errors)
        if has_local_corpus:
            run_command([sys.executable, "-B", "tools/test_classic_skill.py"], errors)
        run_command([sys.executable, "-B", "tools/test_formula_skill.py"], errors)
        run_command([sys.executable, "-B", "tools/test_case_skill.py"], errors)
        run_command([sys.executable, "-B", "tools/test_case_state.py"], errors)
        run_command([sys.executable, "-B", "tools/test_case_record.py"], errors)
        run_command([sys.executable, "-B", "tools/test_followup_skill.py"], errors)
        run_command(
            [sys.executable, "-B", "tools/test_skill_execution_boundaries.py"],
            errors,
        )
        run_command([sys.executable, "-B", "tools/test_h5.py"], errors)
        run_command([sys.executable, "-B", "tools/test_presentation_projection.py"], errors)
        if has_local_corpus:
            run_command([sys.executable, "-B", "tools/test_overall_b2_acceptance.py"], errors)

    if errors:
        print("FAILED: active pre-Skill workspace", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    corpus_status = "local evidence corpus validated" if has_local_corpus else "local evidence corpus not installed"
    print(
        "PASS: public source tree, machine contract, role transport, optional "
        "read-only H5, patient record, and simple case state are valid; "
        + corpus_status
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
