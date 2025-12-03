"""
Main Widget - Nematostella Timelapse Recording Widget
Vollständig integriert mit Recording-Funktionalität

Integriert:
- GUI Panels (Recording, Phase, LED, Status, Log)
- ESP32 GUI Controller (for connection management)
- Camera Adapter
- Event Handling
"""

import logging
from pathlib import Path
from typing import Optional

# Qt imports
try:
    from qtpy.QtCore import QTimer
    from qtpy.QtWidgets import QMessageBox, QTabWidget, QVBoxLayout, QWidget
except:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QMessageBox, QTabWidget, QVBoxLayout, QWidget

# Import GUI components (from GUI subfolder)
# Import controllers and adapters
from .camera_adapters import create_camera_adapter
from .esp32_gui_controller import ESP32GUIController
from .GUI.esp32_connection_panel import ESP32ConnectionPanel
from .GUI.led_control_panel import LEDControlPanel
from .GUI.log_panel import LogPanel
from .GUI.phase_panel import PhaseConfigPanel
from .GUI.recording_panel import RecordingControlPanel
from .GUI.status_panel import StatusPanel
from .recording_controller import RecordingController

logger = logging.getLogger(__name__)


class NematostellaTimelapseCaptureWidget(QWidget):
    """
    Main Widget für Nematostella Timelapse Recording.

    Features:
    - ESP32 Connection Management
    - Recording Control (Start/Stop/Pause)
    - Phase Configuration (Day/Night Cycles)
    - LED Control
    - Live Status Display
    - System Logging
    """

    def __init__(self, napari_viewer=None, camera_manager=None, parent=None):
        """
        Args:
            napari_viewer: Napari viewer instance (optional)
            camera_manager: ImSwitch camera manager (optional)
            parent: Parent widget
        """
        super().__init__(parent)

        self.viewer = napari_viewer
        self.camera_manager = camera_manager

        # Controllers
        self.esp32_gui_controller: Optional[ESP32GUIController] = None
        self.recording_controller: Optional[RecordingController] = None
        self.camera_adapter = None

        # Calibration results storage (for per-phase LED power)
        # These are set by calibration and used when starting phase recordings
        self._calibrated_dark_phase_ir_power: Optional[int] = None
        self._calibrated_light_phase_ir_power: Optional[int] = None
        self._calibrated_light_phase_white_power: Optional[int] = None

        # Setup UI first
        self._setup_ui()

        # Initialize hardware after UI is ready
        QTimer.singleShot(500, self._initialize_hardware)

        logger.info("Main Widget initialized")

    # ========================================================================
    # UI SETUP
    # ========================================================================

    def _setup_ui(self):
        """Setup user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create panels
        self.esp32_panel = ESP32ConnectionPanel()
        self.recording_panel = RecordingControlPanel()
        self.phase_panel = PhaseConfigPanel()
        self.led_panel = LEDControlPanel()
        self.log_panel = LogPanel()

        # Add tabs
        self.tabs.addTab(self.esp32_panel, "🔌 ESP32 Connection")
        self.tabs.addTab(self.recording_panel, "📹 Recording")
        self.tabs.addTab(self.phase_panel, "🌓 Phase Config")
        self.tabs.addTab(self.led_panel, "💡 LED Control")
        self.tabs.addTab(self.log_panel, "📋 System Log")

        # Status panel (bottom)
        self.status_panel = StatusPanel()
        layout.addWidget(self.status_panel)

        # Connect GUI signals
        self._connect_gui_signals()

        # Initial log
        self.log_panel.add_log("System initialized. Ready to connect hardware...", "INFO")

    def _connect_gui_signals(self):
        """Connect GUI panel signals"""
        # Recording Panel
        self.recording_panel.start_requested.connect(self._on_start_recording_requested)
        self.recording_panel.stop_requested.connect(self._on_stop_recording_requested)
        self.recording_panel.pause_requested.connect(self._on_pause_recording_requested)
        self.recording_panel.resume_requested.connect(self._on_resume_recording_requested)

        # LED Panel
        self.led_panel.led_on_requested.connect(self._on_led_on_requested)
        self.led_panel.led_off_requested.connect(self._on_led_off_requested)
        self.led_panel.led_power_changed.connect(self._on_led_power_changed)
        self.led_panel.calibration_requested.connect(self._on_calibration_requested)

    # ========================================================================
    # HARDWARE INITIALIZATION
    # ========================================================================

    def _initialize_hardware(self):
        """Initialize hardware components"""
        try:
            # 1. Initialize Camera
            self.log_panel.add_log("Initializing camera...", "INFO")

            # Debug: Check viewer status
            print(f"\n{'='*60}")
            print("CAMERA INITIALIZATION DEBUG")
            print(f"camera_manager: {self.camera_manager}")
            print(f"viewer: {self.viewer}")
            if self.viewer:
                print(f"viewer type: {type(self.viewer)}")
                if hasattr(self.viewer, "layers"):
                    print(f"viewer.layers: {self.viewer.layers}")
                    print(f"Number of layers: {len(self.viewer.layers)}")
                    for i, layer in enumerate(self.viewer.layers):
                        print(f"  Layer {i}: {layer.name if hasattr(layer, 'name') else 'unnamed'}")
            print(f"{'='*60}\n")

            if self.camera_manager:
                # Use HIK GigE via ImSwitch
                self.camera_adapter = create_camera_adapter(
                    camera_type="hik", camera_manager=self.camera_manager
                )
                self.log_panel.add_log("✅ HIK GigE camera initialized", "SUCCESS")
            elif self.viewer:
                # Use Napari viewer (will auto-detect ImSwitch live layer)
                self.camera_adapter = create_camera_adapter(
                    camera_type="napari", napari_viewer=self.viewer
                )
                # Check if ImSwitch layer was found
                info = self.camera_adapter.get_camera_info()
                layer_name = info.get("layer_name", "unknown")
                if (
                    layer_name
                    and layer_name != "unknown"
                    and any(
                        indicator in str(layer_name)
                        for indicator in ["Live:", "Widefield", "Camera", "Detector"]
                    )
                ):
                    self.log_panel.add_log(f"✅ ImSwitch camera via layer: {layer_name}", "SUCCESS")
                elif layer_name and layer_name != "unknown":
                    self.log_panel.add_log(f"✅ Napari camera initialized: {layer_name}", "SUCCESS")
                else:
                    # No layers found yet (live view not started)
                    self.log_panel.add_log(
                        "⚠️ No camera layers found - start live view first, then use 'Refresh Camera'",
                        "WARNING",
                    )
                    # Keep the adapter but note it needs refresh
            else:
                # Use dummy for testing
                self.camera_adapter = create_camera_adapter(camera_type="dummy")
                self.log_panel.add_log("⚠️ Using dummy camera (no real camera found)", "WARNING")

            # 2. Initialize ESP32 GUI Controller
            self.log_panel.add_log("Setting up ESP32 GUI controller...", "INFO")
            self.esp32_gui_controller = ESP32GUIController(
                connection_panel=self.esp32_panel, log_panel=self.log_panel
            )

            # Connect ESP32 GUI controller signals
            self._connect_esp32_signals()

            self.log_panel.add_log("✅ ESP32 GUI controller ready", "SUCCESS")

            # 3. Auto-connect if enabled
            self.esp32_gui_controller.auto_connect_if_enabled()

            # 4. Initialize Recording Controller
            self.log_panel.add_log("Setting up recording controller...", "INFO")
            self.recording_controller = RecordingController(
                esp32_gui_controller=self.esp32_gui_controller, camera_adapter=self.camera_adapter
            )

            # Connect recording controller signals
            self._connect_recording_signals()

            self.log_panel.add_log("✅ Recording controller ready", "SUCCESS")

            # 5. Update hardware status
            self._update_hardware_status()

            # 6. Start periodic status updates
            self._start_status_updates()

        except Exception as e:
            logger.error(f"Hardware initialization failed: {e}", exc_info=True)
            self.log_panel.add_log(f"❌ Hardware init failed: {e}", "ERROR")
            self._show_error("Initialization Error", str(e))

    def _connect_esp32_signals(self):
        """Connect ESP32 GUI controller signals"""
        if not self.esp32_gui_controller:
            return

        # ESP32 connection status changes
        self.esp32_gui_controller.connection_status_changed.connect(
            self._on_esp32_connection_changed
        )

        # Hardware info updates
        self.esp32_gui_controller.hardware_info_updated.connect(self._on_esp32_hardware_info)

        # Connection errors
        self.esp32_gui_controller.connection_error.connect(self._on_esp32_connection_error)

    def _connect_recording_signals(self):
        """Connect recording controller signals"""
        if not self.recording_controller:
            return

        # Recording status updates
        self.recording_controller.status_updated.connect(self._on_recording_status_updated)

        # Recording errors
        self.recording_controller.error_occurred.connect(self._on_recording_error)

    def _start_status_updates(self):
        """Start periodic status updates"""
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_hardware_status)
        self.status_timer.start(2000)  # Update every 2 seconds

    # ========================================================================
    # ESP32 SIGNAL HANDLERS
    # ========================================================================

    def _on_esp32_connection_changed(self, connected: bool, port: str):
        """Handle ESP32 connection status change"""
        if connected:
            self.log_panel.add_log(f"✅ ESP32 connected on {port}", "SUCCESS")
        else:
            self.log_panel.add_log("⚠️ ESP32 disconnected", "WARNING")

        # Update status display
        self._update_hardware_status()

    def _on_esp32_hardware_info(self, hw_info: dict):
        """Handle ESP32 hardware info update"""
        # Info is already displayed by ESP32ConnectionPanel
        pass

    def _on_esp32_connection_error(self, error_msg: str):
        """Handle ESP32 connection error"""
        self._show_error("ESP32 Connection Error", error_msg)

    # ========================================================================
    # RECORDING CONTROL (GUI Signals)
    # ========================================================================

    def _on_start_recording_requested(self):
        """Start recording button pressed"""
        # Check if ESP32 is connected
        if not self.esp32_gui_controller or not self.esp32_gui_controller.is_connected():
            self._show_error("Error", "ESP32 not connected. Please connect first.")
            return

        # Check if camera is available
        if not self.camera_adapter or not self.camera_adapter.is_available():
            self._show_error("Error", "Camera not available.")
            return

        # Check if recording controller is ready
        if not self.recording_controller:
            self._show_error("Error", "Recording controller not initialized.")
            return

        try:
            # Get configuration from GUI
            recording_config = self.recording_panel.get_config()
            phase_config = self.phase_panel.get_config()

            # Get LED power settings from LED control panel
            led_powers = self.led_panel.get_led_powers()

            # Merge configs
            full_config = {
                **recording_config,
                **phase_config,
                # Legacy single LED powers (for backward compatibility and continuous mode)
                "ir_led_power": led_powers["ir"],
                "white_led_power": led_powers["white"],
            }

            # Add per-phase LED powers if calibrated (for phase recordings)
            # These override legacy values when phase_enabled=True
            if self._calibrated_dark_phase_ir_power is not None:
                full_config["dark_phase_ir_power"] = self._calibrated_dark_phase_ir_power
            if self._calibrated_light_phase_ir_power is not None:
                full_config["light_phase_ir_power"] = self._calibrated_light_phase_ir_power
            if self._calibrated_light_phase_white_power is not None:
                full_config["light_phase_white_power"] = self._calibrated_light_phase_white_power

            # Validate output directory
            output_dir = Path(full_config["output_dir"])
            if not output_dir.exists():
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._show_error("Error", f"Cannot create output directory: {e}")
                    return

            # Start recording via controller
            self.log_panel.add_log("🎬 Starting recording...", "INFO")
            self.log_panel.add_log(f"Config: {full_config}", "DEBUG")

            success = self.recording_controller.start_recording(full_config)

            if success:
                self.log_panel.add_log("✅ Recording started successfully", "SUCCESS")
            else:
                self.log_panel.add_log("❌ Failed to start recording", "ERROR")

        except Exception as e:
            logger.error(f"Start recording error: {e}", exc_info=True)
            self._show_error("Error", f"Failed to start: {e}")
            self.log_panel.add_log(f"❌ Recording start failed: {e}", "ERROR")

    def _on_stop_recording_requested(self):
        """Stop recording button pressed"""
        if not self.recording_controller:
            self.log_panel.add_log("⚠️ Recording controller not initialized", "WARNING")
            return

        try:
            self.log_panel.add_log("⏹️ Stopping recording...", "INFO")
            self.recording_controller.stop_recording()
            self.log_panel.add_log("✅ Recording stopped", "SUCCESS")
        except Exception as e:
            logger.error(f"Stop recording error: {e}", exc_info=True)
            self.log_panel.add_log(f"❌ Stop error: {e}", "ERROR")

    def _on_pause_recording_requested(self):
        """Pause recording button pressed"""
        if not self.recording_controller:
            self.log_panel.add_log("⚠️ Recording controller not initialized", "WARNING")
            return

        try:
            self.log_panel.add_log("⏸️ Pausing recording...", "INFO")
            self.recording_controller.pause_recording()
            self.log_panel.add_log("✅ Recording paused", "SUCCESS")
        except Exception as e:
            logger.error(f"Pause recording error: {e}", exc_info=True)
            self.log_panel.add_log(f"❌ Pause error: {e}", "ERROR")

    def _on_resume_recording_requested(self):
        """Resume recording button pressed"""
        if not self.recording_controller:
            self.log_panel.add_log("⚠️ Recording controller not initialized", "WARNING")
            return

        try:
            self.log_panel.add_log("▶️ Resuming recording...", "INFO")
            self.recording_controller.resume_recording()
            self.log_panel.add_log("✅ Recording resumed", "SUCCESS")
        except Exception as e:
            logger.error(f"Resume recording error: {e}", exc_info=True)
            self.log_panel.add_log(f"❌ Resume error: {e}", "ERROR")

    def _on_recording_status_updated(self, status: dict):
        """Handle recording status update from controller"""
        try:
            # Update recording panel
            self.recording_panel.update_status(status)

            # Update status panel
            rec_status = {
                "recording": status.get("recording", False),
                "paused": status.get("paused", False),
                "current_frame": status.get("current_frame", 0),
                "total_frames": status.get("total_frames", 0),
            }
            self.status_panel.update_recording_status(rec_status)

            # Update phase info if available
            if "phase" in status:
                phase_info = status["phase"]
                self.recording_panel.update_phase_info(phase_info)
                self.status_panel.update_phase_info(phase_info)

        except Exception as e:
            logger.error(f"Error updating recording status: {e}", exc_info=True)

    def _on_recording_error(self, error_msg: str):
        """Handle recording error from controller"""
        self.log_panel.add_log(f"❌ Recording error: {error_msg}", "ERROR")
        self._show_error("Recording Error", error_msg)

    # ========================================================================
    # LED CONTROL (GUI Signals)
    # ========================================================================

    def _on_led_on_requested(self, led_type: str):
        """LED ON button pressed"""
        if not self.esp32_gui_controller:
            self._show_error("Error", "ESP32 GUI controller not initialized")
            return

        if not self.esp32_gui_controller.is_connected():
            self._show_error("Error", "ESP32 not connected")
            return

        try:
            success = self.esp32_gui_controller.led_on(led_type)
            if success:
                self._update_led_status()
        except Exception as e:
            logger.error(f"LED on error: {e}", exc_info=True)
            self._show_error("LED Error", str(e))

    def _on_led_off_requested(self, led_type: str):
        """LED OFF button pressed

        Args:
            led_type: 'ir' or 'white' - specific LED to turn off
        """
        if not self.esp32_gui_controller:
            return

        if not self.esp32_gui_controller.is_connected():
            return

        try:
            success = self.esp32_gui_controller.led_off(led_type)
            if success:
                self._update_led_status()
        except Exception as e:
            logger.error(f"LED off error: {e}", exc_info=True)

    def _on_led_power_changed(self, led_type: str, power: int):
        """LED power slider changed"""
        if not self.esp32_gui_controller:
            return

        if not self.esp32_gui_controller.is_connected():
            return

        try:
            self.esp32_gui_controller.set_led_power(power, led_type)
            # Update will happen via periodic status update
        except Exception as e:
            logger.error(f"LED power change error: {e}", exc_info=True)

    def _on_calibration_requested(self, mode: str):
        """Calibration button pressed"""
        self.log_panel.add_log(f"🔄 Starting {mode.upper()} LED calibration...", "INFO")

        try:
            # Check prerequisites
            if not self.esp32_gui_controller or not self.esp32_gui_controller.is_connected():
                self.log_panel.add_log("❌ ESP32 not connected!", "ERROR")
                self.led_panel.add_calibration_result("❌ ERROR: ESP32 not connected")
                return

            if not self.camera_adapter or not self.camera_adapter.is_available():
                self.log_panel.add_log("❌ Camera not available!", "ERROR")
                self.led_panel.add_calibration_result("❌ ERROR: Camera not available")
                return

            # Run calibration in separate thread to avoid blocking UI
            import threading

            def run_calibration():
                """Run calibration in background thread"""
                try:
                    from .Recorder.calibration_service import CalibrationService

                    # Create capture callback
                    def capture_frame():
                        """Capture frame from camera"""
                        return self.camera_adapter.capture_frame()

                    # Create LED power callback
                    def set_led_power(power, led_type):
                        """Set LED power"""
                        return self.esp32_gui_controller.set_led_power(power, led_type)

                    # Create LED on/off callbacks
                    def led_on(led_type):
                        """Turn LED on"""
                        return self.esp32_gui_controller.led_on(led_type)

                    def led_off():
                        """Turn LED off"""
                        return self.esp32_gui_controller.led_off()

                    # Get calibration settings from GUI
                    use_full_frame = self.led_panel.get_use_full_frame()

                    # Create calibration service
                    calibrator = CalibrationService(
                        capture_callback=capture_frame,
                        set_led_power_callback=set_led_power,
                        led_on_callback=led_on,
                        led_off_callback=led_off,
                        target_intensity=200.0,  # Target mean intensity
                        max_iterations=10,
                        tolerance_percent=5.0,
                        use_full_frame=use_full_frame,  # Use checkbox setting
                        roi_fraction=0.75,  # 75% x 75% center ROI when not using full frame
                    )

                    # Run calibration based on mode
                    if mode == "ir":
                        result = calibrator.calibrate_ir(initial_power=50)
                    elif mode == "white":
                        result = calibrator.calibrate_white(initial_power=30)
                    elif mode == "dual":
                        result = calibrator.calibrate_dual(
                            ir_initial_power=50, white_initial_power=30
                        )
                    else:
                        self.log_panel.add_log(f"❌ Unknown calibration mode: {mode}", "ERROR")
                        return

                    # Report results
                    if result.success:
                        self.log_panel.add_log(
                            f"✅ {mode.upper()} calibration successful!", "SUCCESS"
                        )
                        self.led_panel.add_calibration_result(
                            f"✅ SUCCESS: {result.message}\n"
                            f"   IR Power: {result.ir_power}%\n"
                            f"   White Power: {result.white_power}%\n"
                            f"   Measured Intensity: {result.measured_intensity:.1f}\n"
                            f"   Target Intensity: {result.target_intensity:.1f}\n"
                            f"   Error: {result.error_percent:.1f}%\n"
                            f"   Iterations: {result.iterations}"
                        )

                        # Update GUI sliders with calibrated values
                        self.led_panel.set_led_powers(
                            {"ir": result.ir_power, "white": result.white_power}
                        )

                        # Store calibration results for per-phase recording
                        # These will be used when phase recording is enabled
                        if mode == "ir":
                            # IR calibration → used for dark phase (IR only)
                            self._calibrated_dark_phase_ir_power = result.ir_power
                            self.log_panel.add_log(
                                f"💾 Saved for DARK phase: IR = {result.ir_power}%", "INFO"
                            )
                        elif mode == "white":
                            # White calibration → used for light phase (white only or dual)
                            self._calibrated_light_phase_white_power = result.white_power
                            self.log_panel.add_log(
                                f"💾 Saved for LIGHT phase: White = {result.white_power}%", "INFO"
                            )
                        elif mode == "dual":
                            # Dual calibration → used for light phase (dual LED mode)
                            self._calibrated_light_phase_ir_power = result.ir_power
                            self._calibrated_light_phase_white_power = result.white_power
                            self.log_panel.add_log(
                                f"💾 Saved for LIGHT phase (dual): IR = {result.ir_power}%, White = {result.white_power}%",
                                "INFO",
                            )
                    else:
                        self.log_panel.add_log(f"❌ {mode.upper()} calibration failed", "ERROR")
                        self.led_panel.add_calibration_result(
                            f"❌ FAILED: {result.message}\n"
                            f"   Best Power: IR={result.ir_power}%, White={result.white_power}%\n"
                            f"   Measured Intensity: {result.measured_intensity:.1f}\n"
                            f"   Target Intensity: {result.target_intensity:.1f}\n"
                            f"   Error: {result.error_percent:.1f}%\n"
                            f"   Iterations: {result.iterations}"
                        )

                except Exception as e:
                    self.log_panel.add_log(f"❌ Calibration error: {e}", "ERROR")
                    self.led_panel.add_calibration_result(f"❌ ERROR: {e}")
                    logger.error(f"Calibration error: {e}", exc_info=True)

            # Start calibration thread
            calib_thread = threading.Thread(target=run_calibration, daemon=True)
            calib_thread.start()

        except Exception as e:
            self.log_panel.add_log(f"❌ Failed to start calibration: {e}", "ERROR")
            self.led_panel.add_calibration_result(f"❌ ERROR: {e}")
            logger.error(f"Calibration start error: {e}", exc_info=True)

    # ========================================================================
    # HARDWARE STATUS UPDATES
    # ========================================================================

    def _update_hardware_status(self):
        """Update hardware status display"""
        try:
            # Check ESP32 connection
            esp32_connected = (
                self.esp32_gui_controller is not None and self.esp32_gui_controller.is_connected()
            )

            # Check camera availability
            camera_available = (
                self.camera_adapter is not None and self.camera_adapter.is_available()
            )

            camera_name = "Unknown"
            if self.camera_adapter:
                try:
                    info = self.camera_adapter.get_camera_info()
                    camera_name = info.get("name", "Unknown")
                except:
                    pass

            # Update status panel
            self.status_panel.update_hardware_status(
                {
                    "esp32_connected": esp32_connected,
                    "camera_available": camera_available,
                    "camera_name": camera_name,
                }
            )

            # Update LED status if ESP32 is connected
            if esp32_connected:
                self._update_led_status()

        except Exception as e:
            logger.debug(f"Hardware status update error: {e}")

    def _update_led_status(self):
        """Update LED status display"""
        if not self.esp32_gui_controller or not self.esp32_gui_controller.is_connected():
            return

        try:
            # Check if recording is active - if so, show intended LED configuration
            # (not physical state, since LEDs pulse briefly during each frame)
            if self.recording_controller and self.recording_controller.is_recording():
                # Get recording state to determine current LED configuration
                recording_state = self.recording_controller.get_state()
                if recording_state:
                    # Get current phase info (if phase recording enabled)
                    phase_info = recording_state.get_phase()

                    if phase_info:
                        # Phase recording - show phase-specific LED type
                        led_type = phase_info.led_type  # 'ir', 'white', or 'dual'
                        led_on = True  # Recording is active

                        # Get power from recording config (phase-specific)
                        config = recording_state.get_config()
                        if led_type == "dual":
                            # Dual mode - show average of both powers
                            power = (
                                config.light_phase_ir_power + config.light_phase_white_power
                            ) // 2
                        elif led_type == "ir":
                            # IR only (dark phase)
                            power = config.dark_phase_ir_power
                        else:
                            # White only (light phase, non-dual)
                            power = config.light_phase_white_power
                    else:
                        # Continuous recording (no phases) - show legacy config
                        config = recording_state.get_config()
                        if config:
                            # For continuous mode, check which LED is being used
                            # (This should be tracked better, but for now assume IR is primary)
                            led_type = "ir"  # Default assumption for continuous mode
                            led_on = True
                            power = config.ir_led_power
                        else:
                            led_type = "off"
                            led_on = False
                            power = 0
                else:
                    led_type = "off"
                    led_on = False
                    power = 0
            else:
                # Not recording - query physical LED state from ESP32
                esp32 = self.esp32_gui_controller.get_esp32_controller()
                if not esp32:
                    return

                led_status = esp32.get_led_status()
                if led_status:
                    # Determine which LED is active
                    led_on = led_status.ir_state or led_status.white_state

                    if led_status.ir_state and led_status.white_state:
                        led_type = "dual"
                        power = max(led_status.ir_power, led_status.white_power)
                    elif led_status.ir_state:
                        led_type = "ir"
                        power = led_status.ir_power
                    elif led_status.white_state:
                        led_type = "white"
                        power = led_status.white_power
                    else:
                        led_type = "off"
                        power = 0
                else:
                    return

            # Update LED panel
            self.led_panel.update_status({"led_on": led_on, "led_type": led_type, "power": power})

            # Update status panel
            self.status_panel.update_led_status(
                {"led_on": led_on, "led_type": led_type, "power": power}
            )
        except Exception as e:
            logger.debug(f"LED status update error: {e}")

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def _show_error(self, title: str, message: str):
        """Show error message box"""
        QMessageBox.critical(self, title, message)

    def _show_info(self, title: str, message: str):
        """Show info message box"""
        QMessageBox.information(self, title, message)

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def closeEvent(self, event):
        """Handle widget close event"""
        logger.info("Main Widget closing...")

        # Stop status updates
        if hasattr(self, "status_timer"):
            self.status_timer.stop()

        # Cleanup recording controller
        if self.recording_controller:
            try:
                self.recording_controller.cleanup()
            except Exception as e:
                logger.error(f"Recording controller cleanup error: {e}")

        # Cleanup ESP32 GUI controller
        if self.esp32_gui_controller:
            try:
                self.esp32_gui_controller.cleanup()
            except Exception as e:
                logger.error(f"ESP32 GUI controller cleanup error: {e}")

        logger.info("Main Widget closed")
        event.accept()


# ============================================================================
# NAPARI PLUGIN ENTRY POINT
# ============================================================================


def create_timelapse_widget(
    napari_viewer=None, camera_manager=None
) -> NematostellaTimelapseCaptureWidget:
    """
    Create timelapse widget for Napari plugin.

    Args:
        napari_viewer: Napari viewer instance
        camera_manager: ImSwitch camera manager (optional)

    Returns:
        NematostellaTimelapseCaptureWidget instance
    """
    # If napari_viewer not provided, try to get current viewer
    if napari_viewer is None:
        try:
            import napari

            # Get current viewer if one exists
            if napari.current_viewer():
                napari_viewer = napari.current_viewer()
                print(f"✅ Auto-detected Napari viewer: {napari_viewer}")
            else:
                print("⚠️ No Napari viewer found via napari.current_viewer()")
        except Exception as e:
            print(f"⚠️ Could not auto-detect Napari viewer: {e}")

    widget = NematostellaTimelapseCaptureWidget(
        napari_viewer=napari_viewer, camera_manager=camera_manager
    )
    return widget
