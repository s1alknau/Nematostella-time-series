# """Main timelapse recorder orchestrating ESP32 and data storage with direct ImSwitch integration,
# with preference for a live Napari image layer as the frame source."""
# import time
# import threading
# from typing import Tuple
# from qtpy.QtCore import QObject
# import numpy as np
# from threading import Lock

# # ✅ FIX: pyqtSignal Import with try/except
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal


# class TimelapseRecorder(QObject):
#     """Simplified timelapse recording controller using ImSwitch directly, with Napari live-layer fallback/preference."""

#     # Signals
#     frame_captured = pyqtSignal(int, int)  # current_frame, total_frames
#     recording_started = pyqtSignal()
#     recording_finished = pyqtSignal()
#     recording_paused = pyqtSignal()
#     recording_resumed = pyqtSignal()
#     progress_updated = pyqtSignal(int)  # percentage
#     status_updated = pyqtSignal(str)  # status message
#     error_occurred = pyqtSignal(str)  # recording-related errors only
#     # NEW: Phase change signal
#     phase_changed = pyqtSignal(dict)  # phase_info dict

#     def __init__(self, duration_min: int, interval_sec: int, output_dir: str,
#                  esp32_controller, data_manager, imswitch_main, camera_name: str):
#         super().__init__()

#         # Recording parameters
#         self.duration_min = duration_min
#         self.interval_sec = interval_sec
#         self.output_dir = output_dir

#         # Controllers
#         self.esp32_controller = esp32_controller
#         self.data_manager = data_manager
#         self.imswitch_main = imswitch_main
#         self.camera_name = camera_name

#         #NEW: Phase configuration
#         self.phase_config = phase_config or {
#             'enabled': False,
#             'light_duration_min': 30,
#             'dark_duration_min': 30,
#             'start_with_light': True
#         }

#         # (Optional) Napari viewer; assigned externally (widget does this)
#         self.viewer = None

#         # State variables
#         self.recording = False
#         self.paused = False
#         self.should_stop = False
#         self.current_frame = 0
#         self.total_frames = self._calculate_total_frames()
#         self.start_time = None
#         self.expected_frame_times = []
#         self.cumulative_drift = 0.0

#         # Validation bypass flag (for debugging)
#         self.skip_validation = True

#         # Lock for shared state
#         self._state_lock = Lock()

#         # Recording thread
#         self.recording_thread = None

#     def _calculate_total_frames(self) -> int:
#         """Calculate total number of frames to capture."""
#         total_seconds = self.duration_min * 60
#         return int(total_seconds / self.interval_sec)

#     def start(self):
#         """Start timelapse recording."""
#         with self._state_lock:
#             if self.recording:
#                 self.error_occurred.emit("Recording already in progress")
#                 return

#         try:
#             if not self.skip_validation:
#                 if not self._validate_setup():
#                     return

#             self._initialize_recording()
#             self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
#             self.recording_thread.start()
#             self.recording_started.emit()
#             self.status_updated.emit("Recording started")
#         except Exception as e:
#             self.error_occurred.emit(f"Failed to start recording: {str(e)}")

#     def stop(self):
#         """Stop timelapse recording."""
#         with self._state_lock:
#             if not self.recording:
#                 return
#             self.should_stop = True

#         if self.recording_thread and self.recording_thread.is_alive():
#             self.recording_thread.join(timeout=5.0)

#         self._finalize_recording()
#         self.status_updated.emit("Recording stopped")

#     def pause(self):
#         """Pause recording."""
#         with self._state_lock:
#             if not self.recording or self.paused:
#                 return
#             self.paused = True

#         self.recording_paused.emit()
#         self.status_updated.emit("Recording paused")

#     def resume(self):
#         """Resume recording."""
#         with self._state_lock:
#             if not self.recording or not self.paused:
#                 return
#             self.paused = False

#         self.recording_resumed.emit()
#         self.status_updated.emit("Recording resumed")

#     def probe_frame(self) -> bool:
#         """Lightweight probe to verify frame capture works."""
#         try:
#             frame, metadata = self._safe_capture_frame()
#             print(f"Probe: got frame {frame.shape} from {metadata.get('source')}")
#             return True
#         except Exception as e:
#             print(f"Probe failed: {e}")
#             return False

#     # ------------------------------------------------------------------
#     # Frame capture methods
#     # ------------------------------------------------------------------
#     def _capture_frame_from_napari_layer(self) -> Tuple[np.ndarray, dict]:
#         """Preferentially grab the latest frame from a live Napari image layer."""
#         if self.viewer is None:
#             raise RuntimeError("No Napari viewer assigned for Napari-layer capture")
#         try:
#             from napari.layers import Image
#         except ImportError:
#             raise RuntimeError("Napari not available for layer fallback")

#         # First try to prefer layers with name hints
#         preferred_keywords = ('live', 'widefield', 'imswitch')
#         for layer in self.viewer.layers:
#             if not isinstance(layer, Image):
#                 continue
#             name = getattr(layer, 'name', '').lower()
#             if any(k in name for k in preferred_keywords):
#                 data = getattr(layer, 'data', None)
#                 if data is None:
#                     continue
#                 if hasattr(data, 'size') and data.size == 0:
#                     continue
#                 frame = np.array(data, copy=True)
#                 metadata = {
#                     "timestamp": time.time(),
#                     "camera_name": getattr(self, 'camera_name', 'unknown'),
#                     "frame_shape": frame.shape,
#                     "frame_dtype": str(frame.dtype),
#                     "source": f"napari_layer:{layer.name}",
#                     "fallback": True,
#                     "preferred_layer": True
#                 }
#                 return frame, metadata

#         # Fallback to any non-empty image layer
#         for layer in self.viewer.layers:
#             if not isinstance(layer, Image):
#                 continue
#             data = getattr(layer, 'data', None)
#             if data is None:
#                 continue
#             if hasattr(data, 'size') and data.size == 0:
#                 continue
#             frame = np.array(data, copy=True)
#             metadata = {
#                 "timestamp": time.time(),
#                 "camera_name": getattr(self, 'camera_name', 'unknown'),
#                 "frame_shape": frame.shape,
#                 "frame_dtype": str(frame.dtype),
#                 "source": f"napari_layer:{layer.name}",
#                 "fallback": True
#             }
#             return frame, metadata

#         raise RuntimeError("No suitable Napari image layer found for fallback frame")

#     def _capture_frame_from_imswitch_direct(self) -> Tuple[np.ndarray, dict]:
#         """Attempt to capture frame directly from ImSwitch structures."""
#         if self.imswitch_main is None:
#             raise RuntimeError("ImSwitch not available for direct capture")

#         # Try liveViewWidget
#         try:
#             if hasattr(self.imswitch_main, 'liveViewWidget'):
#                 live_view = self.imswitch_main.liveViewWidget
#                 if hasattr(live_view, 'img') and live_view.img is not None:
#                     frame = live_view.img.copy()
#                     metadata = {
#                         "timestamp": time.time(),
#                         "camera_name": self.camera_name,
#                         "frame_shape": frame.shape,
#                         "frame_dtype": str(frame.dtype),
#                         "imswitch_managed": True,
#                         "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                         "source": "live_view_widget"
#                     }
#                     return frame, metadata
#         except Exception:
#             pass

#         # Try viewWidget
#         try:
#             if hasattr(self.imswitch_main, 'viewWidget'):
#                 view_widget = self.imswitch_main.viewWidget
#                 if hasattr(view_widget, 'getCurrentImage'):
#                     frame = view_widget.getCurrentImage()
#                     if frame is not None:
#                         metadata = {
#                             "timestamp": time.time(),
#                             "camera_name": self.camera_name,
#                             "frame_shape": frame.shape,
#                             "frame_dtype": str(frame.dtype),
#                             "imswitch_managed": True,
#                             "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                             "source": "view_widget"
#                         }
#                         return frame, metadata
#         except Exception:
#             pass

#         # Try imageWidget
#         try:
#             if hasattr(self.imswitch_main, 'imageWidget'):
#                 image_widget = self.imswitch_main.imageWidget
#                 if hasattr(image_widget, 'image') and image_widget.image is not None:
#                     frame = image_widget.image.copy()
#                     metadata = {
#                         "timestamp": time.time(),
#                         "camera_name": self.camera_name,
#                         "frame_shape": frame.shape,
#                         "frame_dtype": str(frame.dtype),
#                         "imswitch_managed": True,
#                         "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                         "source": "image_widget"
#                     }
#                     return frame, metadata
#         except Exception:
#             pass

#         # Try detectorsManager methods
#         if hasattr(self.imswitch_main, 'detectorsManager'):
#             detectors_manager = self.imswitch_main.detectorsManager
#             methods_to_try = [
#                 ('getLatestFrame', True),
#                 ('getLatestFrame', False),
#                 ('getLastImage', True),
#                 ('getLastImage', False),
#                 ('snap', True),
#                 ('snap', False),
#                 ('getImage', True),
#                 ('getImage', False),
#                 ('captureFrame', True),
#                 ('captureFrame', False)
#             ]
#             for method_name, use_camera_name in methods_to_try:
#                 if not hasattr(detectors_manager, method_name):
#                     continue
#                 try:
#                     method = getattr(detectors_manager, method_name)
#                     if use_camera_name:
#                         frame = method(self.camera_name)
#                     else:
#                         frame = method()
#                     if frame is not None:
#                         metadata = {
#                             "timestamp": time.time(),
#                             "camera_name": self.camera_name,
#                             "frame_shape": frame.shape,
#                             "frame_dtype": str(frame.dtype),
#                             "imswitch_managed": True,
#                             "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                             "source": f"detector_manager_{method_name}"
#                         }
#                         return frame, metadata
#                 except Exception:
#                     continue

#         raise RuntimeError("Could not capture frame from any ImSwitch method")

#     def _safe_capture_frame(self) -> Tuple[np.ndarray, dict]:
#         """Unified capture: ImSwitch FIRST (fresh frame), Napari only as fallback."""

#         # ✅ CHANGE: Try ImSwitch FIRST for fresh frames
#         if self.imswitch_main is not None:
#             try:
#                 return self._capture_frame_from_imswitch_direct()
#             except Exception as e:
#                 print(f"ImSwitch direct capture failed: {e}, trying Napari...")

#         # ✅ ADD: Force Napari refresh before capture
#         if self.viewer is not None:
#             try:
#                 # Force layer refresh
#                 self.viewer.layers.events.changed()
#                 time.sleep(0.05)  # Small delay for refresh

#                 frame, metadata = self._capture_frame_from_napari_layer()
#                 return frame, metadata
#             except Exception as e:
#                 print(f"Napari capture also failed: {e}")

#         raise RuntimeError("All frame capture methods failed")

#     # ------------------------------------------------------------------
#     # Validation / Initialization / Loop
#     # ------------------------------------------------------------------
#     def _validate_setup(self) -> bool:
#         """Validate setup before starting recording."""
#         if self.imswitch_main is None and self.viewer is None:
#             self.error_occurred.emit("No ImSwitch controller and no Napari viewer for frame capture")
#             return False

#         # Probe capture path
#         try:
#             frame, metadata = self._safe_capture_frame()
#             if frame is None:
#                 self.error_occurred.emit("Frame capture test returned None")
#                 return False
#             print(f"Validation: Frame capture successful - {frame.shape} from {metadata.get('source')}")

#         except Exception as e:
#             self.error_occurred.emit(f"Frame capture test failed: {str(e)}")
#             return False

#         # ESP32 connection
#         if not self.esp32_controller.is_connected():
#             try:
#                 self.esp32_controller.connect()
#                 print("ESP32 connected during validation")
#             except Exception as e:
#                 self.error_occurred.emit(f"ESP32 connection failed: {str(e)}")
#                 return False

#         return True

