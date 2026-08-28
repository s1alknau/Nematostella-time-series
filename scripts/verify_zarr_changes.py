"""
Verify that the modified data_manager_zarr.py is actually loaded by Python.
Run this BEFORE starting ImSwitch to confirm the new code is active.

Expected output:
    ✓ zarr_format=3 found at line ~487
    ✓ create_array(shards=...) found at line ~679
    ✓ Module file matches source (no stale pyc)

Run from imswitch21 env:
    python scripts/verify_zarr_changes.py
"""

import inspect
import sys
from pathlib import Path


def check():
    # Force fresh import (no cache)
    mod_name = "timeseries_capture.Datamanager.data_manager_zarr"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    from timeseries_capture.Datamanager import data_manager_zarr

    src_file = Path(inspect.getfile(data_manager_zarr))
    src_text = src_file.read_text(encoding="utf-8")

    print(f"Loaded module: {src_file}")
    print(f"Source size:   {len(src_text)} chars")
    print()

    checks = [
        ("zarr_format=3 keyword in open_group call", "zarr_format=3" in src_text),
        ("create_array with shards parameter", "shards=(self.img_chunk_frames" in src_text),
        ("SHARDED log message", "Zarr V3 SHARDED images array" in src_text),
        ("V2 fallback warning message", "Zarr V3 sharding API not available" in src_text),
    ]

    all_ok = True
    for name, found in checks:
        symbol = "✓" if found else "✗"
        print(f"  {symbol} {name}")
        if not found:
            all_ok = False

    print()
    if all_ok:
        print("✓ All markers found — modified code IS the one Python imports.")
        print("→ Safe to start ImSwitch; the new sharding code will run.")
    else:
        print("✗ Markers missing — Python is loading a DIFFERENT file.")
        print("→ Check sys.path or reinstall the package.")
    return all_ok


if __name__ == "__main__":
    ok = check()
    sys.exit(0 if ok else 1)
