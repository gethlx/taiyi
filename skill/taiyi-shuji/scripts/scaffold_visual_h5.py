#!/usr/bin/env python3
"""Copy the confirmed generic visual-H5 assets into a new in-project workspace."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "h5-report"
FILES = {
    "VisualReportShell.tsx": Path("src") / "VisualReportShell.tsx",
    "taiyi-visual-report.css": Path("src") / "taiyi-visual-report.css",
    "silk-jade-surface.webp": Path("src") / "silk-jade-surface.webp",
    "asset-manifest.json": Path("asset-manifest.json"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="New or empty frontend workspace inside the project root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(ROOT):
        raise ValueError("visual H5 workspace must stay inside the project root")

    targets = {source: output_root / relative for source, relative in FILES.items()}
    collisions = [path for path in targets.values() if path.exists()]
    if collisions:
        joined = ", ".join(str(path.relative_to(ROOT)) for path in collisions)
        raise FileExistsError(f"refusing to overwrite existing H5 assets: {joined}")

    for source_name, target in targets.items():
        source = ASSET_ROOT / source_name
        if not source.is_file():
            raise FileNotFoundError(f"missing packaged H5 asset: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    print(
        "PASS: scaffolded generic visual H5 assets at "
        f"{output_root.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