#     def _initialize_recording(self):
#         """Initialize recording session."""
#         with self._state_lock:
#             self.recording = True
#             self.paused = False
#             self.should_stop = False
#             self.current_frame = 0
#         self.start_time = time.time()
#         self.cumulative_drift = 0.0

#         # Calculate expected frame times
#         self.expected_frame_times = [
#             self.start_time + (i * self.interval_sec) for i in range(self.total_frames)
#         ]
#         print(f"Recording initialized: {self.total_frames} frames over {self.duration_min} minutes")

#         # Create HDF5 file
#         try:
#             filepath = self.data_manager.create_recording_file(
#                 self.output_dir,
#                 experiment_name="nematostella_timelapse",
#                 timestamped=True
#             )
#             recording_metadata = {
#                 'duration_minutes': self.duration_min,
#                 'interval_seconds': self.interval_sec,
#                 'expected_frames': self.total_frames,
#                 'led_power': self.esp32_controller.led_power,
#                 'camera_name': self.camera_name,
#                 'imswitch_managed': True,
#                 'esp32_settings': self.esp32_controller.get_status() if self.esp32_controller.is_connected() else {}
#             }
#             self.data_manager.update_recording_metadata(recording_metadata)
#             print(f"Recording file created: {filepath}")
#         except Exception as e:
#             with self._state_lock:
#                 self.recording = False
#             raise RuntimeError(f"Failed to initialize data storage: {str(e)}")

#     def _recording_loop(self):
#         """Main recording loop running in separate thread."""
#         try:
#             print("Recording loop started")
#             self._capture_frame_sync()

#             while True:
#                 with self._state_lock:
#                     if self.should_stop or self.current_frame >= self.total_frames:
#                         break
#                     if self.paused:
#                         pass

#                 if self.paused:
#                     time.sleep(0.1)
#                     continue

#                 now = time.time()
#                 expected_time = self.expected_frame_times[self.current_frame]
#                 if now < expected_time:
#                     time.sleep(min(0.1, expected_time - now))
#                     continue

#                 self._capture_frame_sync()

#             with self._state_lock:
#                 completed = not self.should_stop and self.current_frame >= self.total_frames

#             if completed:
#                 self._finalize_recording()
#                 self.recording_finished.emit()
#                 print("Recording completed successfully")
#         except Exception as e:
#             print(f"Recording loop error: {e}")
#             self.error_occurred.emit(f"Recording error: {str(e)}")
#             self._finalize_recording()

#     def _capture_frame_sync(self):
#         """Capture frame with synchronization - ENHANCED for 72-hour stability."""
#         with self._state_lock:
#             if self.current_frame >= self.total_frames:
#                 return

#         try:
#             # ✅ TIMING COMPENSATION: Measure actual vs expected timing
#             capture_start_time = time.time()
#             expected_time = self.expected_frame_times[self.current_frame] if self.current_frame < len(self.expected_frame_times) else capture_start_time
#             frame_drift = capture_start_time - expected_time
#             self.cumulative_drift += frame_drift

#             # ✅ ADAPTIVE TIMING: Compensate for systematic drift
#             if self.current_frame > 10:  # After warmup period
#                 avg_drift_per_frame = self.cumulative_drift / self.current_frame
#                 if abs(avg_drift_per_frame) > 0.001:  # > 1ms systematic drift
#                     print(f"Compensating for systematic drift: {avg_drift_per_frame*1000:.1f}ms per frame")

#             python_timing = {
#                 'start_time': capture_start_time,
#                 'expected_time': expected_time,
#                 'frame_drift': frame_drift,
#                 'cumulative_drift': self.cumulative_drift
#             }

#             # ✅ HEALTH CHECK: Monitor system every 100 frames (8.3 minutes at 5s intervals)
#             if self.current_frame % 100 == 0 and self.current_frame > 0:
#                 if not self._system_health_check():
#                     self.error_occurred.emit("System health check failed - stopping recording for safety")
#                     return

#             # ✅ SOLUTION 1: Read sensors BEFORE LED activity to avoid interference
#             print("Reading sensors before LED activity...")
#             try:
#                 temp, humidity = self.esp32_controller.read_sensors()
#                 actual_led_power = self.esp32_controller.led_power
#                 print(f"Pre-LED sensors: T={temp:.1f}°C, H={humidity:.1f}%, LED={actual_led_power}%")

#                 # Validate sensor readings
#                 if temp < -10 or temp > 50 or humidity < 0 or humidity > 100:
#                     print(f"Warning: Sensor readings out of range - T={temp:.1f}°C, H={humidity:.1f}%")
#                     # Use reasonable defaults if readings are invalid
#                     temp = 25.0 if temp < -10 or temp > 50 else temp
#                     humidity = 50.0 if humidity < 0 or humidity > 100 else humidity

#             except Exception as sensor_e:
#                 print(f"Pre-LED sensor read failed: {sensor_e}")
#                 temp, humidity = 25.0, 50.0
#                 actual_led_power = self.esp32_controller.led_power

#             # ✅ LED/CAPTURE SEQUENCE (sensor data already obtained)
#             frame = None
#             frame_metadata = None

#             try:
#                 # Turn LED ON
#                 self.esp32_controller.led_on()
#                 print("LED turned ON")

#                 # LED stabilization time
#                 time.sleep(0.5)

#                 # ✅ MEMORY-SAFE CAPTURE: Ensure clean frame capture
#                 for attempt in range(2):  # Try twice for better reliability
#                     try:
#                         frame, frame_metadata = self._safe_capture_frame()
#                         if frame is not None:
#                             break  # Success
#                     except Exception as capture_e:
#                         print(f"Frame capture attempt {attempt + 1} failed: {capture_e}")
#                         if attempt == 1:  # Last attempt
#                             raise capture_e

#                     if attempt == 0:
#                         time.sleep(0.1)  # Wait between attempts

#                 print(f"Frame captured: {frame.shape if frame is not None else 'None'}")

#                 # Turn LED OFF
#                 self.esp32_controller.led_off()
#                 print("LED turned OFF")

#                 # ✅ SOLUTION 2: Optional post-LED sensor reading with delay (for comparison)
#                 try:
#                     print("Waiting for sensor stabilization after LED...")
#                     time.sleep(0.3)  # Wait for DHT22 to stabilize after LED interference

#                     temp_post, humidity_post = self.esp32_controller.read_sensors()
#                     print(f"Post-LED sensors: T={temp_post:.1f}°C, H={humidity_post:.1f}%")

#                     # Compare pre and post LED readings
#                     temp_diff = abs(temp - temp_post)
#                     humidity_diff = abs(humidity - humidity_post)

#                     if temp_diff > 5.0 or humidity_diff > 10.0:
#                         print(f"Warning: Large sensor difference detected - using pre-LED values")
#                         print(f"  Temperature diff: {temp_diff:.1f}°C")
#                         print(f"  Humidity diff: {humidity_diff:.1f}%")
#                         # Keep using pre-LED values (temp, humidity already set)
#                     else:
#                         # Post-LED readings are reasonable, average them
#                         temp = (temp + temp_post) / 2.0
#                         humidity = (humidity + humidity_post) / 2.0
#                         print(f"Using averaged sensor values: T={temp:.1f}°C, H={humidity:.1f}%")

#                 except Exception as post_sensor_e:
#                     print(f"Post-LED sensor read failed: {post_sensor_e}")
#                     print("Using pre-LED sensor values")
#                     # Continue with pre-LED values

#                 esp32_timing = {
#                     'esp32_time_start': capture_start_time,
#                     'esp32_time_end': time.time(),
#                     'led_duration_actual': 500,  # LED stabilization time
#                     'led_power_actual': actual_led_power,
#                     'temperature': temp,
#                     'humidity': humidity
#                 }

#             except Exception as e:
#                 print(f"LED sync failed: {e}")
#                 # Fallback: capture without LED
#                 try:
#                     frame, frame_metadata = self._safe_capture_frame()
#                 except Exception as fallback_e:
#                     print(f"Fallback capture also failed: {fallback_e}")
#                     raise RuntimeError(f"All capture methods failed: LED sync: {e}, Fallback: {fallback_e}")

#                 esp32_timing = {
#                     'esp32_time_start': capture_start_time,
#                     'esp32_time_end': capture_start_time,
#                     'led_duration_actual': 0,
#                     'led_power_actual': 0,
#                     'temperature': temp,  # Use pre-LED sensor values
#                     'humidity': humidity
#                 }

#             capture_end_time = time.time()
#             python_timing['end_time'] = capture_end_time

#             # ✅ MEMORY-SAFE SAVING: Ensure frame is saved and cleaned up
#             if frame is None:
#                 raise RuntimeError("Frame capture resulted in None - cannot save")

#             success = self.data_manager.save_frame(
#                 frame, frame_metadata, esp32_timing, python_timing
#             )

#             # ✅ EXPLICIT MEMORY CLEANUP: Prevent memory leaks
#             if success:
#                 # Clear frame references immediately after saving
#                 del frame, frame_metadata

#                 # Force garbage collection every 50 frames (4.2 minutes)
#                 if self.current_frame % 50 == 0:
#                     import gc
#                     collected = gc.collect()
#                     print(f"Frame {self.current_frame}: Garbage collected {collected} objects")

#                 with self._state_lock:
#                     self.current_frame += 1

#                 progress = int((self.current_frame / self.total_frames) * 100)
#                 self.progress_updated.emit(progress)
#                 self.frame_captured.emit(self.current_frame, self.total_frames)

#                 elapsed_time = capture_end_time - self.start_time
#                 estimated_total = (elapsed_time / self.current_frame) * self.total_frames if self.current_frame > 0 else 0
#                 remaining_time = max(0, estimated_total - elapsed_time)

#                 # ✅ ENHANCED STATUS: Include timing and memory info
#                 status_msg = f"Frame {self.current_frame}/{self.total_frames} - " \
#                             f"Elapsed: {elapsed_time:.1f}s - " \
#                             f"Remaining: {remaining_time:.1f}s - " \
#                             f"Drift: {self.cumulative_drift:.1f}s"
#                 self.status_updated.emit(status_msg)
#                 print(f"Frame {self.current_frame} saved successfully with clean sensor data")

#                 # ✅ CHECKPOINT SAVE: Every hour for data safety
#                 frames_per_hour = 3600 // self.interval_sec  # 720 frames at 5s intervals
#                 if self.current_frame % frames_per_hour == 0:
#                     hours_completed = self.current_frame // frames_per_hour
#                     print(f"=== CHECKPOINT: {hours_completed} hours completed ===")
#                     # Force HDF5 flush for data safety
#                     if hasattr(self.data_manager, 'hdf5_file') and self.data_manager.hdf5_file:
#                         self.data_manager.hdf5_file.flush()
#                         print("HDF5 file flushed to disk")

#             else:
#                 # Clean up even on failure
#                 if frame is not None:
#                     del frame
#                 if frame_metadata is not None:
#                     del frame_metadata

#                 self.error_occurred.emit(f"Failed to save frame {self.current_frame + 1}")
#                 print(f"Failed to save frame {self.current_frame + 1}")

#         except Exception as e:
#             # ✅ ENHANCED ERROR HANDLING: Clean up on any error
#             if 'frame' in locals() and frame is not None:
#                 del frame
#             if 'frame_metadata' in locals() and frame_metadata is not None:
#                 del frame_metadata

#             print(f"Frame capture error: {e}")
#             self.error_occurred.emit(f"Frame capture failed: {str(e)}")

#     def _system_health_check(self) -> bool:
#         """Check system health for long-term stability."""
#         try:
#             import psutil

#             # Check system memory
#             memory = psutil.virtual_memory()
#             if memory.percent > 85:
#                 print(f"WARNING: High system memory usage: {memory.percent:.1f}%")
#                 return False

