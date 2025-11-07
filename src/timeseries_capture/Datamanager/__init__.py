"""
Datamanager Package - HDF5-based Data Storage

HDF5-basiertes Datenmanagement mit umfangreichem Telemetrie-Tracking.

Features:
- HDF5 Container Storage (alles in einer .h5 Datei)
- Raw numpy arrays (uncompressed, für Geschwindigkeit)
- Chunked Timeseries (optimiert für 72h+ Aufnahmen)
- Configurable Telemetry Modes (MINIMAL/STANDARD/COMPREHENSIVE)
- Phase-aware Recording mit Transition Tracking
- Memory-optimized für lange Aufnahmen

HDF5 Structure:
    experiment.h5
    ├── /images/
    │   ├── frame_000000  (numpy array, uncompressed)
    │   ├── frame_000001
    │   └── ...
    ├── /metadata/
    │   └── recording_info (JSON attrs)
    ├── /timeseries/
    │   ├── frame_index
    │   ├── timestamps
    │   ├── recording_elapsed_sec
    │   ├── temperature_celsius
    │   ├── led_type
    │   ├── phase
    │   └── ... (15-53 datasets depending on mode)
    └── /phase_analysis/
        └── transitions (attrs)

Telemetry Modes:
    MINIMAL       (~15 fields) - Für Tests
    STANDARD      (~40 fields) - Empfohlen ⭐
    COMPREHENSIVE (~53 fields) - Maximales Detail

Usage:
    from Datamanager import DataManager, TelemetryMode

    # Create manager
    data_mgr = DataManager(
        telemetry_mode=TelemetryMode.STANDARD,
        chunk_size=512
    )

    # Create HDF5 file
    filepath = data_mgr.create_recording_file(
        output_dir="/path/to/output",
        experiment_name="nematostella_test",
        timestamped=True
    )

    # Save frames
    data_mgr.save_frame(frame, frame_number, metadata)

    # Finalize
    data_mgr.finalize_recording(final_info)
    data_mgr.close_file()

Analysis:
    from Datamanager import load_recording_info, get_recording_summary

    # Load info
    info = load_recording_info("experiment.h5")

    # Get summary
    summary = get_recording_summary("experiment.h5")

Version: 5.0-refactored (HDF5-based)
"""

from .data_manager_hdf5 import (
    ChunkedTimeseriesWriter,
    DataManager,
    TelemetryMode,
    get_recording_summary,
    load_recording_info,
)

__version__ = "5.0.0-refactored"

__all__ = [
    # Main Classes
    "DataManager",
    "TelemetryMode",
    # Internal Components (optional, für advanced usage)
    "ChunkedTimeseriesWriter",
    # Utility Functions
    "load_recording_info",
    "get_recording_summary",
]


# ============================================================================
# TELEMETRY MODE INFO
# ============================================================================

TELEMETRY_MODE_INFO = {
    "MINIMAL": {
        "field_count": 15,
        "description": "Essential fields only",
        "use_case": "Quick tests, debugging",
        "disk_overhead": "Minimal (~30 KB per 720 frames)",
        "fields": [
            "frame_index",
            "timestamps",
            "recording_elapsed_sec",
            "actual_intervals",
            "expected_intervals",
            "temperature_celsius",
            "humidity_percent",
            "led_type",
            "led_power",
            "phase",
            "cycle_number",
            "frame_mean_intensity",
            "sync_success",
        ],
    },
    "STANDARD": {
        "field_count": 40,
        "description": "Recommended for normal recordings",
        "use_case": "Production recordings ⭐",
        "disk_overhead": "Moderate (~80 KB per 720 frames)",
        "fields": [
            "All MINIMAL fields",
            "timing_error_sec",
            "cumulative_drift_sec",
            "led_stabilization_ms",
            "exposure_ms",
            "phase_transitions",
            "frame_statistics",
            "capture_quality_metrics",
        ],
    },
    "COMPREHENSIVE": {
        "field_count": 53,
        "description": "All available fields",
        "use_case": "Detailed analysis, troubleshooting",
        "disk_overhead": "Full (~150 KB per 720 frames)",
        "fields": [
            "All STANDARD fields",
            "operation_timing_details",
            "legacy_field_compatibility",
            "extended_quality_metrics",
        ],
    },
}


def get_telemetry_mode_info(mode_name: str = None) -> dict:
    """
    Get information about telemetry modes.

    Args:
        mode_name: Optional mode name (MINIMAL/STANDARD/COMPREHENSIVE)

    Returns:
        Dictionary with mode information
    """
    if mode_name:
        return TELEMETRY_MODE_INFO.get(mode_name.upper(), {})
    return TELEMETRY_MODE_INFO


# ============================================================================
# FILE SIZE ESTIMATION
# ============================================================================


def estimate_file_size(
    num_frames: int,
    frame_shape: tuple = (2048, 2048),
    frame_dtype: str = "uint16",
    telemetry_mode: str = "STANDARD",
) -> dict:
    """
    Estimate HDF5 file size for a recording.

    Args:
        num_frames: Number of frames
        frame_shape: Frame dimensions (height, width)
        frame_dtype: numpy dtype ('uint8' or 'uint16')
        telemetry_mode: Telemetry detail level

    Returns:
        Dictionary with size estimates in MB and GB
    """
    # Calculate image data size
    bytes_per_pixel = 1 if frame_dtype == "uint8" else 2
    pixels_per_frame = frame_shape[0] * frame_shape[1]
    image_bytes = num_frames * pixels_per_frame * bytes_per_pixel

    # Calculate timeseries overhead
    timeseries_overhead = {
        "MINIMAL": 2,  # ~2 KB per frame
        "STANDARD": 3,  # ~3 KB per frame
        "COMPREHENSIVE": 4,  # ~4 KB per frame
    }

    overhead_kb = timeseries_overhead.get(telemetry_mode.upper(), 3)
    timeseries_bytes = num_frames * overhead_kb * 1024

    # Metadata overhead (constant)
    metadata_bytes = 10 * 1024  # ~10 KB

    # Total
    total_bytes = image_bytes + timeseries_bytes + metadata_bytes

    return {
        "images_mb": image_bytes / (1024 * 1024),
        "timeseries_mb": timeseries_bytes / (1024 * 1024),
        "metadata_mb": metadata_bytes / (1024 * 1024),
        "total_mb": total_bytes / (1024 * 1024),
        "total_gb": total_bytes / (1024 * 1024 * 1024),
        "num_frames": num_frames,
        "frame_shape": frame_shape,
        "telemetry_mode": telemetry_mode,
    }


# ============================================================================
# QUICK INFO
# ============================================================================


def print_package_info():
    """Print package information (useful for debugging)"""
    print(f"Datamanager Package v{__version__}")
    print("HDF5-based storage system")
    print("\nAvailable Telemetry Modes:")
    for mode, info in TELEMETRY_MODE_INFO.items():
        print(f"  {mode}: {info['field_count']} fields - {info['description']}")
    print("\nUsage:")
    print("  from Datamanager import DataManager, TelemetryMode")
    print("  manager = DataManager(telemetry_mode=TelemetryMode.STANDARD)")
