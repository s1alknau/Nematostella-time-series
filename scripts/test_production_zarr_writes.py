"""
End-to-end test: instantiate the actual production DataManagerZarr, write
a few frames, and inspect the resulting on-disk layout.

This bypasses ImSwitch entirely.  If this produces V3 sharded layout,
the production code is correct and any V2 output from ImSwitch means
ImSwitch is loading a stale in-memory module.

Run from imswitch21 env (project root):
    python scripts/test_production_zarr_writes.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

# Ensure src/ is on the path even if the package were not editable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from timeseries_capture.Datamanager.data_manager_zarr import (  # noqa: E402
    DataManagerZarr,
    TelemetryMode,
)


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="prod_zarr_test_"))
    print(f"Test dir: {tmpdir}\n")
    try:
        dm = DataManagerZarr(
            telemetry_mode=TelemetryMode.STANDARD,
            img_chunk_frames=50,
            ts_chunk_size=512,
            save_as_uint8=True,
        )
        path_str = dm.create_recording_file(
            output_dir=str(tmpdir),
            experiment_name="prod_test",
            timestamped=False,
        )
        print(f"Created store: {path_str}\n")

        # Write 5 dummy frames
        H, W = 256, 256
        rng = np.random.default_rng(0)
        for i in range(1, 6):
            frame = rng.integers(0, 4096, size=(H, W), dtype=np.uint16)
            ok = dm.save_frame(
                frame=frame,
                frame_number=i,
                metadata={
                    "phase": "continuous",
                    "cycle_number": 0,
                    "phase_enabled": False,
                    "ir_led_power": 100,
                    "white_led_power": 0,
                    "led_type": "ir",
                    "success": True,
                    "capture_method": "normal",
                },
            )
            print(f"  Frame {i}: enqueue ok={ok}")
        dm.finalize_recording({"experiment_name": "prod_test"})
        print()

        # Inspect what hit the disk
        store_path = Path(path_str)
        print(f"Inspecting: {store_path}")
        for marker in [".zgroup", "zarr.json"]:
            f = store_path / marker
            if f.exists():
                print(f"  ROOT MARKER: {marker} (size {f.stat().st_size})")

        frames_path = store_path / "images" / "frames"
        if frames_path.exists():
            print("\n  frames/ contents:")
            for item in sorted(frames_path.iterdir()):
                kind = "DIR" if item.is_dir() else "file"
                size = item.stat().st_size if item.is_file() else "-"
                print(f"    [{kind}] {item.name}  ({size} bytes)")
                if item.is_dir() and item.name == "c":
                    # V3 layout: chunks/shards under c/
                    print("      c/ subdir contents:")
                    for sub in sorted(item.rglob("*")):
                        if sub.is_file():
                            rel = sub.relative_to(item)
                            print(f"        {rel}  ({sub.stat().st_size} bytes)")

        # Verdict
        has_v3 = (store_path / "zarr.json").exists()
        has_v2 = (store_path / ".zgroup").exists()
        print()
        if has_v3 and not has_v2:
            print("✓ V3 LAYOUT (zarr.json at root) — sharding active")
            return 0
        elif has_v2 and not has_v3:
            print("✗ V2 LAYOUT (.zgroup at root) — sharding NOT active")
            print("  Production code is falling into the V2 fallback path.")
            return 1
        else:
            print("?? Mixed/unknown layout — both markers or neither")
            return 2

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