#             # Check process memory
#             process = psutil.Process()
#             process_memory_mb = process.memory_info().rss / 1024 / 1024
#             if process_memory_mb > 3000:  # 3GB limit
#                 print(f"WARNING: High process memory usage: {process_memory_mb:.1f}MB")
#                 return False

#             # Check disk space
#             disk = psutil.disk_usage('.')
#             free_gb = disk.free / (1024**3)
#             if free_gb < 5:  # 5GB minimum
#                 print(f"WARNING: Low disk space: {free_gb:.1f}GB")
#                 return False

#             # Check ESP32 connection
#             if not self.esp32_controller.is_connected(force_check=True):
#                 print("WARNING: ESP32 connection lost")
#                 try:
#                     self.esp32_controller.connect()
#                     print("ESP32 reconnected successfully")
#                 except Exception as e:
#                     print(f"ESP32 reconnection failed: {e}")
#                     return False

#             # Health check passed
#             if self.current_frame % 500 == 0:  # Log every ~41 minutes
#                 print(f"Health check OK: Memory={memory.percent:.1f}%, "
#                       f"Process={process_memory_mb:.1f}MB, "
#                       f"Disk={free_gb:.1f}GB, "
#                       f"ESP32=Connected")

#             return True

#         except Exception as e:
#             print(f"Health check failed with error: {e}")
#             return False

#     def _finalize_recording(self):
#         """Finalize recording and cleanup."""
#         try:
#             print("Finalizing recording...")
#             if self.data_manager.is_file_open():
#                 self.data_manager.finalize_recording()
#                 print("Data manager finalized")
#             with self._state_lock:
#                 self.recording = False
#                 self.paused = False
#                 self.should_stop = False

#             if self.current_frame == self.total_frames:
#                 self.status_updated.emit(f"Recording completed: {self.current_frame} frames captured")
#                 print(f"Recording completed successfully: {self.current_frame} frames")
#             else:
#                 self.status_updated.emit(f"Recording stopped: {self.current_frame}/{self.total_frames} frames captured")
#                 print(f"Recording stopped early: {self.current_frame}/{self.total_frames} frames")
#         except Exception as e:
#             print(f"Finalization error: {e}")
#             self.error_occurred.emit(f"Error finalizing recording: {str(e)}")

#     def get_recording_status(self) -> dict:
#         """Get current recording status."""
#         with self._state_lock:
#             current_frame = self.current_frame
#             total_frames = self.total_frames
#             recording = self.recording
#             paused = self.paused
#             cumulative_drift = self.cumulative_drift
#         return {
#             'recording': recording,
#             'paused': paused,
#             'current_frame': current_frame,
#             'total_frames': total_frames,
#             'progress_percent': (current_frame / total_frames * 100) if total_frames > 0 else 0,
#             'elapsed_time': time.time() - self.start_time if self.start_time else 0,
#             'cumulative_drift': cumulative_drift,
#             'expected_duration': self.duration_min * 60,
#             'interval_seconds': self.interval_sec
#         }

#     def is_recording(self) -> bool:
#         """Check if currently recording."""
#         with self._state_lock:
#             return self.recording

#     def is_paused(self) -> bool:
#         """Check if recording is paused."""
#         with self._state_lock:
#             return self.paused
# """Main timelapse recorder orchestrating ESP32 and data storage with direct ImSwitch integration,
# enhanced with Day/Night phase support for circadian biology research."""
# import time
# import threading
# from typing import Tuple, Optional
# from qtpy.QtCore import QObject
# import numpy as np
# from threading import Lock

# # ✅ FIX: pyqtSignal Import with try/except
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal


# class TimelapseRecorder(QObject):
#     """Phase-aware timelapse recording controller with ImSwitch integration and Napari fallback."""

#     # Signals
#     frame_captured = pyqtSignal(int, int)  # current_frame, total_frames
#     recording_started = pyqtSignal()
#     recording_finished = pyqtSignal()
#     recording_paused = pyqtSignal()
#     recording_resumed = pyqtSignal()
#     progress_updated = pyqtSignal(int)  # percentage
#     status_updated = pyqtSignal(str)  # status message
#     error_occurred = pyqtSignal(str)  # recording-related errors only
#     phase_changed = pyqtSignal(dict)  # phase_info dict

#     def __init__(self, duration_min: int, interval_sec: int, output_dir: str,
#                  esp32_controller, data_manager, imswitch_main, camera_name: str,
#                  phase_config: dict = None):
#         super().__init__()

#         # Recording parameters
#         self.duration_min = duration_min
#         self.interval_sec = interval_sec
#         self.output_dir = output_dir

#         # Controllers
#         self.esp32_controller = esp32_controller
#         self.data_manager = data_manager
#         self.imswitch_main = imswitch_main
#         self.camera_name = camera_name

#         # ✅ FIX: Proper phase configuration handling
#         self.phase_config = phase_config or {
#             'enabled': False,
#             'light_duration_min': 30,
#             'dark_duration_min': 30,
#             'start_with_light': True
#         }

#         # ✅ NEW: Phase tracking variables
#         self.current_phase = None
#         self.last_phase = None
#         self.phase_start_time = None
#         self.current_cycle = 1

#         # (Optional) Napari viewer; assigned externally (widget does this)
#         self.viewer = None

#         # State variables
#         self.recording = False
#         self.paused = False
#         self.should_stop = False
#         self.current_frame = 0
#         self.total_frames = self._calculate_total_frames()
#         self.start_time = None
#         self.expected_frame_times = []
#         self.cumulative_drift = 0.0

#         # Validation bypass flag (for debugging)
#         self.skip_validation = True

#         # Lock for shared state
#         self._state_lock = Lock()

#         # Recording thread
#         self.recording_thread = None

#         # Initialize phase on creation
#         if self.phase_config['enabled']:
#             print(f"Phase-aware recording initialized: "
#                   f"Light={self.phase_config['light_duration_min']}min, "
#                   f"Dark={self.phase_config['dark_duration_min']}min, "
#                   f"Start={'Light' if self.phase_config['start_with_light'] else 'Dark'}")
#         else:
#             print("Continuous recording mode (no phase cycling)")

#     def _calculate_total_frames(self) -> int:
#         """Calculate total number of frames to capture."""
#         total_seconds = self.duration_min * 60
#         return int(total_seconds / self.interval_sec)

#     # ========================================================================
#     # ✅ NEW: PHASE CALCULATION AND MANAGEMENT
#     # ========================================================================

#     def _get_current_phase_info(self, elapsed_minutes: float) -> dict:
#         """Calculate current phase information based on elapsed time."""
#         if not self.phase_config['enabled']:
#             return {
#                 'phase': 'continuous',
#                 'led_type': 'ir',  # Default to IR for backward compatibility
#                 'phase_elapsed_min': elapsed_minutes,
#                 'phase_remaining_min': 0,
#                 'cycle_number': 1,
#                 'total_cycles': 1,
#                 'phase_transition': False
#             }

#         light_duration = self.phase_config['light_duration_min']
#         dark_duration = self.phase_config['dark_duration_min']
#         cycle_duration = light_duration + dark_duration

#         # Determine starting phase
#         starts_with_light = self.phase_config['start_with_light']

#         # Calculate position in cycles
#         cycle_position = elapsed_minutes % cycle_duration
#         current_cycle = int(elapsed_minutes / cycle_duration) + 1
#         total_duration = self.duration_min
#         total_cycles = max(1, int(total_duration / cycle_duration))

#         # Determine current phase
#         if starts_with_light:
#             if cycle_position < light_duration:
#                 phase = 'light'
#                 led_type = 'white'
#                 phase_elapsed = cycle_position
#                 phase_remaining = light_duration - cycle_position
#             else:
#                 phase = 'dark'
#                 led_type = 'ir'
#                 phase_elapsed = cycle_position - light_duration
#                 phase_remaining = cycle_duration - cycle_position
#         else:
#             if cycle_position < dark_duration:
#                 phase = 'dark'
#                 led_type = 'ir'
#                 phase_elapsed = cycle_position
#                 phase_remaining = dark_duration - cycle_position
#             else:
#                 phase = 'light'
#                 led_type = 'white'
#                 phase_elapsed = cycle_position - dark_duration
#                 phase_remaining = cycle_duration - cycle_position

#         # Detect phase transitions
#         phase_transition = (self.last_phase is not None and
#                           self.last_phase != phase)

#         return {
#             'phase': phase,
#             'led_type': led_type,
#             'phase_elapsed_min': phase_elapsed,
#             'phase_remaining_min': phase_remaining,
#             'cycle_number': current_cycle,
#             'total_cycles': total_cycles,
#             'phase_transition': phase_transition,
#             'cycle_duration_min': cycle_duration
#         }

#     def _handle_phase_change(self, phase_info: dict):
#         """Handle phase transition logic."""
#         if phase_info['phase_transition']:
#             old_phase = self.last_phase
#             new_phase = phase_info['phase']
#             cycle_num = phase_info['cycle_number']

#             print(f"=== PHASE TRANSITION ===")
#             print(f"Phase changed: {old_phase} -> {new_phase} (cycle {cycle_num})")
#             print(f"LED switching: {self.esp32_controller.current_led_type} -> {phase_info['led_type']}")

#             # Switch LED type on ESP32
#             try:
#                 self.esp32_controller.select_led_type(phase_info['led_type'])
#                 print(f"ESP32 LED switched to {phase_info['led_type'].upper()}")
#             except Exception as e:
#                 print(f"Failed to switch ESP32 LED: {e}")
#                 # Continue anyway - capture will still work with wrong LED

#             # Update tracking variables
#             self.current_cycle = cycle_num
#             self.phase_start_time = time.time()

#             # Emit signal for UI updates
#             self.phase_changed.emit(phase_info)

#             print(f"=== PHASE TRANSITION COMPLETE ===")

#     # ========================================================================
#     # RECORDING CONTROL METHODS
#     # ========================================================================

#     def start(self):
#         """Start phase-aware timelapse recording."""
#         with self._state_lock:
#             if self.recording:
#                 self.error_occurred.emit("Recording already in progress")
#                 return

#         try:
#             if not self.skip_validation:
#                 if not self._validate_setup():
#                     return

#             self._initialize_recording()
#             self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
#             self.recording_thread.start()
#             self.recording_started.emit()

#             if self.phase_config['enabled']:
#                 start_phase = "Light" if self.phase_config['start_with_light'] else "Dark"
#                 self.status_updated.emit(f"Phase-aware recording started (starting with {start_phase})")
#             else:
#                 self.status_updated.emit("Continuous recording started")
#         except Exception as e:
#             self.error_occurred.emit(f"Failed to start recording: {str(e)}")

#     def stop(self):
#         """Stop timelapse recording."""
#         with self._state_lock:
#             if not self.recording:
#                 return
#             self.should_stop = True

#         if self.recording_thread and self.recording_thread.is_alive():
#             self.recording_thread.join(timeout=5.0)

#         self._finalize_recording()
#         self.status_updated.emit("Recording stopped")

#     def pause(self):
#         """Pause recording."""
#         with self._state_lock:
#             if not self.recording or self.paused:
#                 return
#             self.paused = True

#         self.recording_paused.emit()
#         self.status_updated.emit("Recording paused")

#     def resume(self):
#         """Resume recording."""
#         with self._state_lock:
#             if not self.recording or not self.paused:
#                 return
#             self.paused = False

#         self.recording_resumed.emit()
#         self.status_updated.emit("Recording resumed")

#     def probe_frame(self) -> bool:
#         """Lightweight probe to verify frame capture works."""
#         try:
#             frame, metadata = self._safe_capture_frame()
#             print(f"Probe: got frame {frame.shape} from {metadata.get('source')}")
#             return True
#         except Exception as e:
#             print(f"Probe failed: {e}")
#             return False

#     # ========================================================================
#     # FRAME CAPTURE METHODS
#     # ========================================================================

