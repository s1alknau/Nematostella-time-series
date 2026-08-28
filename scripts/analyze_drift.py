"""
Diagnose: correlate frame-interval spikes with other telemetry channels
in a nematostella recording (HDF5 .h5/.hdf5 OR Zarr .zarr directory).

Prints:
  1. Store structure (all datasets + shape/dtype/chunks)
  2. Frame-interval statistics (mean/median/p95/p99/max)
  3. Top spikes (frame_index, actual_interval, snapshot of every other
     telemetry channel at that frame) — so recovery events or sensor
     errors that coincide with a spike become visible
  4. Cumulative drift per 10k-frame segment (to see where drift grows)

Usage:
    python scripts/analyze_drift.py path/to/nematostella_timelapse_XXX.h5
    python scripts/analyze_drift.py path/to/file.zarr
    python scripts/analyze_drift.py path/to/file.h5 --threshold 6.0 --top 20
"""

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import h5py
except ImportError:
    h5py = None  # type: ignore[assignment]

try:
    import zarr
except ImportError:
    zarr = None  # type: ignore[assignment]


def detect_format(path: Path) -> str:
    """Return 'hdf5' or 'zarr' based on path."""
    if path.is_dir():
        if (
            (path / ".zgroup").exists()
            or (path / "zarr.json").exists()
            or path.suffix.lower() == ".zarr"
        ):
            return "zarr"
        raise ValueError(f"Directory {path} is not a Zarr store")
    if path.suffix.lower() in (".h5", ".hdf5"):
        return "hdf5"
    return "hdf5"  # best-effort default


def open_store(path: Path):
    """Return (root_container, format_str, close_fn)."""
    fmt = detect_format(path)
    if fmt == "hdf5":
        if h5py is None:
            sys.exit("h5py not installed")
        f = h5py.File(str(path), "r")
        return f, "hdf5", f.close
    else:
        if zarr is None:
            sys.exit("zarr not installed")
        root = zarr.open_group(str(path), mode="r")
        return root, "zarr", lambda: None


def _is_dataset(obj, fmt: str) -> bool:
    """h5py.Dataset or zarr.Array — return True for either."""
    if fmt == "hdf5":
        return isinstance(obj, h5py.Dataset)
    # zarr: v2 uses Array, v3 uses Array. Just check for a shape+dtype.
    return hasattr(obj, "shape") and hasattr(obj, "dtype") and not hasattr(obj, "keys")


def walk_datasets(root, fmt: str):
    """Yield (path, dataset) recursively for every dataset in the store."""
    out = []
    if fmt == "hdf5":

        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                out.append((name, obj))

        root.visititems(visit)
        return out

    # Zarr: manual recursion because visititems() doesn't exist on all versions.
    def recurse(group, prefix: str):
        for key in group.keys():
            child = group[key]
            full_path = f"{prefix}/{key}" if prefix else key
            if _is_dataset(child, fmt):
                out.append((full_path, child))
            else:
                recurse(child, full_path)

    recurse(root, "")
    return out


def find_telemetry_group(root) -> str:
    """Locate the timeseries/telemetry group root (heuristic)."""
    for candidate in ("telemetry", "timeseries", "timings", "meta"):
        if candidate in root:
            return candidate
    return ""


def load_1d(root, name: str, group: str):
    """Try (group/name) then name directly. Return np.ndarray or None."""
    for path in ((f"{group}/{name}" if group else name), name):
        if path and path in root:
            arr = root[path][:]
            if arr.ndim == 1:
                return arr
    return None


def collect_1d_channels(root, fmt: str, n_frames: int) -> dict:
    """Return {name: array} for every 1-D dataset with length ~= n_frames."""
    channels = {}
    for path, ds in walk_datasets(root, fmt):
        if ds.ndim != 1:
            continue
        if ds.shape[0] != n_frames:
            continue
        try:
            channels[path] = ds[:]
        except Exception:
            pass
    return channels


