#!/usr/bin/env python3
"""Render STL files in docs/3D_Druck/STL/ to PNG previews (no external tools).

Self-contained binary/ASCII STL parser + matplotlib rendering, so it works on
any CI runner with just numpy + matplotlib (the previous f3d GitHub Action was
removed upstream). Outputs docs/3D_Druck/previews/<name>.png.

Usage:
    python scripts/render_stl_previews.py [name ...]
Without arguments, renders every STL in the STL folder.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parent.parent
STL_DIR = ROOT / "docs" / "3D_Druck" / "STL"
OUT_DIR = ROOT / "docs" / "3D_Druck" / "previews"


def load_stl(path: Path) -> np.ndarray:
    """Return an (N, 3, 3) array of triangle vertices from a binary or ASCII STL."""
    data = path.read_bytes()
    # ASCII STL starts with "solid" AND contains "facet" (binary may start with
    # "solid" in its 80-byte header too, so check for facet keyword).
    is_ascii = data[:5].lower() == b"solid" and b"facet" in data[:512].lower()
    if is_ascii:
        verts = []
        for line in data.decode("utf-8", "replace").splitlines():
            s = line.strip().split()
            if len(s) == 4 and s[0] == "vertex":
                verts.append([float(s[1]), float(s[2]), float(s[3])])
        arr = np.asarray(verts, dtype=np.float32)
        return arr.reshape(-1, 3, 3)
    # Binary STL: 80-byte header, uint32 count, then 50 bytes per triangle.
    n = struct.unpack_from("<I", data, 80)[0]
    tris = np.zeros((n, 3, 3), dtype=np.float32)
    off = 84
    for i in range(n):
        # 12 floats: normal(3) + v0(3) + v1(3) + v2(3); skip 2-byte attribute
        vals = struct.unpack_from("<12f", data, off)
        tris[i] = np.array(vals[3:12], dtype=np.float32).reshape(3, 3)
        off += 50
    return tris


def render(tris: np.ndarray, out: Path) -> None:
    # Face normals for simple diffuse shading
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals = normals / lengths
    light = np.array([1.0, 1.0, 1.5])
    light = light / np.linalg.norm(light)
    shade = np.clip(normals @ light, 0, 1) * 0.7 + 0.3  # 0.3..1.0
    base = np.array([0.30, 0.55, 0.72])  # teal-ish, matches site accent
    colors = np.clip(shade[:, None] * base[None, :], 0, 1)

    fig = plt.figure(figsize=(8, 6), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    coll = Poly3DCollection(tris, facecolors=colors, edgecolors="none")
    ax.add_collection3d(coll)

    pts = tris.reshape(-1, 3)
    mins, maxs = pts.min(axis=0), pts.max(axis=0)
    center = (mins + maxs) / 2
    span = (maxs - mins).max() / 2 or 1.0
    for setlim, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), center):
        setlim(c - span, c + span)
    try:
        ax.set_box_aspect((1, 1, 1))
    except Exception:
        pass
    ax.view_init(elev=28, azim=45)
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    fig.savefig(out, dpi=100, transparent=True)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:]
    stls = ([STL_DIR / f"{n}.stl" for n in names] if names
            else sorted(STL_DIR.glob("*.stl")))
    for stl in stls:
        if not stl.exists():
            print(f"WARNING: {stl.name} not found, skipping")
            continue
        try:
            tris = load_stl(stl)
            render(tris, OUT_DIR / f"{stl.stem}.png")
            print(f"rendered {stl.stem}.png ({len(tris)} tris)")
        except Exception as e:  # keep going on a bad file
            print(f"WARNING: failed to render {stl.name}: {e}")


if __name__ == "__main__":
    main()
