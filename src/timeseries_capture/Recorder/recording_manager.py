"""
Recording Manager - Haupt-Koordinator für Recording

Verantwortlich für:
- Recording-Loop (Main Thread)
- Koordination aller Components
- Event-Emission (Qt Signals)
- Error-Handling & Recovery
"""

import logging
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
except:
    try:
        from PyQt5.QtCore import QObject, pyqtSignal
    except:

        class QObject:
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
                    except:
                        pass

            def disconnect(self, slot=None):
                if slot is None:
                    self._subs.clear()
                else:
                    self._subs = [f for f in self._subs if f is not slot]

        def pyqtSignal(*_a, **_k):
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

            if config.phase_enabled and config.dual_light_phase:
                print("🔆 Initializing DUAL LED mode for light phases")
                print(f"   IR LED power: {config.ir_led_power}%")
                print(f"   White LED power: {config.white_led_power}%\n")

                logger.info("🔆 Initializing DUAL LED mode for light phases")
                logger.info(f"   IR LED power: {config.ir_led_power}%")
                logger.info(f"   White LED power: {config.white_led_power}%")

                # Set IR LED power
                print("Setting IR LED power...")
                logger.info("Setting IR LED power...")
                success_ir = self.frame_capture.esp32.set_led_power(config.ir_led_power, "ir")
                if success_ir:
                    print(f"✅ IR LED power set to {config.ir_led_power}%")
                    logger.info(f"✅ IR LED power set to {config.ir_led_power}%")
                else:
                    print("❌ Failed to set IR LED power!")
                    logger.error("❌ Failed to set IR LED power!")

                # Small delay between commands
                time.sleep(0.1)

                # Set White LED power (CRITICAL - this was missing!)
                print("Setting White LED power...")
                logger.info("Setting White LED power...")
                success_white = self.frame_capture.esp32.set_led_power(
                    config.white_led_power, "white"
                )
                if success_white:
                    print(f"✅ White LED power set to {config.white_led_power}%")
                    logger.info(f"✅ White LED power set to {config.white_led_power}%")
                else:
                    print("❌ Failed to set White LED power!")
                    logger.error("❌ Failed to set White LED power!")

                if success_ir and success_white:
                    print("✅ Both LED powers configured for dual mode\n")
                    logger.info("✅ Both LED powers configured for dual mode")
                else:
                    print("⚠️  LED power configuration incomplete - dual mode may not work!\n")
                    logger.error("⚠️  LED power configuration incomplete - dual mode may not work!")
            else:
                # Single LED mode - set the IR LED power (default)
                logger.info(f"Setting single LED mode: IR={config.ir_led_power}%")
                self.frame_capture.esp32.set_led_power(config.ir_led_power, "ir")

            logger.info("=" * 60)

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
        """
        logger.info("Recording loop started")

        try:
            while not self._stop_requested and not self.state.is_complete():
                # Check if paused
                if self.state.is_paused():
                    time.sleep(0.1)
                    continue

                # Check timing - warte bis nächstes Frame
                time_until_next = self.state.get_time_until_next_frame()
                if time_until_next > 0:
                    time.sleep(min(time_until_next, 0.1))
                    continue

                # Capture frame
                self._capture_single_frame()

                # Update progress
                progress = self.state.get_progress_percent()
                self.progress_updated.emit(progress)

                # Small sleep to prevent busy-waiting
                time.sleep(0.01)

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

            # Capture frame
            print(
                f"📸 Capturing frame {self.state.current_frame + 1}/{self.state.total_frames} (LED: {led_type}, dual_mode: {dual_mode})"
            )
            logger.info(
                f"Capturing frame {self.state.current_frame + 1}/{self.state.total_frames} (LED: {led_type}, dual_mode: {dual_mode})"
            )
            if phase_info:
                print(
                    f"   Phase: {phase_info.phase.value}, Cycle: {phase_info.cycle_number}/{phase_info.total_cycles}"
                )
                logger.info(
                    f"  Phase: {phase_info.phase.value}, Cycle: {phase_info.cycle_number}/{phase_info.total_cycles}"
                )

            frame, metadata = self.frame_capture.capture_with_retry(
                led_type=led_type, dual_mode=dual_mode, max_retries=3
            )

            if frame is None:
                logger.error("Frame capture failed")
                self.error_occurred.emit("Frame capture failed")
                return

            # Add phase info to metadata
            if phase_info:
                metadata["phase"] = phase_info.phase.value
                metadata["cycle_number"] = phase_info.cycle_number

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

                    logger.info(f"Frame {frame_number} saved successfully")
                else:
                    logger.error(f"Failed to save frame {frame_number}")

        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            self.error_occurred.emit(f"Capture error: {e}")

    def _finalize_recording(self):
        """Finalisiert Recording"""
        logger.info("Finalizing recording...")

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