#     def _capture_frame_from_napari_layer(self) -> Tuple[np.ndarray, dict]:
#         """Preferentially grab the latest frame from a live Napari image layer."""
#         if self.viewer is None:
#             raise RuntimeError("No Napari viewer assigned for Napari-layer capture")
#         try:
#             from napari.layers import Image
#         except ImportError:
#             raise RuntimeError("Napari not available for layer fallback")

#         # First try to prefer layers with name hints
#         preferred_keywords = ('live', 'widefield', 'imswitch')
#         for layer in self.viewer.layers:
#             if not isinstance(layer, Image):
#                 continue
#             name = getattr(layer, 'name', '').lower()
#             if any(k in name for k in preferred_keywords):
#                 data = getattr(layer, 'data', None)
#                 if data is None:
#                     continue
#                 if hasattr(data, 'size') and data.size == 0:
#                     continue
#                 frame = np.array(data, copy=True)
#                 metadata = {
#                     "timestamp": time.time(),
#                     "camera_name": getattr(self, 'camera_name', 'unknown'),
#                     "frame_shape": frame.shape,
#                     "frame_dtype": str(frame.dtype),
#                     "source": f"napari_layer:{layer.name}",
#                     "fallback": True,
#                     "preferred_layer": True
#                 }
#                 return frame, metadata

#         # Fallback to any non-empty image layer
#         for layer in self.viewer.layers:
#             if not isinstance(layer, Image):
#                 continue
#             data = getattr(layer, 'data', None)
#             if data is None:
#                 continue
#             if hasattr(data, 'size') and data.size == 0:
#                 continue
#             frame = np.array(data, copy=True)
#             metadata = {
#                 "timestamp": time.time(),
#                 "camera_name": getattr(self, 'camera_name', 'unknown'),
#                 "frame_shape": frame.shape,
#                 "frame_dtype": str(frame.dtype),
#                 "source": f"napari_layer:{layer.name}",
#                 "fallback": True
#             }
#             return frame, metadata

#         raise RuntimeError("No suitable Napari image layer found for fallback frame")

#     def _capture_frame_from_imswitch_direct(self) -> Tuple[np.ndarray, dict]:
#         """Attempt to capture frame directly from ImSwitch structures."""
#         if self.imswitch_main is None:
#             raise RuntimeError("ImSwitch not available for direct capture")

#         # Try liveViewWidget
#         try:
#             if hasattr(self.imswitch_main, 'liveViewWidget'):
#                 live_view = self.imswitch_main.liveViewWidget
#                 if hasattr(live_view, 'img') and live_view.img is not None:
#                     frame = live_view.img.copy()
#                     metadata = {
#                         "timestamp": time.time(),
#                         "camera_name": self.camera_name,
#                         "frame_shape": frame.shape,
#                         "frame_dtype": str(frame.dtype),
#                         "imswitch_managed": True,
#                         "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                         "source": "live_view_widget"
#                     }
#                     return frame, metadata
#         except Exception:
#             pass

#         # Try viewWidget
#         try:
#             if hasattr(self.imswitch_main, 'viewWidget'):
#                 view_widget = self.imswitch_main.viewWidget
#                 if hasattr(view_widget, 'getCurrentImage'):
#                     frame = view_widget.getCurrentImage()
#                     if frame is not None:
#                         metadata = {
#                             "timestamp": time.time(),
#                             "camera_name": self.camera_name,
#                             "frame_shape": frame.shape,
#                             "frame_dtype": str(frame.dtype),
#                             "imswitch_managed": True,
#                             "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                             "source": "view_widget"
#                         }
#                         return frame, metadata
#         except Exception:
#             pass

#         # Try imageWidget
#         try:
#             if hasattr(self.imswitch_main, 'imageWidget'):
#                 image_widget = self.imswitch_main.imageWidget
#                 if hasattr(image_widget, 'image') and image_widget.image is not None:
#                     frame = image_widget.image.copy()
#                     metadata = {
#                         "timestamp": time.time(),
#                         "camera_name": self.camera_name,
#                         "frame_shape": frame.shape,
#                         "frame_dtype": str(frame.dtype),
#                         "imswitch_managed": True,
#                         "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                         "source": "image_widget"
#                     }
#                     return frame, metadata
#         except Exception:
#             pass

#         # Try detectorsManager methods
#         if hasattr(self.imswitch_main, 'detectorsManager'):
#             detectors_manager = self.imswitch_main.detectorsManager
#             methods_to_try = [
#                 ('getLatestFrame', True),
#                 ('getLatestFrame', False),
#                 ('getLastImage', True),
#                 ('getLastImage', False),
#                 ('snap', True),
#                 ('snap', False),
#                 ('getImage', True),
#                 ('getImage', False),
#                 ('captureFrame', True),
#                 ('captureFrame', False)
#             ]
#             for method_name, use_camera_name in methods_to_try:
#                 if not hasattr(detectors_manager, method_name):
#                     continue
#                 try:
#                     method = getattr(detectors_manager, method_name)
#                     if use_camera_name:
#                         frame = method(self.camera_name)
#                     else:
#                         frame = method()
#                     if frame is not None:
#                         metadata = {
#                             "timestamp": time.time(),
#                             "camera_name": self.camera_name,
#                             "frame_shape": frame.shape,
#                             "frame_dtype": str(frame.dtype),
#                             "imswitch_managed": True,
#                             "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
#                             "source": f"detector_manager_{method_name}"
#                         }
#                         return frame, metadata
#                 except Exception:
#                     continue

#         raise RuntimeError("Could not capture frame from any ImSwitch method")

#     def _safe_capture_frame(self) -> Tuple[np.ndarray, dict]:
#         """Unified capture: ImSwitch FIRST (fresh frame), Napari only as fallback."""

#         # ✅ CHANGE: Try ImSwitch FIRST for fresh frames
#         if self.imswitch_main is not None:
#             try:
#                 return self._capture_frame_from_imswitch_direct()
#             except Exception as e:
#                 print(f"ImSwitch direct capture failed: {e}, trying Napari...")

#         # ✅ ADD: Force Napari refresh before capture
#         if self.viewer is not None:
#             try:
#                 # Force layer refresh
#                 self.viewer.layers.events.changed()
#                 time.sleep(0.05)  # Small delay for refresh

#                 frame, metadata = self._capture_frame_from_napari_layer()
#                 return frame, metadata
#             except Exception as e:
#                 print(f"Napari capture also failed: {e}")

#         raise RuntimeError("All frame capture methods failed")

#     # ========================================================================
#     # VALIDATION / INITIALIZATION / LOOP
#     # ========================================================================

#     def _validate_setup(self) -> bool:
#         """Validate setup before starting recording."""
#         if self.imswitch_main is None and self.viewer is None:
#             self.error_occurred.emit("No ImSwitch controller and no Napari viewer for frame capture")
#             return False

#         # Probe capture path
#         try:
#             frame, metadata = self._safe_capture_frame()
#             if frame is None:
#                 self.error_occurred.emit("Frame capture test returned None")
#                 return False
#             print(f"Validation: Frame capture successful - {frame.shape} from {metadata.get('source')}")

#         except Exception as e:
#             self.error_occurred.emit(f"Frame capture test failed: {str(e)}")
#             return False

#         # ESP32 connection
#         if not self.esp32_controller.is_connected():
#             try:
#                 self.esp32_controller.connect()
#                 print("ESP32 connected during validation")
#             except Exception as e:
#                 self.error_occurred.emit(f"ESP32 connection failed: {str(e)}")
#                 return False

#         # ✅ NEW: Validate phase configuration and LED setup
#         if self.phase_config['enabled']:
#             try:
#                 # Test LED switching capabilities
#                 original_led = self.esp32_controller.current_led_type

#                 # Test IR LED
#                 self.esp32_controller.select_led_type('ir')
#                 time.sleep(0.1)

#                 # Test White LED
#                 self.esp32_controller.select_led_type('white')
#                 time.sleep(0.1)

#                 # Restore original
#                 self.esp32_controller.select_led_type(original_led)

#                 print("Phase validation: LED switching test passed")
#             except Exception as e:
#                 self.error_occurred.emit(f"LED switching test failed: {str(e)}")
#                 return False

#         return True

#     def _initialize_recording(self):
#         """Initialize recording session with phase support."""
#         with self._state_lock:
#             self.recording = True
#             self.paused = False
#             self.should_stop = False
#             self.current_frame = 0
#         self.start_time = time.time()
#         self.cumulative_drift = 0.0

#         # ✅ NEW: Initialize phase tracking
#         if self.phase_config['enabled']:
#             # Set initial LED type
#             initial_led = 'white' if self.phase_config['start_with_light'] else 'ir'
#             try:
#                 self.esp32_controller.select_led_type(initial_led)
#                 print(f"Initial LED set to: {initial_led.upper()}")
#             except Exception as e:
#                 print(f"Failed to set initial LED: {e}")

#             self.current_phase = 'light' if self.phase_config['start_with_light'] else 'dark'
#             self.last_phase = None
#             self.phase_start_time = self.start_time
#             self.current_cycle = 1

#         # Calculate expected frame times
#         self.expected_frame_times = [
#             self.start_time + (i * self.interval_sec) for i in range(self.total_frames)
#         ]

#         phase_info = "with phase cycling" if self.phase_config['enabled'] else "continuous"
#         print(f"Recording initialized: {self.total_frames} frames over {self.duration_min} minutes {phase_info}")

#         # Create HDF5 file with phase metadata
#         try:
#             filepath = self.data_manager.create_recording_file(
#                 self.output_dir,
#                 experiment_name="nematostella_timelapse",
#                 timestamped=True
#             )
#             recording_metadata = {
#                 'duration_minutes': self.duration_min,
#                 'interval_seconds': self.interval_sec,
#                 'expected_frames': self.total_frames,
#                 'led_power': self.esp32_controller.led_power,
#                 'camera_name': self.camera_name,
#                 'imswitch_managed': True,
#                 'esp32_settings': self.esp32_controller.get_status() if self.esp32_controller.is_connected() else {},
#                 # ✅ NEW: Phase metadata
#                 'phase_config': self.phase_config,
#                 'phase_enabled': self.phase_config['enabled'],
#                 'light_duration_min': self.phase_config.get('light_duration_min', 0),
#                 'dark_duration_min': self.phase_config.get('dark_duration_min', 0),
#                 'starts_with_light': self.phase_config.get('start_with_light', True)
#             }
#             self.data_manager.update_recording_metadata(recording_metadata)
#             print(f"Recording file created: {filepath}")
#         except Exception as e:
#             with self._state_lock:
#                 self.recording = False
#             raise RuntimeError(f"Failed to initialize data storage: {str(e)}")

#     def _recording_loop(self):
#         """Main recording loop with phase awareness."""
#         try:
#             print("Phase-aware recording loop started")
#             self._capture_frame_sync()

#             while True:
#                 with self._state_lock:
#                     if self.should_stop or self.current_frame >= self.total_frames:
#                         break
#                     if self.paused:
#                         pass

#                 if self.paused:
#                     time.sleep(0.1)
#                     continue

#                 now = time.time()
#                 expected_time = self.expected_frame_times[self.current_frame]
#                 if now < expected_time:
#                     time.sleep(min(0.1, expected_time - now))
#                     continue

#                 self._capture_frame_sync()

#             with self._state_lock:
#                 completed = not self.should_stop and self.current_frame >= self.total_frames

#             if completed:
#                 self._finalize_recording()
#                 self.recording_finished.emit()
#                 print("Phase-aware recording completed successfully")
#         except Exception as e:
#             print(f"Recording loop error: {e}")
#             self.error_occurred.emit(f"Recording error: {str(e)}")
#             self._finalize_recording()

#     def _capture_frame_sync(self):
#         """Capture frame with phase-aware synchronization."""
#         with self._state_lock:
#             if self.current_frame >= self.total_frames:
#                 return

