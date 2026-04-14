"""
Recording Manager - Haupt-Koordinator für Recording

Verantwortlich für:
- Recording-Loop (Main Thread)
- Koordination aller Components
- Event-Emission (Qt Signals)
- Error-Handling & Recovery
"""

import logging
import os
import sys
import threading
import time
from typing import Optional

from ..Datamanager import DataManager
from .frame_capture import FrameCaptureService
from .phase_manager import PhaseManager
from .recording_state import ExperimentSchedule, RecordingConfig, RecordingState
from .schedule_manager import ScheduleManager

# Qt Signals (optional)
try:
    from qtpy.QtCore import QObject
    from qtpy.QtCore import Signal as pyqtSignal
except ImportError:

    class QObject:  # type: ignore[no-redef]
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

    def pyqtSignal(*_a, **_k):  # type: ignore[no-redef]
        return _SignalShim()


logger = logging.getLogger(__name__)


class RecordingManager(QObject):
    """
    Haupt-Manager für Recording.

    Koordiniert:
    - RecordingState (Status & Progress)
    - PhaseManager (Day/Night Cycles)
    - FrameCaptureService (Hardware Coordination)
    - DataManager (File I/O)

    Keine direkte Hardware-Abhängigkeit - nutzt Adapter!
    """

    # Qt Signals
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    recording_paused = pyqtSignal()
    recording_resumed = pyqtSignal()

    frame_captured = pyqtSignal(int, int)  # current_frame, total_frames
    progress_updated = pyqtSignal(float)  # progress_percent
    phase_changed = pyqtSignal(str, int)  # phase_name, cycle_number
    segment_changed = pyqtSignal(int, str)  # segment_index, segment_label

    error_occurred = pyqtSignal(str)  # error_message

    def __init__(self, frame_capture_service: FrameCaptureService):
        """
        Args:
            frame_capture_service: FrameCaptureService instance
        """
        super().__init__()

        # Components
        self.frame_capture = frame_capture_service
        self.state = RecordingState()
        self.phase_manager: Optional[PhaseManager] = None
        self.schedule_manager: Optional[ScheduleManager] = None  # optional multi-segment
        self.data_manager: Optional[DataManager] = None  # also assigned DataManagerZarr at runtime

        # Recording thread
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_requested = False

        # Cumulative signed drift and last actual frame interval (read by get_status())
        self._cumulative_drift_sec: float = 0.0
        self._last_capture_time: float = float("nan")
        self._last_actual_interval_sec: float = float("nan")

        logger.info("RecordingManager initialized")

    # ========================================================================
    # RECORDING CONTROL
    # ========================================================================

    def start_recording(
        self,
        config: RecordingConfig,
        schedule: Optional[ExperimentSchedule] = None,
    ) -> bool:
        """
        Startet Recording.

        Args:
            config:   Recording-Konfiguration (always required)
            schedule: Optional ExperimentSchedule for multi-segment recordings.
                      When provided, config should be schedule.to_recording_config().

        Returns:
            True wenn erfolgreich gestartet
        """
        if self.state.is_active():
            logger.error("Recording already active")
            return False

        logger.info("Starting recording...")

        try:
            # Setup components
            self.state.set_config(config)

            # Setup Schedule Manager (multi-segment) OR classic Phase Manager
            if schedule is not None:
                self.schedule_manager = ScheduleManager(
                    schedule,
                    on_segment_changed=self._on_segment_changed,
                )
                self.phase_manager = None
                logger.info(f"Using ScheduleManager: {len(schedule.segments)} segment(s)")
            else:
                self.schedule_manager = None
                # Setup Phase Manager
                if config.phase_enabled:
                    self.phase_manager = PhaseManager(config)
                else:
                    self.phase_manager = None

            # Setup Data Manager
            from ..Datamanager import TelemetryMode

            if getattr(config, "output_format", "hdf5") == "zarr":
                from ..Datamanager.data_manager_zarr import DataManagerZarr
                from ..Datamanager.data_manager_zarr import TelemetryMode as ZarrTelemetryMode

                self.data_manager = DataManagerZarr(  # type: ignore[assignment]
                    telemetry_mode=ZarrTelemetryMode.STANDARD,
                    img_chunk_frames=50,
                    ts_chunk_size=512,
                    save_as_uint8=getattr(config, "save_as_uint8", False),
                )
                logger.info("Using Zarr data manager")
            else:
                self.data_manager = DataManager(
                    telemetry_mode=TelemetryMode.STANDARD,
                    chunk_size=512,
                    save_as_uint8=getattr(config, "save_as_uint8", False),
                )
                logger.info("Using HDF5 data manager")

            # Create recording file
            recording_file = self.data_manager.create_recording_file(  # type: ignore[union-attr]
                output_dir=config.output_dir,
                experiment_name=config.experiment_name,
                timestamped=True,
            )

            if not recording_file:
                raise RuntimeError("Failed to create recording file")

            # Set recording configuration
            self.data_manager.set_recording_config(  # type: ignore[union-attr]
                {
                    "duration_minutes": config.duration_min,
                    "interval_seconds": config.interval_sec,
                    "phase_enabled": config.phase_enabled,
                    "expected_frames": self.state.total_frames,
                    # Phase config
                    "light_duration_min": config.light_duration_min,
                    "dark_duration_min": config.dark_duration_min,
                    "start_with_light": config.start_with_light,
                    "dual_light_phase": config.dual_light_phase,
                    # LED power config
                    "ir_led_power": config.ir_led_power,
                    "white_led_power": config.white_led_power,
                    "dark_phase_ir_power": config.dark_phase_ir_power,
                    "light_phase_ir_power": config.light_phase_ir_power,
                    "light_phase_white_power": config.light_phase_white_power,
                }
            )

            # Setup Frame Capture timing
            # Get actual camera exposure time from ImSwitch
            try:
                camera_exposure_ms = self.frame_capture.camera.get_exposure_ms()
                logger.info(f"Using camera exposure time: {camera_exposure_ms:.1f} ms")
            except Exception as e:
                logger.warning(f"Could not get camera exposure, using default: {e}")
                camera_exposure_ms = 10.0

            if config.phase_enabled:
                # Use stabilization from phase config
                stab_ms = 1000  # Default LED stabilization time
                # For phase recording, use camera trigger latency (time to wait after LED on)
                # This should be: LED stabilization - camera exposure
                # But we'll use the configured latency value
                exp_ms = config.camera_trigger_latency_ms
            else:
                # No phase recording: use actual camera exposure time
                stab_ms = 1000  # LED stabilization before capture
                exp_ms = int(camera_exposure_ms)  # Use actual camera exposure

            self.frame_capture.set_timing(stab_ms, exp_ms)
            logger.info(
                f"Frame capture timing set: {stab_ms}ms stabilization + {exp_ms}ms trigger latency"
            )

            # ================================================================
            # CRITICAL: Reset LED state cache before recording
            # ================================================================
            # This ensures Frame 0 starts fresh with proper LED configuration
            self.frame_capture.reset_led_state()
            logger.info("LED state cache reset for new recording")

            # Reset phase tracking so the first frame always triggers a phase
            # transition — ensuring set_white_continuous() is called even if
            # this recording starts in the same phase the previous one ended in.
            self._last_phase = None

            # ================================================================
            # Initialize LED powers for dual mode (CRITICAL FIX)
            # ================================================================
            # If using dual LED mode, set BOTH LED powers before recording starts
            # Otherwise the white LED power will be 0% and won't turn on!
            print("\n" + "=" * 60)
            print("LED POWER INITIALIZATION")
            print(f"Phase enabled: {config.phase_enabled}")
            print(f"Dual light phase: {config.dual_light_phase}")
            print(f"Start with light: {config.start_with_light}")
            print("=" * 60 + "\n")

            logger.info("=" * 60)
            logger.info("LED POWER INITIALIZATION")
            logger.info(f"Phase enabled: {config.phase_enabled}")
            logger.info(f"Dual light phase: {config.dual_light_phase}")
            logger.info(f"Start with light: {config.start_with_light}")
            logger.info("=" * 60)

            if config.phase_enabled:
                # PHASE RECORDING: Use per-phase LED powers for intensity matching
                print("🔆 Initializing PER-PHASE LED powers")
                print(f"   Dark phase IR power: {config.dark_phase_ir_power}%")
                print(f"   Light phase IR power: {config.light_phase_ir_power}%")
                print(f"   Light phase White power: {config.light_phase_white_power}%\n")

                logger.info("🔆 Initializing PER-PHASE LED powers")
                logger.info(f"   Dark phase IR power: {config.dark_phase_ir_power}%")
                logger.info(f"   Light phase IR power: {config.light_phase_ir_power}%")
                logger.info(f"   Light phase White power: {config.light_phase_white_power}%")

                # NOTE: LED powers will be set dynamically per frame based on current phase
                # This is handled in _capture_single_frame() by calling _set_phase_led_powers()
                print("✅ Per-phase LED power configuration ready")
                print("   Powers will be set dynamically based on current phase\n")
                logger.info("✅ Per-phase LED power configuration ready")

            else:
                # CONTINUOUS RECORDING: Use legacy single LED powers
                logger.info("Setting LED powers for continuous mode:")
                logger.info(f"   IR LED power: {config.ir_led_power}%")
                logger.info(f"   White LED power: {config.white_led_power}%")

                # Set IR LED power
                success_ir = self.frame_capture.esp32.set_led_power(config.ir_led_power, "ir")
                time.sleep(0.1)  # Small delay between commands

                # Set White LED power
                success_white = self.frame_capture.esp32.set_led_power(
                    config.white_led_power, "white"
                )

                if success_ir and success_white:
                    logger.info("✅ Both LED powers configured for continuous mode")
                else:
                    logger.warning(
                        f"⚠️ LED power configuration incomplete (IR: {success_ir}, White: {success_white})"
                    )

            logger.info("=" * 60)

            # ================================================================
            # DISABLE AUTO-GAIN / AUTO-EXPOSURE before recording starts
            # ================================================================
            # Global pixel drift (seen as linear ramp in all ROIs) is caused by
            # camera AGC slowly adjusting gain across the recording.  Force both
            # GainAuto and ExposureAuto to Off so every frame uses the same
            # fixed gain/exposure settings.
            try:
                agc_result = self.frame_capture.camera.disable_auto_settings()
                if agc_result.get("gain_auto_off") or agc_result.get("exposure_auto_off"):
                    logger.info(
                        f"Camera auto settings disabled: GainAuto={agc_result['gain_auto_off']}, "
                        f"ExposureAuto={agc_result['exposure_auto_off']} | "
                        f"gain={agc_result['current_gain']}, exposure_ms={agc_result['current_exposure']}"
                    )
                else:
                    logger.warning(
                        "⚠️  Could not disable camera auto settings "
                        "(no-op on dummy/napari adapter or setParameter not available)"
                    )
            except Exception as e:
                logger.warning(f"disable_auto_settings call failed: {e}")

            # ================================================================
            # Initial sensor query before recording starts
            # ================================================================
            # Force the counter so query_sensors_if_needed() always fires here,
            # even if the previous recording ended mid-cycle.
            if self.frame_capture:
                self.frame_capture.reset_led_state()
                logger.info("Querying initial sensor values...")
                self.frame_capture.query_sensors_if_needed()
                logger.info("Initial sensor query complete")

            # ================================================================
            # Set process priority to HIGH for stable timing
            # ================================================================
            self._set_high_priority()

            # Reset cumulative drift and interval tracker for new recording
            self._cumulative_drift_sec = 0.0
            self._last_capture_time = float("nan")
            self._last_actual_interval_sec = float("nan")

            # Start recording state
            self.state.start_recording()

            # ================================================================
            # CRITICAL: Sync Data Manager start time with Recording State
            # ================================================================
            # The Data Manager's recording_start_time was set earlier during
            # create_recording_file(), but we need it to match the actual
            # recording start time for proper timestamp calculation
            self.data_manager.recording_start_time = self.state.start_time  # type: ignore[union-attr]
            logger.info(f"Data Manager start time synchronized: {self.state.start_time:.3f}")

            # Start phase/schedule recording
            if self.schedule_manager:
                self.schedule_manager.start_phase_recording()
            elif self.phase_manager:
                self.phase_manager.start_phase_recording()

            # Start recording thread
            self._stop_requested = False
            self._recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
            self._recording_thread.start()

            self.recording_started.emit()
            logger.info("Recording started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.error_occurred.emit(f"Failed to start: {e}")
            return False

    def stop_recording(self):
        """Stoppt Recording"""
        if not self.state.is_active():
            logger.warning("No active recording to stop")
            return

        logger.info("Stopping recording...")
        self._stop_requested = True
        self.state.stop_recording()

    def pause_recording(self):
        """Pausiert Recording"""
        if not self.state.is_recording():
            logger.warning("Cannot pause: not recording")
            return

        logger.info("Pausing recording...")
        self.state.pause_recording()
        self.recording_paused.emit()

    def resume_recording(self):
        """Setzt Recording fort"""
        if not self.state.is_paused():
            logger.warning("Cannot resume: not paused")
            return

        logger.info("Resuming recording...")
        self.state.resume_recording()
        self.recording_resumed.emit()

    # ========================================================================
    # RECORDING LOOP (Main Logic)
    # ========================================================================

    def _recording_loop(self):
        """
        Haupt-Recording-Loop.
        Läuft in separatem Thread.

        CRITICAL TIMING FIX:
        - Sleep for FULL duration (not in 0.1s chunks) to prevent timing drift
        - Check every 0.5s for pause/stop to remain responsive
        - This prevents overhead accumulation over long recordings
        """
        logger.info("Recording loop started")

        try:
            while not self._stop_requested and not self.state.is_complete():
                # Check if paused
                if self.state.is_paused():
                    time.sleep(0.1)
                    continue

                # ================================================================
                # OPTIMIZED TIMING v2.4: Deadline-based sleep with minimal jitter
                # ================================================================
                # Calculate absolute deadline for next frame (prevents jitter accumulation)
                next_frame_deadline = self.state.start_time + (
                    self.state.current_frame * self.state.get_config().interval_sec
                )

                # Wait until deadline, checking periodically for pause/stop
                # Use 0.5s chunks for responsiveness, but always respect absolute deadline
                while True:
                    current_time = time.time()
                    time_remaining = next_frame_deadline - current_time

                    # If deadline reached or passed, break immediately
                    if time_remaining <= 0.001:  # 1ms threshold for precision
                        break

                    # Check if stop/pause requested
                    if self._stop_requested or self.state.is_paused():
                        break

                    # Sleep in chunks for responsiveness, but never overshoot deadline
                    if time_remaining > 0.5:
                        # Long wait remaining: sleep 0.5s chunk
                        time.sleep(0.5)
                    elif time_remaining > 0.05:
                        # Medium wait: sleep 50ms chunk (more precise near deadline)
                        time.sleep(0.05)
                    else:
                        # Final precision sleep to exact deadline
                        time.sleep(time_remaining)
                        break  # Exit after precision sleep

                # Final check after sleep (might have been paused/stopped)
                if self._stop_requested or self.state.is_paused():
                    continue

                # Capture frame — pass deadline so per-frame drift can be recorded
                self._capture_single_frame(deadline=next_frame_deadline)

                # Query sensors BETWEEN frame captures (not during capture)
                # This prevents timing interference with frame capture
                if self.frame_capture:
                    self.frame_capture.query_sensors_if_needed()

                # Update progress
                progress = self.state.get_progress_percent()
                self.progress_updated.emit(progress)

            # Finalize
            self._finalize_recording()

        except Exception as e:
            logger.error(f"Recording loop error: {e}")
            self.error_occurred.emit(f"Recording error: {e}")
            self._finalize_recording()

    def _capture_single_frame(self, deadline: float = 0.0):
        """Captured ein einzelnes Frame"""
        try:
            # Check if this is the last frame BEFORE phase transition
            # This prevents phase transition at exactly t=duration (e.g., t=120s)
            # which would cause the last frame to be captured in the wrong phase
            is_last_frame = (self.state.current_frame + 1) >= self.state.total_frames

            # Get phase info (if enabled)
            phase_info = None
            led_type = "ir"
            dual_mode = False

            # Use ScheduleManager when a schedule is active, else classic PhaseManager
            active_manager = self.schedule_manager or self.phase_manager
            if active_manager and active_manager.is_enabled():
                # Get phase info, but prevent transition if this is the last frame
                phase_info = active_manager.get_current_phase_info(prevent_transition=is_last_frame)

                if phase_info:
                    led_type = phase_info.led_type
                    dual_mode = led_type == "dual"

                    # Update state with phase info
                    self.state.set_phase(phase_info)

                    # Emit phase change signal
                    self.phase_changed.emit(phase_info.phase.value, phase_info.cycle_number)

            # Set phase-specific LED powers (if phase recording enabled)
            phase_transition_occurred = False
            if phase_info:
                phase_transition_occurred = self._set_phase_led_powers(
                    phase_info, led_type, dual_mode
                )

            # ================================================================
            # CAMERA BUFFER FLUSH AFTER PHASE TRANSITION (DISABLED)
            # ================================================================
            # NOTE: Buffer flushing is currently DISABLED due to camera stability issues
            # Direct camera.capture_frame() calls can cause the camera to freeze or fail
            #
            # The LED stabilization time (1000ms) should be sufficient for the camera
            # to naturally flush old frames from its internal buffer.
            # If phase transition artifacts persist, consider:
            # - Increasing LED stabilization time instead
            # - Using a different buffer clearing strategy
            if phase_transition_occurred:
                logger.debug("⚡ Phase transition detected (buffer flush disabled for stability)")

            # ================================================================
            # FRAME CAPTURE WITH BRIGHTNESS VALIDATION (v2.4.1+)
            # ================================================================
            # Captures frame with automatic retry if frame is too dark (black frame bug)
            # This prevents occasional system delays from causing completely black frames
            # Uses adaptive threshold based on calibrated intensity (from RecordingConfig)

            frame_number = self.state.current_frame + 1
            max_capture_retries = 3
            config = self.state.config
            assert config is not None  # guaranteed: recording is active
            brightness_threshold = config.brightness_validation_threshold

            logger.debug(
                f"Capturing frame {frame_number}/{self.state.total_frames} (LED: {led_type}, dual_mode: {dual_mode})"
            )
            if phase_info:
                logger.debug(
                    f"Phase: {phase_info.phase.value}, Cycle: {phase_info.cycle_number}/{phase_info.total_cycles}"
                )

            frame = None
            metadata: dict = {}

            import numpy as np

            def _normalize_to_255(arr: np.ndarray) -> float:
                mean = float(np.mean(arr))
                if arr.dtype.kind == "u":
                    return mean * 255.0 / float(np.iinfo(arr.dtype).max)
                elif arr.dtype.kind == "f":
                    return mean * 255.0
                return mean

            def _frame_mean(f: np.ndarray) -> float:
                if config.use_full_frame_for_validation:
                    return _normalize_to_255(f)
                h, w = f.shape[:2]
                roi_frac = config.roi_fraction
                center_h, center_w = h // 2, w // 2
                roi_h, roi_w = int(h * roi_frac), int(w * roi_frac)
                roi_y1 = center_h - roi_h // 2
                roi_x1 = center_w - roi_w // 2
                return _normalize_to_255(f[roi_y1 : roi_y1 + roi_h, roi_x1 : roi_x1 + roi_w])

            # One full LED pulse to capture the frame (includes 1 s stabilization).
            # capture_with_retry handles camera-level failures (None returns).
            frame, metadata = self.frame_capture.capture_with_retry(
                led_type=led_type, dual_mode=dual_mode, max_retries=3
            )
            if metadata is None:
                metadata = {}

            if frame is None:
                logger.error("Frame capture failed")
                self.error_occurred.emit("Frame capture failed")
                return

            # Brightness check: if the frame is too dark (LED not yet stable,
            # timing race, or stale buffer) re-read from the camera without
            # re-firing the LED pulse.  Each re-read is cheap (~50 ms) so
            # 3 retries add at most ~150 ms — well inside the 5 s interval.
            frame_mean_val = _frame_mean(frame)
            for retry_attempt in range(max_capture_retries):
                if frame_mean_val >= brightness_threshold:
                    if retry_attempt > 0:
                        logger.info(
                            f"✅ Frame {frame_number} recovered (mean={frame_mean_val:.1f}) "
                            f"on re-read {retry_attempt}"
                        )
                    break

                logger.warning(
                    f"⚠️  Frame {frame_number} too dark (mean={frame_mean_val:.1f} < {brightness_threshold}), "
                    f"re-read {retry_attempt + 1}/{max_capture_retries}"
                )

                if retry_attempt < max_capture_retries - 1:
                    time.sleep(0.05)  # Wait for ImSwitch LV worker to push next frame
                    reread = self.frame_capture.camera.capture_frame()
                    if reread is not None:
                        frame = reread
                        frame_mean_val = _frame_mean(frame)
                else:
                    logger.error(
                        f"❌ Frame {frame_number} still dark (mean={frame_mean_val:.1f}) "
                        f"after {max_capture_retries} re-reads - saving anyway"
                    )
                    metadata["capture_method"] = "dark_frame_recovered"

            if frame is None:
                logger.error("Frame capture failed after all retries")
                self.error_occurred.emit("Frame capture failed")
                return

            # ================================================================
            # ENRICH METADATA with missing timeseries fields
            # ================================================================
            # Add phase info to metadata
            if phase_info:
                metadata["phase"] = phase_info.phase.value
                metadata["cycle_number"] = phase_info.cycle_number
                metadata["phase_enabled"] = True
            else:
                metadata["phase"] = "continuous"
                metadata["cycle_number"] = 0
                metadata["phase_enabled"] = False

            # Add LED power info (actual powers used for this frame)
            if config and phase_info and config.phase_enabled:
                # Phase recording: Use per-phase powers
                from .recording_state import PhaseType

                if phase_info.phase == PhaseType.DARK:
                    metadata["ir_led_power"] = config.dark_phase_ir_power
                    metadata["white_led_power"] = 0
                else:
                    # Light phase
                    if dual_mode:
                        metadata["ir_led_power"] = config.light_phase_ir_power
                        metadata["white_led_power"] = config.light_phase_white_power
                    else:
                        metadata["ir_led_power"] = 0
                        metadata["white_led_power"] = config.light_phase_white_power
            elif config:
                # Continuous recording: Use single powers
                if led_type == "ir" or dual_mode:
                    metadata["ir_led_power"] = config.ir_led_power
                    metadata["white_led_power"] = config.white_led_power if dual_mode else 0
                elif led_type == "white":
                    metadata["ir_led_power"] = 0
                    metadata["white_led_power"] = config.white_led_power
                else:
                    metadata["ir_led_power"] = -1
                    metadata["white_led_power"] = -1
            else:
                metadata["ir_led_power"] = -1
                metadata["white_led_power"] = -1

            # Add capture method
            if "error" in metadata:
                metadata["capture_method"] = "failed"
            elif metadata.get("success", False):
                metadata["capture_method"] = "normal"
            else:
                metadata["capture_method"] = "unknown"

            # Inject segment info when using a schedule
            if self.schedule_manager:
                metadata["segment_index"] = self.schedule_manager.current_segment_index
                metadata["segment_label"] = self.schedule_manager.current_segment_label

            # Add per-frame capture timing (elapsed since recording start + drift vs deadline)
            # Use capture_complete_time (after camera.capture_frame() returned) — this is the
            # actual moment the sensor was read, excluding LED stabilization overhead.
            # Fall back to capture_start only if capture_complete_time is absent.
            capture_time = metadata.get(
                "capture_complete_time", metadata.get("capture_start", time.time())
            )
            metadata["capture_elapsed_sec"] = capture_time - self.state.start_time
            metadata["frame_drift_sec"] = capture_time - deadline if deadline > 0 else float("nan")

            # Accumulate signed drift: positive when interval too long, negative when too short
            import math

            _cfg = self.state.get_config()
            interval_sec = _cfg.interval_sec if _cfg is not None else 0.0
            if not math.isnan(self._last_capture_time):
                actual_interval = capture_time - self._last_capture_time
                self._last_actual_interval_sec = actual_interval
                self._cumulative_drift_sec += actual_interval - interval_sec
            self._last_capture_time = capture_time

            # Save frame
            frame_number = self.state.current_frame + 1

            if self.data_manager:
                success = self.data_manager.save_frame(
                    frame=frame, frame_number=frame_number, metadata=metadata
                )

                if success:
                    # Increment frame counter
                    self.state.increment_frame()

                    # Emit signal
                    self.frame_captured.emit(self.state.current_frame, self.state.total_frames)

                    # Periodic progress logging (every 10 frames to reduce I/O overhead)
                    if frame_number % 10 == 0 or frame_number == 1:
                        logger.info(
                            f"Progress: Frame {frame_number}/{self.state.total_frames} saved"
                        )
                    else:
                        logger.debug(f"Frame {frame_number} saved successfully")
                else:
                    logger.error(f"Failed to save frame {frame_number}")

        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            self.error_occurred.emit(f"Capture error: {e}")

    def _set_high_priority(self):
        """Set process priority to HIGH for stable frame timing"""
        try:
            if sys.platform == "win32":
                import ctypes

                # Get current process handle
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                # HIGH_PRIORITY_CLASS = 0x00000080
                ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000080)
                logger.info("✅ Process priority set to HIGH for stable timing")
                print("✅ Process priority set to HIGH for stable timing")
            else:
                # Linux/macOS: use nice
                os.nice(-10)  # Higher priority (requires root on Linux)
                logger.info("✅ Process nice value set to -10")
        except Exception as e:
            logger.warning(f"⚠️ Could not set high priority: {e}")
            print(f"⚠️ Could not set high priority: {e}")

    def _restore_normal_priority(self):
        """Restore normal process priority after recording"""
        try:
            if sys.platform == "win32":
                import ctypes

                handle = ctypes.windll.kernel32.GetCurrentProcess()
                # NORMAL_PRIORITY_CLASS = 0x00000020
                ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000020)
                logger.info("Process priority restored to NORMAL")
        except Exception as e:
            logger.warning(f"Could not restore priority: {e}")

    def _finalize_recording(self):
        """Finalisiert Recording"""
        logger.info("Finalizing recording...")

        # Restore normal priority
        self._restore_normal_priority()

        try:
            # Turn off LED to save power
            if self.frame_capture:
                self.frame_capture.turn_off_led()

            # Get final state
            final_state = self.state.get_snapshot()

            # Add additional info
            final_info = {
                "experiment_name": (
                    self.state.config.experiment_name if self.state.config else "unknown"
                ),
                "total_frames_captured": self.state.current_frame,
                "total_frames_planned": self.state.total_frames,
                "elapsed_time": self.state.get_elapsed_time(),
                "status": final_state["status"],
                "config": self.state.config.__dict__ if self.state.config else {},
            }

            # Add phase / schedule summary
            if self.schedule_manager:
                final_info["schedule_summary"] = self.schedule_manager.get_phase_summary()
            elif self.phase_manager:
                final_info["phase_summary"] = self.phase_manager.get_phase_summary()

            # Add capture stats
            final_info["capture_stats"] = self.frame_capture.get_capture_stats()

            # Finalize data manager
            if self.data_manager:
                self.data_manager.finalize_recording(final_info)

            # Update state
            self.state.finish_recording()

            # Emit signal
            self.recording_stopped.emit()

            logger.info("Recording finalized successfully")

        except Exception as e:
            logger.error(f"Error finalizing recording: {e}")

    def _on_segment_changed(self, new_index: int):
        """
        Called by ScheduleManager when a segment transition occurs.
        Resets _last_phase so the first frame of the new segment triggers a
        full LED power update, then emits the segment_changed signal.
        """
        self._last_phase = None
        label = ""
        if self.schedule_manager:
            label = self.schedule_manager.current_segment_label
        logger.info(f"Segment changed → {new_index}: {label!r}")
        self.segment_changed.emit(new_index, label)

    def _set_phase_led_powers(self, phase_info, led_type: str, dual_mode: bool) -> bool:
        """
        Sets LED powers based on current phase for intensity matching.

        This method is called before each frame capture during phase recording
        to ensure correct LED powers for the current phase.

        Args:
            phase_info: Current phase information
            led_type: LED type for this frame ('ir', 'white', or 'dual')
            dual_mode: Whether dual LED mode is active

        Returns:
            True if phase transition occurred (LED configuration changed), False otherwise
        """
        config = self.state.get_config()
        if not config or not config.phase_enabled:
            return False

        from .recording_state import PhaseType

        # Track if this is a new phase (transition occurred)
        current_phase = phase_info.phase
        phase_transition = False

        if not hasattr(self, "_last_phase"):
            self._last_phase = None

        if self._last_phase is None or self._last_phase != current_phase:
            phase_transition = True
            logger.info(f"🔄 Phase transition: {self._last_phase} → {current_phase}")
            self._last_phase = current_phase

        # LED powers are only updated on phase transitions.
        # Calling set_led_power() every frame causes a PWM glitch on the ESP32
        # (analogWrite re-arms the timer, briefly outputting 0) which is visible
        # as a short LED flicker during the continuous light phase.
        if not phase_transition:
            return False

        # Detect whether the current segment is a continuous (non-LD) light segment.
        # Schedule-designer continuous segments (phase_enabled=False, led_type white/dual)
        # should behave like white_led_continuous — the LED stays on between frames.
        _continuous_light_segment = False
        if self.schedule_manager is not None and self.schedule_manager.is_enabled():
            _seg = self.schedule_manager._schedule.segments[self.schedule_manager._current_seg_idx]
            _continuous_light_segment = not _seg.phase_enabled and _seg.continuous_led_type in (
                "white",
                "dual",
            )

        use_continuous = config.white_led_continuous or _continuous_light_segment

        # Determine which LED powers to set based on current phase
        if phase_info.phase == PhaseType.DARK:
            ir_power = config.dark_phase_ir_power
            logger.info(f"[PHASE POWER] Dark phase transition: Setting IR={ir_power}%")
            self.frame_capture.esp32.set_led_power(ir_power, "ir")

            if use_continuous:
                self.frame_capture.set_white_continuous(False)

        else:
            ir_power = config.light_phase_ir_power
            white_power = config.light_phase_white_power

            if dual_mode:
                logger.info(
                    f"[PHASE POWER] Light phase transition (dual): IR={ir_power}%, White={white_power}%"
                )
                self.frame_capture.esp32.set_led_power(ir_power, "ir")
                time.sleep(0.01)
                self.frame_capture.esp32.set_led_power(white_power, "white")
            else:
                logger.info(f"[PHASE POWER] Light phase transition (white): White={white_power}%")
                self.frame_capture.esp32.set_led_power(white_power, "white")

            if use_continuous:
                self.frame_capture.set_white_continuous(True)
                logger.info(
                    f"[PHASE POWER] Continuous white/dual LED activated "
                    f"({'schedule segment' if _continuous_light_segment else 'phase config'})"
                )

        return phase_transition

    # ========================================================================
    # STATUS & INFO
    # ========================================================================

    def get_status(self) -> dict:
        """Gibt aktuellen Status zurück"""
        status = self.state.get_snapshot()

        # Add data manager stats
        if self.data_manager:
            status["data_stats"] = self.data_manager.get_stats()

        # Add capture stats
        status["capture_stats"] = self.frame_capture.get_capture_stats()

        # Cumulative interval overrun since recording start
        status["cumulative_drift_sec"] = self._cumulative_drift_sec
        status["last_actual_interval_sec"] = self._last_actual_interval_sec

        return status

    def get_recording_directory(self) -> Optional[str]:
        """Gibt Recording-Directory zurück"""
        if self.data_manager:
            rec_dir = self.data_manager.get_recording_directory()
            return str(rec_dir) if rec_dir else None
        return None

    def is_recording(self) -> bool:
        """Gibt zurück ob gerade recording läuft"""
        return self.state.is_recording()

    def is_paused(self) -> bool:
        """Gibt zurück ob paused"""
        return self.state.is_paused()

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def cleanup(self):
        """Cleanup (bei Shutdown)"""
        logger.info("RecordingManager cleanup...")

        # Stop recording if active
        if self.state.is_active():
            self.stop_recording()

            # Wait for thread to finish
            if self._recording_thread and self._recording_thread.is_alive():
                self._recording_thread.join(timeout=5.0)

        # Cleanup data manager
        if self.data_manager:
            self.data_manager.cleanup()

        logger.info("RecordingManager cleanup complete")
