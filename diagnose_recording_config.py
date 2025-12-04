"""
Diagnostic script to check recording configuration from HDF5 file.

This will show us:
1. What config values were stored in the HDF5 file metadata
2. What LED power values were actually used during recording
3. Whether per-phase calibration was applied or not

Usage:
    python diagnose_recording_config.py <path_to_hdf5_file>
"""

import sys
from pathlib import Path
import h5py
import numpy as np


def diagnose_recording(hdf5_path: str):
    """Diagnose recording configuration from HDF5 file"""

    path = Path(hdf5_path)
    if not path.exists():
        print(f"[ERROR] File not found: {hdf5_path}")
        return

    print(f"[DIAGNOSTIC] Analyzing: {path.name}")
    print("=" * 80)

    with h5py.File(path, 'r') as f:
        # ====================================================================
        # 1. Check file-level metadata (recording config)
        # ====================================================================
        print("\n[CONFIG] RECORDING CONFIGURATION (from HDF5 attributes):")
        print("-" * 80)

        # Try to read from recording_info JSON first (new format)
        import json
        recording_info = {}
        if 'recording_info' in f.attrs:
            try:
                recording_info = json.loads(f.attrs['recording_info'])
                print("[INFO] Found recording_info JSON attribute")
            except Exception as e:
                print(f"[WARNING] Could not parse recording_info JSON: {e}")

        # Check if phase recording was enabled
        # Try recording_info first, then direct attribute
        phase_enabled = recording_info.get('phase_enabled', f.attrs.get('phase_enabled', False))
        print(f"phase_enabled: {phase_enabled}")

        if phase_enabled:
            light_duration = recording_info.get('light_duration_min', f.attrs.get('light_duration_min', 'N/A'))
            dark_duration = recording_info.get('dark_duration_min', f.attrs.get('dark_duration_min', 'N/A'))
            dual_light = recording_info.get('dual_light_phase', f.attrs.get('dual_light_phase', 'N/A'))
            start_light = recording_info.get('start_with_light', f.attrs.get('start_with_light', 'N/A'))
            print(f"light_duration_min: {light_duration}")
            print(f"dark_duration_min: {dark_duration}")
            print(f"dual_light_phase: {dual_light}")
            print(f"start_with_light: {start_light}")

        print("\n[LED POWER] LED POWER CONFIG:")
        print("-" * 80)

        # Legacy single power values (try recording_info first, then direct attributes)
        ir_led_power = recording_info.get('ir_led_power', f.attrs.get('ir_led_power', 'N/A'))
        white_led_power = recording_info.get('white_led_power', f.attrs.get('white_led_power', 'N/A'))
        print(f"Legacy ir_led_power: {ir_led_power}%")
        print(f"Legacy white_led_power: {white_led_power}%")

        # Per-phase power values (should be present if calibration was done)
        dark_phase_ir = recording_info.get('dark_phase_ir_power', f.attrs.get('dark_phase_ir_power', 'N/A'))
        light_phase_ir = recording_info.get('light_phase_ir_power', f.attrs.get('light_phase_ir_power', 'N/A'))
        light_phase_white = recording_info.get('light_phase_white_power', f.attrs.get('light_phase_white_power', 'N/A'))

        print(f"\nPer-phase dark_phase_ir_power: {dark_phase_ir}%")
        print(f"Per-phase light_phase_ir_power: {light_phase_ir}%")
        print(f"Per-phase light_phase_white_power: {light_phase_white}%")

        # ====================================================================
        # 2. Check actual LED powers used in frames
        # ====================================================================
        if 'timeseries' not in f:
            print("\n[ERROR] No timeseries group found in HDF5 file")
            return

        ts = f['timeseries']

        # Check if per-LED power fields exist
        has_ir_power = 'ir_led_power' in ts
        has_white_power = 'white_led_power' in ts
        has_phase_str = 'phase_str' in ts

        print(f"\n[TIMESERIES] TIMESERIES DATA FIELDS:")
        print("-" * 80)
        print(f"Has ir_led_power field: {has_ir_power}")
        print(f"Has white_led_power field: {has_white_power}")
        print(f"Has phase_str field: {has_phase_str}")

        if not (has_ir_power and has_white_power and has_phase_str):
            print("\n[WARNING] Missing required fields for per-phase LED power analysis")
            print("This HDF5 file was created with old code before per-LED power fields were added.")
            return

        # Load data
        ir_powers = ts['ir_led_power'][:]
        white_powers = ts['white_led_power'][:]
        phase_strs = ts['phase_str'][:]

        print(f"\n[ACTUAL VALUES] ACTUAL LED POWERS USED IN RECORDING:")
        print("-" * 80)

        # Analyze by phase
        unique_phases = np.unique(phase_strs)

        for phase in unique_phases:
            mask = phase_strs == phase
            ir_in_phase = ir_powers[mask]
            white_in_phase = white_powers[mask]

            # Get unique power values used in this phase
            unique_ir = np.unique(ir_in_phase)
            unique_white = np.unique(white_in_phase)

            print(f"\n{phase.decode() if isinstance(phase, bytes) else phase} Phase:")
            print(f"  IR LED powers used: {unique_ir}")
            print(f"  White LED powers used: {unique_white}")
            print(f"  Frame count: {np.sum(mask)}")

        # ====================================================================
        # 3. DIAGNOSIS
        # ====================================================================
        print(f"\n\n[DIAGNOSIS] DIAGNOSIS:")
        print("=" * 80)

        # Check if calibrated values were applied
        if phase_enabled:
            # Expected: per-phase powers should not be 100/50 (defaults)
            if dark_phase_ir == 100 and light_phase_ir == 100 and light_phase_white == 50:
                print("[ERROR] PROBLEM: Per-phase powers are still at default values (100/100/50)")
                print("   This means calibrated values were NOT saved to the recording config.")
                print("\n   Possible causes:")
                print("   1. Calibrations were run but GUI wasn't restarted to load updated code")
                print("   2. Calibrations were run but 'Saved for...' messages didn't appear")
                print("   3. Recording was started before running calibrations")
            elif dark_phase_ir != 'N/A' and light_phase_ir != 'N/A':
                print("[OK] Per-phase power values are present in config!")
                print(f"   Dark phase IR: {dark_phase_ir}%")
                print(f"   Light phase IR: {light_phase_ir}%")
                print(f"   Light phase White: {light_phase_white}%")

                # Now check if they were actually used
                dark_mask = phase_strs == b'dark'
                light_mask = phase_strs == b'light'

                actual_dark_ir = np.unique(ir_powers[dark_mask])
                actual_light_ir = np.unique(ir_powers[light_mask])
                actual_light_white = np.unique(white_powers[light_mask])

                if len(actual_dark_ir) == 1 and actual_dark_ir[0] == dark_phase_ir:
                    print(f"   [OK] Dark phase IR power matches config: {actual_dark_ir[0]}%")
                else:
                    print(f"   [ERROR] Dark phase IR power MISMATCH: config={dark_phase_ir}%, actual={actual_dark_ir}")

                if len(actual_light_ir) == 1 and actual_light_ir[0] == light_phase_ir:
                    print(f"   [OK] Light phase IR power matches config: {actual_light_ir[0]}%")
                else:
                    print(f"   [ERROR] Light phase IR power MISMATCH: config={light_phase_ir}%, actual={actual_light_ir}")

                if len(actual_light_white) == 1 and actual_light_white[0] == light_phase_white:
                    print(f"   [OK] Light phase White power matches config: {actual_light_white[0]}%")
                else:
                    print(f"   [ERROR] Light phase White power MISMATCH: config={light_phase_white}%, actual={actual_light_white}")
            else:
                print("[WARNING] Per-phase power fields are missing from config")
                print("   The recording config doesn't have per-phase power values.")
                print("   This means the GUI didn't include calibrated values when starting recording.")
        else:
            print("[INFO] Phase recording was NOT enabled")
            print(f"   Using legacy single power values: IR={ir_led_power}%, White={white_led_power}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_recording_config.py <path_to_hdf5_file>")
        sys.exit(1)

    diagnose_recording(sys.argv[1])
