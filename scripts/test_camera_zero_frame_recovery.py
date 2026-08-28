"""
Test: HIK camera zero-frame detection and buffer recovery.

Runs from within ImSwitch (napari plugin context) so the real camera adapter
is used. Simulates the zero-frame condition that occurs after extended recording
by monkey-patching getLatestFrame() to return zeroed arrays for N calls, then
verifying that:
  1. Zero frames are detected and return None (not passed to brightness check)
  2. flushBuffers / stopAcquisition+startAcquisition is called after threshold
  3. Normal frames resume after recovery

Usage (run from ImSwitch napari console or a script launched in the same process):
    exec(open("scripts/test_camera_zero_frame_recovery.py").read())
"""

import logging
import time

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zero_frame_test")


def run_test(camera_adapter):
    """
    Args:
        camera_adapter: A live HIKCameraAdapter instance from main_widget.frame_capture.camera
    """
    detector_name = camera_adapter.detector_name
    detector = camera_adapter.camera_manager._detectorManagers[detector_name]

    # ----------------------------------------------------------------
    # 1. Verify normal operation — capture a real frame
    # ----------------------------------------------------------------
    logger.info("=== Step 1: Normal frame capture ===")
    frame = camera_adapter.capture_frame()
    if frame is None:
        logger.error("FAIL: Normal frame returned None — camera not ready")
        return
    logger.info(f"PASS: Normal frame shape={frame.shape} dtype={frame.dtype} max={frame.max()}")

    # ----------------------------------------------------------------
    # 2. Inject zero frames by patching getLatestFrame
    # ----------------------------------------------------------------
    logger.info("\n=== Step 2: Injecting zero frames ===")
    original_get_latest = detector.getLatestFrame
    zero_frame = np.zeros(frame.shape, dtype=frame.dtype)
    inject_count = [0]
    flush_called = [False]
    stop_called = [False]
    start_called = [False]

    def fake_zero_frame():
        inject_count[0] += 1
        logger.info(f"  [INJECT] Returning zero frame #{inject_count[0]}")
        return zero_frame.copy()

    # Patch recovery methods to track calls
    original_flush = getattr(detector, "flushBuffers", None)
    original_stop = getattr(detector, "stopAcquisition", None)
    original_start = getattr(detector, "startAcquisition", None)

    def fake_flush():
        flush_called[0] = True
        logger.info("  [DETECTOR] flushBuffers() called")
        if original_flush:
            original_flush()

    def fake_stop():
        stop_called[0] = True
        logger.info("  [DETECTOR] stopAcquisition() called")

    def fake_start():
        start_called[0] = True
        logger.info("  [DETECTOR] startAcquisition() called")

    detector.getLatestFrame = fake_zero_frame
    if original_flush:
        detector.flushBuffers = fake_flush
    if original_stop:
        detector.stopAcquisition = fake_stop
    if original_start:
        detector.startAcquisition = fake_start

    # Reset adapter state
    camera_adapter._consecutive_zero_frames = 0
    threshold = camera_adapter._zero_frame_reacq_threshold

    results = []
    for i in range(threshold + 2):
        result = camera_adapter.capture_frame()
        results.append(result)
        logger.info(f"  capture {i+1}: returned {'None' if result is None else 'frame'}")

    # Restore originals
    detector.getLatestFrame = original_get_latest
    if original_flush:
        detector.flushBuffers = original_flush
    if original_stop:
        detector.stopAcquisition = original_stop
    if original_start:
        detector.startAcquisition = original_start

    # ----------------------------------------------------------------
    # 3. Verify results
    # ----------------------------------------------------------------
    logger.info("\n=== Step 3: Verify results ===")

    all_none = all(r is None for r in results)
    if all_none:
        logger.info("PASS: All zero frames returned None (brightness retry will handle them)")
    else:
        logger.error(
            f"FAIL: {sum(r is not None for r in results)} zero frames passed through as valid"
        )

    recovery_triggered = flush_called[0] or (stop_called[0] and start_called[0])
    if recovery_triggered:
        if flush_called[0]:
            logger.info(f"PASS: flushBuffers() called after {threshold} consecutive zero frames")
        else:
            logger.info(
                f"PASS: stopAcquisition+startAcquisition called after {threshold} consecutive zero frames"
            )
    else:
        logger.error(f"FAIL: No recovery method called after {threshold} consecutive zero frames")

    # ----------------------------------------------------------------
    # 4. Verify normal capture resumes after recovery
    # ----------------------------------------------------------------
    logger.info("\n=== Step 4: Normal capture after recovery ===")
    time.sleep(0.3)
    camera_adapter._consecutive_zero_frames = 0
    frame_after = camera_adapter.capture_frame()
    if frame_after is not None and frame_after.max() > 0:
        logger.info(f"PASS: Normal frame resumed after recovery max={frame_after.max()}")
    else:
        logger.warning(
            "Could not verify normal frame — LED may be off (run during active illumination)"
        )

    logger.info("\n=== Test complete ===")


# Entry point when exec()'d from ImSwitch console:
# Assumes `widget` is the main NematostellaWidget accessible in the napari context
try:
    cam = widget.frame_capture.camera  # type: ignore[name-defined]  # noqa: F821
    run_test(cam)
except NameError:
    logger.error(
        "Could not find 'widget'. Run this from the ImSwitch napari console with the "
        "timelapse plugin loaded, or pass the camera adapter directly to run_test()."
    )
