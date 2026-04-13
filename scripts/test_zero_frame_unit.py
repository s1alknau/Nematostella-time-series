"""
Unit test for HIK camera zero-frame detection and buffer recovery.

Runs without ImSwitch or real hardware by mocking the detector and
camera manager. Verifies the logic added to HikGigECameraAdapter.

Run with:
    python scripts/test_zero_frame_unit.py
"""

import logging
import os

# ---------------------------------------------------------------------------
# Bootstrap: make src importable without installing the package
# ---------------------------------------------------------------------------
import pathlib
import sys
from unittest.mock import MagicMock

import numpy as np

_repo_root = pathlib.Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(_repo_root / "src"))

from timeseries_capture.camera_adapters import HikGigECameraAdapter  # noqa: E402

logging.basicConfig(level=logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(frame_shape=(512, 512)):
    """Return a HikGigECameraAdapter wired to a mock detector.

    Mimics the ImSwitch DetectorsManager interface:
      camera_manager[name]  -> detector
      camera_manager.getAllDeviceNames() -> list of names
    """
    detector = MagicMock()
    detector.getLatestFrame = MagicMock(return_value=np.ones(frame_shape, dtype=np.uint16) * 1000)
    # Expose all recovery methods
    detector.flushBuffers = MagicMock()
    detector.stopAcquisition = MagicMock()
    detector.startAcquisition = MagicMock()

    camera_manager = MagicMock()
    # __getitem__ so camera_manager["TestCam"] returns the detector
    camera_manager.__getitem__ = MagicMock(return_value=detector)
    camera_manager.getAllDeviceNames = MagicMock(return_value=["TestCam"])

    adapter = HikGigECameraAdapter(camera_manager, detector_name="TestCam")
    return adapter, detector


def _zero_frame(shape=(512, 512)):
    return np.zeros(shape, dtype=np.uint16)


def _normal_frame(shape=(512, 512)):
    return np.ones(shape, dtype=np.uint16) * 1000


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f" - {detail}" if detail else ""))


# ---- Test 1: Normal frame passes through ---------------------------------
print("\n[1] Normal frame passes through")
adapter, detector = _make_adapter()
detector.getLatestFrame.return_value = _normal_frame()

frame = adapter.capture_frame()
check("Returns non-None", frame is not None)
check("Frame max > 0", frame is not None and frame.max() > 0)
check("Zero counter stays 0", adapter._consecutive_zero_frames == 0)
check("flushBuffers NOT called", not detector.flushBuffers.called)


# ---- Test 2: Zero frame returns None and increments counter --------------
print("\n[2] Single zero frame -> None, counter increments")
adapter, detector = _make_adapter()
detector.getLatestFrame.return_value = _zero_frame()

frame = adapter.capture_frame()
check("Returns None for zero frame", frame is None)
check("Counter incremented to 1", adapter._consecutive_zero_frames == 1)
check("flushBuffers NOT called yet", not detector.flushBuffers.called)


# ---- Test 3: Recovery triggers after threshold ---------------------------
print("\n[3] Recovery triggers after threshold consecutive zero frames")
adapter, detector = _make_adapter()
detector.getLatestFrame.return_value = _zero_frame()
threshold = adapter._zero_frame_reacq_threshold

frames = [adapter.capture_frame() for _ in range(threshold)]
check(f"All {threshold} frames returned None", all(f is None for f in frames))
check("flushBuffers called once", detector.flushBuffers.call_count == 1)
check("Counter reset to 0 after recovery", adapter._consecutive_zero_frames == 0)


# ---- Test 4: Counter resets when normal frame arrives -------------------
print("\n[4] Counter resets on first normal frame")
adapter, detector = _make_adapter()
threshold = adapter._zero_frame_reacq_threshold

# 2 zero frames
detector.getLatestFrame.return_value = _zero_frame()
adapter.capture_frame()
adapter.capture_frame()
check("Counter = 2 after 2 zero frames", adapter._consecutive_zero_frames == 2)

# 1 normal frame
detector.getLatestFrame.return_value = _normal_frame()
frame = adapter.capture_frame()
check("Counter reset to 0", adapter._consecutive_zero_frames == 0)
check("Normal frame returned", frame is not None and frame.max() > 0)
check("flushBuffers NOT called", not detector.flushBuffers.called)


# ---- Test 5: fallback stop/start when flushBuffers absent ---------------
print("\n[5] Fallback: stopAcquisition+startAcquisition when no flushBuffers")
adapter, detector = _make_adapter()
del detector.flushBuffers  # remove flushBuffers so hasattr returns False
detector.getLatestFrame.return_value = _zero_frame()
threshold = adapter._zero_frame_reacq_threshold

for _ in range(threshold):
    adapter.capture_frame()

check("stopAcquisition called", detector.stopAcquisition.call_count >= 1)
check("startAcquisition called", detector.startAcquisition.call_count >= 1)


# ---- Test 6: No crash when no recovery method at all -------------------
print("\n[6] No crash when detector has no recovery methods")
adapter, detector = _make_adapter()
del detector.flushBuffers
del detector.stopAcquisition
del detector.startAcquisition
detector.getLatestFrame.return_value = _zero_frame()
threshold = adapter._zero_frame_reacq_threshold

try:
    for _ in range(threshold):
        adapter.capture_frame()
    check("No exception raised", True)
except Exception as e:
    check("No exception raised", False, str(e))


# ---- Test 7: Recovery repeats if zeros continue -------------------------
print("\n[7] Recovery repeats on next batch of zero frames")
adapter, detector = _make_adapter()
detector.getLatestFrame.return_value = _zero_frame()
threshold = adapter._zero_frame_reacq_threshold

# First batch -> first recovery
for _ in range(threshold):
    adapter.capture_frame()
first_flush_count = detector.flushBuffers.call_count

# Second batch -> second recovery
for _ in range(threshold):
    adapter.capture_frame()
check(
    "flushBuffers called twice (one per batch)",
    detector.flushBuffers.call_count == 2,
    f"actual={detector.flushBuffers.call_count}",
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    print("FAILED tests:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  [FAIL] {name}" + (f" - {detail}" if detail else ""))
    sys.exit(1)
else:
    print("All tests passed!")
