"""
Check camera exposure settings used during calibration vs recording.

Usage:
    python check_exposure_settings.py <path_to_hdf5_file>
"""

import sys
from pathlib import Path

import h5py
import numpy as np


def check_exposure(hdf5_path: str):
    """Check exposure settings from HDF5 recording"""

    path = Path(hdf5_path)
    if not path.exists():
        print(f"[ERROR] File not found: {hdf5_path}")
        return

    print(f"[EXPOSURE CHECK] Analyzing: {path.name}")
    print("=" * 80)

    with h5py.File(path, "r") as f:
        if "timeseries" not in f:
            print("[ERROR] No timeseries group found")
            return

        ts = f["timeseries"]

        if "exposure_ms" not in ts:
            print("[ERROR] No exposure_ms field in timeseries")
            print("This file was created with old code before exposure tracking was added.")
            return

        # Load exposure data
        exposure_ms = ts["exposure_ms"][:]

        # Get unique values
        unique_exposures = np.unique(exposure_ms)

        print("\n[EXPOSURE TIMES] Exposure times used during recording:")
        print("-" * 80)
        print(f"Unique exposure values: {unique_exposures} ms")

        if len(unique_exposures) == 1:
            print(f"[OK] Consistent exposure time: {unique_exposures[0]} ms")
        else:
            print("[WARNING] Multiple exposure times detected!")
            for exp in unique_exposures:
                count = np.sum(exposure_ms == exp)
                print(f"  {exp} ms: {count} frames ({count/len(exposure_ms)*100:.1f}%)")

        # Statistics
        print(f"\nMean exposure: {np.mean(exposure_ms):.2f} ms")
        print(f"Std deviation: {np.std(exposure_ms):.2f} ms")
        print(f"Min: {np.min(exposure_ms):.2f} ms")
        print(f"Max: {np.max(exposure_ms):.2f} ms")

        # Camera info from attributes
        print("\n[CAMERA INFO] Camera configuration:")
        print("-" * 80)

        # Try to get from recording_info
        import json

        if "recording_info" in f.attrs:
            try:
                _recording_info = json.loads(f.attrs["recording_info"])
            except Exception:
                pass

        # Try to find camera exposure in attributes
        for key in f.attrs.keys():
            if "exposure" in key.lower() or "camera" in key.lower():
                value = f.attrs[key]
                if isinstance(value, bytes):
                    value = value.decode()
                print(f"{key}: {value}")

        # Recommendations
        print("\n[RECOMMENDATIONS]:")
        print("=" * 80)

        if len(unique_exposures) == 1:
            exp_value = unique_exposures[0]
            print(f"Recording uses consistent exposure of {exp_value} ms.")
            print("\nTo ensure calibration matches recording:")
            print(f"1. Verify camera is set to {exp_value} ms BEFORE running calibration")
            print("2. Do NOT change camera exposure between calibration and recording")
            print("3. If intensities don't match, check:")
            print("   - Camera exposure in ImSwitch GUI")
            print("   - LED stabilization time (should be >= 500ms)")
            print("   - ROI settings (calibration uses center 75%)")
        else:
            print("[ERROR] Inconsistent exposure times detected!")
            print("This should not happen. Check frame capture code.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_exposure_settings.py <path_to_hdf5_file>")
        print("\nThis script checks camera exposure settings used during recording")
        print("and helps diagnose calibration vs recording intensity mismatches.")
        sys.exit(1)

    check_exposure(sys.argv[1])