def summarise(intervals: np.ndarray) -> None:
    print("\n== Frame-interval statistics (seconds) ==")
    print(f"  n           = {len(intervals)}")
    print(f"  mean        = {intervals.mean():.3f}")
    print(f"  median      = {np.median(intervals):.3f}")
    print(f"  std         = {intervals.std():.3f}")
    print(f"  p95         = {np.percentile(intervals, 95):.3f}")
    print(f"  p99         = {np.percentile(intervals, 99):.3f}")
    print(f"  max         = {intervals.max():.3f}")


def drift_by_segment(intervals: np.ndarray, target_interval: float, segment: int = 10_000) -> None:
    print(
        f"\n== Cumulative drift per {segment}-frame segment " f"(target={target_interval:.2f}s) =="
    )
    for start in range(0, len(intervals), segment):
        chunk = intervals[start : start + segment]
        drift = float((chunk - target_interval).sum())
        avg = float(chunk.mean())
        print(
            f"  frames {start:>7}..{start+len(chunk):>7}: "
            f"avg={avg:.3f}s, drift_added={drift:+7.2f}s"
        )


def show_spikes(intervals: np.ndarray, channels: dict, threshold: float, top: int) -> None:
    spike_idx = np.where(intervals > threshold)[0]
    print(f"\n== Spikes above {threshold:.2f}s ==")
    print(
        f"  {len(spike_idx)} frames exceed threshold "
        f"(={100*len(spike_idx)/len(intervals):.2f}% of {len(intervals)})"
    )

    if len(spike_idx) == 0:
        return

    # Rank by interval size, show worst N
    ranked = spike_idx[np.argsort(intervals[spike_idx])[::-1]][:top]
    other_names = [n for n in channels if not n.endswith("actual_intervals")]

    print(f"\n  Top {min(top, len(ranked))} worst spikes with concurrent telemetry values:")
    header = f"    {'frame':>7}  {'interval':>9}  " + "  ".join(
        f"{n.split('/')[-1][:18]:>18}" for n in other_names
    )
    print(header)
    print("    " + "-" * (len(header) - 4))
    for idx in ranked:
        row = f"    {int(idx):>7}  {intervals[idx]:>9.3f}  " + "  ".join(
            f"{_fmt(channels[n][idx]):>18}" for n in other_names
        )
        print(row)


def _fmt(v):
    try:
        f = float(v)
        if abs(f) < 1e-3 or abs(f) > 1e6:
            return f"{f:.2e}"
        return f"{f:.3f}"
    except Exception:
        return str(v)[:18]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "path", type=Path, help="Path to HDF5 file (.h5/.hdf5) or Zarr directory (.zarr)"
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=6.0,
        help="Interval (s) above which a frame counts as spike (default 6.0)",
    )
    ap.add_argument(
        "--top", type=int, default=20, help="How many worst spikes to list (default 20)"
    )
    ap.add_argument(
        "--target",
        type=float,
        default=None,
        help="Target frame interval (s). Default: median of actual_intervals.",
    )
    args = ap.parse_args()

    if not args.path.exists():
        sys.exit(f"Path not found: {args.path}")

    root, fmt, close = open_store(args.path)
    try:
        print(f"== {fmt.upper()} structure: {args.path.name} ==")
        for path, ds in walk_datasets(root, fmt):
            comp = getattr(ds, "compression", None) or getattr(ds, "compressor", None) or "raw"
            chunks = getattr(ds, "chunks", None)
            print(
                f"  {path:<45} shape={ds.shape} dtype={ds.dtype} "
                f"chunks={chunks} compression={comp}"
            )

        group = find_telemetry_group(root)
        intervals = load_1d(root, "actual_intervals", group)
        if intervals is None:
            sys.exit("\nERROR: could not find 'actual_intervals' dataset.")

        summarise(intervals)

        target = args.target if args.target is not None else float(np.median(intervals))
        drift_by_segment(intervals, target)

        channels = collect_1d_channels(root, fmt, len(intervals))
        show_spikes(intervals, channels, args.threshold, args.top)
    finally:
        close()


if __name__ == "__main__":
    main()
