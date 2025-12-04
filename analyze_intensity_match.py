"""
Analyze intensity matching between phases in HDF5 recording.

This script calculates the actual intensity difference between dark and light phases
and provides recommendations for recalibration if needed.

Usage:
    python analyze_intensity_match.py <path_to_hdf5_file>
"""

import sys
from pathlib import Path
import h5py
import numpy as np


def analyze_intensity_match(hdf5_path: str):
    """Analyze intensity matching between phases"""

    path = Path(hdf5_path)
    if not path.exists():
        print(f"[ERROR] File not found: {hdf5_path}")
        return

    print(f"[ANALYSIS] Analyzing intensity match: {path.name}")
    print("=" * 80)

    with h5py.File(path, 'r') as f:
        if 'timeseries' not in f:
            print("[ERROR] No timeseries group found")
            return

        ts = f['timeseries']

        # Check required fields
        if 'frame_mean_intensity' not in ts or 'phase_str' not in ts:
            print("[ERROR] Missing required fields (frame_mean_intensity or phase_str)")
            return

        # Load data
        intensities = ts['frame_mean_intensity'][:]
        phase_strs = ts['phase_str'][:]

        # Analyze by phase
        unique_phases = np.unique(phase_strs)

        print("\n[INTENSITY ANALYSIS] Per-Phase Statistics:")
        print("-" * 80)

        phase_stats = {}
        for phase in unique_phases:
            mask = phase_strs == phase
            phase_intensities = intensities[mask]

            phase_name = phase.decode() if isinstance(phase, bytes) else phase
            mean = np.mean(phase_intensities)
            std = np.std(phase_intensities)
            min_val = np.min(phase_intensities)
            max_val = np.max(phase_intensities)

            phase_stats[phase_name] = {
                'mean': mean,
                'std': std,
                'min': min_val,
                'max': max_val,
                'count': np.sum(mask)
            }

            print(f"\n{phase_name.upper()} Phase:")
            print(f"  Mean intensity: {mean:.2f} grayscale")
            print(f"  Std deviation: {std:.2f} grayscale")
            print(f"  Range: {min_val:.2f} - {max_val:.2f}")
            print(f"  Frame count: {np.sum(mask)}")

        # Calculate difference between phases
        if len(phase_stats) >= 2:
            phases = list(phase_stats.keys())
            phase1, phase2 = phases[0], phases[1]

            mean1 = phase_stats[phase1]['mean']
            mean2 = phase_stats[phase2]['mean']

            abs_diff = abs(mean1 - mean2)
            # Calculate relative difference as percentage of the higher value
            rel_diff_pct = (abs_diff / max(mean1, mean2)) * 100.0

            print("\n[PHASE COMPARISON]")
            print("=" * 80)
            print(f"Phase 1 ({phase1}): {mean1:.2f} grayscale")
            print(f"Phase 2 ({phase2}): {mean2:.2f} grayscale")
            print(f"Absolute difference: {abs_diff:.2f} grayscale")
            print(f"Relative difference: {rel_diff_pct:.2f}%")

            # Check against target
            target_intensity = 200.0
            error1 = abs(mean1 - target_intensity)
            error2 = abs(mean2 - target_intensity)
            error1_pct = (error1 / target_intensity) * 100.0
            error2_pct = (error2 / target_intensity) * 100.0

            print(f"\n[TARGET COMPARISON] (Target: {target_intensity:.0f} grayscale)")
            print("-" * 80)
            print(f"{phase1}: {mean1:.2f} (error: {error1:.2f} / {error1_pct:.2f}%)")
            print(f"{phase2}: {mean2:.2f} (error: {error2:.2f} / {error2_pct:.2f}%)")

            # Recommendations
            print("\n[RECOMMENDATIONS]")
            print("=" * 80)

            if rel_diff_pct <= 5.0:
                print("✅ PASS: Phase difference is within 5% tolerance")
            else:
                print(f"❌ FAIL: Phase difference ({rel_diff_pct:.2f}%) exceeds 5% tolerance")
                print("\nRecommended actions:")

                if error1_pct > 2.5 or error2_pct > 2.5:
                    print("\n1. RE-CALIBRATE with tighter tolerance:")
                    print("   - Both phases are significantly off target (>2.5%)")
                    print("   - Run IR calibration (for dark phase)")
                    print("   - Run Dual calibration (for light phase)")
                    print("   - Both should target 200 grayscale with ≤2.5% tolerance")

                if mean1 < target_intensity - 5 and mean2 < target_intensity - 5:
                    print("\n2. CHECK CAMERA SETTINGS:")
                    print(f"   - Both phases are below target ({mean1:.0f}, {mean2:.0f} < 200)")
                    print("   - Verify camera exposure time matches calibration")
                    print("   - Consider increasing target intensity or LED power limits")

                if abs(mean1 - mean2) > 10:
                    print("\n3. VERIFY LED HARDWARE:")
                    print(f"   - Large intensity difference ({abs_diff:.0f} grayscale)")
                    print("   - Check LED connections and power supply")
                    print("   - Verify ESP32 PWM output is stable")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_intensity_match.py <path_to_hdf5_file>")
        sys.exit(1)

    analyze_intensity_match(sys.argv[1])
