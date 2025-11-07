# latest (updated)
"""Complete TimelapseRecorder with fixed timing, precise intervals, and phase-aware recording."""
from __future__ import annotations
import time
import threading
from typing import Tuple, Optional
import numpy as np
from threading import Lock
import logging

# Qt + Signal, immer als pyqtSignal verfügbar
try:
    from qtpy.QtCore import QObject, Signal as pyqtSignal
except Exception:
    try:
        from PyQt6.QtCore import QObject, pyqtSignal
    except Exception:
        try:
            from PyQt5.QtCore import QObject, pyqtSignal
        except Exception:
            # Fallback-Shim, falls Qt gar nicht verfügbar ist (Import/Tests laufen trotzdem)
            class QObject:  # type: ignore
                pass

            class _SignalShim:
                def __init__(self, *_a, **_k):
                    self._subs = []

                def connect(self, slot):
                    if callable(slot):
                        self._subs.append(slot)

                def emit(self, *args, **kwargs):
                    for fn in list(self._subs):
                        try:
                            fn(*args, **kwargs)
                        except Exception:
                            pass

                def disconnect(self, slot=None):
                    if slot is None:
                        self._subs.clear()
                    else:
                        self._subs = [f for f in self._subs if f is not slot]

            def pyqtSignal(*_a, **_k):  # type: ignore
                return _SignalShim()


logger = logging.getLogger(__name__)


