#!/usr/bin/env python3
"""Collect Markdown docs into docs/ so MkDocs can serve them.

The canonical source of these files stays where it is (GitHub/PyPI read the
root README of each repo). MkDocs only builds files inside docs_dir, so we copy
the relevant ones in before building. The copies are git-ignored.

Sources:
  * this repo (recording plugin): CHANGELOG.md, Nematostella_circadian_cycle.md
  * the analysis plugin (napari-hdf5-activity): README + guides

The analysis repo location is resolved in this order:
  1. env var ANALYSIS_REPO (used by the CI workflow)
  2. ../napari-hdf5-activity  (sibling checkout)

Run before `mkdocs serve` or `mkdocs build`:

    python scripts/sync_docs.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

LOCAL_MAPPING = {
    "CHANGELOG.md": "changelog.md",
    "Nematostella_circadian_cycle.md": "circadian.md",
}

# Markdown pages from the analysis repo -> docs/analysis/<name>
ANALYSIS_MAPPING = {
    "docs/USER_GUIDE.md": "user-guide.md",
    "docs/CIRCADIAN_ANALYSIS.md": "circadian-analysis.md",
    "EXTENDED_ANALYSIS.md": "extended-analysis.md",
    "PERFORMANCE_OPTIMIZATIONS.md": "performance.md",
    "AVI_INTEGRATION_README.md": "avi-integration.md",
}

# Non-markdown assets copied verbatim (link targets referenced by the pages)
ANALYSIS_ASSETS = {
    "docs/entrainment_protocol.txt": "entrainment_protocol.txt",
    "docs/entrainment_protocol_EN.txt": "entrainment_protocol_EN.txt",
}

# Rewrite internal links so they point at the renamed pages in docs/analysis/.
# Applied in order to the copied markdown text.
LINK_REWRITES = [
    ("../EXTENDED_ANALYSIS.md", "extended-analysis.md"),
    ("EXTENDED_ANALYSIS.md", "extended-analysis.md"),
    ("../PERFORMANCE_OPTIMIZATIONS.md", "performance.md"),
    ("PERFORMANCE_OPTIMIZATIONS.md", "performance.md"),
    ("../AVI_INTEGRATION_README.md", "avi-integration.md"),
    ("AVI_INTEGRATION_README.md", "avi-integration.md"),
    ("docs/CIRCADIAN_ANALYSIS.md", "circadian-analysis.md"),
    ("CIRCADIAN_ANALYSIS.md", "circadian-analysis.md"),
    ("docs/USER_GUIDE.md", "user-guide.md"),
    ("USER_GUIDE.md", "user-guide.md"),
    ("../README.md", "index.md"),
]


def resolve_analysis_repo():
    env = os.environ.get("ANALYSIS_REPO")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(ROOT.parent / "napari-hdf5-activity")
    for c in candidates:
        if c.is_dir():
            return c
    return None


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"copied {src.name} -> {dst.relative_to(ROOT)}")


def copy_markdown_with_rewrites(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    for old, new in LINK_REWRITES:
        text = text.replace(old, new)
    dst.write_text(text, encoding="utf-8")
    print(f"copied {src.name} -> {dst.relative_to(ROOT)} (links rewritten)")


def main() -> None:
    DOCS.mkdir(exist_ok=True)

    for src_name, dst_name in LOCAL_MAPPING.items():
        src = ROOT / src_name
        if not src.exists():
            print(f"WARNING: {src_name} not found, skipping")
            continue
        copy(src, DOCS / dst_name)

    analysis_repo = resolve_analysis_repo()
    if analysis_repo is None:
        print("WARNING: analysis repo (napari-hdf5-activity) not found; "
              "set ANALYSIS_REPO or place it next to this repo.")
        return

    print(f"analysis repo: {analysis_repo}")
    for src_rel, dst_name in ANALYSIS_MAPPING.items():
        src = analysis_repo / src_rel
        if not src.exists():
            print(f"WARNING: {src_rel} not found in analysis repo, skipping")
            continue
        copy_markdown_with_rewrites(src, DOCS / "analysis" / dst_name)

    for src_rel, dst_name in ANALYSIS_ASSETS.items():
        src = analysis_repo / src_rel
        if not src.exists():
            print(f"WARNING: {src_rel} not found in analysis repo, skipping")
            continue
        copy(src, DOCS / "analysis" / dst_name)


if __name__ == "__main__":
    main()