#         try:
#             # ✅ PHASE MANAGEMENT: Calculate current phase
#             capture_start_time = time.time()
#             elapsed_minutes = (capture_start_time - self.start_time) / 60.0
#             phase_info = self._get_current_phase_info(elapsed_minutes)

#             # ✅ PHASE TRANSITION: Handle phase changes
#             if phase_info['phase'] != self.last_phase:
#                 self._handle_phase_change(phase_info)
#                 self.last_phase = phase_info['phase']

#             # Timing compensation
#             expected_time = self.expected_frame_times[self.current_frame] if self.current_frame < len(self.expected_frame_times) else capture_start_time
#             frame_drift = capture_start_time - expected_time
#             self.cumulative_drift += frame_drift

#             # Adaptive timing compensation
#             if self.current_frame > 10:
#                 avg_drift_per_frame = self.cumulative_drift / self.current_frame
#                 if abs(avg_drift_per_frame) > 0.001:
#                     print(f"Compensating for systematic drift: {avg_drift_per_frame*1000:.1f}ms per frame")

#             python_timing = {
#                 'start_time': capture_start_time,
#                 'expected_time': expected_time,
#                 'frame_drift': frame_drift,
#                 'cumulative_drift': self.cumulative_drift
#             }

#             # Health check every 100 frames
#             if self.current_frame % 100 == 0 and self.current_frame > 0:
#                 if not self._system_health_check():
#                     self.error_occurred.emit("System health check failed - stopping recording for safety")
#                     return

#             # ✅ PHASE-AWARE LED CONTROL: Use appropriate LED for current phase
#             led_type = phase_info.get('led_type', 'ir')

#             # Pre-capture sensor reading
#             print(f"Reading sensors before LED activity (Phase: {phase_info['phase'].upper()}, LED: {led_type.upper()})...")
#             try:
#                 temp, humidity = self.esp32_controller.read_sensors()
#                 actual_led_power = self.esp32_controller.led_power
#                 print(f"Pre-LED sensors: T={temp:.1f}°C, H={humidity:.1f}%, LED={actual_led_power}%")

#                 # Validate sensor readings
#                 if temp < -10 or temp > 50 or humidity < 0 or humidity > 100:
#                     print(f"Warning: Sensor readings out of range - T={temp:.1f}°C, H={humidity:.1f}%")
#                     temp = 25.0 if temp < -10 or temp > 50 else temp
#                     humidity = 50.0 if humidity < 0 or humidity > 100 else humidity

#             except Exception as sensor_e:
#                 print(f"Pre-LED sensor read failed: {sensor_e}")
#                 temp, humidity = 25.0, 50.0
#                 actual_led_power = self.esp32_controller.led_power

#             # ✅ PHASE-AWARE CAPTURE: Use ESP32 phase-aware synchronization
#             frame = None
#             frame_metadata = None
#             esp32_timing = None

#             try:
#                 if self.phase_config['enabled']:
#                     # Use phase-aware synchronization
#                     esp32_timing = self.esp32_controller.synchronize_capture_with_led(
#                         led_type=led_type,
#                         led_duration_ms=500
#                     )
#                     print(f"Phase-aware sync capture completed with {led_type.upper()} LED")
#                 else:
#                     # Use standard synchronization (backward compatibility)
#                     esp32_timing = self.esp32_controller.synchronize_capture()
#                     print("Standard sync capture completed")

#                 # Capture frame during LED illumination
#                 frame, frame_metadata = self._safe_capture_frame()
#                 print(f"Frame captured: {frame.shape if frame is not None else 'None'}")

#             except Exception as sync_e:
#                 print(f"LED sync failed: {sync_e}")
#                 # Fallback: capture without LED synchronization
#                 try:
#                     frame, frame_metadata = self._safe_capture_frame()
#                     # Create fallback timing info
#                     esp32_timing = {
#                         'esp32_time_start': capture_start_time,
#                         'esp32_time_end': time.time(),
#                         'led_duration_actual': 0,
#                         'led_power_actual': 0,
#                         'temperature': temp,
#                         'humidity': humidity,
#                         'led_type_used': led_type,
#                         'phase_aware_capture': False,
#                         'sync_failed': True
#                     }
#                 except Exception as fallback_e:
#                     print(f"Fallback capture also failed: {fallback_e}")
#                     raise RuntimeError(f"All capture methods failed: LED sync: {sync_e}, Fallback: {fallback_e}")

#             capture_end_time = time.time()
#             python_timing['end_time'] = capture_end_time

#             # Memory-safe saving with phase metadata
#             if frame is None:
#                 raise RuntimeError("Frame capture resulted in None - cannot save")

#             # ✅ ENHANCED METADATA: Add phase information to frame metadata
#             if frame_metadata is None:
#                 frame_metadata = {}

#             frame_metadata.update({
#                 'current_phase': phase_info['phase'],
#                 'led_type_used': led_type,
#                 'phase_elapsed_min': phase_info.get('phase_elapsed_min', 0),
#                 'phase_remaining_min': phase_info.get('phase_remaining_min', 0),
#                 'cycle_number': phase_info.get('cycle_number', 1),
#                 'total_cycles': phase_info.get('total_cycles', 1),
#                 'phase_transition': phase_info.get('phase_transition', False),
#                 'phase_enabled': self.phase_config['enabled']
#             })

#             success = self.data_manager.save_frame(
#                 frame, frame_metadata, esp32_timing, python_timing
#             )

#             # Explicit memory cleanup
#             if success:
#                 del frame, frame_metadata

#                 # Garbage collection every 50 frames
#                 if self.current_frame % 50 == 0:
#                     import gc
#                     collected = gc.collect()
#                     print(f"Frame {self.current_frame}: Garbage collected {collected} objects")

#                 with self._state_lock:
#                     self.current_frame += 1

#                 progress = int((self.current_frame / self.total_frames) * 100)
#                 self.progress_updated.emit(progress)
#                 self.frame_captured.emit(self.current_frame, self.total_frames)

#                 elapsed_time = capture_end_time - self.start_time
#                 estimated_total = (elapsed_time / self.current_frame) * self.total_frames if self.current_frame > 0 else 0
#                 remaining_time = max(0, estimated_total - elapsed_time)

#                 # ✅ ENHANCED STATUS: Include phase and timing info
#                 phase_text = f"Phase: {phase_info['phase'].upper()}" if self.phase_config['enabled'] else "Continuous"
#                 status_msg = f"Frame {self.current_frame}/{self.total_frames} - " \
#                             f"{phase_text} - " \
#                             f"Elapsed: {elapsed_time:.1f}s - " \
#                             f"Remaining: {remaining_time:.1f}s"
#                 self.status_updated.emit(status_msg)
#                 print(f"Frame {self.current_frame} saved successfully with phase data: {phase_info['phase']}")

#                 # Checkpoint save every hour
#                 frames_per_hour = 3600 // self.interval_sec
#                 if self.current_frame % frames_per_hour == 0:
#                     hours_completed = self.current_frame // frames_per_hour
#                     current_phase = phase_info['phase'].upper() if self.phase_config['enabled'] else "CONTINUOUS"
#                     print(f"=== CHECKPOINT: {hours_completed} hours completed - Current phase: {current_phase} ===")
#                     if hasattr(self.data_manager, 'hdf5_file') and self.data_manager.hdf5_file:
#                         self.data_manager.hdf5_file.flush()
#                         print("HDF5 file flushed to disk")

#             else:
#                 # Clean up on failure
#                 if frame is not None:
#                     del frame
#                 if frame_metadata is not None:
#                     del frame_metadata

#                 self.error_occurred.emit(f"Failed to save frame {self.current_frame + 1}")
#                 print(f"Failed to save frame {self.current_frame + 1}")

#         except Exception as e:
#             # Enhanced error handling with cleanup
#             if 'frame' in locals() and frame is not None:
#                 del frame
#             if 'frame_metadata' in locals() and frame_metadata is not None:
#                 del frame_metadata

#             print(f"Frame capture error: {e}")
#             self.error_occurred.emit(f"Frame capture failed: {str(e)}")

#     def _system_health_check(self) -> bool:
#         """Check system health for long-term stability."""
#         try:
#             import psutil

#             # Check system memory
#             memory = psutil.virtual_memory()
#             if memory.percent > 85:
#                 print(f"WARNING: High system memory usage: {memory.percent:.1f}%")
#                 return False

#             # Check process memory
#             process = psutil.Process()
#             process_memory_mb = process.memory_info().rss / 1024 / 1024
#             if process_memory_mb > 3000:  # 3GB limit
#                 print(f"WARNING: High process memory usage: {process_memory_mb:.1f}MB")
#                 return False

#             # Check disk space
#             disk = psutil.disk_usage('.')
#             free_gb = disk.free / (1024**3)
#             if free_gb < 5:  # 5GB minimum
#                 print(f"WARNING: Low disk space: {free_gb:.1f}GB")
#                 return False

#             # Check ESP32 connection
#             if not self.esp32_controller.is_connected(force_check=True):
#                 print("WARNING: ESP32 connection lost")
#                 try:
#                     self.esp32_controller.connect()
#                     print("ESP32 reconnected successfully")
#                     # ✅ PHASE RECOVERY: Restore LED state after reconnection
#                     if self.phase_config['enabled'] and hasattr(self, 'current_phase'):
#                         led_type = 'white' if self.current_phase == 'light' else 'ir'
#                         self.esp32_controller.select_led_type(led_type)
#                         print(f"LED state restored to {led_type.upper()} after reconnection")
#                 except Exception as e:
#                     print(f"ESP32 reconnection failed: {e}")
#                     return False

#             # Health check passed
#             if self.current_frame % 500 == 0:  # Log every ~41 minutes
#                 current_phase = getattr(self, 'current_phase', 'continuous').upper()
#                 print(f"Health check OK: Memory={memory.percent:.1f}%, "
#                       f"Process={process_memory_mb:.1f}MB, "
#                       f"Disk={free_gb:.1f}GB, "
#                       f"ESP32=Connected, "
#                       f"Phase={current_phase}")

#             return True

#         except Exception as e:
#             print(f"Health check failed with error: {e}")
#             return False

#     def _finalize_recording(self):
#         """Finalize recording and cleanup."""
#         try:
#             print("Finalizing phase-aware recording...")
#             if self.data_manager.is_file_open():
#                 self.data_manager.finalize_recording()
#                 print("Data manager finalized")
#             with self._state_lock:
#                 self.recording = False
#                 self.paused = False
#                 self.should_stop = False

#             # ✅ LED CLEANUP: Turn off all LEDs
#             try:
#                 if self.esp32_controller.is_connected():
#                     self.esp32_controller.turn_off_all_leds()
#                     print("All LEDs turned off")
#             except Exception as led_e:
#                 print(f"Failed to turn off LEDs: {led_e}")

#             if self.current_frame == self.total_frames:
#                 phase_text = "with phase cycling" if self.phase_config['enabled'] else "continuous"
#                 self.status_updated.emit(f"Recording completed: {self.current_frame} frames captured ({phase_text})")
#                 print(f"Recording completed successfully: {self.current_frame} frames ({phase_text})")
#             else:
#                 self.status_updated.emit(f"Recording stopped: {self.current_frame}/{self.total_frames} frames captured")
#                 print(f"Recording stopped early: {self.current_frame}/{self.total_frames} frames")
#         except Exception as e:
#             print(f"Finalization error: {e}")
#             self.error_occurred.emit(f"Error finalizing recording: {str(e)}")

#     def get_recording_status(self) -> dict:
#         """Get current recording status with phase information."""
#         with self._state_lock:
#             current_frame = self.current_frame
#             total_frames = self.total_frames
#             recording = self.recording
#             paused = self.paused
#             cumulative_drift = self.cumulative_drift

