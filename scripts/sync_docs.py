#!/usr/bin/env python3
"""Collect Markdown docs into docs/ so MkDocs can serve them.

The canonical source of these files stays where it is (GitHub/PyPI read the
root README of each repo). MkDocs only builds files inside docs_dir, so we copy
the relevant ones in before building. The copies are git-ignored.

Sources:
  * this repo (recording plugin): CHANGELOG.md, Nematostella_circadian_cycle.md
  * the analysis plugin (napari-hdf5-activity): README + guides
  * the LSFT plugin (napari-lsft): README + demo asset

Each external repo location is resolved in this order:
  1. env var ANALYSIS_REPO / LSFT_REPO (used by the CI workflow)
  2. ../napari-hdf5-activity / ../napari-lsft  (sibling checkout)

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

# LSFT plugin (napari-lsft): a single README page -> docs/lsft/index.md
LSFT_MAPPING = {
    "README.md": "index.md",
}

# Demo asset referenced by the LSFT README (copied next to the page)
LSFT_ASSETS = {
    "examples/lsft_nema_hd_anim.gif": "lsft_nema_hd_anim.gif",
}

# The LSFT README points at the asset via its repo-relative path; the copy sits
# next to the page, so flatten the path.
LSFT_REWRITES = [
    ("examples/lsft_nema_hd_anim.gif", "lsft_nema_hd_anim.gif"),
]

# Text rewrites applied to the copied analysis markdown (in order):
#  - point internal links at the renamed pages in docs/analysis/
#  - the Chi2 periodogram (Sokolove & Bushell 1978) is not Fisher's method,
#    so drop "Fisher/" from the heading, TOC entry and its anchor link.
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
    # Example plots referenced by EXTENDED_ANALYSIS.md live at docs/images/extended/
    # in the analysis repo; on the site the page sits in docs/analysis/, so point
    # at the copies synced to docs/analysis/images/extended/.
    ("docs/images/extended/", "images/extended/"),
    ("#fisherchi-periodogram", "#chi2-periodogram"),
    ("Fisher/Chi² Periodogram", "Chi² Periodogram"),
    ("Fisher/Chi² periodogram", "Chi² periodogram"),
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


def resolve_lsft_repo():
    env = os.environ.get("LSFT_REPO")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(ROOT.parent / "napari-lsft")
    for c in candidates:
        if c.is_dir():
            return c
    return None


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"copied {src.name} -> {dst.relative_to(ROOT)}")


def copy_markdown_with_rewrites(src: Path, dst: Path, rewrites=LINK_REWRITES) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    for old, new in rewrites:
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
    else:
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

        # Example plots embedded in EXTENDED_ANALYSIS.md (docs/images/extended/*.png)
        ext_img_src = analysis_repo / "docs" / "images" / "extended"
        if ext_img_src.is_dir():
            for img in sorted(ext_img_src.glob("*.png")):
                copy(img, DOCS / "analysis" / "images" / "extended" / img.name)

    lsft_repo = resolve_lsft_repo()
    if lsft_repo is None:
        print("NOTE: LSFT repo (napari-lsft) not found; skipping LSFT page "
              "(set LSFT_REPO or place it next to this repo). This is expected "
              "if the repo is still private and CI could not check it out.")
    else:
        print(f"lsft repo: {lsft_repo}")
        for src_rel, dst_name in LSFT_MAPPING.items():
            src = lsft_repo / src_rel
            if not src.exists():
                print(f"WARNING: {src_rel} not found in LSFT repo, skipping")
                continue
            copy_markdown_with_rewrites(src, DOCS / "lsft" / dst_name, LSFT_REWRITES)

        for src_rel, dst_name in LSFT_ASSETS.items():
            src = lsft_repo / src_rel
            if not src.exists():
                print(f"WARNING: {src_rel} not found in LSFT repo, skipping")
                continue
            copy(src, DOCS / "lsft" / dst_name)


if __name__ == "__main__":
    main()