class TimelapseRecorder(QObject):
    """Complete phase-aware timelapse recorder with corrected LED timing and precise intervals."""

    # Signals
    frame_captured = pyqtSignal(int, int)  # current_frame, total_frames
    recording_started = pyqtSignal()
    recording_finished = pyqtSignal()
    recording_paused = pyqtSignal()
    recording_resumed = pyqtSignal()
    progress_updated = pyqtSignal(int)  # percentage
    status_updated = pyqtSignal(str)  # status message
    error_occurred = pyqtSignal(str)  # recording-related errors only
    phase_changed = pyqtSignal(dict)  # phase_info dict

    # def __init__(self, duration_min: int, interval_sec: int, output_dir: str,
    #             esp32_controller, camera_manager, data_manager, imswitch_main, camera_name: str,
    #             phase_config: dict = None):
    #     super().__init__()

    #     # Recording parameters
    #     self.duration_min = duration_min
    #     self.interval_sec = interval_sec
    #     self.output_dir = output_dir

    #     # Controllers
    #     self.esp32_controller = esp32_controller
    #     self.data_manager = data_manager
    #     self.imswitch_main = imswitch_main
    #     self.camera_name = camera_name
    #     self.camera_manager = camera_manager
    #     # Phase configuration (+ defaults for features we use later)
    #     self.phase_config = (phase_config or {
    #         'enabled': False,
    #         'light_duration_min': 30,
    #         'dark_duration_min': 30,
    #         'start_with_light': True,
    #         # NEW: default values used by the capture timing
    #         'dual_light_phase': False,
    #         'camera_trigger_latency_ms': 20,   # small fudge so snap aligns with LED ON
    #     })
    #     # If caller passed a dict but omitted keys, fill sensible defaults
    #     self.phase_config.setdefault('dual_light_phase', False)
    #     self.phase_config.setdefault('camera_trigger_latency_ms', 20)

    #     # NEW: expose latency as attribute for the capture routine
    #     try:
    #         self.camera_trigger_latency_ms = int(self.phase_config.get('camera_trigger_latency_ms', 20))
    #     except Exception:
    #         self.camera_trigger_latency_ms = 20
    #     # sanity clamp
    #     if self.camera_trigger_latency_ms < 0:
    #         self.camera_trigger_latency_ms = 0
    #     if self.camera_trigger_latency_ms > 200:
    #         self.camera_trigger_latency_ms = 200  # prevent silly values

    #     # Phase tracking
    #     self.current_phase = None
    #     self.last_phase = None
    #     self.phase_start_time = None
    #     self.current_cycle = 1

    #     # Napari viewer (assigned externally)
    #     self.viewer = None

    #     # State variables
    #     self.recording = False
    #     self.paused = False
    #     self.should_stop = False
    #     self.current_frame = 0
    #     self.total_frames = self._calculate_total_frames()
    #     self.start_time = None
    #     self.expected_frame_times = []

    #     # Precise timing tracking
    #     self.actual_frame_times = []
    #     self.cumulative_drift = 0.0
    #     self.last_frame_end_time = None

    #     # Validation bypass
    #     self.skip_validation = True

    #     # Memory tracking
    #     self.last_memory_check = 0.0

    #     # Lock for shared state
    #     self._state_lock = Lock()

    #     # Recording thread
    #     self.recording_thread = None

    #     # Initialize
    #     if self.phase_config['enabled']:
    #         logger.info(
    #             "Phase-aware recording: Light=%dmin, Dark=%dmin, dual_light=%s, snap_latency=%dms",
    #             self.phase_config['light_duration_min'],
    #             self.phase_config['dark_duration_min'],
    #             self.phase_config['dual_light_phase'],
    #             self.camera_trigger_latency_ms,
    #         )
    #     else:
    #         logger.info("Continuous recording mode")
    def __init__(
        self,
        duration_min: int = 60,
        interval_sec: int = 5,
        output_dir: str = ".",
        esp32_controller=None,
        camera_manager=None,
        data_manager=None,
        imswitch_main=None,
        camera_name: str = "Camera",
        phase_config: dict = None,
        experiment_name: str = "timelapse",  # ✅ NEW - Widget might pass this
    ):
        super().__init__()

        # Recording parameters
        self.duration_min = duration_min
        self.interval_sec = interval_sec
        self.output_dir = output_dir

        # Controllers
        self.esp32_controller = esp32_controller
        self.data_manager = data_manager
        self.imswitch_main = imswitch_main
        self.camera_name = camera_name
        self.camera_manager = camera_manager

        # Phase configuration (+ defaults for features we use later)
        self.phase_config = phase_config or {
            "enabled": False,
            "light_duration_min": 30,
            "dark_duration_min": 30,
            "start_with_light": True,
            # NEW: default values used by the capture timing
            "dual_light_phase": False,
            "camera_trigger_latency_ms": 20,  # small fudge so snap aligns with LED ON
        }
        # If caller passed a dict but omitted keys, fill sensible defaults
        self.phase_config.setdefault("dual_light_phase", False)
        self.phase_config.setdefault("camera_trigger_latency_ms", 20)

        # NEW: expose latency as attribute for the capture routine
        try:
            self.camera_trigger_latency_ms = int(
                self.phase_config.get("camera_trigger_latency_ms", 20)
            )
        except Exception:
            self.camera_trigger_latency_ms = 20
        # sanity clamp
        if self.camera_trigger_latency_ms < 0:
            self.camera_trigger_latency_ms = 0
        if self.camera_trigger_latency_ms > 200:
            self.camera_trigger_latency_ms = 200  # prevent silly values

        # Phase tracking
        self.current_phase = None
        self.last_phase = None
        self.phase_start_time = None
        self.current_cycle = 1

        # Napari viewer (assigned externally)
        self.viewer = None

        # State variables
        self.recording = False
        self.paused = False
        self.should_stop = False
        self.current_frame = 0
        self.total_frames = self._calculate_total_frames()
        self.start_time = None
        self.expected_frame_times = []

        # Precise timing tracking
        self.actual_frame_times = []
        self.cumulative_drift = 0.0
        self.last_frame_end_time = None

        # Validation bypass
        self.skip_validation = True

        # Memory tracking
        self.last_memory_check = 0.0

        # Lock for shared state
        self._state_lock = Lock()

        # Recording thread
        self.recording_thread = None

        # Initialize
        if self.phase_config["enabled"]:
            logger.info(
                "Phase-aware recording: Light=%dmin, Dark=%dmin, dual_light=%s, snap_latency=%dms",
                self.phase_config["light_duration_min"],
                self.phase_config["dark_duration_min"],
                self.phase_config["dual_light_phase"],
                self.camera_trigger_latency_ms,
            )
        else:
            logger.info("Continuous recording mode")

    def _get_camera_exposure_ms(self, default_ms: int = 10) -> int:
        """
        Get camera exposure time in milliseconds from ImSwitch.
        Called ONCE at recording start to sync with ESP32.
        """
        print("\n" + "=" * 60)
        print(">>> _get_camera_exposure_ms() DEBUG")
        print("=" * 60)

        try:
            # ✅ Read from ImSwitch detector manager
            if hasattr(self, "imswitch_main") and self.imswitch_main:
                print(">>> ImSwitch main controller: FOUND")

                try:
                    detector_mgr = getattr(self.imswitch_main, "detectorsManager", None)

                    if detector_mgr:
                        print(f">>> Detector manager: FOUND")

                        if hasattr(detector_mgr, "_detectors"):
                            print(
                                f">>> Detectors available: {list(detector_mgr._detectors.keys())}"
                            )

                            # Find HIK camera detector
                            for name, det in detector_mgr._detectors.items():
                                print(f">>> Checking detector: {name}")

                                if "hik" in name.lower() or "camera" in name.lower():
                                    print(f">>> ✓ Found camera detector: {name}")

                                    if hasattr(det, "_camera"):
                                        cam = det._camera
                                        print(f">>> Camera object: {type(cam).__name__}")

                                        if hasattr(cam, "getPropertyValue"):
                                            print(
                                                ">>> Calling cam.getPropertyValue('ExposureTime')..."
                                            )

                                            try:
                                                exp = cam.getPropertyValue("ExposureTime")
                                                print(f">>> Raw exposure value: {exp}")

                                                if exp and exp > 0:
                                                    # Convert microseconds to milliseconds if needed
                                                    if exp > 10000:  # Likely in microseconds
                                                        print(
                                                            f">>> Converting from microseconds: {exp}μs"
                                                        )
                                                        exp = exp / 1000.0
                                                        print(
                                                            f">>> Converted to milliseconds: {exp}ms"
                                                        )

                                                    print(f">>> ✅ SUCCESS: Exposure = {exp}ms")
                                                    print("=" * 60 + "\n")
                                                    logger.info(
                                                        f"Camera exposure read from ImSwitch: {exp}ms"
                                                    )
                                                    return int(exp)
                                                else:
                                                    print(f">>> Invalid exposure value: {exp}")
                                            except Exception as prop_e:
                                                print(f">>> getPropertyValue failed: {prop_e}")
                                        else:
                                            print(">>> Camera has no getPropertyValue method")
                                    else:
                                        print(">>> Detector has no _camera attribute")
                                else:
                                    print(f">>> Skipping (not a camera): {name}")
                        else:
                            print(">>> Detector manager has no _detectors attribute")
                    else:
                        print(">>> Detector manager: NOT FOUND")

                except Exception as e:
                    print(f">>> Exception reading from ImSwitch: {e}")
                    logger.debug(f"ImSwitch exposure read failed: {e}")
            else:
                print(">>> ImSwitch main controller: NOT FOUND")

            # ✅ Fallback to default
            print(f">>> ⚠️ FALLBACK: Using default exposure: {default_ms}ms")
            print("=" * 60 + "\n")
            logger.warning(f"Could not read exposure - using default {default_ms}ms")
            return default_ms

        except Exception as e:
            logger.warning(f"Error getting camera exposure: {e}")
            print(f">>> ❌ ERROR: {e}")
            print(f">>> Using default: {default_ms}ms")
            print("=" * 60 + "\n")
            return default_ms

    def _calculate_total_frames(self) -> int:
        """
        Calculate total frames needed to reach target duration.

        Formula: frames = (duration_seconds / interval_seconds) + 1
        The +1 ensures the last frame is captured AT the target duration.
        """
        duration_seconds = self.duration_min * 60

        # Calculate number of intervals
        num_intervals = int(duration_seconds / self.interval_sec)

        # Number of frames = number of intervals + 1 (for the endpoint)
        total_frames = num_intervals + 1

        print(f">>> _calculate_total_frames():")
        print(f"    Duration: {self.duration_min} min = {duration_seconds}s")
        print(f"    Interval: {self.interval_sec}s")
        print(f"    Intervals: {num_intervals}")
        print(f"    Total frames: {total_frames}")
        print(f"    Last frame at: {num_intervals * self.interval_sec}s")

        return total_frames

    # ========================================================================
    # PHASE CALCULATION AND MANAGEMENT
    # ========================================================================

    def _get_current_phase_info(self, elapsed_minutes: float) -> dict:
        """Calculate current phase information based on elapsed time."""
        if not self.phase_config["enabled"]:
            return {
                "phase": "continuous",
                "led_type": "ir",
                "phase_elapsed_min": elapsed_minutes,
                "phase_remaining_min": 0,
                "cycle_number": 1,
                "total_cycles": 1,
                "phase_transition": False,
            }

        light_duration = self.phase_config["light_duration_min"]
        dark_duration = self.phase_config["dark_duration_min"]
        cycle_duration = light_duration + dark_duration
        starts_with_light = self.phase_config["start_with_light"]

        # CRITICAL FIX: Clamp elapsed time to prevent wrap-around at end
        total_duration = self.duration_min
        if elapsed_minutes >= total_duration:
            # We're at or past the end - stay in the last phase
            elapsed_minutes = total_duration - 0.001  # Just before end

        cycle_position = elapsed_minutes % cycle_duration

        # Calculate cycle number (1-indexed) with proper clamping
        current_cycle = int(elapsed_minutes / cycle_duration) + 1
        total_cycles = max(1, int(total_duration / cycle_duration))
        current_cycle = min(current_cycle, total_cycles)  # Don't exceed total cycles

        if starts_with_light:
            if cycle_position < light_duration:
                phase = "light"
                led_type = "white"
                phase_elapsed = cycle_position
                phase_remaining = light_duration - cycle_position
            else:
                phase = "dark"
                led_type = "ir"
                phase_elapsed = cycle_position - light_duration
                phase_remaining = cycle_duration - cycle_position
        else:
            if cycle_position < dark_duration:
                phase = "dark"
                led_type = "ir"
                phase_elapsed = cycle_position
                phase_remaining = dark_duration - cycle_position
            else:
                phase = "light"
                led_type = "white"
                phase_elapsed = cycle_position - dark_duration
                phase_remaining = cycle_duration - cycle_position

        phase_transition = self.last_phase is not None and self.last_phase != phase

        return {
            "phase": phase,
            "led_type": led_type,
            "phase_elapsed_min": phase_elapsed,
            "phase_remaining_min": phase_remaining,
            "cycle_number": current_cycle,
            "total_cycles": total_cycles,
            "phase_transition": phase_transition,
            "cycle_duration_min": cycle_duration,
        }

    def _handle_phase_change(self, phase_info: dict):
        """
        Handle phase transition efficiently.

        Optimized to minimize delay during phase transitions:
        - Quick LED switch (no extra waits)
        - Calibration verification (but no re-applying)
        - Stabilization happens during normal capture flow
        """
        if phase_info["phase_transition"]:
            old_phase = self.last_phase
            new_phase = phase_info["phase"]
            led_type = phase_info["led_type"]
            cycle_num = phase_info["cycle_number"]

            logger.info(f"=== PHASE TRANSITION: {old_phase} → {new_phase} (cycle {cycle_num}) ===")

            try:
                # ✅ OPTIMIZED: Only switch if LED type actually changed
                current_led = getattr(self.esp32_controller, "current_led_type", None)

                if current_led != led_type:
                    logger.info(f"Switching LED: {current_led} → {led_type}")
                    self.esp32_controller.select_led_type(led_type)

                    # ✅ CRITICAL: Only brief pause for command processing
                    # NO long stabilization wait - that happens during capture!
                    time.sleep(0.1)  # 100ms for ESP32 to process command

                    # Verify calibration (logging only, no action)
                    if (
                        hasattr(self.esp32_controller, "calibrated_powers")
                        and self.esp32_controller.calibrated_powers
                    ):
                        # Check which power should be active
                        if led_type.lower() in ["white", "whitelight"]:
                            expected_power = self.esp32_controller.calibrated_powers.get("white")
                        else:
                            expected_power = self.esp32_controller.calibrated_powers.get("ir")

                        actual_power = self.esp32_controller.led_power

                        if expected_power:
                            if abs(actual_power - expected_power) <= 1:
                                logger.info(
                                    f"✓ Calibrated power ready: {led_type.upper()} = {actual_power}%"
                                )
                            else:
                                logger.warning(
                                    f"⚠ Power mismatch: expected {expected_power}%, got {actual_power}%"
                                )
                else:
                    logger.debug(f"LED already correct: {led_type.upper()}")

            except Exception as e:
                logger.error(f"LED switch failed: {e}")

            # Update state
            self.current_cycle = cycle_num
            self.phase_start_time = time.time()

            # Emit signal for UI
            self.phase_changed.emit(phase_info)

            logger.info(f"Phase transition complete (LED stabilization will happen during capture)")

    # ========================================================================
    # RECORDING CONTROL
    # ========================================================================

    # def start(self):
    #     """Start timelapse recording."""
    #     logger.info("=== STARTING TIMELAPSE RECORDING ===")
    #     with self._state_lock:
    #         if getattr(self, "recording", False):
    #             msg = "Recording already in progress"
    #             logger.error(msg)
    #             try:
    #                 self.error_occurred.emit(msg)
    #             finally:
    #                 return

    #         # initialize flags early to avoid races
    #         self.should_stop = False
    #         self.paused = False
    #         self.recording = False   # will flip to True in _initialize_recording()

    #     try:
    #         if not getattr(self, "skip_validation", False):
    #             if not self._validate_setup():
    #                 return

    #         # must set self.recording = True in here (or right after)
    #         self._initialize_recording()  # make sure this sets self.recording = True

    #         self.recording_thread = threading.Thread(
    #             target=self._recording_loop, daemon=True
    #         )
    #         self.recording_thread.start()

    #         try:
    #             self.recording_started.emit()
    #         except Exception:
    #             pass

    #         logger.info("Recording started successfully")

    #     except Exception as e:
    #         logger.exception("Failed to start recording")
    #         try:
    #             self.error_occurred.emit(f"Failed to start recording: {e}")
    #         except Exception:
    #             pass
    # ------------------------
    # def start(self):
    #     """Start timelapse recording with proper LED initialization."""
    #     logger.info("=== STARTING TIMELAPSE RECORDING ===")
    #     print("\n" + "="*80)
    #     print(">>> RECORDER: start() CALLED")
    #     print("="*80)

    #     with self._state_lock:
    #         if getattr(self, "recording", False):
    #             msg = "Recording already in progress"
    #             logger.error(msg)
    #             print(f">>> ERROR: {msg}")
    #             try:
    #                 self.error_occurred.emit(msg)
    #             finally:
    #                 return

    #         # Initialize flags early to avoid races
    #         self.should_stop = False
    #         self.paused = False
    #         self.recording = False   # will flip to True in _initialize_recording()

    #     try:
    #         # Validation
    #         if not getattr(self, "skip_validation", False):
    #             print(">>> Step 1: Validating setup...")
    #             if not self._validate_setup():
    #                 print(">>> Validation failed - aborting")
    #                 return
    #             print(">>> Validation passed")

    #         # Initialize recording (sets self.recording = True)
    #         print(">>> Step 2: Initializing recording...")
    #         self._initialize_recording()
    #         print(">>> Recording initialized")

    #         # ================================================================
    #         # ✅ NEW: Initialize LED for starting phase BEFORE recording starts
    #         # ================================================================
    #         print(">>> Step 3: Initializing LED for starting phase...")

    #         try:
    #             # Determine starting phase (elapsed = 0 minutes)
    #             phase_info = self._get_current_phase_info(0.0)
    #             led_type = phase_info.get('led_type', 'ir')
    #             starting_phase = phase_info.get('phase', 'continuous')

    #             print(f">>> Starting phase: {starting_phase} | LED: {led_type}")
    #             logger.info(f"Starting with {starting_phase.upper()} phase - LED: {led_type.upper()}")

    #             # Check if ESP32 is available
    #             if self.esp32_controller and hasattr(self.esp32_controller, 'select_led_type'):
    #                 print(f">>> Selecting {led_type.upper()} LED...")

    #                 # Switch to starting LED
    #                 self.esp32_controller.select_led_type(led_type)

    #                 # ✅ CRITICAL: Give LED time to stabilize after switch
    #                 stabilization_time = 0.5  # 500ms
    #                 print(f">>> Waiting {stabilization_time}s for LED to stabilize...")
    #                 time.sleep(stabilization_time)

    #                 print(f">>> LED initialized: {led_type.upper()} ready for capture")
    #                 logger.info(f"LED initialized: {led_type.upper()} ready")

    #                 # ✅ CRITICAL: Set initial phase to avoid unnecessary switch at Frame 0
    #                 self.last_phase = starting_phase
    #                 print(f">>> Initial phase set: {starting_phase}")

    #             else:
    #                 print(">>> Warning: ESP32 not available for LED initialization")
    #                 logger.warning("ESP32 not available - LED not initialized")
    #                 self.last_phase = None  # Will trigger normal phase handling

    #         except Exception as led_init_e:
    #             # Log but continue - recording will attempt to recover
    #             logger.warning(f"LED initialization failed: {led_init_e}")
    #             print(f">>> Warning: LED init failed: {led_init_e}")
    #             print(f">>> Continuing anyway - Frame 0 may have incorrect lighting")
    #             self.last_phase = None  # Will trigger normal phase handling

    #             try:
    #                 self.error_occurred.emit(f"LED init warning: {led_init_e}")
    #             except Exception:
    #                 pass
    def start(self):
        """Start timelapse recording with proper LED initialization."""
        logger.info("=== STARTING TIMELAPSE RECORDING ===")
        print("\n" + "=" * 80)
        print(">>> RECORDER: start() CALLED")
        print("=" * 80)

        with self._state_lock:
            if getattr(self, "recording", False):
                msg = "Recording already in progress"
                logger.error(msg)
                print(f">>> ERROR: {msg}")
                try:
                    self.error_occurred.emit(msg)
                finally:
                    return

            # Initialize flags early to avoid races
            self.should_stop = False
            self.paused = False
            self.recording = False  # will flip to True in _initialize_recording()

        try:
            # Validation
            if not getattr(self, "skip_validation", False):
                print(">>> Step 1: Validating setup...")
                if not self._validate_setup():
                    print(">>> Validation failed - aborting")
                    return
                print(">>> Validation passed")

            # Initialize recording (sets self.recording = True)
            print(">>> Step 2: Initializing recording...")
            self._initialize_recording()
            print(">>> Recording initialized")

            # ================================================================
            # ✅ Step 3: LED INITIALIZATION
            # ================================================================
            print(">>> Step 3: Initializing LED for starting phase...")

            try:
                # Determine starting phase (elapsed = 0 minutes)
                phase_info = self._get_current_phase_info(0.0)
                led_type = phase_info.get("led_type", "ir")
                starting_phase = phase_info.get("phase", "continuous")

                print(f">>> Starting phase: {starting_phase} | LED: {led_type}")
                logger.info(
                    f"Starting with {starting_phase.upper()} phase - LED: {led_type.upper()}"
                )

                # Check if ESP32 is available
                if self.esp32_controller and hasattr(self.esp32_controller, "select_led_type"):
                    print(f">>> Selecting {led_type.upper()} LED...")

                    # Switch to starting LED
                    self.esp32_controller.select_led_type(led_type)

                    # ✅ Give LED time to stabilize after switch
                    stabilization_time = 1.0  # 1000ms
                    print(f">>> Waiting {stabilization_time}s for LED to stabilize...")
                    time.sleep(stabilization_time)

                    print(f">>> LED initialized: {led_type.upper()} ready")
                    logger.info(f"LED initialized: {led_type.upper()} ready")

                    # ✅ Set initial phase to avoid unnecessary switch at Frame 0
                    self.last_phase = starting_phase
                    print(f">>> Initial phase set: {starting_phase}")

                else:
                    print(">>> Warning: ESP32 not available for LED initialization")
                    logger.warning("ESP32 not available - LED not initialized")
                    self.last_phase = None

            except Exception as led_init_e:
                logger.warning(f"LED initialization failed: {led_init_e}")
                print(f">>> Warning: LED init failed: {led_init_e}")
                print(f">>> Continuing anyway - Frame 0 may have incorrect lighting")
                self.last_phase = None

            # ================================================================
            # ✅ Step 4: CAMERA WARMUP
            # ================================================================
            print(">>> Step 4: Camera warmup...")

            try:
                # Do a dummy capture to "wake up" the camera
                # The first capture is always slower!
                print(">>> Performing warmup capture...")

                # Try to capture a frame (will be discarded)
                warmup_frame = None
                try:
                    if hasattr(self, "_safe_capture_frame"):
                        warmup_frame, _ = self._safe_capture_frame()
                    elif hasattr(self, "_memory_safe_capture_frame"):
                        warmup_frame, _ = self._memory_safe_capture_frame()

                    if warmup_frame is not None:
                        print(f">>> Warmup capture successful: {warmup_frame.shape}")
                        logger.info("Camera warmup completed")

                        # Clean up immediately
                        del warmup_frame
                        warmup_frame = None

                        # Small pause to let camera reset
                        time.sleep(0.2)
                    else:
                        print(">>> Warmup capture returned None (camera might not be ready)")
                        logger.warning("Warmup capture failed - camera may be slow on Frame 0")

                except Exception as warmup_e:
                    print(f">>> Warmup capture failed: {warmup_e}")
                    logger.warning(f"Camera warmup failed: {warmup_e}")
                    # Continue anyway - Frame 0 might just be slower

                print(">>> Camera warmup complete")

            except Exception as warmup_error:
                print(f">>> Warmup error (non-fatal): {warmup_error}")
                logger.warning(f"Camera warmup error: {warmup_error}")

            # ================================================================
            # ✅ Step 5: ESP32 TIMING SYNC
            # ================================================================
            print("\n" + "=" * 80)
            print(">>> Step 5: ESP32 TIMING SYNC")
            print("=" * 80)

            try:
                # Get actual camera exposure (with detailed debug)
                print(">>> Reading camera exposure from ImSwitch...")
                current_exp_ms = int(self._get_camera_exposure_ms(default_ms=10))

                print("\n>>> CAMERA EXPOSURE:")
                print(f"    Value read: {current_exp_ms}ms")
                print(f"    Source: ImSwitch detector manager")

                # Get ESP32 current values
                esp32_current_exp = int(getattr(self.esp32_controller, "exposure_ms", 10))
                esp32_current_stab = int(
                    getattr(self.esp32_controller, "led_stabilization_ms", 500)
                )

                print("\n>>> ESP32 CURRENT VALUES:")
                print(f"    Stabilization: {esp32_current_stab}ms")
                print(f"    Exposure: {esp32_current_exp}ms")

                # Check if sync needed
                if current_exp_ms != esp32_current_exp:
                    print("\n>>> ⚠️ MISMATCH DETECTED!")
                    print(f"    Camera: {current_exp_ms}ms")
                    print(f"    ESP32:  {esp32_current_exp}ms")
                    print(f"    Difference: {abs(current_exp_ms - esp32_current_exp)}ms")
                else:
                    print("\n>>> ✓ Already synchronized")

                # ALWAYS sync at start (don't trust previous values)
                print("\n>>> SYNCING ESP32...")
                print(f"    Setting: stab={esp32_current_stab}ms, exp={current_exp_ms}ms")

                self.esp32_controller.set_timing(
                    stabilization_ms=esp32_current_stab, exposure_ms=current_exp_ms
                )

                # Update controller's internal state
                self.esp32_controller.exposure_ms = current_exp_ms

                # Wait for firmware to process
                print(">>> Waiting 200ms for firmware to process...")
                time.sleep(0.2)

                print("\n>>> ✅ ESP32 TIMING SYNC COMPLETE")
                print(f"    Stabilization: {esp32_current_stab}ms")
                print(f"    Exposure: {current_exp_ms}ms")
                print(f"    Total LED duration: {esp32_current_stab + current_exp_ms}ms")
                print("=" * 80 + "\n")

                logger.info(
                    f"ESP32 timing synced at start: stab={esp32_current_stab}ms, exp={current_exp_ms}ms"
                )

            except Exception as sync_e:
                logger.error(f"ESP32 timing sync failed: {sync_e}")
                print(f"\n>>> ❌ ESP32 TIMING SYNC FAILED: {sync_e}")
                print(">>> Continuing with default values...")
                print("=" * 80 + "\n")

            # ================================================================
            # Step 6: Start recording thread
            # ================================================================
            print(">>> Step 6: Starting recording thread...")
            self.recording_thread = threading.Thread(
                target=self._recording_loop, daemon=True, name="RecordingThread"
            )
            self.recording_thread.start()
            print(">>> Recording thread started")

            # Emit signal
            try:
                self.recording_started.emit()
                print(">>> recording_started signal emitted")
            except Exception as signal_e:
                print(f">>> Warning: Signal emit failed: {signal_e}")

            logger.info("Recording started successfully")
            print(">>> Recording started successfully")
            print("=" * 80 + "\n")

        except Exception as e:
            logger.exception("Failed to start recording")
            print(f"\n>>> CRITICAL ERROR in start(): {e}")
            import traceback

            traceback.print_exc()

            # Ensure recording flag is reset on failure
            with self._state_lock:
                self.recording = False
                self.should_stop = True

            try:
                self.error_occurred.emit(f"Failed to start recording: {e}")
            except Exception:
                pass

            print("=" * 80 + "\n")

    def stop(self):
        """Request stop (non-blocking)."""
        with self._state_lock:
            if not getattr(self, "recording", False):
                return
            self.should_stop = True

        try:
            self.status_updated.emit("Stopping recording...")
        except Exception:
            pass

    def stop_and_wait(self, timeout: float = 10.0) -> bool:
        """Stop and wait for completion (blocking)."""
        self.stop()
        t = getattr(self, "recording_thread", None)
        if t and t.is_alive():
            t.join(timeout=timeout)

        # Fallback: ensure file is closed even if the thread died early
        try:
            if getattr(self, "data_manager", None) and self.data_manager.is_file_open():
                self.data_manager.close_file()
        except Exception:
            pass

        return not (t and t.is_alive())

    def pause(self):
        """Pause recording."""
        with self._state_lock:
            if not getattr(self, "recording", False) or getattr(self, "paused", False):
                return
            self.paused = True
        try:
            self.recording_paused.emit()
            self.status_updated.emit("Recording paused")
        except Exception:
            pass

    def resume(self):
        """Resume recording."""
        with self._state_lock:
            if not getattr(self, "recording", False) or not getattr(self, "paused", False):
                return
            self.paused = False
        try:
            self.recording_resumed.emit()
            self.status_updated.emit("Recording resumed")
        except Exception:
            pass

    def probe_frame(self) -> bool:
        """Lightweight probe to verify frame capture works."""
        try:
            frame, metadata = self._safe_capture_frame()
            logger.info(f"Probe: got frame {frame.shape} from {metadata.get('source')}")
            return True
        except Exception as e:
            logger.error(f"Probe failed: {e}")
            return False

    # ========================================================================
    # FRAME CAPTURE METHODS
    # ========================================================================

    def _capture_frame_sync_fixed(self) -> float:
        """
        Frame capture with correct LED timing.
        Captures DURING the LED pulse (supports optional dual-LED in LIGHT phase).
        Exposure is synced once at recording start - no runtime re-sync needed.

        Returns:
            float: Absolute capture timestamp (seconds since epoch)
        """
        print(f"\n{'='*80}")
        print(
            f">>> _capture_frame_sync_fixed() START: Frame {self.current_frame}/{self.total_frames}"
        )
        print(f"{'='*80}")
        logger.debug(f"Starting frame capture: {self.current_frame}/{self.total_frames}")

        with self._state_lock:
            if self.current_frame >= self.total_frames:
                print(f">>> SKIP: Frame {self.current_frame} >= {self.total_frames}")
                return time.time()

        frame = None
        frame_metadata = None
        esp32_timing = None
        actual_capture_timestamp = time.time()

        try:
            # Memory check every 10 frames
            if self.current_frame > 0 and self.current_frame % 10 == 0:
                print(f">>> Memory check at frame {self.current_frame}")
                if not self._memory_safety_check():
                    print(">>> ERROR: Memory safety threshold exceeded")
                    self.error_occurred.emit("Memory safety threshold exceeded")
                    with self._state_lock:
                        self.should_stop = True
                    return actual_capture_timestamp

            # Phase calculation
            operation_start_time = time.time()
            capture_start_time = operation_start_time
            elapsed_minutes = (capture_start_time - self.start_time) / 60.0
            phase_info = self._get_current_phase_info(elapsed_minutes)

            print(
                f">>> Phase info: {phase_info.get('phase')} | LED: {phase_info.get('led_type', 'unknown')}"
            )

            # Handle phase transitions
            current_phase = phase_info["phase"]
            last_phase = getattr(self, "last_phase", None)

            if current_phase != last_phase and last_phase is not None:
                print(f">>> Phase transition: {last_phase} → {current_phase}")
                self._handle_phase_change(phase_info)
                self.last_phase = current_phase
            elif last_phase is None:
                print(f">>> Initial phase recorded: {current_phase}")
                self.last_phase = current_phase
            else:
                print(f">>> Phase unchanged: {current_phase}")

            # Cleanup memory-intensive layers
            self._cleanup_memory_intensive_layers()

            # Build timing metadata
            if self.current_frame < len(self.expected_frame_times):
                expected_time = self.expected_frame_times[self.current_frame]
            else:
                expected_time = capture_start_time

            capture_elapsed_sec = capture_start_time - self.start_time
            expected_elapsed_sec = self.current_frame * self.interval_sec
            timing_error_sec = capture_elapsed_sec - expected_elapsed_sec

            if self.current_frame > 0 and len(self.actual_frame_times) > 0:
                actual_interval_sec = capture_start_time - self.actual_frame_times[-1]
                interval_error_sec = actual_interval_sec - self.interval_sec
            else:
                actual_interval_sec = 0.0
                interval_error_sec = 0.0

            frame_drift = capture_start_time - expected_time
            self.cumulative_drift += frame_drift

            python_timing = {
                "capture_timestamp_absolute": float(capture_start_time),
                "operation_start_absolute": float(operation_start_time),
                "operation_end_absolute": float(capture_start_time),
                "capture_elapsed_sec": float(capture_elapsed_sec),
                "expected_elapsed_sec": float(expected_elapsed_sec),
                "actual_interval_sec": float(actual_interval_sec),
                "expected_interval_sec": float(self.interval_sec),
                "interval_error_sec": float(interval_error_sec),
                "timing_error_sec": float(timing_error_sec),
                "cumulative_drift_sec": float(self.cumulative_drift),
                "operation_duration_sec": 0.0,
                "capture_overhead_sec": 0.0,
                "start_time": capture_start_time,
                "expected_time": expected_time,
                "frame_drift": frame_drift,
                "cumulative_drift": self.cumulative_drift,
                "expected_interval": self.interval_sec,
            }

            print(
                f">>> Timing: interval={actual_interval_sec:.3f}s, error={timing_error_sec:+.3f}s, drift={timing_error_sec:+.3f}s"
            )

            # Health check
            if self.current_frame % 100 == 0 and self.current_frame > 0:
                print(f">>> Health check at frame {self.current_frame}")
                if not self._system_health_check():
                    print(">>> ERROR: System health check failed")
                    self.error_occurred.emit("System health check failed")
                    return actual_capture_timestamp

            # CAPTURE DURING LED PULSE
            try:
                use_dual = bool(
                    self.phase_config.get("enabled")
                    and phase_info.get("phase") == "light"
                    and self.phase_config.get("dual_light_phase", False)
                )
                led_type = phase_info.get("led_type", "ir")

                if hasattr(self.esp32_controller, "get_capture_window_timing"):
                    timing_info = self.esp32_controller.get_capture_window_timing()
                    stab_ms = int(timing_info.get("led_stabilization_ms", 500))
                    exp_ms = int(timing_info.get("exposure_ms", self.esp32_controller.exposure_ms))
                else:
                    stab_ms = int(getattr(self.esp32_controller, "led_stabilization_ms", 500))
                    exp_ms = int(getattr(self.esp32_controller, "exposure_ms", 10))
                    timing_info = {
                        "led_stabilization_ms": stab_ms,
                        "exposure_ms": exp_ms,
                    }

                lat_ms = int(
                    getattr(
                        self,
                        "camera_trigger_latency_ms",
                        self.phase_config.get("camera_trigger_latency_ms", 20),
                    )
                )
                desired_ms_from_pulse = max(0, int(round(stab_ms + (exp_ms / 2.0) - lat_ms)))
                snap_delay_sec = desired_ms_from_pulse / 1000.0

                if hasattr(self.esp32_controller, "begin_sync_pulse"):
                    print(">>> Step 1: Starting LED pulse (non-blocking API)...")
                    pulse_start_time = self.esp32_controller.begin_sync_pulse(dual=use_dual)
                    if not isinstance(pulse_start_time, (int, float)):
                        pulse_start_time = time.time()

                    target = pulse_start_time + snap_delay_sec
                    while True:
                        now = time.time()
                        rem = target - now
                        if rem <= 0:
                            break
                        time.sleep(rem - 0.002 if rem > 0.004 else 0)

                    print(
                        f">>> CAPTURE NOW (LED ON) — stab={stab_ms}ms exp={exp_ms}ms latency={lat_ms}ms"
                    )
                    frame_capture_start = time.time()
                    frame, frame_metadata = self._memory_safe_capture_frame()
                    if frame is None:
                        raise RuntimeError("Frame capture returned None")
                    frame_capture_end = time.time()

                    actual_capture_timestamp = frame_capture_start

                print(">>> Waiting for ESP32 sync complete...")
                esp32_timing = self.esp32_controller.wait_sync_complete(timeout=5.0)

                # Read fresh sensor values
                print(">>> Reading fresh sensor values...")
                try:
                    actual_temp, actual_humidity = self.esp32_controller.read_sensors()

                    if -40 <= actual_temp <= 85:
                        esp32_timing["temperature"] = actual_temp
                        esp32_timing["temperature_celsius"] = actual_temp
                        print(f">>> Sensors: T={actual_temp:.1f}°C, H={actual_humidity:.1f}%")
                    else:
                        logger.warning(f"Temperature out of DHT22 range: {actual_temp}°C")
                        esp32_timing["temperature"] = np.nan
                        esp32_timing["temperature_celsius"] = np.nan

                    if 0 <= actual_humidity <= 100:
                        esp32_timing["humidity"] = actual_humidity
                        esp32_timing["humidity_percent"] = actual_humidity
                    else:
                        logger.warning(f"Humidity out of range: {actual_humidity}%")
                        esp32_timing["humidity"] = np.nan
                        esp32_timing["humidity_percent"] = np.nan

                except Exception as sensor_e:
                    logger.warning(f"Post-capture sensor read failed: {sensor_e}")
                    esp32_timing.setdefault("temperature", np.nan)
                    esp32_timing.setdefault("temperature_celsius", np.nan)
                    esp32_timing.setdefault("humidity", np.nan)
                    esp32_timing.setdefault("humidity_percent", np.nan)

                esp32_timing.update(
                    {
                        "mode": "dual" if use_dual else "single",
                        "led_type_used": ("dual" if use_dual else led_type),
                        "exposure_ms": exp_ms,
                        "led_stabilization_ms": stab_ms,
                        "sync_timing_ms": esp32_timing.get("timing_ms", stab_ms + exp_ms),
                        "led_duration_ms": esp32_timing.get(
                            "led_duration_ms", esp32_timing.get("timing_ms", stab_ms + exp_ms)
                        ),
                    }
                )

                cap_ms = (frame_capture_end - frame_capture_start) * 1000.0
                logger.debug(f"Frame captured in {cap_ms:.1f} ms while LED was ON")

            except Exception as capture_e:
                logger.error(f"Capture failed: {capture_e}")
                print(f">>> CAPTURE EXCEPTION: {type(capture_e).__name__}: {capture_e}")
                if frame is not None:
                    del frame
                    frame = None
                raise

            # Build metadata
            try:
                print(">>> Building metadata...")
                capture_end_time = time.time()

                python_timing["operation_end_absolute"] = float(capture_end_time)
                python_timing["end_time"] = capture_end_time
                python_timing["operation_duration_sec"] = float(
                    capture_end_time - operation_start_time
                )

                if esp32_timing:
                    led_duration_sec = esp32_timing.get("led_duration_ms", 0) / 1000.0
                    python_timing["capture_overhead_sec"] = float(
                        python_timing["operation_duration_sec"] - led_duration_sec
                    )
                else:
                    python_timing["capture_overhead_sec"] = 0.0

                if esp32_timing is None:
                    esp32_timing = {
                        "esp32_time_start": pulse_start_time,
                        "esp32_time_end": capture_end_time,
                        "led_duration_ms": stab_ms + exp_ms,
                        "sync_timing_ms": stab_ms + exp_ms,
                        "exposure_ms": exp_ms,
                        "led_stabilization_ms": stab_ms,
                        "led_power_actual": getattr(self.esp32_controller, "led_power", -1),
                        "temperature": np.nan,
                        "temperature_celsius": np.nan,
                        "humidity": np.nan,
                        "humidity_percent": np.nan,
                        "led_type_used": ("dual" if use_dual else phase_info.get("led_type", "ir")),
                        "phase_aware_capture": self.phase_config.get("enabled", False),
                    }

                    try:
                        t, h = self.esp32_controller.read_sensors()
                        if -40 <= t <= 85:
                            esp32_timing["temperature"] = t
                            esp32_timing["temperature_celsius"] = t
                        if 0 <= h <= 100:
                            esp32_timing["humidity"] = h
                            esp32_timing["humidity_percent"] = h
                    except Exception:
                        pass

                if frame_metadata is None:
                    frame_metadata = {"timestamp": actual_capture_timestamp, "source": "unknown"}

                frame_metadata.update(
                    {
                        "timestamp": actual_capture_timestamp,
                        "current_phase": phase_info["phase"],
                        "led_type_used": ("dual" if use_dual else phase_info.get("led_type", "ir")),
                        "phase_elapsed_min": phase_info.get("phase_elapsed_min", 0.0),
                        "phase_remaining_min": phase_info.get("phase_remaining_min", 0.0),
                        "cycle_number": phase_info.get("cycle_number", 1),
                        "total_cycles": phase_info.get("total_cycles", 1),
                        "phase_transition": phase_info.get("phase_transition", False),
                        "phase_enabled": self.phase_config.get("enabled", False),
                        "captured_during_led_pulse": True,
                        "capture_delay_sec": snap_delay_sec,
                        "camera_trigger_latency_ms": lat_ms,
                        "temperature": (
                            esp32_timing.get("temperature", np.nan) if esp32_timing else np.nan
                        ),
                        "humidity": (
                            esp32_timing.get("humidity", np.nan) if esp32_timing else np.nan
                        ),
                    }
                )
                print(">>> Metadata built successfully")

            except Exception as metadata_e:
                logger.error(f"Metadata preparation failed: {metadata_e}")
                if frame is not None:
                    del frame
                raise

            # Save frame
            success = False
            try:
                print(f">>> Saving frame {self.current_frame} to HDF5...")
                logger.debug(f"Saving frame {self.current_frame}...")

                success = self.data_manager.save_frame(
                    frame, frame_metadata, esp32_timing, python_timing, memory_optimized=False
                )

                if success:
                    print(f">>> Frame {self.current_frame} SAVED SUCCESSFULLY to HDF5")
                else:
                    print(f">>> Frame {self.current_frame} SAVE FAILED")

            except Exception as save_e:
                logger.error(f"Frame save error: {save_e}")
                success = False

            # Progress and status
            if success:
                self.actual_frame_times.append(actual_capture_timestamp)
                self.last_frame_end_time = time.time()

                with self._state_lock:
                    self.current_frame += 1

                progress = int((self.current_frame / self.total_frames) * 100)
                self.progress_updated.emit(progress)
                self.frame_captured.emit(self.current_frame, self.total_frames)

                print(f">>> Progress: {self.current_frame}/{self.total_frames} ({progress}%)")

                elapsed_time = time.time() - self.start_time
                remaining_frames = self.total_frames - self.current_frame
                estimated_remaining = (
                    (elapsed_time / self.current_frame) * remaining_frames
                    if self.current_frame > 0
                    else 0.0
                )

                phase_text = (
                    f"Phase: {phase_info['phase'].upper()}"
                    if self.phase_config.get("enabled", False)
                    else "Continuous"
                )
                status_msg = f"Frame {self.current_frame}/{self.total_frames} - {phase_text} - Remaining: {estimated_remaining:.1f}s"
                self.status_updated.emit(status_msg)

                # Hourly checkpoint
                frames_per_hour = max(1, int(3600 // max(1, int(self.interval_sec))))
                if self.current_frame % frames_per_hour == 0:
                    hours_completed = self.current_frame // frames_per_hour
                    current_phase = (
                        phase_info["phase"].upper()
                        if self.phase_config.get("enabled", False)
                        else "CONTINUOUS"
                    )

                    if hasattr(self.data_manager, "hdf5_file") and self.data_manager.hdf5_file:
                        self.data_manager.hdf5_file.flush()

                    import gc

                    gc.collect()

                    memory_status = self._get_memory_status()
                    logger.info(
                        f"=== CHECKPOINT: {hours_completed}h - Phase: {current_phase} - Memory: {memory_status} ==="
                    )
            else:
                self.error_occurred.emit(f"Failed to save frame {self.current_frame + 1}")

            print(f">>> _capture_frame_sync_fixed() END: Frame {self.current_frame}")
            print(f"{'='*80}\n")

        except Exception as e:
            if "frame" in locals() and frame is not None:
                try:
                    del frame
                except Exception:
                    pass
            logger.error(f"Frame capture error: {e}")
            try:
                self.error_occurred.emit(f"Frame capture failed: {str(e)}")
            except Exception:
                pass
            raise

        finally:
            # ================================================================
            # AGGRESSIVE MEMORY CLEANUP
            # ================================================================
            print(">>> Cleaning up frame data...")

            if frame is not None:
                try:
                    frame.flags.writeable = False
                    del frame
                except Exception:
                    pass
                frame = None

            if frame_metadata is not None:
                try:
                    frame_metadata.clear()
                    del frame_metadata
                except Exception:
                    pass
                frame_metadata = None

            if esp32_timing is not None:
                try:
                    esp32_timing.clear()
                    del esp32_timing
                except Exception:
                    pass
                esp32_timing = None

            # Adaptive GC
            import gc

            try:
                import psutil

                mem = psutil.virtual_memory()
                available_gb = mem.available / (1024**3)

                if available_gb < 1.5:
                    collected = gc.collect()
                    if collected > 0:
                        print(f">>> CRITICAL GC (RAM: {available_gb:.1f}GB): {collected} objects")
                elif available_gb < 2.5:
                    if self.current_frame % 2 == 0:
                        collected = gc.collect()
                        if collected > 0:
                            print(f">>> Full GC (RAM: {available_gb:.1f}GB): {collected} objects")
                    else:
                        gc.collect(generation=0)
                else:
                    if self.current_frame % 10 == 0:
                        collected = gc.collect()
                        if collected > 0:
                            print(f">>> Full GC (RAM: {available_gb:.1f}GB): {collected} objects")
                    elif self.current_frame % 2 == 0:
                        gc.collect(generation=0)
            except Exception:
                if self.current_frame % 2 == 0:
                    gc.collect()

            # Napari cleanup
            if self.current_frame % 2 == 0 and self.viewer:
                try:
                    while len(self.viewer.layers) > 2:
                        layer = self.viewer.layers[0]
                        if hasattr(layer, "data"):
                            try:
                                del layer.data
                            except:
                                pass
                        self.viewer.layers.remove(layer)
                except Exception:
                    pass

        # ✅ Return NACH dem finally!
        return actual_capture_timestamp
        #     finally:
        #         # ✅ CRITICAL: Aggressive cleanup for long recordings
        #         print(">>> Cleaning up frame data...")

        #         # Delete frame data
        #         if frame is not None:
        #             try:
        #                 frame.flags.writeable = False
        #                 del frame
        #             except Exception:
        #                 pass
        #             finally:
        #                 frame = None

        #         # Delete metadata dicts
        #         if frame_metadata is not None:
        #             try:
        #                 frame_metadata.clear()
        #                 del frame_metadata
        #             except Exception:
        #                 pass
        #             finally:
        #                 frame_metadata = None

        #         if esp32_timing is not None:
        #             try:
        #                 esp32_timing.clear()
        #                 del esp32_timing
        #             except Exception:
        #                 pass
        #             finally:
        #                 esp32_timing = None

        #         # ✅ Force GC every frame
        #         import gc
        #         if self.current_frame % 1 == 0:  # Every frame
        #             collected = gc.collect(generation=0)  # Fast gen-0 collection
        #             if collected > 5:  # Only log if significant
        #                 print(f">>> GC collected {collected} objects")

        #         # ✅ Full GC every 100 frames
        #         if self.current_frame % 100 == 0:
        #             collected = gc.collect()  # Full collection
        #             print(f">>> Full GC collected {collected} objects")

        #     # Progress + status
        #     if success:
        #         self.actual_frame_times.append(actual_capture_timestamp)
        #         self.last_frame_end_time = time.time()

        #         with self._state_lock:
        #             self.current_frame += 1

        #         progress = int((self.current_frame / self.total_frames) * 100)
        #         self.progress_updated.emit(progress)
        #         self.frame_captured.emit(self.current_frame, self.total_frames)

        #         print(f">>> Progress: {self.current_frame}/{self.total_frames} ({progress}%)")

        #         elapsed_time = time.time() - self.start_time
        #         remaining_frames = self.total_frames - self.current_frame
        #         estimated_remaining = (elapsed_time / self.current_frame) * remaining_frames if self.current_frame > 0 else 0.0

        #         phase_text = f"Phase: {phase_info['phase'].upper()}" if self.phase_config.get('enabled', False) else "Continuous"
        #         status_msg = f"Frame {self.current_frame}/{self.total_frames} - {phase_text} - Remaining: {estimated_remaining:.1f}s"
        #         self.status_updated.emit(status_msg)

        #         # Hourly checkpoint
        #         frames_per_hour = max(1, int(3600 // max(1, int(self.interval_sec))))
        #         if self.current_frame % frames_per_hour == 0:
        #             hours_completed = self.current_frame // frames_per_hour
        #             current_phase = phase_info['phase'].upper() if self.phase_config.get('enabled', False) else "CONTINUOUS"

        #             # Force HDF5 flush
        #             if hasattr(self.data_manager, 'hdf5_file') and self.data_manager.hdf5_file:
        #                 self.data_manager.hdf5_file.flush()
        #                 print(f">>> CHECKPOINT: HDF5 flushed to disk")

        #             import gc
        #             gc.collect()
        #             print(f">>> CHECKPOINT: Full GC completed")

        #             memory_status = self._get_memory_status()
        #             logger.info(f"=== CHECKPOINT: {hours_completed}h - Phase: {current_phase} - Memory: {memory_status} ===")
        #             print(f"=== CHECKPOINT: {hours_completed}h - Phase: {current_phase} - Memory: {memory_status} ===")
        #     else:
        #         print(f">>> FRAME {self.current_frame + 1} NOT SAVED - emitting error")
        #         self.error_occurred.emit(f"Failed to save frame {self.current_frame + 1}")

        #     print(f">>> _capture_frame_sync_fixed() END: Frame {self.current_frame}")
        #     print(f"{'='*80}\n")

        #     # ✅ CRITICAL: Return the actual capture timestamp
        #     return actual_capture_timestamp

        # except Exception as e:
        #     # Propagate fatal errors
        #     if 'frame' in locals() and frame is not None:
        #         try:
        #             del frame
        #         except Exception:
        #             pass
        #     logger.error(f"Frame capture error: {e}")
        #     print(f"\n!!! CRITICAL ERROR in _capture_frame_sync_fixed(): {type(e).__name__}: {e}")
        #     import traceback
        #     traceback.print_exc()
        #     try:
        #         self.error_occurred.emit(f"Frame capture failed: {str(e)}")
        #     except Exception:
        #         pass
        #     raise

    # ========================================================================
    # MEMORY OPTIMIZATION METHODS
    # ========================================================================

    def _memory_safe_capture_frame(self) -> Tuple[np.ndarray, dict]:
        """Memory-safe frame capture with immediate optimization."""
        try:
            import gc

            gc.collect()

            frame, metadata = self._safe_capture_frame()

            if frame is None:
                raise RuntimeError("Frame capture returned None")

            frame = self._optimize_frame_memory(frame)

            return frame, metadata

        except Exception as e:
            if "frame" in locals() and frame is not None:
                del frame
            raise RuntimeError(f"Memory-safe capture failed: {e}")

    def _optimize_frame_memory(self, frame: np.ndarray) -> np.ndarray:
        """Optimize frame memory usage without losing scientific data."""
        if frame is None:
            return None

        original_size = frame.nbytes

        # Ensure contiguous array
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
            logger.debug(f"Frame made contiguous: {original_size//1024}KB")

        # Convert to optimal dtype
        if frame.dtype == np.float64:
            frame = frame.astype(np.float32)
            logger.debug(
                f"Frame optimized: float64->float32, {original_size//1024}KB->{frame.nbytes//1024}KB"
            )
        elif frame.dtype == np.int64:
            max_val = np.max(frame)
            if max_val <= 65535:
                frame = frame.astype(np.uint16)
                logger.debug(
                    f"Frame optimized: int64->uint16, {original_size//1024}KB->{frame.nbytes//1024}KB"
                )

        return frame

    def _cleanup_memory_intensive_layers(self):
        """
        Remove temporary/large layers from napari to prevent memory accumulation.
        Critical for long (72h) recordings!
        """
        if self.viewer is None:
            return

        try:
            layers_to_remove = []

            # Pattern 1: Temporary capture layers
            temp_patterns = [
                "timelapse live",
                "timelapse_live",
                "captured frames",
                "temp",
                "test",
                "quick test",
                "warmup",
            ]

            for layer in self.viewer.layers:
                layer_name = getattr(layer, "name", "").lower()

                # Remove temp layers
                if any(pattern in layer_name for pattern in temp_patterns):
                    layers_to_remove.append(layer)
                    continue

                # ✅ NEW: Remove old image layers (keep only last 2)
                if layer_name.startswith("frame_"):
                    layers_to_remove.append(layer)

            # Remove identified layers
            if layers_to_remove:
                for layer in layers_to_remove:
                    try:
                        self.viewer.layers.remove(layer)
                        # ✅ NEW: Explicitly delete layer data
                        if hasattr(layer, "data"):
                            try:
                                del layer.data
                            except Exception:
                                pass
                    except Exception as e:
                        pass  # Layer might already be removed

                if len(layers_to_remove) > 0:
                    print(f">>> Removed {len(layers_to_remove)} memory-intensive layers")

                    # ✅ NEW: Force immediate GC after layer removal
                    import gc

                    gc.collect()

            # ✅ NEW: Limit total layer count
            max_layers = 3
            if len(self.viewer.layers) > max_layers:
                excess = len(self.viewer.layers) - max_layers
                print(
                    f">>> Viewer has {len(self.viewer.layers)} layers, removing {excess} oldest..."
                )
                for _ in range(excess):
                    try:
                        layer = self.viewer.layers[0]  # Remove oldest
                        if hasattr(layer, "data"):
                            del layer.data
                        self.viewer.layers.remove(layer)
                    except Exception:
                        break

        except Exception as e:
            # Don't fail recording for cleanup errors
            pass

    def _memory_safety_check(self) -> bool:
        """
        Check system memory and abort if too low.
        For 72h recordings, we need stricter limits!
        """
        try:
            import psutil

            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            percent_available = memory.percent

            # ✅ OLD: 1.0GB threshold (too low!)
            # ✅ NEW: 2.0GB threshold for safety margin
            min_available_gb = 1.0
            max_usage_percent = 85.0  # Don't exceed 85% RAM usage

            if available_gb < min_available_gb:
                logger.error(
                    f"Low system memory: {available_gb:.1f}GB available "
                    f"(threshold: {min_available_gb}GB)"
                )
                return False

            if percent_available > max_usage_percent:
                logger.error(
                    f"High memory usage: {percent_available:.1f}% "
                    f"(threshold: {max_usage_percent}%)"
                )
                return False

            # Log memory status occasionally
            if self.current_frame % 100 == 0:
                logger.info(
                    f"Memory OK: {available_gb:.1f}GB available "
                    f"({100 - percent_available:.1f}% free)"
                )

            return True

        except Exception as e:
            logger.warning(f"Memory check failed: {e}")
            return True  # Don't abort on check failure

    def _get_memory_status(self) -> str:
        """Get current memory status string for logging."""
        try:
            import psutil

            memory = psutil.virtual_memory()
            process = psutil.Process()
            process_mb = process.memory_info().rss / (1024 * 1024)
            available_gb = memory.available / (1024**3)
            return f"{process_mb:.1f}MB process, {available_gb:.1f}GB available"
        except:
            return "monitoring unavailable"

    # ========================================================================
    # VALIDATION / INITIALIZATION / RECORDING LOOP
    # ========================================================================

    def _validate_setup(self) -> bool:
        """Validate setup before starting recording."""
        if self.imswitch_main is None and self.viewer is None:
            self.error_occurred.emit(
                "No ImSwitch controller and no Napari viewer for frame capture"
            )
            return False

        # Probe capture path
        try:
            frame, metadata = self._safe_capture_frame()
            if frame is None:
                self.error_occurred.emit("Frame capture test returned None")
                return False
            logger.info(
                f"Validation: Frame capture successful - {frame.shape} from {metadata.get('source')}"
            )

        except Exception as e:
            self.error_occurred.emit(f"Frame capture test failed: {str(e)}")
            return False

        # ESP32 connection
        if not self.esp32_controller.is_connected():
            try:
                self.esp32_controller.connect()
                logger.info("ESP32 connected during validation")
            except Exception as e:
                self.error_occurred.emit(f"ESP32 connection failed: {str(e)}")
                return False

        # Validate phase configuration and LED setup
        if self.phase_config["enabled"]:
            try:
                original_led = self.esp32_controller.current_led_type

                self.esp32_controller.select_led_type("ir")
                time.sleep(0.1)

                self.esp32_controller.select_led_type("white")
                time.sleep(0.1)

                self.esp32_controller.select_led_type(original_led)

                logger.info("Phase validation: LED switching test passed")
            except Exception as e:
                self.error_occurred.emit(f"LED switching test failed: {str(e)}")
                return False

        return True

    def _initialize_recording(self):
        """Initialize recording session with proper cleanup (idempotent)."""
        logger.info("Initializing recording...")

        # ensure flag exists on all code paths
        self._live_view_was_active = False

        # Safely close an existing HDF5 file if open
        try:
            if self.data_manager.is_file_open():
                logger.info("Closing existing HDF5 file...")
                self.data_manager.close_file()
                time.sleep(0.2)
        except Exception as e:
            logger.warning(f"Closing previous HDF5 failed (continuing): {e}")

        # State flags & counters
        with self._state_lock:
            self.recording = True
            self.paused = False
            self.should_stop = False
            self.current_frame = 0

        # Bookkeeping
        self._finalized = False
        self._finished_emitted = False
        self.start_time = time.time()
        self.cumulative_drift = 0.0
        self.actual_frame_times = []
        self.last_frame_end_time = None

        # Phase config (robust read)
        pc = getattr(self, "phase_config", {}) or {}
        phase_enabled = bool(pc.get("enabled", False))
        start_with_light = bool(pc.get("start_with_light", True))
        light_min = int(pc.get("light_duration_min", 0) or 0)
        dark_min = int(pc.get("dark_duration_min", 0) or 0)
        dual_light_phase = bool(pc.get("dual_light_phase", False))
        cam_latency_ms = int(
            pc.get("camera_trigger_latency_ms", getattr(self, "camera_trigger_latency_ms", 20))
        )

        # Ensure ESP32 connection if present
        try:
            if hasattr(self, "esp32_controller") and self.esp32_controller:
                if (
                    hasattr(self.esp32_controller, "is_connected")
                    and not self.esp32_controller.is_connected()
                ):
                    self.esp32_controller.connect()
                    logger.info("ESP32 connected during initialization")
        except Exception as e:
            logger.warning(f"ESP32 connect attempt failed (continuing): {e}")
        # ========================================================================
        # Test sensors before starting recording
        # ========================================================================
        print("\n>>> SENSOR TEST:")
        try:
            for i in range(3):
                t, h = self.esp32_controller.read_sensors()
                print(f"    Test {i+1}/3: T={t:.1f}°C, H={h:.1f}%")

                # Check if readings are reasonable
                if t < -40 or t > 85:
                    logger.warning(f"Temperature reading unusual: {t}°C")
                if h < 0 or h > 100:
                    logger.warning(f"Humidity reading unusual: {h}%")

                if i < 2:
                    time.sleep(0.5)

            logger.info("Sensor test completed")
            print(">>> Sensor test PASSED")

        except Exception as e:
            logger.warning(f"Sensor test failed: {e}")
            print(f">>> ⚠️ Sensor test FAILED: {e}")
            print(">>> Recording will continue, but sensor data may be unreliable")

        # Set initial LED (if phase cycling)
        if phase_enabled and hasattr(self, "esp32_controller") and self.esp32_controller:
            initial_led = "white" if start_with_light else "ir"
            try:
                self.esp32_controller.select_led_type(initial_led)
                logger.info(f"Initial LED set to: {initial_led.upper()}")
            except Exception as e:
                logger.error(f"Failed to set initial LED: {e}")

            self.current_phase = "light" if start_with_light else "dark"
            self.last_phase = None
            self.phase_start_time = self.start_time
            self.current_cycle = 1

        # Prepare expected capture times (absolute schedule)
        self.expected_frame_times = [
            self.start_time + (i * self.interval_sec) for i in range(self.total_frames)
        ]

        phase_info_txt = "with phase cycling" if phase_enabled else "continuous"
        logger.info(
            f"Recording initialized: {self.total_frames} frames over "
            f"{self.duration_min} minutes {phase_info_txt}"
        )

        # Create HDF5 + write run metadata
        try:
            filepath = self.data_manager.create_recording_file(
                self.output_dir,
                experiment_name="nematostella_timelapse",
                timestamped=True,
            )
            logger.info(f"HDF5 file created: {filepath}")

            led_power = None
            try:
                led_power = self.esp32_controller.led_power
            except Exception:
                pass

            recording_metadata = {
                "duration_minutes": self.duration_min,
                "interval_seconds": self.interval_sec,
                "expected_frames": self.total_frames,
                "led_power": led_power,
                "camera_name": getattr(self, "camera_name", "unknown"),
                "imswitch_managed": True,
                "esp32_settings": {},
                # full phase config snapshot
                "phase_config": {
                    "enabled": phase_enabled,
                    "light_duration_min": light_min,
                    "dark_duration_min": dark_min,
                    "start_with_light": start_with_light,
                    "dual_light_phase": dual_light_phase,
                    "camera_trigger_latency_ms": cam_latency_ms,
                },
                # flattened convenience keys
                "phase_enabled": phase_enabled,
                "light_duration_min": light_min,
                "dark_duration_min": dark_min,
                "starts_with_light": start_with_light,
                "dual_light_phase": dual_light_phase,
                "camera_trigger_latency_ms": cam_latency_ms,
                # run features
                "timing_corrected": True,
                "capture_during_led_pulse": True,
            }

            self.data_manager.update_recording_metadata(recording_metadata)
            logger.info("Metadata updated successfully")

            # ─────────────────────────────────────────────────────────────
            # Pause/stop live view so we control exactly when frames are captured
            # ─────────────────────────────────────────────────────────────
            if self.imswitch_main and hasattr(self.imswitch_main, "liveViewWidget"):
                try:
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "liveViewActive") and live_view.liveViewActive:
                        if hasattr(live_view, "stopLiveView"):
                            live_view.stopLiveView()
                            logger.info("Live view stopped - manual control enabled")
                            self._live_view_was_active = True
                        elif hasattr(live_view, "pauseStream"):
                            live_view.pauseStream()
                            logger.info("Live view paused")
                            self._live_view_was_active = True
                except Exception as e:
                    logger.warning(f"Could not stop live view: {e}")
                    self._live_view_was_active = False

        except Exception as e:
            logger.error(f"Failed to initialize data storage: {e}")
            import traceback

            traceback.print_exc()
            with self._state_lock:
                self.recording = False
            # Ensure file is really closed
            try:
                if self.data_manager.is_file_open():
                    self.data_manager.close_file()
            except Exception:
                pass
            raise RuntimeError(f"Failed to initialize data storage: {str(e)}")

    # --------------latest-----
    def _recording_loop(self):
        """
        Main recording loop with precise timing.
        Captures frames at EXACT intervals by compensating for capture overhead.
        """
        print("\n" + "=" * 80)
        print(">>> RECORDING LOOP STARTED")
        print(f">>> Target: {self.total_frames} frames at {self.interval_sec}s intervals")
        print(f">>> Duration: {self.duration_min} minutes")
        print("=" * 80 + "\n")
        # ════════════════════════════════════════════════════════════════════
        # ✅ WARMUP: Capture one dummy frame to initialize camera/LED
        # ════════════════════════════════════════════════════════════════════
        try:
            print(">>> WARMUP: Capturing dummy frame to initialize system...")

            # Do a complete capture cycle (but don't save it)
            self.esp32_controller.begin_sync_pulse(dual=False)
            time.sleep(self.esp32_controller.led_stabilization_ms / 1000.0)

            # Try to capture (don't care if it fails)
            try:
                dummy_frame, _ = self._capture_frame_simple()
                print(f">>> WARMUP: Dummy frame captured: {dummy_frame.shape}")
            except Exception as e:
                print(f">>> WARMUP: Dummy capture failed (OK): {e}")

            # Wait for LED off
            self.esp32_controller.wait_sync_complete(timeout=10.0)

            # Extra delay before starting real recording
            time.sleep(0.5)

            print(">>> WARMUP: Complete - starting real recording\n")

        except Exception as warmup_e:
            print(f">>> WARMUP: Failed (continuing anyway): {warmup_e}")
        try:
            while not self.should_stop:
                with self._state_lock:
                    if self.current_frame >= self.total_frames:
                        print(f"\n>>> All {self.total_frames} frames captured")
                        break

                    frame_index = self.current_frame

                # ================================================================
                # ✅ PRECISE TIMING: Calculate EXACT time for this frame
                # ================================================================
                target_time = self.start_time + (frame_index * self.interval_sec)
                current_time = time.time()
                wait_time = target_time - current_time

                # Debug timing every 5 frames
                if frame_index % 5 == 0 or wait_time < 0:
                    elapsed = current_time - self.start_time
                    print(f"\n>>> Frame {frame_index} timing:")
                    print(f"    Elapsed: {elapsed:.3f}s")
                    print(f"    Target: {frame_index * self.interval_sec:.3f}s")
                    print(f"    Drift: {(elapsed - frame_index * self.interval_sec):+.3f}s")
                    print(f"    Wait: {wait_time:.3f}s")

                # ================================================================
                # WAIT until exact target time (compensates for previous overhead)
                # ================================================================
                if wait_time > 0:
                    # If we need to wait, sleep precisely
                    if wait_time > 0.5:
                        # Long wait: sleep most of it
                        time.sleep(wait_time - 0.1)

                        # Busy-wait for last 100ms for precision
                        while time.time() < target_time - 0.001:
                            time.sleep(0.001)
                    else:
                        # Short wait: busy-wait for precision
                        while time.time() < target_time:
                            time.sleep(0.001)
                elif wait_time < -0.5:
                    # We're late! Log warning
                    logger.warning(f"Frame {frame_index} is {-wait_time:.3f}s late")
                    print(f">>> ⚠️ WARNING: Frame {frame_index} is {-wait_time:.3f}s late!")

                # ================================================================
                # CAPTURE FRAME (at precise target time)
                # ================================================================
                capture_start = time.time()
                actual_drift = capture_start - target_time

                if abs(actual_drift) > 0.01:  # More than 10ms drift
                    print(f">>> Capture drift: {actual_drift*1000:+.1f}ms")

                try:
                    actual_capture_timestamp = self._capture_frame_sync_fixed()

                    capture_end = time.time()
                    capture_duration = capture_end - capture_start

                    # Log capture time occasionally
                    if frame_index % 10 == 0:
                        print(f">>> Frame {frame_index} captured in {capture_duration:.3f}s")

                except Exception as e:
                    logger.error(f"Frame {frame_index} capture failed: {e}")
                    print(f">>> ERROR: Frame {frame_index} failed: {e}")

                    # Decide: stop or continue?
                    if frame_index < 5:
                        # Early frames: stop on error
                        print(">>> Early frame failed - stopping recording")
                        with self._state_lock:
                            self.should_stop = True
                        break
                    else:
                        # Later frames: try to continue
                        print(">>> Continuing to next frame...")
                        with self._state_lock:
                            self.current_frame += 1
                        continue

            # ================================================================
            # RECORDING COMPLETE
            # ================================================================
            final_time = time.time()
            total_duration = final_time - self.start_time

            print("\n" + "=" * 80)
            print(">>> RECORDING LOOP FINISHED")
            print(f">>> Total frames captured: {self.current_frame}")
            print(f">>> Total duration: {total_duration:.1f}s ({total_duration/60:.2f} min)")
            print(f">>> Target duration: {self.duration_min*60}s ({self.duration_min} min)")
            print(f">>> Overhead: {total_duration - self.duration_min*60:.1f}s")
            print("=" * 80 + "\n")

            logger.info(f"Recording complete: {self.current_frame} frames in {total_duration:.1f}s")

        except Exception as e:
            logger.exception("Recording loop error")
            print(f"\n>>> CRITICAL ERROR in recording loop: {e}")
            import traceback

            traceback.print_exc()

        finally:
            with self._state_lock:
                self.recording = False

            try:
                self.recording_finished.emit()
            except Exception:
                pass

            print(">>> Recording loop thread exiting\n")

    def _trigger_imswitch_snap(self) -> Tuple[np.ndarray, dict]:
        """Trigger fresh camera snap in ImSwitch."""
        if not self.imswitch_main:
            raise RuntimeError("ImSwitch not available")

        detectors_manager = self.imswitch_main.detectorsManager

        # Try different snap/trigger methods in ImSwitch
        snap_methods = [
            ("snap", True),  # snap(camera_name)
            ("snapImage", True),  # snapImage(camera_name)
            ("getLatestFrame", True),  # getLatestFrame(camera_name)
            ("execOnCurrent", False),  # execOnCurrent('snap')
        ]

        for method_name, use_camera_name in snap_methods:
            if not hasattr(detectors_manager, method_name):
                continue

            try:
                method = getattr(detectors_manager, method_name)

                # Trigger acquisition
                if method_name == "execOnCurrent":
                    frame = method("snap")
                elif use_camera_name:
                    frame = method(self.camera_name)
                else:
                    frame = method()

                # Small delay to ensure frame is captured
                time.sleep(0.02)  # 20ms should be enough for most cameras

                # Now read the fresh frame
                if hasattr(self.imswitch_main, "liveViewWidget"):
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "img") and live_view.img is not None:
                        frame = live_view.img.copy()

                        if frame is not None and frame.size > 0:
                            metadata = {
                                "timestamp": time.time(),
                                "camera_name": self.camera_name,
                                "frame_shape": frame.shape,
                                "frame_dtype": str(frame.dtype),
                                "source": f"triggered_snap_{method_name}",
                                "triggered": True,
                                "fresh_acquisition": True,
                            }
                            logger.debug(f"Triggered fresh frame via {method_name}")
                            return frame, metadata

            except Exception as e:
                logger.debug(f"Snap method {method_name} failed: {e}")
                continue

        raise RuntimeError("Could not trigger ImSwitch snap")

    def _safe_capture_frame(self) -> Tuple[np.ndarray, dict]:
        """
        CRITICAL: Trigger fresh camera acquisition - don't read stale buffer!
        This ensures we capture during LED pulse, not before/after.
        """

        # Method 1: Try ImSwitch snap/trigger methods (FRESH acquisition)
        if self.imswitch_main is not None:
            try:
                frame, metadata = self._trigger_imswitch_snap()
                if frame is not None:
                    return frame, metadata
            except Exception as e:
                logger.debug(f"ImSwitch snap failed: {e}")

        # Method 2: Force Napari to refresh from camera
        if self.viewer is not None:
            try:
                frame, metadata = self._force_napari_refresh()
                if frame is not None:
                    return frame, metadata
            except Exception as e:
                logger.debug(f"Napari refresh failed: {e}")

        # Method 3: Last resort - read buffer (will be stale!)
        logger.warning("Using stale buffer - LED sync may not work!")
        return self._capture_frame_from_imswitch_direct()

    def _force_napari_refresh(self) -> Tuple[np.ndarray, dict]:
        """Force Napari to get fresh frame from camera."""
        if not self.viewer:
            raise RuntimeError("No Napari viewer")

        # Force viewer to update all layers
        try:
            self.viewer.layers.events.changed()
            time.sleep(0.05)  # Give it time to refresh
        except Exception:
            pass

        # Now try to get the (hopefully) fresh frame
        from napari.layers import Image

        for layer in self.viewer.layers:
            if not isinstance(layer, Image):
                continue

            try:
                # Force layer data update
                layer.refresh()
            except Exception:
                pass

            data = getattr(layer, "data", None)
            if data is None or data.size == 0:
                continue

            frame = np.array(data, copy=True)
            metadata = {
                "timestamp": time.time(),
                "camera_name": self.camera_name,
                "frame_shape": frame.shape,
                "frame_dtype": str(frame.dtype),
                "source": f"napari_refreshed:{layer.name}",
                "triggered": True,
            }
            return frame, metadata

        raise RuntimeError("No suitable Napari layer found")

    def _system_health_check(self) -> bool:
        """System health check for long-term stability."""
        try:
            import psutil

            memory = psutil.virtual_memory()
            if memory.percent > 85:
                logger.warning(f"High system memory usage: {memory.percent:.1f}%")
                return False

            process = psutil.Process()
            process_memory_mb = process.memory_info().rss / 1024 / 1024
            if process_memory_mb > 3000:
                logger.warning(f"High process memory usage: {process_memory_mb:.1f}MB")
                return False

            disk = psutil.disk_usage(".")
            free_gb = disk.free / (1024**3)
            if free_gb < 5:
                logger.warning(f"Low disk space: {free_gb:.1f}GB")
                return False

            if not self.esp32_controller.is_connected(force_check=True):
                logger.warning("ESP32 connection lost")
                try:
                    self.esp32_controller.connect()
                    logger.info("ESP32 reconnected")

                    # Phase recovery
                    if self.phase_config["enabled"] and hasattr(self, "current_phase"):
                        led_type = "white" if self.current_phase == "light" else "ir"
                        self.esp32_controller.select_led_type(led_type)
                        logger.info(f"LED state restored to {led_type.upper()}")
                except Exception as e:
                    logger.error(f"ESP32 reconnection failed: {e}")
                    return False

            if self.current_frame % 500 == 0:
                current_phase = getattr(self, "current_phase", "continuous").upper()
                logger.info(
                    f"Health OK: Memory={memory.percent:.1f}%, "
                    f"Process={process_memory_mb:.1f}MB, Disk={free_gb:.1f}GB, "
                    f"ESP32=Connected, Phase={current_phase}"
                )

            return True

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_recording_status(self) -> dict:
        """Get recording status with timing info."""
        with self._state_lock:
            current_frame = self.current_frame
            total_frames = self.total_frames
            recording = self.recording
            paused = self.paused
            cumulative_drift = self.cumulative_drift

        phase_status = {}
        if self.phase_config["enabled"] and recording and self.start_time:
            elapsed_min = (time.time() - self.start_time) / 60.0
            phase_info = self._get_current_phase_info(elapsed_min)
            phase_status = {
                "current_phase": phase_info.get("phase", "unknown"),
                "led_type": phase_info.get("led_type", "ir"),
                "cycle_number": phase_info.get("cycle_number", 1),
                "total_cycles": phase_info.get("total_cycles", 1),
                "phase_remaining_min": phase_info.get("phase_remaining_min", 0),
            }

        # Timing accuracy
        timing_accuracy = "unknown"
        if len(self.actual_frame_times) > 1:
            actual_intervals = np.diff(self.actual_frame_times)
            mean_error = np.mean(np.abs(actual_intervals - self.interval_sec))
            timing_accuracy = f"{mean_error:.3f}s deviation"

        status = {
            "recording": recording,
            "paused": paused,
            "current_frame": current_frame,
            "total_frames": total_frames,
            "progress_percent": (current_frame / total_frames * 100) if total_frames > 0 else 0,
            "elapsed_time": time.time() - self.start_time if self.start_time else 0,
            "cumulative_drift": cumulative_drift,
            "expected_duration": self.duration_min * 60,
            "interval_seconds": self.interval_sec,
            "phase_enabled": self.phase_config["enabled"],
            "timing_accuracy": timing_accuracy,
            "timing_corrected": True,
            **phase_status,
        }

        return status

    def is_recording(self) -> bool:
        """Check if recording."""
        with self._state_lock:
            return self.recording

    def is_paused(self) -> bool:
        """Check if paused."""
        with self._state_lock:
            return self.paused