#         # ✅ PHASE STATUS: Add current phase info
#         phase_status = {}
#         if self.phase_config['enabled'] and recording and self.start_time:
#             elapsed_min = (time.time() - self.start_time) / 60.0
#             phase_info = self._get_current_phase_info(elapsed_min)
#             phase_status = {
#                 'current_phase': phase_info.get('phase', 'unknown'),
#                 'led_type': phase_info.get('led_type', 'ir'),
#                 'cycle_number': phase_info.get('cycle_number', 1),
#                 'total_cycles': phase_info.get('total_cycles', 1),
#                 'phase_remaining_min': phase_info.get('phase_remaining_min', 0)
#             }

#         status = {
#             'recording': recording,
#             'paused': paused,
#             'current_frame': current_frame,
#             'total_frames': total_frames,
#             'progress_percent': (current_frame / total_frames * 100) if total_frames > 0 else 0,
#             'elapsed_time': time.time() - self.start_time if self.start_time else 0,
#             'cumulative_drift': cumulative_drift,
#             'expected_duration': self.duration_min * 60,
#             'interval_seconds': self.interval_sec,
#             'phase_enabled': self.phase_config['enabled'],
#             **phase_status
#         }

#         return status

#     def is_recording(self) -> bool:
#         """Check if currently recording."""
#         with self._state_lock:
#             return self.recording

#     def is_paused(self) -> bool:
#         """Check if recording is paused."""
#         with self._state_lock:
#             return self.paused
"""Main timelapse recorder orchestrating ESP32 and data storage with direct ImSwitch integration,
enhanced with Day/Night phase support and memory optimization for 72-hour recordings."""
import time
import threading
from typing import Tuple, Optional
from qtpy.QtCore import QObject
import numpy as np
from threading import Lock

# ✅ FIX: pyqtSignal Import with try/except
try:
    from qtpy.QtCore import pyqtSignal
except ImportError:
    from qtpy.QtCore import Signal as pyqtSignal


