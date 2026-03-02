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
from .recording_state import RecordingConfig, RecordingState

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
        self.data_manager: Optional[DataManager] = None

        # Recording thread
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_requested = False

        logger.info("RecordingManager initialized")

    # ========================================================================
    # RECORDING CONTROL
    # ========================================================================

    def start_recording(self, config: RecordingConfig) -> bool:
        """
        Startet Recording.

        Args:
            config: Recording-Konfiguration

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

            # Setup Phase Manager
            if config.phase_enabled:
                self.phase_manager = PhaseManager(config)
            else:
                self.phase_manager = None

            # Setup Data Manager
            from ..Datamanager import TelemetryMode

            self.data_manager = DataManager(telemetry_mode=TelemetryMode.STANDARD, chunk_size=512)

            # Create recording file
            recording_file = self.data_manager.create_recording_file(
                output_dir=config.output_dir,
                experiment_name=config.experiment_name,
                timestamped=True,
            )

            if not recording_file:
                raise RuntimeError("Failed to create recording file")

            # Set recording configuration
            self.data_manager.set_recording_config(
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
            # Initial sensor query before recording starts
            # ================================================================
            # This ensures we have valid temperature/humidity values for frame 0
            if self.frame_capture:
                logger.info("Querying initial sensor values...")
                self.frame_capture.query_sensors_if_needed()
                logger.info("Initial sensor query complete")

            # ================================================================
            # Set process priority to HIGH for stable timing
            # ================================================================
            self._set_high_priority()

            # Start recording state
            self.state.start_recording()

            # ================================================================
            # CRITICAL: Sync Data Manager start time with Recording State
            # ================================================================
            # The Data Manager's recording_start_time was set earlier during
            # create_recording_file(), but we need it to match the actual
            # recording start time for proper timestamp calculation
            self.data_manager.recording_start_time = self.state.start_time
            logger.info(f"Data Manager start time synchronized: {self.state.start_time:.3f}")

            # Start phase recording
            if self.phase_manager:
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

                # Capture frame
                self._capture_single_frame()

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

    def _capture_single_frame(self):
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

            if self.phase_manager and self.phase_manager.is_enabled():
                # Get phase info, but prevent transition if this is the last frame
                phase_info = self.phase_manager.get_current_phase_info(
                    prevent_transition=is_last_frame
                )

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
            brightness_threshold = (
                self.state.config.brightness_validation_threshold
            )  # Adaptive threshold

            logger.debug(
                f"Capturing frame {frame_number}/{self.state.total_frames} (LED: {led_type}, dual_mode: {dual_mode})"
            )
            if phase_info:
                logger.debug(
                    f"Phase: {phase_info.phase.value}, Cycle: {phase_info.cycle_number}/{phase_info.total_cycles}"
                )

            frame = None
            metadata = None

            for retry_attempt in range(max_capture_retries):
                # Attempt frame capture
                frame, metadata = self.frame_capture.capture_with_retry(
                    led_type=led_type, dual_mode=dual_mode, max_retries=3
                )

                if frame is None:
                    logger.error("Frame capture failed")
                    self.error_occurred.emit("Frame capture failed")
                    return

                # Validate frame brightness (using same ROI as calibration)
                import numpy as np

                # Calculate mean intensity using same method as calibration
                if self.state.config.use_full_frame_for_validation:
                    # Use entire frame
                    frame_mean = float(np.mean(frame))
                else:
                    # Use center ROI (same as calibration)
                    h, w = frame.shape[:2]
                    roi_frac = self.state.config.roi_fraction

                    # Calculate ROI boundaries
                    center_h = h // 2
                    center_w = w // 2
                    roi_h = int(h * roi_frac)
                    roi_w = int(w * roi_frac)

                    roi_y1 = center_h - roi_h // 2
                    roi_y2 = roi_y1 + roi_h
                    roi_x1 = center_w - roi_w // 2
                    roi_x2 = roi_x1 + roi_w

                    # Extract ROI and calculate mean
                    roi_region = frame[roi_y1:roi_y2, roi_x1:roi_x2]
                    frame_mean = float(np.mean(roi_region))

                # Check if frame is too dark (likely a timing issue)
                if frame_mean < brightness_threshold:
                    logger.warning(
                        f"⚠️  Frame {frame_number} too dark (mean={frame_mean:.1f} < {brightness_threshold}), "
                        f"retry {retry_attempt + 1}/{max_capture_retries}"
                    )

                    if retry_attempt < max_capture_retries - 1:
                        # Wait a bit before retry to let system stabilize
                        time.sleep(0.5)
                        continue
                    else:
                        # Last retry failed - log error but save frame anyway
                        logger.error(
                            f"❌ Frame {frame_number} still dark (mean={frame_mean:.1f}) after {max_capture_retries} retries - saving anyway"
                        )
                        metadata["capture_method"] = "dark_frame_recovered"
                        break
                else:
                    # Frame brightness OK
                    if retry_attempt > 0:
                        logger.info(
                            f"✅ Frame {frame_number} recovered successfully (mean={frame_mean:.1f}) on retry {retry_attempt + 1}"
                        )
                    break

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
            config = self.state.get_config()
            if config and phase_info and config.phase_enabled:
                # Phase recording: Use per-phase powers
                from .recording_state import PhaseType

                if phase_info.phase == PhaseType.DARK:
                    metadata["led_power"] = config.dark_phase_ir_power
                    metadata["ir_led_power"] = config.dark_phase_ir_power
                    metadata["white_led_power"] = 0
                else:
                    # Light phase
                    if dual_mode:
                        metadata["led_power"] = (
                            config.light_phase_ir_power
                        )  # Store IR power in legacy field
                        metadata["ir_led_power"] = config.light_phase_ir_power
                        metadata["white_led_power"] = config.light_phase_white_power
                    else:
                        metadata["led_power"] = config.light_phase_white_power
                        metadata["ir_led_power"] = 0
                        metadata["white_led_power"] = config.light_phase_white_power
            elif config:
                # Continuous recording: Use legacy single powers
                if led_type == "ir" or dual_mode:
                    metadata["led_power"] = config.ir_led_power
                    metadata["ir_led_power"] = config.ir_led_power
                    metadata["white_led_power"] = config.white_led_power if dual_mode else 0
                elif led_type == "white":
                    metadata["led_power"] = config.white_led_power
                    metadata["ir_led_power"] = 0
                    metadata["white_led_power"] = config.white_led_power
                else:
                    metadata["led_power"] = -1
                    metadata["ir_led_power"] = -1
                    metadata["white_led_power"] = -1
            else:
                metadata["led_power"] = -1
                metadata["ir_led_power"] = -1
                metadata["white_led_power"] = -1

            # Add capture method
            if "error" in metadata:
                metadata["capture_method"] = "failed"
            elif metadata.get("success", False):
                metadata["capture_method"] = "normal"
            else:
                metadata["capture_method"] = "unknown"

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

            # Add phase summary
            if self.phase_manager:
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

        # Determine which LED powers to set based on current phase
        if phase_info.phase == PhaseType.DARK:
            # Dark phase: Use dark_phase_ir_power for IR LED
            ir_power = config.dark_phase_ir_power
            white_power = 0  # White LED not used in dark phase

            logger.debug(f"[PHASE POWER] Dark phase: Setting IR={ir_power}%")
            self.frame_capture.esp32.set_led_power(ir_power, "ir")

        else:
            # Light phase: Use light_phase powers
            ir_power = config.light_phase_ir_power
            white_power = config.light_phase_white_power

            if dual_mode:
                # Dual LED mode: Set both powers
                logger.debug(
                    f"[PHASE POWER] Light phase (dual): Setting IR={ir_power}%, White={white_power}%"
                )
                self.frame_capture.esp32.set_led_power(ir_power, "ir")
                time.sleep(0.01)  # Small delay between commands
                self.frame_capture.esp32.set_led_power(white_power, "white")
            else:
                # White-only light phase
                logger.debug(f"[PHASE POWER] Light phase (white): Setting White={white_power}%")
                self.frame_capture.esp32.set_led_power(white_power, "white")

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