class TimelapseRecorder(QObject):
    """Phase-aware timelapse recording controller with ImSwitch integration and memory optimization."""

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

    def __init__(
        self,
        duration_min: int,
        interval_sec: int,
        output_dir: str,
        esp32_controller,
        data_manager,
        imswitch_main,
        camera_name: str,
        phase_config: dict = None,
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

        # ✅ FIX: Proper phase configuration handling
        self.phase_config = phase_config or {
            "enabled": False,
            "light_duration_min": 30,
            "dark_duration_min": 30,
            "start_with_light": True,
        }

        # ✅ NEW: Phase tracking variables
        self.current_phase = None
        self.last_phase = None
        self.phase_start_time = None
        self.current_cycle = 1

        # (Optional) Napari viewer; assigned externally (widget does this)
        self.viewer = None

        # State variables
        self.recording = False
        self.paused = False
        self.should_stop = False
        self.current_frame = 0
        self.total_frames = self._calculate_total_frames()
        self.start_time = None
        self.expected_frame_times = []
        self.cumulative_drift = 0.0

        # Validation bypass flag (for debugging)
        self.skip_validation = True

        # ✅ MEMORY: Memory tracking variables
        self.last_memory_check = 0.0

        # Lock for shared state
        self._state_lock = Lock()

        # Recording thread
        self.recording_thread = None

        # Initialize phase on creation
        if self.phase_config["enabled"]:
            print(
                f"Phase-aware recording initialized: "
                f"Light={self.phase_config['light_duration_min']}min, "
                f"Dark={self.phase_config['dark_duration_min']}min, "
                f"Start={'Light' if self.phase_config['start_with_light'] else 'Dark'}"
            )
        else:
            print("Continuous recording mode (no phase cycling)")

    def _calculate_total_frames(self) -> int:
        """Calculate total number of frames to capture."""
        total_seconds = self.duration_min * 60
        return int(total_seconds / self.interval_sec)

    # ========================================================================
    # ✅ NEW: PHASE CALCULATION AND MANAGEMENT
    # ========================================================================

    def _get_current_phase_info(self, elapsed_minutes: float) -> dict:
        """Calculate current phase information based on elapsed time."""
        if not self.phase_config["enabled"]:
            return {
                "phase": "continuous",
                "led_type": "ir",  # Default to IR for backward compatibility
                "phase_elapsed_min": elapsed_minutes,
                "phase_remaining_min": 0,
                "cycle_number": 1,
                "total_cycles": 1,
                "phase_transition": False,
            }

        light_duration = self.phase_config["light_duration_min"]
        dark_duration = self.phase_config["dark_duration_min"]
        cycle_duration = light_duration + dark_duration

        # Determine starting phase
        starts_with_light = self.phase_config["start_with_light"]

        # Calculate position in cycles
        cycle_position = elapsed_minutes % cycle_duration
        current_cycle = int(elapsed_minutes / cycle_duration) + 1
        total_duration = self.duration_min
        total_cycles = max(1, int(total_duration / cycle_duration))

        # Determine current phase
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

        # Detect phase transitions
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
        """Handle phase transition with calibration verification - whitelight_power version."""
        if phase_info["phase_transition"]:
            old_phase = self.last_phase
            new_phase = phase_info["phase"]
            led_type = phase_info["led_type"]
            cycle_num = phase_info["cycle_number"]

            print(f"=== PHASE TRANSITION ===")
            print(f"Phase: {old_phase} → {new_phase} (cycle {cycle_num})")
            print(f"LED: {self.esp32_controller.current_led_type} → {led_type}")

            # Switch LED type with calibrated power
            try:
                old_led_type = self.esp32_controller.current_led_type
                self.esp32_controller.select_led_type(led_type)

                # ✅ Verify calibration was applied with whitelight_power support
                if (
                    hasattr(self.esp32_controller, "calibrated_powers")
                    and self.esp32_controller.calibrated_powers
                ):
                    # ✅ Handle both 'white' and 'whitelight' LED types
                    calibration_key = (
                        "whitelight"
                        if led_type.lower() in ["white", "whitelight"]
                        else led_type.lower()
                    )
                    expected_power = self.esp32_controller.calibrated_powers.get(calibration_key)
                    actual_power = self.esp32_controller.led_power

                    if expected_power and abs(actual_power - expected_power) <= 1:
                        led_display = (
                            "WhiteLight" if calibration_key == "whitelight" else led_type.upper()
                        )
                        print(f"✓ Calibrated power applied: {led_display} LED = {actual_power}%")
                    else:
                        print(f"⚠ Power mismatch: expected {expected_power}%, got {actual_power}%")
                else:
                    print("⚠ No calibration available - using default power")

            except Exception as e:
                print(f"Failed to switch LED: {e}")
                # Log error but continue recording

            # Update tracking and emit signal
            self.current_cycle = cycle_num
            self.phase_start_time = time.time()
            self.phase_changed.emit(phase_info)
            print("=== TRANSITION COMPLETE ===")

    # ========================================================================
    # RECORDING CONTROL METHODS
    # ========================================================================

    def start(self):
        """Start phase-aware timelapse recording."""
        with self._state_lock:
            if self.recording:
                self.error_occurred.emit("Recording already in progress")
                return

        try:
            if not self.skip_validation:
                if not self._validate_setup():
                    return

            self._initialize_recording()
            self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
            self.recording_thread.start()
            self.recording_started.emit()

            if self.phase_config["enabled"]:
                start_phase = "Light" if self.phase_config["start_with_light"] else "Dark"
                self.status_updated.emit(
                    f"Phase-aware recording started (starting with {start_phase})"
                )
            else:
                self.status_updated.emit("Continuous recording started")
        except Exception as e:
            self.error_occurred.emit(f"Failed to start recording: {str(e)}")

    def stop(self):
        """Stop timelapse recording."""
        with self._state_lock:
            if not self.recording:
                return
            self.should_stop = True

        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=5.0)

        self._finalize_recording()
        self.status_updated.emit("Recording stopped")

    def pause(self):
        """Pause recording."""
        with self._state_lock:
            if not self.recording or self.paused:
                return
            self.paused = True

        self.recording_paused.emit()
        self.status_updated.emit("Recording paused")

    def resume(self):
        """Resume recording."""
        with self._state_lock:
            if not self.recording or not self.paused:
                return
            self.paused = False

        self.recording_resumed.emit()
        self.status_updated.emit("Recording resumed")

    def probe_frame(self) -> bool:
        """Lightweight probe to verify frame capture works."""
        try:
            frame, metadata = self._safe_capture_frame()
            print(f"Probe: got frame {frame.shape} from {metadata.get('source')}")
            return True
        except Exception as e:
            print(f"Probe failed: {e}")
            return False

    # ========================================================================
    # FRAME CAPTURE METHODS
    # ========================================================================

    def _capture_frame_from_napari_layer(self) -> Tuple[np.ndarray, dict]:
        """Preferentially grab the latest frame from a live Napari image layer."""
        if self.viewer is None:
            raise RuntimeError("No Napari viewer assigned for Napari-layer capture")
        try:
            from napari.layers import Image
        except ImportError:
            raise RuntimeError("Napari not available for layer fallback")

        # First try to prefer layers with name hints
        preferred_keywords = ("live", "widefield", "imswitch")
        for layer in self.viewer.layers:
            if not isinstance(layer, Image):
                continue
            name = getattr(layer, "name", "").lower()
            if any(k in name for k in preferred_keywords):
                data = getattr(layer, "data", None)
                if data is None:
                    continue
                if hasattr(data, "size") and data.size == 0:
                    continue
                frame = np.array(data, copy=True)
                metadata = {
                    "timestamp": time.time(),
                    "camera_name": getattr(self, "camera_name", "unknown"),
                    "frame_shape": frame.shape,
                    "frame_dtype": str(frame.dtype),
                    "source": f"napari_layer:{layer.name}",
                    "fallback": True,
                    "preferred_layer": True,
                }
                return frame, metadata

        # Fallback to any non-empty image layer
        for layer in self.viewer.layers:
            if not isinstance(layer, Image):
                continue
            data = getattr(layer, "data", None)
            if data is None:
                continue
            if hasattr(data, "size") and data.size == 0:
                continue
            frame = np.array(data, copy=True)
            metadata = {
                "timestamp": time.time(),
                "camera_name": getattr(self, "camera_name", "unknown"),
                "frame_shape": frame.shape,
                "frame_dtype": str(frame.dtype),
                "source": f"napari_layer:{layer.name}",
                "fallback": True,
            }
            return frame, metadata

        raise RuntimeError("No suitable Napari image layer found for fallback frame")

    def _capture_frame_from_imswitch_direct(self) -> Tuple[np.ndarray, dict]:
        """Attempt to capture frame directly from ImSwitch structures."""
        if self.imswitch_main is None:
            raise RuntimeError("ImSwitch not available for direct capture")

        # Try liveViewWidget
        try:
            if hasattr(self.imswitch_main, "liveViewWidget"):
                live_view = self.imswitch_main.liveViewWidget
                if hasattr(live_view, "img") and live_view.img is not None:
                    frame = live_view.img.copy()
                    metadata = {
                        "timestamp": time.time(),
                        "camera_name": self.camera_name,
                        "frame_shape": frame.shape,
                        "frame_dtype": str(frame.dtype),
                        "imswitch_managed": True,
                        "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
                        "source": "live_view_widget",
                    }
                    return frame, metadata
        except Exception:
            pass

        # Try viewWidget
        try:
            if hasattr(self.imswitch_main, "viewWidget"):
                view_widget = self.imswitch_main.viewWidget
                if hasattr(view_widget, "getCurrentImage"):
                    frame = view_widget.getCurrentImage()
                    if frame is not None:
                        metadata = {
                            "timestamp": time.time(),
                            "camera_name": self.camera_name,
                            "frame_shape": frame.shape,
                            "frame_dtype": str(frame.dtype),
                            "imswitch_managed": True,
                            "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
                            "source": "view_widget",
                        }
                        return frame, metadata
        except Exception:
            pass

        # Try imageWidget
        try:
            if hasattr(self.imswitch_main, "imageWidget"):
                image_widget = self.imswitch_main.imageWidget
                if hasattr(image_widget, "image") and image_widget.image is not None:
                    frame = image_widget.image.copy()
                    metadata = {
                        "timestamp": time.time(),
                        "camera_name": self.camera_name,
                        "frame_shape": frame.shape,
                        "frame_dtype": str(frame.dtype),
                        "imswitch_managed": True,
                        "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
                        "source": "image_widget",
                    }
                    return frame, metadata
        except Exception:
            pass

        # Try detectorsManager methods
        if hasattr(self.imswitch_main, "detectorsManager"):
            detectors_manager = self.imswitch_main.detectorsManager
            methods_to_try = [
                ("getLatestFrame", True),
                ("getLatestFrame", False),
                ("getLastImage", True),
                ("getLastImage", False),
                ("snap", True),
                ("snap", False),
                ("getImage", True),
                ("getImage", False),
                ("captureFrame", True),
                ("captureFrame", False),
            ]
            for method_name, use_camera_name in methods_to_try:
                if not hasattr(detectors_manager, method_name):
                    continue
                try:
                    method = getattr(detectors_manager, method_name)
                    if use_camera_name:
                        frame = method(self.camera_name)
                    else:
                        frame = method()
                    if frame is not None:
                        metadata = {
                            "timestamp": time.time(),
                            "camera_name": self.camera_name,
                            "frame_shape": frame.shape,
                            "frame_dtype": str(frame.dtype),
                            "imswitch_managed": True,
                            "pixel_format": "Mono16" if frame.ndim == 2 else "RGB8",
                            "source": f"detector_manager_{method_name}",
                        }
                        return frame, metadata
                except Exception:
                    continue

        raise RuntimeError("Could not capture frame from any ImSwitch method")

    def _safe_capture_frame(self) -> Tuple[np.ndarray, dict]:
        """Unified capture: ImSwitch FIRST (fresh frame), Napari only as fallback."""

        # ✅ CHANGE: Try ImSwitch FIRST for fresh frames
        if self.imswitch_main is not None:
            try:
                return self._capture_frame_from_imswitch_direct()
            except Exception as e:
                print(f"ImSwitch direct capture failed: {e}, trying Napari...")

        # ✅ ADD: Force Napari refresh before capture
        if self.viewer is not None:
            try:
                # Force layer refresh
                self.viewer.layers.events.changed()
                time.sleep(0.05)  # Small delay for refresh

                frame, metadata = self._capture_frame_from_napari_layer()
                return frame, metadata
            except Exception as e:
                print(f"Napari capture also failed: {e}")

        raise RuntimeError("All frame capture methods failed")

    # ========================================================================
    # ✅ NEW: MEMORY OPTIMIZATION METHODS
    # ========================================================================

    def _memory_safe_capture_frame(self) -> Tuple[np.ndarray, dict]:
        """Memory-safe frame capture with immediate optimization."""
        try:
            # ✅ MEMORY: Clear any cached references before capture
            import gc

            gc.collect()

            # Capture frame using existing method
            frame, metadata = self._safe_capture_frame()

            if frame is None:
                raise RuntimeError("Frame capture returned None")

            # ✅ MEMORY: Optimize frame immediately after capture
            frame = self._optimize_frame_memory(frame)

            return frame, metadata

        except Exception as e:
            # ✅ MEMORY: Ensure cleanup on capture failure
            if "frame" in locals() and frame is not None:
                del frame
            raise RuntimeError(f"Memory-safe capture failed: {e}")

    def _optimize_frame_memory(self, frame: np.ndarray) -> np.ndarray:
        """Optimize frame memory usage without losing scientific data."""
        if frame is None:
            return None

        original_size = frame.nbytes

        # ✅ MEMORY: Ensure contiguous array (more efficient for HDF5)
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
            print(f"Frame made contiguous: {original_size//1024}KB")

        # ✅ MEMORY: Convert to optimal dtype if needed (preserve scientific precision)
        if frame.dtype == np.float64:
            # Most cameras don't need float64 precision
            frame = frame.astype(np.float32)
            print(
                f"Frame optimized: float64->float32, {original_size//1024}KB->{frame.nbytes//1024}KB"
            )
        elif frame.dtype == np.int64:
            # Most cameras use 16-bit or less
            max_val = np.max(frame)
            if max_val <= 65535:
                frame = frame.astype(np.uint16)
                print(
                    f"Frame optimized: int64->uint16, {original_size//1024}KB->{frame.nbytes//1024}KB"
                )

        return frame

    def _cleanup_memory_intensive_layers(self):
        """Clean up napari layers that might accumulate frames."""
        if self.viewer is None:
            return

        try:
            layers_to_check = []
            for layer in self.viewer.layers:
                # Look for layers that might be accumulating data
                layer_name = getattr(layer, "name", "").lower()
                if any(
                    keyword in layer_name for keyword in ["timelapse", "capture", "temp", "cache"]
                ):
                    layers_to_check.append(layer)

            for layer in layers_to_check:
                try:
                    # If layer has large data, clear it but keep the layer
                    data = getattr(layer, "data", None)
                    if (
                        data is not None
                        and hasattr(data, "nbytes")
                        and data.nbytes > 10 * 1024 * 1024
                    ):  # > 10MB
                        print(
                            f"Clearing large layer data: {layer.name} ({data.nbytes//1024//1024}MB)"
                        )
                        # Don't delete the layer, just clear its data
                        if hasattr(layer, "data"):
                            layer.data = np.zeros((10, 10), dtype=data.dtype)  # Minimal placeholder
                except Exception as e:
                    print(f"Layer cleanup warning: {e}")

        except Exception as e:
            print(f"Layer cleanup failed: {e}")

    def _memory_safety_check(self) -> bool:
        """Check if system has enough memory to continue recording safely."""
        try:
            import psutil

            # System memory check
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)

            if available_gb < 2.0:  # Less than 2GB available
                print(f"WARNING: Low system memory: {available_gb:.1f}GB available")
                return False

            # Process memory check
            process = psutil.Process()
            process_memory_mb = process.memory_info().rss / (1024 * 1024)

            if process_memory_mb > 4000:  # More than 4GB process memory
                print(f"WARNING: High process memory: {process_memory_mb:.1f}MB")
                return False

            # Memory growth rate check
            if hasattr(self, "last_memory_check"):
                growth_rate = process_memory_mb - self.last_memory_check
                if growth_rate > 100:  # Growing more than 100MB between checks
                    print(f"WARNING: High memory growth rate: {growth_rate:.1f}MB since last check")
                    # Force garbage collection
                    import gc

                    collected = gc.collect()
                    print(f"Emergency GC: collected {collected} objects")

            self.last_memory_check = process_memory_mb

            return True

        except ImportError:
            print("psutil not available for memory monitoring")
            return True  # Continue without monitoring
        except Exception as e:
            print(f"Memory check failed: {e}")
            return True  # Continue on error

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
    # VALIDATION / INITIALIZATION / LOOP
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
            print(
                f"Validation: Frame capture successful - {frame.shape} from {metadata.get('source')}"
            )

        except Exception as e:
            self.error_occurred.emit(f"Frame capture test failed: {str(e)}")
            return False

        # ESP32 connection
        if not self.esp32_controller.is_connected():
            try:
                self.esp32_controller.connect()
                print("ESP32 connected during validation")
            except Exception as e:
                self.error_occurred.emit(f"ESP32 connection failed: {str(e)}")
                return False

        # ✅ NEW: Validate phase configuration and LED setup
        if self.phase_config["enabled"]:
            try:
                # Test LED switching capabilities
                original_led = self.esp32_controller.current_led_type

                # Test IR LED
                self.esp32_controller.select_led_type("ir")
                time.sleep(0.1)

                # Test White LED
                self.esp32_controller.select_led_type("white")
                time.sleep(0.1)

                # Restore original
                self.esp32_controller.select_led_type(original_led)

                print("Phase validation: LED switching test passed")
            except Exception as e:
                self.error_occurred.emit(f"LED switching test failed: {str(e)}")
                return False

        return True

    def _initialize_recording(self):
        """Initialize recording session with phase support."""
        with self._state_lock:
            self.recording = True
            self.paused = False
            self.should_stop = False
            self.current_frame = 0
        self.start_time = time.time()
        self.cumulative_drift = 0.0

        # ✅ NEW: Initialize phase tracking
        if self.phase_config["enabled"]:
            # Set initial LED type
            initial_led = "white" if self.phase_config["start_with_light"] else "ir"
            try:
                self.esp32_controller.select_led_type(initial_led)
                print(f"Initial LED set to: {initial_led.upper()}")
            except Exception as e:
                print(f"Failed to set initial LED: {e}")

            self.current_phase = "light" if self.phase_config["start_with_light"] else "dark"
            self.last_phase = None
            self.phase_start_time = self.start_time
            self.current_cycle = 1

        # Calculate expected frame times
        self.expected_frame_times = [
            self.start_time + (i * self.interval_sec) for i in range(self.total_frames)
        ]

        phase_info = "with phase cycling" if self.phase_config["enabled"] else "continuous"
        print(
            f"Recording initialized: {self.total_frames} frames over {self.duration_min} minutes {phase_info}"
        )

        # Create HDF5 file with phase metadata
        try:
            filepath = self.data_manager.create_recording_file(
                self.output_dir, experiment_name="nematostella_timelapse", timestamped=True
            )
            recording_metadata = {
                "duration_minutes": self.duration_min,
                "interval_seconds": self.interval_sec,
                "expected_frames": self.total_frames,
                "led_power": self.esp32_controller.led_power,
                "camera_name": self.camera_name,
                "imswitch_managed": True,
                "esp32_settings": (
                    self.esp32_controller.get_status()
                    if self.esp32_controller.is_connected()
                    else {}
                ),
                # ✅ NEW: Phase metadata
                "phase_config": self.phase_config,
                "phase_enabled": self.phase_config["enabled"],
                "light_duration_min": self.phase_config.get("light_duration_min", 0),
                "dark_duration_min": self.phase_config.get("dark_duration_min", 0),
                "starts_with_light": self.phase_config.get("start_with_light", True),
            }
            self.data_manager.update_recording_metadata(recording_metadata)
            print(f"Recording file created: {filepath}")
        except Exception as e:
            with self._state_lock:
                self.recording = False
            raise RuntimeError(f"Failed to initialize data storage: {str(e)}")

    def _recording_loop(self):
        """Main recording loop with phase awareness."""
        try:
            print("Phase-aware recording loop started")
            self._capture_frame_sync()

            while True:
                with self._state_lock:
                    if self.should_stop or self.current_frame >= self.total_frames:
                        break
                    if self.paused:
                        pass

                if self.paused:
                    time.sleep(0.1)
                    continue

                now = time.time()
                expected_time = self.expected_frame_times[self.current_frame]
                if now < expected_time:
                    time.sleep(min(0.1, expected_time - now))
                    continue

                self._capture_frame_sync()

            with self._state_lock:
                completed = not self.should_stop and self.current_frame >= self.total_frames

            if completed:
                self._finalize_recording()
                self.recording_finished.emit()
                print("Phase-aware recording completed successfully")
        except Exception as e:
            print(f"Recording loop error: {e}")
            self.error_occurred.emit(f"Recording error: {str(e)}")
            self._finalize_recording()

    def _capture_frame_sync(self):
        """Memory-optimized frame capture with aggressive cleanup and streaming write."""
        with self._state_lock:
            if self.current_frame >= self.total_frames:
                return

        frame = None
        frame_metadata = None
        esp32_timing = None

        try:
            # ✅ MEMORY: Aggressive memory monitoring
            if self.current_frame % 20 == 0:  # Check every 20 frames (1.7 minutes)
                if not self._memory_safety_check():
                    self.error_occurred.emit(
                        "Memory safety threshold exceeded - stopping recording"
                    )
                    return

            # Phase and timing calculations (lightweight)
            capture_start_time = time.time()
            elapsed_minutes = (capture_start_time - self.start_time) / 60.0
            phase_info = self._get_current_phase_info(elapsed_minutes)

            if phase_info["phase"] != self.last_phase:
                self._handle_phase_change(phase_info)
                self.last_phase = phase_info["phase"]

            # ✅ CRITICAL: Clean napari layers BEFORE capture to prevent accumulation
            self._cleanup_memory_intensive_layers()

            # Timing compensation
            expected_time = (
                self.expected_frame_times[self.current_frame]
                if self.current_frame < len(self.expected_frame_times)
                else capture_start_time
            )
            frame_drift = capture_start_time - expected_time
            self.cumulative_drift += frame_drift

            python_timing = {
                "start_time": capture_start_time,
                "expected_time": expected_time,
                "frame_drift": frame_drift,
                "cumulative_drift": self.cumulative_drift,
            }

            # Health check every 100 frames
            if self.current_frame % 100 == 0 and self.current_frame > 0:
                if not self._system_health_check():
                    self.error_occurred.emit(
                        "System health check failed - stopping recording for safety"
                    )
                    return

            # Pre-capture sensor reading (minimal memory)
            led_type = phase_info.get("led_type", "ir")
            temp, humidity = 25.0, 50.0  # Defaults

            try:
                temp, humidity = self.esp32_controller.read_sensors()
                if temp < -10 or temp > 50 or humidity < 0 or humidity > 100:
                    temp, humidity = 25.0, 50.0  # Fallback
            except Exception as sensor_e:
                print(f"Sensor read failed: {sensor_e}")

            # ✅ STREAMING APPROACH: Capture -> Process -> Save -> Dispose immediately
            try:
                # Phase-aware capture
                if self.phase_config["enabled"]:
                    esp32_timing = self.esp32_controller.synchronize_capture_with_led(
                        led_type=led_type, led_duration_ms=500
                    )
                else:
                    esp32_timing = self.esp32_controller.synchronize_capture()

                # ✅ MEMORY: Capture with immediate size optimization
                frame, frame_metadata = self._memory_safe_capture_frame()

                if frame is None:
                    raise RuntimeError("Frame capture returned None")

                print(
                    f"Frame {self.current_frame}: captured {frame.shape}, {frame.dtype}, {frame.nbytes//1024}KB"
                )

            except Exception as capture_e:
                print(f"Capture failed: {capture_e}")
                # ✅ MEMORY: Even on failure, ensure cleanup
                if frame is not None:
                    del frame
                    frame = None
                if frame_metadata is not None:
                    del frame_metadata
                    frame_metadata = None
                raise

            # ✅ MEMORY: Build minimal metadata (avoid large objects)
            try:
                capture_end_time = time.time()
                python_timing["end_time"] = capture_end_time

                # Ensure ESP32 timing exists
                if esp32_timing is None:
                    esp32_timing = {
                        "esp32_time_start": capture_start_time,
                        "esp32_time_end": capture_end_time,
                        "led_duration_actual": 0,
                        "led_power_actual": self.esp32_controller.led_power,
                        "temperature": temp,
                        "humidity": humidity,
                        "led_type_used": led_type,
                        "phase_aware_capture": self.phase_config["enabled"],
                    }

                # Add lightweight phase metadata to frame_metadata
                if frame_metadata is None:
                    frame_metadata = {"timestamp": capture_start_time, "source": "unknown"}

                # ✅ MEMORY: Add only essential phase info (avoid copying large phase_info dict)
                frame_metadata.update(
                    {
                        "current_phase": phase_info["phase"],
                        "led_type_used": led_type,
                        "phase_elapsed_min": phase_info.get("phase_elapsed_min", 0),
                        "cycle_number": phase_info.get("cycle_number", 1),
                        "phase_transition": phase_info.get("phase_transition", False),
                        "phase_enabled": self.phase_config["enabled"],
                    }
                )

            except Exception as metadata_e:
                print(f"Metadata preparation failed: {metadata_e}")
                # ✅ MEMORY: Cleanup on metadata failure
                if frame is not None:
                    del frame
                if frame_metadata is not None:
                    del frame_metadata
                raise

            # ✅ CRITICAL: STREAMING WRITE - Save immediately and dispose
            success = False
            try:
                print(f"Frame {self.current_frame}: saving to HDF5...")

                # ✅ MEMORY: Direct streaming save (no intermediate storage)
                success = self.data_manager.save_frame_streaming(
                    frame, frame_metadata, esp32_timing, python_timing
                )

                if success:
                    print(f"Frame {self.current_frame}: saved successfully")
                else:
                    print(f"Frame {self.current_frame}: save failed")

            except Exception as save_e:
                print(f"Frame save error: {save_e}")
                success = False

            # ✅ CRITICAL: IMMEDIATE CLEANUP regardless of save success
            finally:
                # Force cleanup of large objects immediately
                if frame is not None:
                    print(f"Frame {self.current_frame}: disposing {frame.nbytes//1024}KB frame")
                    del frame
                    frame = None

                if frame_metadata is not None:
                    del frame_metadata
                    frame_metadata = None

                if esp32_timing is not None:
                    # Keep only essential timing info for next iteration, clear large data
                    esp32_timing = None

                # ✅ MEMORY: Force garbage collection more frequently for long recordings
                if self.current_frame % 10 == 0:  # Every 10 frames instead of 50
                    import gc

                    collected = gc.collect()
                    if collected > 0:
                        print(f"Frame {self.current_frame}: GC collected {collected} objects")

            # Update progress only on successful save
            if success:
                with self._state_lock:
                    self.current_frame += 1

                progress = int((self.current_frame / self.total_frames) * 100)
                self.progress_updated.emit(progress)
                self.frame_captured.emit(self.current_frame, self.total_frames)

                # Status update
                elapsed_time = time.time() - self.start_time
                remaining_frames = self.total_frames - self.current_frame
                estimated_remaining = (
                    (elapsed_time / self.current_frame) * remaining_frames
                    if self.current_frame > 0
                    else 0
                )

                phase_text = (
                    f"Phase: {phase_info['phase'].upper()}"
                    if self.phase_config["enabled"]
                    else "Continuous"
                )
                status_msg = (
                    f"Frame {self.current_frame}/{self.total_frames} - {phase_text} - "
                    f"Remaining: {estimated_remaining:.1f}s"
                )
                self.status_updated.emit(status_msg)

                # ✅ MEMORY: Enhanced memory reporting every hour
                frames_per_hour = 3600 // self.interval_sec
                if self.current_frame % frames_per_hour == 0:
                    hours_completed = self.current_frame // frames_per_hour
                    current_phase = (
                        phase_info["phase"].upper()
                        if self.phase_config["enabled"]
                        else "CONTINUOUS"
                    )

                    # Force HDF5 flush and memory reporting
                    if hasattr(self.data_manager, "hdf5_file") and self.data_manager.hdf5_file:
                        self.data_manager.hdf5_file.flush()

                    # Memory status
                    memory_status = self._get_memory_status()
                    print(
                        f"=== CHECKPOINT: {hours_completed}h - Phase: {current_phase} - Memory: {memory_status} ==="
                    )
            else:
                self.error_occurred.emit(f"Failed to save frame {self.current_frame + 1}")

        except Exception as e:
            # ✅ MEMORY: Final cleanup on any error
            if "frame" in locals() and frame is not None:
                del frame
            if "frame_metadata" in locals() and frame_metadata is not None:
                del frame_metadata
            if "esp32_timing" in locals() and esp32_timing is not None:
                del esp32_timing

            print(f"Frame capture error: {e}")
            self.error_occurred.emit(f"Frame capture failed: {str(e)}")

    def _system_health_check(self) -> bool:
        """Check system health for long-term stability."""
        try:
            import psutil

            # Check system memory
            memory = psutil.virtual_memory()
            if memory.percent > 85:
                print(f"WARNING: High system memory usage: {memory.percent:.1f}%")
                return False

            # Check process memory
            process = psutil.Process()
            process_memory_mb = process.memory_info().rss / 1024 / 1024
            if process_memory_mb > 3000:  # 3GB limit
                print(f"WARNING: High process memory usage: {process_memory_mb:.1f}MB")
                return False

            # Check disk space
            disk = psutil.disk_usage(".")
            free_gb = disk.free / (1024**3)
            if free_gb < 5:  # 5GB minimum
                print(f"WARNING: Low disk space: {free_gb:.1f}GB")
                return False

            # Check ESP32 connection
            if not self.esp32_controller.is_connected(force_check=True):
                print("WARNING: ESP32 connection lost")
                try:
                    self.esp32_controller.connect()
                    print("ESP32 reconnected successfully")
                    # ✅ PHASE RECOVERY: Restore LED state after reconnection
                    if self.phase_config["enabled"] and hasattr(self, "current_phase"):
                        led_type = "white" if self.current_phase == "light" else "ir"
                        self.esp32_controller.select_led_type(led_type)
                        print(f"LED state restored to {led_type.upper()} after reconnection")
                except Exception as e:
                    print(f"ESP32 reconnection failed: {e}")
                    return False

            # Health check passed
            if self.current_frame % 500 == 0:  # Log every ~41 minutes
                current_phase = getattr(self, "current_phase", "continuous").upper()
                print(
                    f"Health check OK: Memory={memory.percent:.1f}%, "
                    f"Process={process_memory_mb:.1f}MB, "
                    f"Disk={free_gb:.1f}GB, "
                    f"ESP32=Connected, "
                    f"Phase={current_phase}"
                )

            return True

        except Exception as e:
            print(f"Health check failed with error: {e}")
            return False

    def _finalize_recording(self):
        """Finalize recording and cleanup."""
        try:
            print("Finalizing phase-aware recording...")
            if self.data_manager.is_file_open():
                self.data_manager.finalize_recording()
                print("Data manager finalized")
            with self._state_lock:
                self.recording = False
                self.paused = False
                self.should_stop = False

            # ✅ LED CLEANUP: Turn off all LEDs
            try:
                if self.esp32_controller.is_connected():
                    self.esp32_controller.turn_off_all_leds()
                    print("All LEDs turned off")
            except Exception as led_e:
                print(f"Failed to turn off LEDs: {led_e}")

            if self.current_frame == self.total_frames:
                phase_text = "with phase cycling" if self.phase_config["enabled"] else "continuous"
                self.status_updated.emit(
                    f"Recording completed: {self.current_frame} frames captured ({phase_text})"
                )
                print(
                    f"Recording completed successfully: {self.current_frame} frames ({phase_text})"
                )
            else:
                self.status_updated.emit(
                    f"Recording stopped: {self.current_frame}/{self.total_frames} frames captured"
                )
                print(f"Recording stopped early: {self.current_frame}/{self.total_frames} frames")
        except Exception as e:
            print(f"Finalization error: {e}")
            self.error_occurred.emit(f"Error finalizing recording: {str(e)}")

    def get_recording_status(self) -> dict:
        """Get current recording status with phase information."""
        with self._state_lock:
            current_frame = self.current_frame
            total_frames = self.total_frames
            recording = self.recording
            paused = self.paused
            cumulative_drift = self.cumulative_drift

        # ✅ PHASE STATUS: Add current phase info
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
            **phase_status,
        }

        return status

    def is_recording(self) -> bool:
        """Check if currently recording."""
        with self._state_lock:
            return self.recording

    def is_paused(self) -> bool:
        """Check if recording is paused."""
        with self._state_lock:
            return self.paused
