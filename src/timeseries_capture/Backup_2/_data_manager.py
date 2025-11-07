# """Data manager for HDF5 file storage and metadata management - FIXED VERSION."""

# import h5py
# import numpy as np
# import time
# import json
# from pathlib import Path
# from typing import Dict, Any, Optional, List
# from qtpy.QtCore import QObject

# # ✅ FIX: pyqtSignal Import with try/except
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal


# class DataManager(QObject):
#     """Manager for HDF5 data storage and metadata."""
#     # Unit definitions for clarity
#     UNITS = {
#         'time': 'seconds',
#         'temperature': 'celsius',
#         'humidity': 'percent',
#         'led_power': 'percent',
#         'led_duration': 'milliseconds',  # This one IS in ms
#         'frame_drift': 'seconds',
#         'intervals': 'seconds'
#     }
#     # Signals
#     file_created = pyqtSignal(str)  # filepath
#     frame_saved = pyqtSignal(int)  # frame_number
#     metadata_updated = pyqtSignal(dict)  # metadata
#     error_occurred = pyqtSignal(str)  # error message


#     def __init__(self):
#         super().__init__()
#         self.hdf5_file = None
#         self.current_filepath = None
#         self.frame_count = 0
#         self.recording_metadata = {}
#         self.expected_frame_interval = 5.0  # Default 5 seconds

#     def create_recording_file(self, output_dir: str, experiment_name: str = None,
#                             timestamped: bool = True) -> str:
#         """Create new HDF5 file for recording with clean structure."""
#         # Generate filename
#         if experiment_name is None:
#             experiment_name = "nematostella_timelapse"

#         timestamp = time.strftime("%Y%m%d_%H%M%S") if timestamped else ""
#         filename = f"{experiment_name}_{timestamp}.h5" if timestamp else f"{experiment_name}.h5"

#         # Create output directory if it doesn't exist
#         output_path = Path(output_dir)
#         if timestamped:
#             # Create timestamped subdirectory
#             timestamp_dir = time.strftime("%Y%m%d_%H%M%S")
#             output_path = output_path / timestamp_dir

#         output_path.mkdir(parents=True, exist_ok=True)

#         self.current_filepath = output_path / filename

#         try:
#             # Create HDF5 file
#             self.hdf5_file = h5py.File(self.current_filepath, 'w')

#             # ✅ Clean structure: Only what we need
#             images_group = self.hdf5_file.create_group('images')
#             metadata_group = self.hdf5_file.create_group('metadata')  # Keep for debugging
#             # ❌ REMOVED: timing and environmental groups (replaced by timeseries)

#             # Create attributes for file metadata
#             self.hdf5_file.attrs['created'] = time.time()
#             self.hdf5_file.attrs['created_human'] = time.strftime("%Y-%m-%d %H:%M:%S")
#             self.hdf5_file.attrs['experiment_name'] = experiment_name
#             self.hdf5_file.attrs['file_version'] = '2.2'  # ✅ Updated version - fixed expected_intervals
#             self.hdf5_file.attrs['software'] = 'napari-timelapse-capture'
#             self.hdf5_file.attrs['structure'] = 'timeseries_only'  # Document the clean structure

#             # Initialize frame counter
#             self.frame_count = 0

#             # Initialize recording metadata
#             self.recording_metadata = {
#                 'start_time': time.time(),
#                 'expected_frames': 0,
#                 'actual_frames': 0,
#                 'duration_minutes': 0,
#                 'interval_seconds': 0,
#                 'led_power': 0,
#                 'camera_settings': {},
#                 'esp32_settings': {}
#             }

#             self.file_created.emit(str(self.current_filepath))
#             return str(self.current_filepath)

#         except Exception as e:
#             error_msg = f"Failed to create HDF5 file: {str(e)}"
#             self.error_occurred.emit(error_msg)
#             raise RuntimeError(error_msg)

#     def save_frame(self, frame: np.ndarray, frame_metadata: dict,
#                 esp32_timing: dict, python_timing: dict) -> bool:
#         """Save frame and associated metadata to HDF5 file with clean time-series structure."""
#         if not self.hdf5_file:
#             raise RuntimeError("No HDF5 file open")

#         try:
#             frame_num = self.frame_count

#             # Save image data
#             frame_dataset_name = f"frame_{frame_num:06d}"
#             images_group = self.hdf5_file['images']

#             frame_dataset = images_group.create_dataset(
#                 frame_dataset_name,
#                 data=frame,
#                 compression='gzip',
#                 compression_opts=1
#             )

#             # Add frame attributes
#             frame_dataset.attrs['timestamp'] = frame_metadata.get('timestamp', time.time())
#             frame_dataset.attrs['frame_number'] = frame_num
#             frame_dataset.attrs['source'] = frame_metadata.get('source', 'unknown')

#             # ✅ Create time-series datasets on first frame
#             if frame_num == 0:
#                 self._create_timeseries_datasets()

#             # ✅ Append data to time-series datasets (this is what you want!)
#             self._append_timeseries_data(frame_num, frame, frame_metadata, esp32_timing, python_timing)

#             # Save detailed metadata (keep for debugging)
#             metadata_group = self.hdf5_file['metadata']
#             metadata_dataset_name = f"metadata_{frame_num:06d}"

#             full_metadata = {
#                 'frame_metadata': frame_metadata,
#                 'esp32_timing': esp32_timing,
#                 'python_timing': python_timing,
#                 'frame_number': frame_num
#             }

#             metadata_json = json.dumps(full_metadata, default=str)
#             metadata_dataset = metadata_group.create_dataset(
#                 metadata_dataset_name,
#                 data=metadata_json,
#                 dtype=h5py.string_dtype()
#             )

#             # ❌ REMOVED: Old timing structure (no more timing_000000 datasets)
#             # ❌ REMOVED: Old environmental structure (data is now in timeseries)

#             # Update frame count
#             self.frame_count += 1
#             self.recording_metadata['actual_frames'] = self.frame_count

#             # Flush to ensure data is written
#             self.hdf5_file.flush()

#             self.frame_saved.emit(frame_num)
#             return True

#         except Exception as e:
#             error_msg = f"Failed to save frame {frame_num}: {str(e)}"
#             self.error_occurred.emit(error_msg)
#             return False

#     def _create_timeseries_datasets(self):
#         """Create resizable time-series datasets with comprehensive unit documentation."""
#         try:
#             # Create time-series group
#             timeseries_group = self.hdf5_file.create_group('timeseries')

#             # Unit definitions for reference
#             UNITS = {
#                 'time': 'seconds',
#                 'temperature': 'celsius',
#                 'humidity': 'percent',
#                 'led_power': 'percent',
#                 'led_duration': 'milliseconds',
#                 'frame_drift': 'seconds',
#                 'intervals': 'seconds'
#             }

#             # ✅ ADD: Frame index as X-axis for all plots
#             timeseries_group.create_dataset('frame_index',
#                                         shape=(0,), maxshape=(None,), dtype='i4')

#             # Frame timing data (all in seconds)
#             timeseries_group.create_dataset('frame_intervals',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('capture_timestamps',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('expected_timestamps',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('frame_drift',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('cumulative_drift',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('actual_intervals',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('expected_intervals',
#                                         shape=(0,), maxshape=(None,), dtype='f8')

#             # LED data
#             timeseries_group.create_dataset('led_power_percent',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('led_duration_ms',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('led_sync_success',
#                                         shape=(0,), maxshape=(None,), dtype='bool')

#             # Environmental data
#             timeseries_group.create_dataset('temperature',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('humidity',
#                                         shape=(0,), maxshape=(None,), dtype='f4')

#             # Frame statistics
#             timeseries_group.create_dataset('frame_mean',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('frame_max',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('frame_min',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('frame_std',
#                                         shape=(0,), maxshape=(None,), dtype='f4')

#             # Capture method tracking
#             timeseries_group.create_dataset('capture_method',
#                                         shape=(0,), maxshape=(None,),
#                                         dtype=h5py.string_dtype())

#             # ✅ ENHANCED: Group-level documentation with unit definitions
#             timeseries_group.attrs['description'] = 'Time-series data for timelapse analysis'
#             timeseries_group.attrs['x_axis'] = 'frame_index'
#             timeseries_group.attrs['units_time'] = 'seconds'
#             timeseries_group.attrs['units_temperature'] = 'celsius'
#             timeseries_group.attrs['units_humidity'] = 'percent'
#             timeseries_group.attrs['units_led_power'] = 'percent'
#             timeseries_group.attrs['units_led_duration'] = 'milliseconds'
#             timeseries_group.attrs['expected_intervals_fixed'] = True
#             timeseries_group.attrs['unit_standard'] = 'All timing data stored in seconds for scientific consistency'

#             # ✅ ENHANCED: Comprehensive dataset descriptions with units and typical ranges

#             # Frame indexing
#             timeseries_group['frame_index'].attrs['description'] = 'Frame number sequence (0, 1, 2, ...)'
#             timeseries_group['frame_index'].attrs['units'] = 'dimensionless'
#             timeseries_group['frame_index'].attrs['use'] = 'Primary X-axis for all time-series plots'

#             # Timing datasets (all in seconds)
#             timeseries_group['frame_intervals'].attrs['description'] = 'Time elapsed since recording start'
#             timeseries_group['frame_intervals'].attrs['units'] = 'seconds'
#             timeseries_group['frame_intervals'].attrs['typical_range'] = '0 to recording_duration'

#             timeseries_group['capture_timestamps'].attrs['description'] = 'Unix timestamps of frame capture'
#             timeseries_group['capture_timestamps'].attrs['units'] = 'seconds (Unix epoch)'

#             timeseries_group['expected_timestamps'].attrs['description'] = 'Theoretical timestamps if perfect timing'
#             timeseries_group['expected_timestamps'].attrs['units'] = 'seconds (Unix epoch)'

#             timeseries_group['frame_drift'].attrs['description'] = 'Time difference: actual - expected frame capture (seconds)'
#             timeseries_group['frame_drift'].attrs['units'] = 'seconds'
#             timeseries_group['frame_drift'].attrs['typical_range'] = '-0.5 to +0.5 seconds'
#             timeseries_group['frame_drift'].attrs['interpretation'] = 'Positive=late, Negative=early, Zero=perfect'
#             timeseries_group['frame_drift'].attrs['display_hint'] = 'Multiply by 1000 for millisecond display'

#             timeseries_group['cumulative_drift'].attrs['description'] = 'Total accumulated timing error since recording start'
#             timeseries_group['cumulative_drift'].attrs['units'] = 'seconds'
#             timeseries_group['cumulative_drift'].attrs['interpretation'] = 'Cumulative sum of individual frame drifts'

#             timeseries_group['actual_intervals'].attrs['description'] = 'Measured time between consecutive frames'
#             timeseries_group['actual_intervals'].attrs['units'] = 'seconds'
#             timeseries_group['actual_intervals'].attrs['expected_value'] = f'{self.expected_frame_interval} seconds'

#             timeseries_group['expected_intervals'].attrs['description'] = 'Configured frame interval (constant)'
#             timeseries_group['expected_intervals'].attrs['units'] = 'seconds'
#             timeseries_group['expected_intervals'].attrs['expected_constant_value'] = self.expected_frame_interval
#             timeseries_group['expected_intervals'].attrs['should_be_constant'] = True
#             timeseries_group['expected_intervals'].attrs['note'] = 'All values should equal configured interval'

#             # LED datasets
#             timeseries_group['led_power_percent'].attrs['description'] = 'LED illumination power setting'
#             timeseries_group['led_power_percent'].attrs['units'] = 'percent'
#             timeseries_group['led_power_percent'].attrs['range'] = '0 to 100'

#             timeseries_group['led_duration_ms'].attrs['description'] = 'LED flash duration'
#             timeseries_group['led_duration_ms'].attrs['units'] = 'milliseconds'
#             timeseries_group['led_duration_ms'].attrs['note'] = 'Only LED parameter stored in milliseconds'

#             timeseries_group['led_sync_success'].attrs['description'] = 'Whether LED sync was successful'
#             timeseries_group['led_sync_success'].attrs['units'] = 'boolean'

#             # Environmental datasets
#             timeseries_group['temperature'].attrs['description'] = 'Ambient temperature'
#             timeseries_group['temperature'].attrs['units'] = 'celsius'
#             timeseries_group['temperature'].attrs['typical_range'] = '15 to 35 degrees'

#             timeseries_group['humidity'].attrs['description'] = 'Relative humidity'
#             timeseries_group['humidity'].attrs['units'] = 'percent'
#             timeseries_group['humidity'].attrs['range'] = '0 to 100'

#             # Frame statistics
#             for stat in ['frame_mean', 'frame_max', 'frame_min', 'frame_std']:
#                 timeseries_group[stat].attrs['description'] = f'Frame {stat.split("_")[1]} pixel intensity'
#                 timeseries_group[stat].attrs['units'] = 'pixel_intensity'
#                 timeseries_group[stat].attrs['depends_on'] = 'camera bit depth and settings'

#             timeseries_group['capture_method'].attrs['description'] = 'Method used for frame capture'
#             timeseries_group['capture_method'].attrs['units'] = 'string'
#             timeseries_group['capture_method'].attrs['examples'] = 'timer, manual, external_trigger'

#             print(f"Enhanced time-series datasets created with comprehensive unit documentation")
#             print(f"Expected frame interval: {self.expected_frame_interval}s")
#             print(f"Timing precision: millisecond accuracy stored as decimal seconds")

#         except Exception as e:
#             print(f"Error creating time-series datasets: {e}")
#     def _append_timeseries_data(self, frame_num: int, frame: np.ndarray, frame_metadata: dict,
#                             esp32_timing: dict, python_timing: dict):
#         """Append data to time-series datasets with frame indexing and enhanced unit logging."""
#         try:
#             timeseries_group = self.hdf5_file['timeseries']

#             # Get timing values
#             current_timestamp = frame_metadata.get('timestamp', time.time())
#             expected_timestamp = python_timing.get('expected_time', current_timestamp)
#             frame_drift = python_timing.get('frame_drift', 0.0)
#             cumulative_drift = python_timing.get('cumulative_drift', 0.0)

#             # ✅ FIX: Calculate intervals correctly
#             if frame_num == 0:
#                 actual_interval = 0.0  # First frame has no previous frame
#                 self.last_timestamp = current_timestamp
#                 self.recording_start_time = current_timestamp
#             else:
#                 actual_interval = current_timestamp - getattr(self, 'last_timestamp', current_timestamp)
#                 self.last_timestamp = current_timestamp

#             # ✅ FIX: expected_interval should ALWAYS be the configured value
#             expected_interval = self.expected_frame_interval  # Constant for all frames!

#             # Frame interval since recording start
#             frame_interval_from_start = current_timestamp - getattr(self, 'recording_start_time', current_timestamp)

#             # ✅ IMPROVED: Calculate frame statistics with better error handling
#             if frame is not None and hasattr(frame, 'shape') and frame.size > 0:
#                 try:
#                     frame_stats = {
#                         'mean': float(np.mean(frame)),
#                         'max': float(np.max(frame)),
#                         'min': float(np.min(frame)),
#                         'std': float(np.std(frame))
#                     }
#                 except Exception as e:
#                     print(f"Error calculating frame stats: {e}")
#                     frame_stats = {'mean': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
#             else:
#                 frame_stats = {'mean': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}

#             # ✅ Prepare all data including frame index
#             datasets_data = {
#                 'frame_index': frame_num,  # ✅ X-axis for plotting!
#                 'frame_intervals': frame_interval_from_start,
#                 'capture_timestamps': current_timestamp,
#                 'expected_timestamps': expected_timestamp,
#                 'frame_drift': frame_drift,
#                 'cumulative_drift': cumulative_drift,
#                 'actual_intervals': actual_interval,
#                 'expected_intervals': expected_interval,  # ✅ NOW ALWAYS = configured interval
#                 'led_power_percent': esp32_timing.get('led_power_actual', 0),
#                 'led_duration_ms': esp32_timing.get('led_duration_actual', 0),
#                 'led_sync_success': esp32_timing.get('led_duration_actual', 0) > 0,
#                 'temperature': esp32_timing.get('temperature', 0.0),
#                 'humidity': esp32_timing.get('humidity', 0.0),
#                 'frame_mean': frame_stats['mean'],
#                 'frame_max': frame_stats['max'],
#                 'frame_min': frame_stats['min'],
#                 'frame_std': frame_stats['std'],
#                 'capture_method': frame_metadata.get('source', 'unknown')
#             }

#             # Resize and append to each dataset
#             for dataset_name, value in datasets_data.items():
#                 dataset = timeseries_group[dataset_name]
#                 # Resize dataset to add one more element
#                 dataset.resize((frame_num + 1,))
#                 # Set the new value
#                 dataset[frame_num] = value

#             # ✅ ENHANCED: Logging with clear units and both seconds/milliseconds
#             led_duration = esp32_timing.get('led_duration_actual', 0)
#             temp = esp32_timing.get('temperature', 0)

#             print(f"Frame {frame_num}: expected={expected_interval:.1f}s, actual={actual_interval:.1f}s, "
#                 f"drift={frame_drift:.3f}s ({frame_drift*1000:.1f}ms), "
#                 f"cumul_drift={cumulative_drift:.3f}s ({cumulative_drift*1000:.1f}ms), "
#                 f"temp={temp:.1f}°C, LED={led_duration:.0f}ms")

#             # ✅ BONUS: Log timing quality assessment every 10 frames
#             if frame_num > 0 and frame_num % 10 == 0:
#                 drift_abs = abs(frame_drift)
#                 if drift_abs < 0.05:  # < 50ms
#                     quality = "excellent"
#                 elif drift_abs < 0.1:  # < 100ms
#                     quality = "good"
#                 elif drift_abs < 0.2:  # < 200ms
#                     quality = "acceptable"
#                 else:
#                     quality = "poor"

#                 print(f"  Frame {frame_num}: Timing quality = {quality} "
#                     f"(drift: {drift_abs*1000:.1f}ms, cumulative: {cumulative_drift*1000:.1f}ms)")

#         except Exception as e:
#             print(f"Error appending time-series data: {e}")
#     # def _append_timeseries_data(self, frame_num: int, frame: np.ndarray, frame_metadata: dict,
#     #                         esp32_timing: dict, python_timing: dict):
#     #     """Append data to time-series datasets with frame indexing - FIXED VERSION."""
#     #     try:
#     #         timeseries_group = self.hdf5_file['timeseries']

#     #         # Get timing values
#     #         current_timestamp = frame_metadata.get('timestamp', time.time())
#     #         expected_timestamp = python_timing.get('expected_time', current_timestamp)
#     #         frame_drift = python_timing.get('frame_drift', 0.0)
#     #         cumulative_drift = python_timing.get('cumulative_drift', 0.0)

#     #         # ✅ FIX: Calculate intervals correctly
#     #         if frame_num == 0:
#     #             actual_interval = 0.0  # First frame has no previous frame
#     #             self.last_timestamp = current_timestamp
#     #             self.recording_start_time = current_timestamp
#     #         else:
#     #             actual_interval = current_timestamp - getattr(self, 'last_timestamp', current_timestamp)
#     #             self.last_timestamp = current_timestamp

#     #         # ✅ FIX: expected_interval should ALWAYS be the configured value
#     #         expected_interval = self.expected_frame_interval  # Constant for all frames!

#     #         # Frame interval since recording start
#     #         frame_interval_from_start = current_timestamp - getattr(self, 'recording_start_time', current_timestamp)

#     #         # ✅ IMPROVED: Calculate frame statistics with better error handling
#     #         if frame is not None and hasattr(frame, 'shape') and frame.size > 0:
#     #             try:
#     #                 frame_stats = {
#     #                     'mean': float(np.mean(frame)),
#     #                     'max': float(np.max(frame)),
#     #                     'min': float(np.min(frame)),
#     #                     'std': float(np.std(frame))
#     #                 }
#     #             except Exception as e:
#     #                 print(f"Error calculating frame stats: {e}")
#     #                 frame_stats = {'mean': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
#     #         else:
#     #             frame_stats = {'mean': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}

#     #         # ✅ Prepare all data including frame index
#     #         datasets_data = {
#     #             'frame_index': frame_num,  # ✅ X-axis for plotting!
#     #             'frame_intervals': frame_interval_from_start,
#     #             'capture_timestamps': current_timestamp,
#     #             'expected_timestamps': expected_timestamp,
#     #             'frame_drift': frame_drift,
#     #             'cumulative_drift': cumulative_drift,
#     #             'actual_intervals': actual_interval,
#     #             'expected_intervals': expected_interval,  # ✅ NOW ALWAYS = configured interval
#     #             'led_power_percent': esp32_timing.get('led_power_actual', 0),
#     #             'led_duration_ms': esp32_timing.get('led_duration_actual', 0),
#     #             'led_sync_success': esp32_timing.get('led_duration_actual', 0) > 0,
#     #             'temperature': esp32_timing.get('temperature', 0.0),
#     #             'humidity': esp32_timing.get('humidity', 0.0),
#     #             'frame_mean': frame_stats['mean'],
#     #             'frame_max': frame_stats['max'],
#     #             'frame_min': frame_stats['min'],
#     #             'frame_std': frame_stats['std'],
#     #             'capture_method': frame_metadata.get('source', 'unknown')
#     #         }

#     #         # Resize and append to each dataset
#     #         for dataset_name, value in datasets_data.items():
#     #             dataset = timeseries_group[dataset_name]
#     #             # Resize dataset to add one more element
#     #             dataset.resize((frame_num + 1,))
#     #             # Set the new value
#     #             dataset[frame_num] = value

#     #             print(f"Frame {frame_num}: expected={expected_interval:.1f}s, actual={actual_interval:.1f}s, "
#     #                 f"drift={frame_drift:.3f}s ({frame_drift*1000:.1f}ms), temp={esp32_timing.get('temperature', 0):.1f}°C")
#     #     except Exception as e:
#     #         print(f"Error appending time-series data: {e}")

#     def _create_timing_dataset(self, frame_num: int, frame_metadata: dict,
#                               esp32_timing: dict, python_timing: dict) -> np.ndarray:
#         """Create structured timing dataset (legacy format)."""
#         # Define structured dtype for timing data
#         timing_dtype = np.dtype([
#             ('frame_number', 'i4'),
#             ('python_time_start', 'f8'),
#             ('python_time_capture', 'f8'),
#             ('python_time_end', 'f8'),
#             ('esp32_time_start', 'f8'),
#             ('esp32_time_end', 'f8'),
#             ('camera_timestamp', 'f8'),
#             ('led_duration_actual', 'f4'),
#             ('led_power_actual', 'i2'),
#             ('frame_drift', 'f4'),
#             ('cumulative_drift', 'f4')
#         ])

#         # Calculate timing metrics
#         python_capture_time = frame_metadata.get('timestamp', time.time())
#         expected_time = python_timing.get('expected_time', python_capture_time)
#         frame_drift = python_timing.get('frame_drift', 0.0)
#         cumulative_drift = python_timing.get('cumulative_drift', 0.0)

#         # Create timing record
#         timing_record = np.array([
#             (
#                 frame_num,
#                 python_timing.get('start_time', python_capture_time),
#                 python_capture_time,
#                 python_timing.get('end_time', python_capture_time),
#                 esp32_timing.get('esp32_time_start', 0),
#                 esp32_timing.get('esp32_time_end', 0),
#                 frame_metadata.get('timestamp_device', python_capture_time),
#                 esp32_timing.get('led_duration_actual', 0),
#                 esp32_timing.get('led_power_actual', 0),
#                 frame_drift,
#                 cumulative_drift
#             )
#         ], dtype=timing_dtype)

#         return timing_record

#     def _save_environmental_data(self, frame_num: int, esp32_timing: dict):
#         """Save environmental sensor data (legacy format)."""
#         env_group = self.hdf5_file['environmental']
#         env_dataset_name = f"env_{frame_num:06d}"

#         # Create environmental data record
#         env_dtype = np.dtype([
#             ('frame_number', 'i4'),
#             ('timestamp', 'f8'),
#             ('temperature', 'f4'),
#             ('humidity', 'f4')
#         ])

#         env_record = np.array([
#             (
#                 frame_num,
#                 time.time(),
#                 esp32_timing.get('temperature', 0.0),
#                 esp32_timing.get('humidity', 0.0)
#             )
#         ], dtype=env_dtype)

#         env_dataset = env_group.create_dataset(env_dataset_name, data=env_record)
#     def update_recording_metadata(self, metadata: dict):
#         """Update recording metadata with enhanced interval logging."""
#         self.recording_metadata.update(metadata)

#         # ✅ ENHANCED: Store expected frame interval with unit clarity
#         if 'interval_seconds' in metadata:
#             old_interval = self.expected_frame_interval
#             self.expected_frame_interval = metadata['interval_seconds']
#             print(f"Expected frame interval: {old_interval:.1f}s → {self.expected_frame_interval:.1f}s")
#             print(f"  Unit standard: All timing stored in seconds with millisecond precision")
#             print(f"  For display: multiply drift values by 1000 for milliseconds")

#         self.metadata_updated.emit(self.recording_metadata.copy())

#         # Save to HDF5 attributes
#         if self.hdf5_file:
#             for key, value in metadata.items():
#                 try:
#                     self.hdf5_file.attrs[key] = value
#                 except (TypeError, ValueError):
#                     # Convert to string if can't store directly
#                     self.hdf5_file.attrs[key] = str(value)
#     # def update_recording_metadata(self, metadata: dict):
#     #     """Update recording metadata and store expected frame interval."""
#     #     self.recording_metadata.update(metadata)

#     #     # ✅ IMPROVED: Store expected frame interval for timing analysis
#     #     if 'interval_seconds' in metadata:
#     #         self.expected_frame_interval = metadata['interval_seconds']
#     #         print(f"Expected frame interval updated to: {self.expected_frame_interval}s")

#     #     self.metadata_updated.emit(self.recording_metadata.copy())

#     #     # Save to HDF5 attributes
#     #     if self.hdf5_file:
#     #         for key, value in metadata.items():
#     #             try:
#     #                 self.hdf5_file.attrs[key] = value
#     #             except (TypeError, ValueError):
#     #                 # Convert to string if can't store directly
#     #                 self.hdf5_file.attrs[key] = str(value)

#     # def finalize_recording(self):
#     #     """Finalize recording and save final metadata."""
#     #     if not self.hdf5_file:
#     #         return

#     #     try:
#     #         # Update final metadata
#     #         self.recording_metadata['end_time'] = time.time()
#     #         self.recording_metadata['total_duration'] = (
#     #             self.recording_metadata['end_time'] - self.recording_metadata['start_time']
#     #         )
#     #         self.recording_metadata['actual_frames'] = self.frame_count

#     #         # Save final metadata to attributes
#     #         self.update_recording_metadata(self.recording_metadata)

#     #         # Add final attributes to timeseries group for easy access
#     #         if 'timeseries' in self.hdf5_file and self.frame_count > 0:
#     #             timeseries_group = self.hdf5_file['timeseries']
#     #             timeseries_group.attrs['total_frames'] = self.frame_count
#     #             timeseries_group.attrs['recording_duration'] = self.recording_metadata['total_duration']
#     #             timeseries_group.attrs['mean_interval'] = self.recording_metadata.get('interval_seconds', 0)

#     #             # ✅ IMPROVED: Calculate comprehensive statistics from the time-series data
#     #             try:
#     #                 if 'frame_drift' in timeseries_group and timeseries_group['frame_drift'].size > 0:
#     #                     drift_data = timeseries_group['frame_drift'][:]
#     #                     timeseries_group.attrs['mean_frame_drift'] = float(np.mean(drift_data))
#     #                     timeseries_group.attrs['std_frame_drift'] = float(np.std(drift_data))
#     #                     timeseries_group.attrs['max_frame_drift'] = float(np.max(drift_data))
#     #                     timeseries_group.attrs['min_frame_drift'] = float(np.min(drift_data))

#     #                 # Add statistics for expected vs actual intervals
#     #                 if 'actual_intervals' in timeseries_group and timeseries_group['actual_intervals'].size > 1:
#     #                     actual_intervals = timeseries_group['actual_intervals'][1:]  # Skip first frame (0.0)
#     #                     expected_intervals = timeseries_group['expected_intervals'][1:]

#     #                     timeseries_group.attrs['mean_actual_interval'] = float(np.mean(actual_intervals))
#     #                     timeseries_group.attrs['std_actual_interval'] = float(np.std(actual_intervals))
#     #                     timeseries_group.attrs['mean_expected_interval'] = float(np.mean(expected_intervals))

#     #                     # Interval accuracy
#     #                     interval_errors = actual_intervals - expected_intervals
#     #                     timeseries_group.attrs['mean_interval_error'] = float(np.mean(interval_errors))
#     #                     timeseries_group.attrs['std_interval_error'] = float(np.std(interval_errors))

#     #             except Exception as e:
#     #                 print(f"Could not calculate drift statistics: {e}")

#     #         print(f"Recording finalized: {self.frame_count} frames, clean structure with fixed expected_intervals")

#     #         # Close file
#     #         self.hdf5_file.close()
#     #         self.hdf5_file = None

#     #     except Exception as e:
#     #         error_msg = f"Error finalizing recording: {str(e)}"
#     #         self.error_occurred.emit(error_msg)
#     def finalize_recording(self):
#         """Finalize recording with comprehensive unit-aware statistics."""
#         if not self.hdf5_file:
#             return

#         try:
#             # Update final metadata
#             self.recording_metadata['end_time'] = time.time()
#             self.recording_metadata['total_duration'] = (
#                 self.recording_metadata['end_time'] - self.recording_metadata['start_time']
#             )
#             self.recording_metadata['actual_frames'] = self.frame_count

#             # Save final metadata to attributes
#             self.update_recording_metadata(self.recording_metadata)

#             # Add final attributes to timeseries group for easy access
#             if 'timeseries' in self.hdf5_file and self.frame_count > 0:
#                 timeseries_group = self.hdf5_file['timeseries']
#                 timeseries_group.attrs['total_frames'] = self.frame_count
#                 timeseries_group.attrs['recording_duration'] = self.recording_metadata['total_duration']
#                 timeseries_group.attrs['mean_interval'] = self.recording_metadata.get('interval_seconds', 0)

#                 # ✅ ENHANCED: Calculate comprehensive statistics with unit documentation
#                 try:
#                     if 'frame_drift' in timeseries_group and timeseries_group['frame_drift'].size > 0:
#                         drift_data = timeseries_group['frame_drift'][:]
#                         drift_stats = {
#                             'mean_frame_drift_seconds': float(np.mean(drift_data)),
#                             'mean_frame_drift_ms': float(np.mean(drift_data) * 1000),
#                             'std_frame_drift_seconds': float(np.std(drift_data)),
#                             'std_frame_drift_ms': float(np.std(drift_data) * 1000),
#                             'max_frame_drift_seconds': float(np.max(drift_data)),
#                             'max_frame_drift_ms': float(np.max(drift_data) * 1000),
#                             'min_frame_drift_seconds': float(np.min(drift_data)),
#                             'min_frame_drift_ms': float(np.min(drift_data) * 1000)
#                         }

#                         # Store both second and millisecond versions
#                         for key, value in drift_stats.items():
#                             timeseries_group.attrs[key] = value

#                     # Add statistics for expected vs actual intervals
#                     if 'actual_intervals' in timeseries_group and timeseries_group['actual_intervals'].size > 1:
#                         actual_intervals = timeseries_group['actual_intervals'][1:]  # Skip first frame (0.0)
#                         expected_intervals = timeseries_group['expected_intervals'][1:]

#                         interval_stats = {
#                             'mean_actual_interval_seconds': float(np.mean(actual_intervals)),
#                             'std_actual_interval_seconds': float(np.std(actual_intervals)),
#                             'mean_expected_interval_seconds': float(np.mean(expected_intervals)),
#                             'mean_interval_error_seconds': float(np.mean(actual_intervals - expected_intervals)),
#                             'mean_interval_error_ms': float(np.mean(actual_intervals - expected_intervals) * 1000),
#                             'std_interval_error_seconds': float(np.std(actual_intervals - expected_intervals)),
#                             'std_interval_error_ms': float(np.std(actual_intervals - expected_intervals) * 1000)
#                         }

#                         for key, value in interval_stats.items():
#                             timeseries_group.attrs[key] = value

#                     # ✅ ENHANCED: Final recording summary with units
#                     mean_drift_ms = timeseries_group.attrs.get('mean_frame_drift_ms', 0)
#                     max_drift_ms = timeseries_group.attrs.get('max_frame_drift_ms', 0)

#                     print(f"\n=== RECORDING FINALIZED ===")
#                     print(f"Frames: {self.frame_count}")
#                     print(f"Duration: {self.recording_metadata['total_duration']/60:.1f} minutes")
#                     print(f"Mean drift: {mean_drift_ms:.1f}ms")
#                     print(f"Max drift: {max_drift_ms:.1f}ms")
#                     print(f"Data structure: Enhanced timeseries with comprehensive unit documentation")
#                     print(f"Unit standard: All timing in seconds, LED duration in milliseconds")

#                 except Exception as e:
#                     print(f"Could not calculate drift statistics: {e}")

#             # Close file
#             self.hdf5_file.close()
#             self.hdf5_file = None

#         except Exception as e:
#             error_msg = f"Error finalizing recording: {str(e)}"
#             self.error_occurred.emit(error_msg)
#     def _create_summary_datasets(self):
#         """Create summary datasets for analysis."""
#         if self.frame_count == 0:
#             return

#         try:
#             # Create summary group
#             summary_group = self.hdf5_file.create_group('summary')

#             # Collect all timing data (legacy)
#             timing_group = self.hdf5_file['timing']
#             timing_list = []

#             for i in range(self.frame_count):
#                 timing_dataset_name = f"timing_{i:06d}"
#                 if timing_dataset_name in timing_group:
#                     timing_data = timing_group[timing_dataset_name][()]
#                     timing_list.append(timing_data)

#             if timing_list:
#                 # Create combined timing dataset
#                 combined_timing = np.concatenate(timing_list)
#                 summary_group.create_dataset('all_timing', data=combined_timing)

#                 # Calculate summary statistics
#                 frame_drifts = combined_timing['frame_drift']
#                 summary_stats = {
#                     'mean_frame_drift': np.mean(frame_drifts),
#                     'std_frame_drift': np.std(frame_drifts),
#                     'max_frame_drift': np.max(frame_drifts),
#                     'min_frame_drift': np.min(frame_drifts),
#                     'total_frames': len(frame_drifts)
#                 }

#                 # Save statistics as attributes
#                 for key, value in summary_stats.items():
#                     summary_group.attrs[key] = value

#             # Collect environmental data if available (legacy)
#             env_group = self.hdf5_file['environmental']
#             env_list = []

#             for i in range(self.frame_count):
#                 env_dataset_name = f"env_{i:06d}"
#                 if env_dataset_name in env_group:
#                     env_data = env_group[env_dataset_name][()]
#                     env_list.append(env_data)

#             if env_list:
#                 combined_env = np.concatenate(env_list)
#                 summary_group.create_dataset('all_environmental', data=combined_env)

#         except Exception as e:
#             print(f"Warning: Could not create summary datasets: {e}")

#     def get_recording_info(self) -> dict:
#         """Get current recording information."""
#         info = self.recording_metadata.copy()
#         info['current_filepath'] = str(self.current_filepath) if self.current_filepath else None
#         info['frames_saved'] = self.frame_count
#         info['file_open'] = self.hdf5_file is not None
#         return info

#     def close_file(self):
#         """Close the current HDF5 file."""
#         if self.hdf5_file:
#             try:
#                 self.hdf5_file.close()
#             except:
#                 pass
#             finally:
#                 self.hdf5_file = None
#                 self.current_filepath = None
#                 self.frame_count = 0

#     def is_file_open(self) -> bool:
#         """Check if a file is currently open."""
#         return self.hdf5_file is not None

#     @staticmethod
#     def load_recording(filepath: str) -> dict:
#         """Load recording data from HDF5 file."""
#         try:
#             with h5py.File(filepath, 'r') as f:
#                 # Load basic information
#                 info = {
#                     'filepath': filepath,
#                     'created': f.attrs.get('created', 0),
#                     'experiment_name': f.attrs.get('experiment_name', 'Unknown'),
#                     'file_version': f.attrs.get('file_version', '1.0'),
#                     'total_frames': f.attrs.get('actual_frames', 0)
#                 }

#                 # Load summary data if available
#                 if 'summary' in f:
#                     summary_group = f['summary']
#                     info['summary_stats'] = dict(summary_group.attrs)

#                     if 'all_timing' in summary_group:
#                         info['timing_data'] = summary_group['all_timing'][()]

#                     if 'all_environmental' in summary_group:
#                         info['environmental_data'] = summary_group['all_environmental'][()]

#                 return info

#         except Exception as e:
#             raise RuntimeError(f"Failed to load recording: {str(e)}")

#     @staticmethod
#     def load_frame(filepath: str, frame_number: int) -> tuple[np.ndarray, dict]:
#         """Load specific frame and metadata from HDF5 file."""
#         try:
#             with h5py.File(filepath, 'r') as f:
#                 # Load image
#                 frame_dataset_name = f"frame_{frame_number:06d}"
#                 if frame_dataset_name not in f['images']:
#                     raise ValueError(f"Frame {frame_number} not found")

#                 frame = f['images'][frame_dataset_name][()]

#                 # Load metadata
#                 metadata_dataset_name = f"metadata_{frame_number:06d}"
#                 if metadata_dataset_name in f['metadata']:
#                     metadata_json = f['metadata'][metadata_dataset_name][()]
#                     metadata = json.loads(metadata_json)
#                 else:
#                     metadata = {}

#                 return frame, metadata

#         except Exception as e:
#             raise RuntimeError(f"Failed to load frame {frame_number}: {str(e)}")

#     @staticmethod
#     def get_file_info(filepath: str) -> dict:
#         """Get basic information about HDF5 file without loading data."""
#         try:
#             with h5py.File(filepath, 'r') as f:
#                 info = {
#                     'filepath': filepath,
#                     'created': f.attrs.get('created', 0),
#                     'created_human': f.attrs.get('created_human', 'Unknown'),
#                     'experiment_name': f.attrs.get('experiment_name', 'Unknown'),
#                     'file_version': f.attrs.get('file_version', '1.0'),
#                     'software': f.attrs.get('software', 'Unknown'),
#                     'total_frames': f.attrs.get('actual_frames', 0),
#                     'duration_minutes': f.attrs.get('duration_minutes', 0),
#                     'interval_seconds': f.attrs.get('interval_seconds', 0),
#                     'groups': list(f.keys()),
#                     'file_size_mb': Path(filepath).stat().st_size / (1024 * 1024)
#                 }

#                 # Check what data is available
#                 if 'images' in f:
#                     info['image_count'] = len(f['images'].keys())
#                 if 'timing' in f:
#                     info['timing_count'] = len(f['timing'].keys())
#                 if 'environmental' in f:
#                     info['environmental_count'] = len(f['environmental'].keys())
#                 if 'timeseries' in f:
#                     info['timeseries_datasets'] = list(f['timeseries'].keys())

#                 return info

#         except Exception as e:
#             raise RuntimeError(f"Failed to get file info: {str(e)}")

#     # ✅ BONUS: Utility function to fix existing files
#     @staticmethod
#     def fix_expected_intervals_in_existing_file(filepath: str, expected_interval: float):
#         """Fix expected_intervals in existing HDF5 file with unit documentation."""
#         try:
#             with h5py.File(filepath, 'r+') as f:  # r+ = read/write, file must exist
#                 if 'timeseries' in f and 'expected_intervals' in f['timeseries']:
#                     dataset = f['timeseries']['expected_intervals']
#                     old_values = dataset[:5] if len(dataset) > 0 else []

#                     print(f"Fixing {len(dataset)} expected_intervals:")
#                     print(f"  Old values (first 5): {old_values}")
#                     print(f"  New value: {expected_interval}s (constant for all frames)")

#                     dataset[:] = expected_interval
#                     dataset.attrs['fixed'] = True
#                     dataset.attrs['fix_timestamp'] = time.time()
#                     dataset.attrs['fix_description'] = f'Fixed to constant {expected_interval} seconds'
#                     dataset.attrs['units'] = 'seconds'

#                     print(f"✅ expected_intervals fixed to {expected_interval}s!")
#                     return True
#                 else:
#                     print("No timeseries/expected_intervals found in file")
#                     return False
#         except Exception as e:
#             print(f"Error fixing file: {e}")
#             return False
#     # def fix_expected_intervals_in_existing_file(filepath: str, expected_interval: float):
#     #     """Fix expected_intervals in existing HDF5 file."""
#     #     try:
#     #         with h5py.File(filepath, 'r+') as f:  # r+ = read/write, file must exist
#     #             if 'timeseries' in f and 'expected_intervals' in f['timeseries']:
#     #                 dataset = f['timeseries']['expected_intervals']
#     #                 print(f"Fixing {len(dataset)} expected_intervals to {expected_interval}s")
#     #                 dataset[:] = expected_interval
#     #                 dataset.attrs['fixed'] = True
#     #                 dataset.attrs['fix_timestamp'] = time.time()
#     #                 dataset.attrs['fix_description'] = 'Fixed from zero values to constant expected interval'
#     #                 print("expected_intervals fixed!")
#     #                 return True
#     #             else:
#     #                 print("No timeseries/expected_intervals found in file")
#     #                 return False
#     #     except Exception as e:
#     #         print(f"Error fixing file: {e}")
#     #         return False
# """Phase-aware data manager for HDF5 file storage and metadata management with day/night cycle support."""

# import h5py
# import numpy as np
# import time
# import json
# from pathlib import Path
# from typing import Dict, Any, Optional, List
# from qtpy.QtCore import QObject

# # ✅ FIX: pyqtSignal Import with try/except
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal


# class DataManager(QObject):
#     """Phase-aware manager for HDF5 data storage and metadata with comprehensive day/night cycle support."""

#     # Unit definitions for clarity and scientific consistency
#     UNITS = {
#         'time': 'seconds',
#         'temperature': 'celsius',
#         'humidity': 'percent',
#         'led_power': 'percent',
#         'led_duration': 'milliseconds',  # Only LED duration in ms
#         'frame_drift': 'seconds',
#         'intervals': 'seconds',
#         'phase_duration': 'minutes',
#         'cycle_number': 'dimensionless'
#     }

#     # Signals
#     file_created = pyqtSignal(str)  # filepath
#     frame_saved = pyqtSignal(int)  # frame_number
#     metadata_updated = pyqtSignal(dict)  # metadata
#     error_occurred = pyqtSignal(str)  # error message
#     phase_transition_detected = pyqtSignal(dict)  # phase transition info

#     def __init__(self):
#         super().__init__()
#         self.hdf5_file = None
#         self.current_filepath = None
#         self.frame_count = 0
#         self.recording_metadata = {}
#         self.expected_frame_interval = 5.0  # Default 5 seconds

#         # ✅ NEW: Phase tracking for transition detection
#         self.last_phase = None
#         self.phase_transition_count = 0
#         self.cycle_count = 0

#     def create_recording_file(self, output_dir: str, experiment_name: str = None,
#                             timestamped: bool = True) -> str:
#         """Create new HDF5 file for phase-aware recording with enhanced structure."""
#         # Generate filename
#         if experiment_name is None:
#             experiment_name = "nematostella_timelapse"

#         timestamp = time.strftime("%Y%m%d_%H%M%S") if timestamped else ""
#         filename = f"{experiment_name}_{timestamp}.h5" if timestamp else f"{experiment_name}.h5"

#         # Create output directory if it doesn't exist
#         output_path = Path(output_dir)
#         if timestamped:
#             # Create timestamped subdirectory
#             timestamp_dir = time.strftime("%Y%m%d_%H%M%S")
#             output_path = output_path / timestamp_dir

#         output_path.mkdir(parents=True, exist_ok=True)

#         self.current_filepath = output_path / filename

#         try:
#             # Create HDF5 file
#             self.hdf5_file = h5py.File(self.current_filepath, 'w')

#             # ✅ ENHANCED: Clean structure with phase support
#             images_group = self.hdf5_file.create_group('images')
#             metadata_group = self.hdf5_file.create_group('metadata')
#             # ✅ NEW: Phase analysis group for transition events
#             phase_group = self.hdf5_file.create_group('phase_analysis')

#             # Create attributes for file metadata
#             self.hdf5_file.attrs['created'] = time.time()
#             self.hdf5_file.attrs['created_human'] = time.strftime("%Y-%m-%d %H:%M:%S")
#             self.hdf5_file.attrs['experiment_name'] = experiment_name
#             self.hdf5_file.attrs['file_version'] = '3.0'  # ✅ NEW: Phase-aware version
#             self.hdf5_file.attrs['software'] = 'napari-timelapse-capture-phase-aware'
#             self.hdf5_file.attrs['structure'] = 'phase_aware_timeseries'
#             self.hdf5_file.attrs['phase_support'] = True

#             # Initialize frame and phase counters
#             self.frame_count = 0
#             self.phase_transition_count = 0
#             self.cycle_count = 0
#             self.last_phase = None

#             # Initialize recording metadata with phase support
#             self.recording_metadata = {
#                 'start_time': time.time(),
#                 'expected_frames': 0,
#                 'actual_frames': 0,
#                 'duration_minutes': 0,
#                 'interval_seconds': 0,
#                 'led_power': 0,
#                 'camera_settings': {},
#                 'esp32_settings': {},
#                 # ✅ NEW: Phase configuration metadata
#                 'phase_enabled': False,
#                 'phase_config': {},
#                 'phase_transitions': 0,
#                 'cycles_completed': 0
#             }

#             self.file_created.emit(str(self.current_filepath))
#             print(f"Phase-aware HDF5 file created: {self.current_filepath}")
#             return str(self.current_filepath)

#         except Exception as e:
#             error_msg = f"Failed to create phase-aware HDF5 file: {str(e)}"
#             self.error_occurred.emit(error_msg)
#             raise RuntimeError(error_msg)

#     def save_frame(self, frame: np.ndarray, frame_metadata: dict,
#                 esp32_timing: dict, python_timing: dict) -> bool:
#         """Save frame with phase-aware metadata to HDF5 file."""
#         if not self.hdf5_file:
#             raise RuntimeError("No HDF5 file open")

#         try:
#             frame_num = self.frame_count

#             # Save image data
#             frame_dataset_name = f"frame_{frame_num:06d}"
#             images_group = self.hdf5_file['images']

#             frame_dataset = images_group.create_dataset(
#                 frame_dataset_name,
#                 data=frame,
#                 compression='gzip',
#                 compression_opts=1
#             )

#             # Add frame attributes including phase info
#             frame_dataset.attrs['timestamp'] = frame_metadata.get('timestamp', time.time())
#             frame_dataset.attrs['frame_number'] = frame_num
#             frame_dataset.attrs['source'] = frame_metadata.get('source', 'unknown')

#             # ✅ NEW: Phase attributes on frame
#             if frame_metadata.get('phase_enabled', False):
#                 frame_dataset.attrs['current_phase'] = frame_metadata.get('current_phase', 'continuous')
#                 frame_dataset.attrs['led_type_used'] = frame_metadata.get('led_type_used', 'ir')
#                 frame_dataset.attrs['cycle_number'] = frame_metadata.get('cycle_number', 1)
#                 frame_dataset.attrs['phase_transition'] = frame_metadata.get('phase_transition', False)

#             # ✅ Create time-series datasets on first frame
#             if frame_num == 0:
#                 self._create_phase_aware_timeseries_datasets()

#             # ✅ Append data to time-series datasets with phase support
#             self._append_phase_aware_timeseries_data(frame_num, frame, frame_metadata, esp32_timing, python_timing)

#             # Save detailed metadata (enhanced with phase data)
#             metadata_group = self.hdf5_file['metadata']
#             metadata_dataset_name = f"metadata_{frame_num:06d}"

#             full_metadata = {
#                 'frame_metadata': frame_metadata,
#                 'esp32_timing': esp32_timing,
#                 'python_timing': python_timing,
#                 'frame_number': frame_num,
#                 # ✅ NEW: Explicit phase metadata extraction
#                 'phase_info': self._extract_phase_metadata(frame_metadata)
#             }

#             metadata_json = json.dumps(full_metadata, default=str)
#             metadata_dataset = metadata_group.create_dataset(
#                 metadata_dataset_name,
#                 data=metadata_json,
#                 dtype=h5py.string_dtype()
#             )

#             # ✅ NEW: Handle phase transitions
#             self._process_phase_transition(frame_num, frame_metadata)

#             # Update frame count
#             self.frame_count += 1
#             self.recording_metadata['actual_frames'] = self.frame_count

#             # Flush to ensure data is written
#             self.hdf5_file.flush()

#             self.frame_saved.emit(frame_num)
#             return True

#         except Exception as e:
#             error_msg = f"Failed to save frame {frame_num}: {str(e)}"
#             self.error_occurred.emit(error_msg)
#             return False

#     def _create_phase_aware_timeseries_datasets(self):
#         """Create enhanced time-series datasets with comprehensive phase support."""
#         try:
#             # Create time-series group
#             timeseries_group = self.hdf5_file.create_group('timeseries')

#             # ✅ CORE: Frame index as X-axis for all plots
#             timeseries_group.create_dataset('frame_index',
#                                         shape=(0,), maxshape=(None,), dtype='i4')

#             # ✅ TIMING: Frame timing data (all in seconds)
#             timeseries_group.create_dataset('frame_intervals',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('capture_timestamps',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('expected_timestamps',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('frame_drift',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('cumulative_drift',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('actual_intervals',
#                                         shape=(0,), maxshape=(None,), dtype='f8')
#             timeseries_group.create_dataset('expected_intervals',
#                                         shape=(0,), maxshape=(None,), dtype='f8')

#             # ✅ LED: LED control data
#             timeseries_group.create_dataset('led_power_percent',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('led_duration_ms',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('led_sync_success',
#                                         shape=(0,), maxshape=(None,), dtype='bool')

#             # ✅ NEW: Phase-specific LED tracking
#             timeseries_group.create_dataset('led_type_used',
#                                         shape=(0,), maxshape=(None,),
#                                         dtype=h5py.string_dtype())
#             timeseries_group.create_dataset('led_type_numeric',
#                                         shape=(0,), maxshape=(None,), dtype='i1')  # 0=IR, 1=White

#             # ✅ ENVIRONMENTAL: Environmental sensor data
#             timeseries_group.create_dataset('temperature',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('humidity',
#                                         shape=(0,), maxshape=(None,), dtype='f4')

#             # ✅ FRAME STATS: Frame statistics
#             timeseries_group.create_dataset('frame_mean',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('frame_max',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('frame_min',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('frame_std',
#                                         shape=(0,), maxshape=(None,), dtype='f4')

#             # ✅ CAPTURE: Capture method tracking
#             timeseries_group.create_dataset('capture_method',
#                                         shape=(0,), maxshape=(None,),
#                                         dtype=h5py.string_dtype())

#             # ========================================================================
#             # ✅ NEW: COMPREHENSIVE PHASE DATASETS FOR CIRCADIAN ANALYSIS
#             # ========================================================================

#             # Phase state tracking
#             timeseries_group.create_dataset('current_phase',
#                                         shape=(0,), maxshape=(None,),
#                                         dtype=h5py.string_dtype())
#             timeseries_group.create_dataset('phase_numeric',
#                                         shape=(0,), maxshape=(None,), dtype='i1')  # 0=continuous, 1=light, 2=dark
#             timeseries_group.create_dataset('phase_enabled',
#                                         shape=(0,), maxshape=(None,), dtype='bool')

#             # Phase timing (in minutes for biological relevance)
#             timeseries_group.create_dataset('phase_elapsed_min',
#                                         shape=(0,), maxshape=(None,), dtype='f4')
#             timeseries_group.create_dataset('phase_remaining_min',
#                                         shape=(0,), maxshape=(None,), dtype='f4')

#             # Cycle tracking
#             timeseries_group.create_dataset('cycle_number',
#                                         shape=(0,), maxshape=(None,), dtype='i4')
#             timeseries_group.create_dataset('total_cycles',
#                                         shape=(0,), maxshape=(None,), dtype='i4')

#             # Phase transition markers
#             timeseries_group.create_dataset('phase_transition',
#                                         shape=(0,), maxshape=(None,), dtype='bool')
#             timeseries_group.create_dataset('transition_count',
#                                         shape=(0,), maxshape=(None,), dtype='i4')

#             # ========================================================================
#             # ✅ ENHANCED: Comprehensive dataset documentation with phase units
#             # ========================================================================

#             # Group-level documentation
#             timeseries_group.attrs['description'] = 'Phase-aware time-series data for circadian timelapse analysis'
#             timeseries_group.attrs['x_axis'] = 'frame_index'
#             timeseries_group.attrs['phase_support'] = True
#             timeseries_group.attrs['circadian_analysis_ready'] = True

#             # Unit definitions
#             for unit_key, unit_value in self.UNITS.items():
#                 timeseries_group.attrs[f'units_{unit_key}'] = unit_value

#             timeseries_group.attrs['unit_standard'] = 'Timing in seconds, LED duration in ms, phases in minutes'

#             # ✅ TIMING: Documentation for timing datasets
#             timing_datasets = {
#                 'frame_index': ('Frame sequence number', 'dimensionless', 'Primary X-axis'),
#                 'frame_intervals': ('Time since recording start', 'seconds', '0 to total_duration'),
#                 'capture_timestamps': ('Unix timestamps', 'seconds', 'Unix epoch time'),
#                 'expected_timestamps': ('Theoretical timestamps', 'seconds', 'Perfect timing baseline'),
#                 'frame_drift': ('Timing error (actual-expected)', 'seconds', '±0.5 typical'),
#                 'cumulative_drift': ('Total accumulated drift', 'seconds', 'Sum of all drifts'),
#                 'actual_intervals': ('Measured frame spacing', 'seconds', 'interval_seconds ± variation'),
#                 'expected_intervals': ('Configured frame spacing', 'seconds', 'Constant value')
#             }

#             for dataset_name, (desc, units, typical) in timing_datasets.items():
#                 ds = timeseries_group[dataset_name]
#                 ds.attrs['description'] = desc
#                 ds.attrs['units'] = units
#                 ds.attrs['typical_range'] = typical
#                 if 'expected' in dataset_name:
#                     ds.attrs['should_be_constant'] = True
#                 if 'drift' in dataset_name:
#                     ds.attrs['display_hint'] = 'Multiply by 1000 for millisecond display'

#             # ✅ LED: Documentation for LED datasets
#             led_datasets = {
#                 'led_power_percent': ('LED illumination power', 'percent', '0-100'),
#                 'led_duration_ms': ('LED flash duration', 'milliseconds', '100-1000 typical'),
#                 'led_sync_success': ('LED synchronization success', 'boolean', 'True/False'),
#                 'led_type_used': ('LED type for illumination', 'string', 'ir/white'),
#                 'led_type_numeric': ('LED type as number', 'dimensionless', '0=IR, 1=White')
#             }

#             for dataset_name, (desc, units, typical) in led_datasets.items():
#                 ds = timeseries_group[dataset_name]
#                 ds.attrs['description'] = desc
#                 ds.attrs['units'] = units
#                 ds.attrs['range_or_values'] = typical
#                 if 'type' in dataset_name:
#                     ds.attrs['use_case'] = 'Day/night phase analysis and LED performance tracking'

#             # ✅ ENVIRONMENTAL: Documentation for environmental datasets
#             env_datasets = {
#                 'temperature': ('Ambient temperature', 'celsius', '15-35°C typical'),
#                 'humidity': ('Relative humidity', 'percent', '0-100%')
#             }

#             for dataset_name, (desc, units, typical) in env_datasets.items():
#                 ds = timeseries_group[dataset_name]
#                 ds.attrs['description'] = desc
#                 ds.attrs['units'] = units
#                 ds.attrs['typical_range'] = typical
#                 ds.attrs['sensor'] = 'DHT22'

#             # ✅ FRAME STATS: Documentation for frame statistics
#             frame_stats_datasets = {
#                 'frame_mean': ('Mean pixel intensity', 'pixel_value', 'Camera dependent'),
#                 'frame_max': ('Maximum pixel intensity', 'pixel_value', 'Camera dependent'),
#                 'frame_min': ('Minimum pixel intensity', 'pixel_value', 'Camera dependent'),
#                 'frame_std': ('Pixel intensity std dev', 'pixel_value', 'Camera dependent')
#             }

#             for dataset_name, (desc, units, typical) in frame_stats_datasets.items():
#                 ds = timeseries_group[dataset_name]
#                 ds.attrs['description'] = desc
#                 ds.attrs['units'] = units
#                 ds.attrs['depends_on'] = typical
#                 ds.attrs['use_case'] = 'Image quality monitoring and analysis'

#             # ========================================================================
#             # ✅ NEW: COMPREHENSIVE PHASE DATASET DOCUMENTATION
#             # ========================================================================

#             # Phase state datasets
#             phase_datasets = {
#                 'current_phase': ('Active circadian phase', 'string', 'light/dark/continuous'),
#                 'phase_numeric': ('Phase as number', 'dimensionless', '0=continuous, 1=light, 2=dark'),
#                 'phase_enabled': ('Phase cycling active', 'boolean', 'True/False'),
#                 'phase_elapsed_min': ('Time in current phase', 'minutes', '0 to phase_duration'),
#                 'phase_remaining_min': ('Time left in phase', 'minutes', '0 to phase_duration'),
#                 'cycle_number': ('Current circadian cycle', 'dimensionless', '1, 2, 3, ...'),
#                 'total_cycles': ('Total planned cycles', 'dimensionless', 'Based on duration/cycle_time'),
#                 'phase_transition': ('Phase change marker', 'boolean', 'True at transitions'),
#                 'transition_count': ('Number of transitions', 'dimensionless', 'Cumulative count')
#             }

#             for dataset_name, (desc, units, typical) in phase_datasets.items():
#                 ds = timeseries_group[dataset_name]
#                 ds.attrs['description'] = desc
#                 ds.attrs['units'] = units
#                 ds.attrs['values_or_range'] = typical
#                 ds.attrs['circadian_analysis'] = True

#                 # Special documentation for key phase datasets
#                 if dataset_name == 'current_phase':
#                     ds.attrs['analysis_use'] = 'Primary phase identification for circadian rhythm analysis'
#                     ds.attrs['values'] = 'light (day phase, white LED), dark (night phase, IR LED), continuous (no cycling)'
#                 elif dataset_name == 'phase_transition':
#                     ds.attrs['analysis_use'] = 'Identify exact timing of day/night transitions for event analysis'
#                     ds.attrs['event_detection'] = 'Use boolean True values to mark transition points'
#                 elif dataset_name == 'cycle_number':
#                     ds.attrs['analysis_use'] = 'Track complete circadian cycles for longitudinal analysis'

#             # ✅ CAPTURE: Documentation for capture method
#             ds = timeseries_group['capture_method']
#             ds.attrs['description'] = 'Frame capture source method'
#             ds.attrs['units'] = 'string'
#             ds.attrs['typical_values'] = 'imswitch_direct, napari_layer, manual_trigger'

#             print(f"Phase-aware time-series datasets created:")
#             print(f"  - Standard datasets: frame timing, LED control, environmental")
#             print(f"  - Phase datasets: current_phase, cycle_number, transitions")
#             print(f"  - Analysis ready: LED type tracking, phase timing, transition markers")
#             print(f"  - Expected frame interval: {self.expected_frame_interval}s")

#         except Exception as e:
#             error_msg = f"Error creating phase-aware time-series datasets: {e}"
#             print(error_msg)
#             self.error_occurred.emit(error_msg)

#     def _append_phase_aware_timeseries_data(self, frame_num: int, frame: np.ndarray,
#                                           frame_metadata: dict, esp32_timing: dict, python_timing: dict):
#         """Append data to time-series datasets with comprehensive phase support."""
#         try:
#             timeseries_group = self.hdf5_file['timeseries']

#             # ✅ TIMING: Get timing values
#             current_timestamp = frame_metadata.get('timestamp', time.time())
#             expected_timestamp = python_timing.get('expected_time', current_timestamp)
#             frame_drift = python_timing.get('frame_drift', 0.0)
#             cumulative_drift = python_timing.get('cumulative_drift', 0.0)

#             # Calculate intervals
#             if frame_num == 0:
#                 actual_interval = 0.0  # First frame has no previous frame
#                 self.last_timestamp = current_timestamp
#                 self.recording_start_time = current_timestamp
#             else:
#                 actual_interval = current_timestamp - getattr(self, 'last_timestamp', current_timestamp)
#                 self.last_timestamp = current_timestamp

#             expected_interval = self.expected_frame_interval  # Always constant
#             frame_interval_from_start = current_timestamp - getattr(self, 'recording_start_time', current_timestamp)

#             # ✅ FRAME STATS: Calculate frame statistics
#             if frame is not None and hasattr(frame, 'shape') and frame.size > 0:
#                 try:
#                     frame_stats = {
#                         'mean': float(np.mean(frame)),
#                         'max': float(np.max(frame)),
#                         'min': float(np.min(frame)),
#                         'std': float(np.std(frame))
#                     }
#                 except Exception as e:
#                     print(f"Error calculating frame stats: {e}")
#                     frame_stats = {'mean': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
#             else:
#                 frame_stats = {'mean': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}

#             # ✅ PHASE: Extract phase information from frame metadata
#             phase_info = self._extract_phase_metadata(frame_metadata)

#             # Convert LED type to numeric for analysis
#             led_type_str = phase_info.get('led_type_used', 'ir')
#             led_type_numeric = 1 if led_type_str.lower() == 'white' else 0

#             # Convert phase to numeric for analysis
#             phase_str = phase_info.get('current_phase', 'continuous')
#             if phase_str == 'light':
#                 phase_numeric = 1
#             elif phase_str == 'dark':
#                 phase_numeric = 2
#             else:
#                 phase_numeric = 0  # continuous

#             # ✅ COMPREHENSIVE: Prepare all data including phase information
#             datasets_data = {
#                 # Core frame indexing
#                 'frame_index': frame_num,

#                 # Timing data (all in seconds)
#                 'frame_intervals': frame_interval_from_start,
#                 'capture_timestamps': current_timestamp,
#                 'expected_timestamps': expected_timestamp,
#                 'frame_drift': frame_drift,
#                 'cumulative_drift': cumulative_drift,
#                 'actual_intervals': actual_interval,
#                 'expected_intervals': expected_interval,

#                 # LED control data
#                 'led_power_percent': esp32_timing.get('led_power_actual', 0),
#                 'led_duration_ms': esp32_timing.get('led_duration_actual', 0),
#                 'led_sync_success': esp32_timing.get('led_duration_actual', 0) > 0,
#                 'led_type_used': led_type_str,
#                 'led_type_numeric': led_type_numeric,

#                 # Environmental data
#                 'temperature': esp32_timing.get('temperature', 0.0),
#                 'humidity': esp32_timing.get('humidity', 0.0),

#                 # Frame statistics
#                 'frame_mean': frame_stats['mean'],
#                 'frame_max': frame_stats['max'],
#                 'frame_min': frame_stats['min'],
#                 'frame_std': frame_stats['std'],

#                 # Capture method
#                 'capture_method': frame_metadata.get('source', 'unknown'),

#                 # ========================================================================
#                 # ✅ NEW: COMPREHENSIVE PHASE DATA FOR CIRCADIAN ANALYSIS
#                 # ========================================================================

#                 # Phase state
#                 'current_phase': phase_str,
#                 'phase_numeric': phase_numeric,
#                 'phase_enabled': phase_info.get('phase_enabled', False),

#                 # Phase timing (in minutes for biological relevance)
#                 'phase_elapsed_min': phase_info.get('phase_elapsed_min', 0.0),
#                 'phase_remaining_min': phase_info.get('phase_remaining_min', 0.0),

#                 # Cycle tracking
#                 'cycle_number': phase_info.get('cycle_number', 1),
#                 'total_cycles': phase_info.get('total_cycles', 1),

#                 # Transition tracking
#                 'phase_transition': phase_info.get('phase_transition', False),
#                 'transition_count': getattr(self, 'phase_transition_count', 0)
#             }

#             # ✅ APPEND: Resize and append to each dataset
#             for dataset_name, value in datasets_data.items():
#                 dataset = timeseries_group[dataset_name]
#                 dataset.resize((frame_num + 1,))
#                 dataset[frame_num] = value

#             # ✅ ENHANCED: Comprehensive logging with phase and timing info
#             led_duration = esp32_timing.get('led_duration_actual', 0)
#             temp = esp32_timing.get('temperature', 0)
#             phase_enabled = phase_info.get('phase_enabled', False)

#             if phase_enabled:
#                 cycle_num = phase_info.get('cycle_number', 1)
#                 phase_elapsed = phase_info.get('phase_elapsed_min', 0)
#                 transition_marker = " [TRANSITION]" if phase_info.get('phase_transition', False) else ""

#                 print(f"Frame {frame_num}: {phase_str.upper()} phase (cycle {cycle_num}, {phase_elapsed:.1f}min), "
#                       f"{led_type_str.upper()} LED, expected={expected_interval:.1f}s, actual={actual_interval:.1f}s, "
#                       f"drift={frame_drift:.3f}s ({frame_drift*1000:.1f}ms), T={temp:.1f}°C{transition_marker}")
#             else:
#                 print(f"Frame {frame_num}: CONTINUOUS mode, {led_type_str.upper()} LED, "
#                       f"expected={expected_interval:.1f}s, actual={actual_interval:.1f}s, "
#                       f"drift={frame_drift:.3f}s ({frame_drift*1000:.1f}ms), T={temp:.1f}°C")

#             # ✅ QUALITY: Timing quality assessment every 10 frames
#             if frame_num > 0 and frame_num % 10 == 0:
#                 drift_abs = abs(frame_drift)
#                 if drift_abs < 0.05:  # < 50ms
#                     quality = "excellent"
#                 elif drift_abs < 0.1:  # < 100ms
#                     quality = "good"
#                 elif drift_abs < 0.2:  # < 200ms
#                     quality = "acceptable"
#                 else:
#                     quality = "poor"

#                 phase_quality = f", Phase: {phase_str}" if phase_enabled else ""
#                 print(f"  Frame {frame_num}: Timing quality = {quality} "
#                       f"(drift: {drift_abs*1000:.1f}ms){phase_quality}")

#         except Exception as e:
#             error_msg = f"Error appending phase-aware time-series data: {e}"
#             print(error_msg)
#             self.error_occurred.emit(error_msg)

#     def _extract_phase_metadata(self, frame_metadata: dict) -> dict:
#         """Extract and validate phase metadata from frame metadata."""
#         return {
#             'phase_enabled': frame_metadata.get('phase_enabled', False),
#             'current_phase': frame_metadata.get('current_phase', 'continuous'),
#             'led_type_used': frame_metadata.get('led_type_used', 'ir'),
#             'phase_elapsed_min': frame_metadata.get('phase_elapsed_min', 0.0),
#             'phase_remaining_min': frame_metadata.get('phase_remaining_min', 0.0),
#             'cycle_number': frame_metadata.get('cycle_number', 1),
#             'total_cycles': frame_metadata.get('total_cycles', 1),
#             'phase_transition': frame_metadata.get('phase_transition', False)
#         }

#     def _process_phase_transition(self, frame_num: int, frame_metadata: dict):
#         """Process and log phase transitions for analysis."""
#         current_phase = frame_metadata.get('current_phase', 'continuous')
#         is_transition = frame_metadata.get('phase_transition', False)

#         # Track phase transitions
#         if is_transition and current_phase != self.last_phase:
#             self.phase_transition_count += 1

#             # Update cycle count on light->dark transitions (end of cycle)
#             if self.last_phase == 'light' and current_phase == 'dark':
#                 self.cycle_count += 1

#             # Create phase transition record
#             transition_info = {
#                 'frame_number': frame_num,
#                 'timestamp': frame_metadata.get('timestamp', time.time()),
#                 'from_phase': self.last_phase,
#                 'to_phase': current_phase,
#                 'cycle_number': frame_metadata.get('cycle_number', 1),
#                 'transition_count': self.phase_transition_count,
#                 'led_type_change': f"{self.last_phase}_to_{current_phase}"
#             }

#             # Save to phase analysis group
#             try:
#                 phase_group = self.hdf5_file['phase_analysis']
#                 transition_dataset_name = f"transition_{self.phase_transition_count:03d}"

#                 transition_json = json.dumps(transition_info, default=str)
#                 transition_dataset = phase_group.create_dataset(
#                     transition_dataset_name,
#                     data=transition_json,
#                     dtype=h5py.string_dtype()
#                 )

#                 # Add attributes for easy querying
#                 transition_dataset.attrs['frame_number'] = frame_num
#                 transition_dataset.attrs['from_phase'] = self.last_phase or 'initial'
#                 transition_dataset.attrs['to_phase'] = current_phase
#                 transition_dataset.attrs['cycle_number'] = frame_metadata.get('cycle_number', 1)

#                 print(f"Phase transition {self.phase_transition_count}: {self.last_phase} → {current_phase} at frame {frame_num}")

#                 # Emit signal for real-time monitoring
#                 self.phase_transition_detected.emit(transition_info)

#             except Exception as e:
#                 print(f"Error saving phase transition: {e}")

#         self.last_phase = current_phase

#     def update_recording_metadata(self, metadata: dict):
#         """Update recording metadata with enhanced phase configuration support."""
#         self.recording_metadata.update(metadata)

#         # Update expected frame interval
#         if 'interval_seconds' in metadata:
#             old_interval = self.expected_frame_interval
#             self.expected_frame_interval = metadata['interval_seconds']
#             print(f"Expected frame interval: {old_interval:.1f}s → {self.expected_frame_interval:.1f}s")

#         # ✅ NEW: Handle phase configuration metadata
#         if 'phase_config' in metadata:
#             phase_config = metadata['phase_config']
#             self.recording_metadata['phase_enabled'] = phase_config.get('enabled', False)
#             self.recording_metadata['light_duration_min'] = phase_config.get('light_duration_min', 0)
#             self.recording_metadata['dark_duration_min'] = phase_config.get('dark_duration_min', 0)
#             self.recording_metadata['starts_with_light'] = phase_config.get('start_with_light', True)

#             print(f"Phase configuration updated:")
#             print(f"  - Enabled: {self.recording_metadata['phase_enabled']}")
#             if self.recording_metadata['phase_enabled']:
#                 print(f"  - Light phase: {self.recording_metadata['light_duration_min']}min")
#                 print(f"  - Dark phase: {self.recording_metadata['dark_duration_min']}min")
#                 print(f"  - Starts with: {'Light' if self.recording_metadata['starts_with_light'] else 'Dark'}")

#         self.metadata_updated.emit(self.recording_metadata.copy())

#         # Save to HDF5 attributes
#         if self.hdf5_file:
#             for key, value in metadata.items():
#                 try:
#                     self.hdf5_file.attrs[key] = value
#                 except (TypeError, ValueError):
#                     # Convert to string if can't store directly
#                     self.hdf5_file.attrs[key] = str(value)

#     def finalize_recording(self):
#         """Finalize recording with comprehensive phase-aware statistics."""
#         if not self.hdf5_file:
#             return

#         try:
#             # Update final metadata
#             self.recording_metadata['end_time'] = time.time()
#             self.recording_metadata['total_duration'] = (
#                 self.recording_metadata['end_time'] - self.recording_metadata['start_time']
#             )
#             self.recording_metadata['actual_frames'] = self.frame_count
#             self.recording_metadata['phase_transitions'] = self.phase_transition_count
#             self.recording_metadata['cycles_completed'] = self.cycle_count

#             # Save final metadata to attributes
#             self.update_recording_metadata(self.recording_metadata)

#             # Add comprehensive statistics to timeseries group
#             if 'timeseries' in self.hdf5_file and self.frame_count > 0:
#                 timeseries_group = self.hdf5_file['timeseries']

#                 # Basic recording statistics
#                 timeseries_group.attrs['total_frames'] = self.frame_count
#                 timeseries_group.attrs['recording_duration'] = self.recording_metadata['total_duration']
#                 timeseries_group.attrs['mean_interval'] = self.recording_metadata.get('interval_seconds', 0)

#                 # ✅ NEW: Phase-specific statistics
#                 timeseries_group.attrs['phase_transitions'] = self.phase_transition_count
#                 timeseries_group.attrs['cycles_completed'] = self.cycle_count
#                 timeseries_group.attrs['phase_enabled'] = self.recording_metadata.get('phase_enabled', False)

#                 # Calculate comprehensive statistics
#                 try:
#                     # Timing statistics
#                     if 'frame_drift' in timeseries_group and timeseries_group['frame_drift'].size > 0:
#                         drift_data = timeseries_group['frame_drift'][:]
#                         self._add_timing_statistics(timeseries_group, drift_data)

#                     # Interval statistics
#                     if 'actual_intervals' in timeseries_group and timeseries_group['actual_intervals'].size > 1:
#                         self._add_interval_statistics(timeseries_group)

#                     # ✅ NEW: Phase-specific statistics
#                     if self.recording_metadata.get('phase_enabled', False):
#                         self._add_phase_statistics(timeseries_group)

#                 except Exception as e:
#                     print(f"Could not calculate comprehensive statistics: {e}")

#             # ✅ NEW: Finalize phase analysis group
#             self._finalize_phase_analysis()

#             # Final summary
#             duration_hours = self.recording_metadata['total_duration'] / 3600
#             phase_text = f"({self.phase_transition_count} transitions, {self.cycle_count} cycles)" if self.recording_metadata.get('phase_enabled', False) else "(continuous mode)"

#             print(f"\n=== PHASE-AWARE RECORDING FINALIZED ===")
#             print(f"Frames: {self.frame_count}")
#             print(f"Duration: {duration_hours:.1f} hours")
#             print(f"Phase cycling: {phase_text}")
#             print(f"Data structure: Enhanced phase-aware timeseries")
#             print(f"File: {self.current_filepath}")

#             # Close file
#             self.hdf5_file.close()
#             self.hdf5_file = None

#         except Exception as e:
#             error_msg = f"Error finalizing phase-aware recording: {str(e)}"
#             print(error_msg)
#             self.error_occurred.emit(error_msg)

#     def _add_timing_statistics(self, timeseries_group, drift_data):
#         """Add comprehensive timing statistics with unit documentation."""
#         drift_stats = {
#             'mean_frame_drift_seconds': float(np.mean(drift_data)),
#             'mean_frame_drift_ms': float(np.mean(drift_data) * 1000),
#             'std_frame_drift_seconds': float(np.std(drift_data)),
#             'std_frame_drift_ms': float(np.std(drift_data) * 1000),
#             'max_frame_drift_seconds': float(np.max(drift_data)),
#             'max_frame_drift_ms': float(np.max(drift_data) * 1000),
#             'min_frame_drift_seconds': float(np.min(drift_data)),
#             'min_frame_drift_ms': float(np.min(drift_data) * 1000),
#             'timing_quality': 'excellent' if np.std(drift_data) < 0.05 else 'good' if np.std(drift_data) < 0.1 else 'acceptable'
#         }

#         for key, value in drift_stats.items():
#             timeseries_group.attrs[key] = value

#     def _add_interval_statistics(self, timeseries_group):
#         """Add interval accuracy statistics."""
#         actual_intervals = timeseries_group['actual_intervals'][1:]  # Skip first frame
#         expected_intervals = timeseries_group['expected_intervals'][1:]

#         interval_stats = {
#             'mean_actual_interval_seconds': float(np.mean(actual_intervals)),
#             'std_actual_interval_seconds': float(np.std(actual_intervals)),
#             'mean_expected_interval_seconds': float(np.mean(expected_intervals)),
#             'mean_interval_error_seconds': float(np.mean(actual_intervals - expected_intervals)),
#             'mean_interval_error_ms': float(np.mean(actual_intervals - expected_intervals) * 1000),
#             'std_interval_error_seconds': float(np.std(actual_intervals - expected_intervals)),
#             'std_interval_error_ms': float(np.std(actual_intervals - expected_intervals) * 1000)
#         }

#         for key, value in interval_stats.items():
#             timeseries_group.attrs[key] = value

#     def _add_phase_statistics(self, timeseries_group):
#         """Add phase-specific statistics for circadian analysis."""
#         try:
#             # Phase distribution
#             if 'current_phase' in timeseries_group:
#                 phases = timeseries_group['current_phase'][:]
#                 unique_phases, counts = np.unique(phases, return_counts=True)

#                 phase_distribution = {}
#                 for phase, count in zip(unique_phases, counts):
#                     if isinstance(phase, bytes):
#                         phase = phase.decode('utf-8')
#                     phase_distribution[f'{phase}_frames'] = int(count)
#                     phase_distribution[f'{phase}_percent'] = float(count / len(phases) * 100)

#                 for key, value in phase_distribution.items():
#                     timeseries_group.attrs[key] = value

#             # LED type usage
#             if 'led_type_used' in timeseries_group:
#                 led_types = timeseries_group['led_type_used'][:]
#                 unique_leds, counts = np.unique(led_types, return_counts=True)

#                 for led_type, count in zip(unique_leds, counts):
#                     if isinstance(led_type, bytes):
#                         led_type = led_type.decode('utf-8')
#                     timeseries_group.attrs[f'led_{led_type}_frames'] = int(count)
#                     timeseries_group.attrs[f'led_{led_type}_percent'] = float(count / len(led_types) * 100)

#             # Phase transition rate
#             if self.phase_transition_count > 0 and self.frame_count > 0:
#                 transition_rate = self.phase_transition_count / (self.recording_metadata['total_duration'] / 3600)  # per hour
#                 timeseries_group.attrs['phase_transitions_per_hour'] = float(transition_rate)

#             print(f"Phase statistics calculated: {self.phase_transition_count} transitions, {self.cycle_count} cycles")

#         except Exception as e:
#             print(f"Error calculating phase statistics: {e}")

#     def _finalize_phase_analysis(self):
#         """Finalize phase analysis group with summary information."""
#         try:
#             if 'phase_analysis' in self.hdf5_file:
#                 phase_group = self.hdf5_file['phase_analysis']

#                 # Add summary attributes
#                 phase_group.attrs['total_transitions'] = self.phase_transition_count
#                 phase_group.attrs['total_cycles'] = self.cycle_count
#                 phase_group.attrs['phase_enabled'] = self.recording_metadata.get('phase_enabled', False)

#                 if self.recording_metadata.get('phase_enabled', False):
#                     phase_group.attrs['light_duration_min'] = self.recording_metadata.get('light_duration_min', 0)
#                     phase_group.attrs['dark_duration_min'] = self.recording_metadata.get('dark_duration_min', 0)
#                     phase_group.attrs['starts_with_light'] = self.recording_metadata.get('starts_with_light', True)

#                 print(f"Phase analysis finalized: {len(phase_group.keys())} transition records")

#         except Exception as e:
#             print(f"Error finalizing phase analysis: {e}")

#     # ========================================================================
#     # ✅ ENHANCED: Utility methods for phase-aware analysis
#     # ========================================================================

#     def get_recording_info(self) -> dict:
#         """Get comprehensive recording information including phase status."""
#         info = self.recording_metadata.copy()
#         info['current_filepath'] = str(self.current_filepath) if self.current_filepath else None
#         info['frames_saved'] = self.frame_count
#         info['file_open'] = self.hdf5_file is not None
#         info['phase_transitions'] = getattr(self, 'phase_transition_count', 0)
#         info['cycles_completed'] = getattr(self, 'cycle_count', 0)
#         return info

#     @staticmethod
#     def load_phase_aware_recording(filepath: str) -> dict:
#         """Load phase-aware recording data from HDF5 file."""
#         try:
#             with h5py.File(filepath, 'r') as f:
#                 # Load basic information
#                 info = {
#                     'filepath': filepath,
#                     'created': f.attrs.get('created', 0),
#                     'experiment_name': f.attrs.get('experiment_name', 'Unknown'),
#                     'file_version': f.attrs.get('file_version', '1.0'),
#                     'total_frames': f.attrs.get('actual_frames', 0),
#                     'phase_support': f.attrs.get('phase_support', False)
#                 }

#                 # Load phase configuration
#                 if f.attrs.get('phase_enabled', False):
#                     info['phase_config'] = {
#                         'enabled': f.attrs.get('phase_enabled', False),
#                         'light_duration_min': f.attrs.get('light_duration_min', 0),
#                         'dark_duration_min': f.attrs.get('dark_duration_min', 0),
#                         'starts_with_light': f.attrs.get('starts_with_light', True),
#                         'transitions': f.attrs.get('phase_transitions', 0),
#                         'cycles': f.attrs.get('cycles_completed', 0)
#                     }

#                 # Load timeseries data
#                 if 'timeseries' in f:
#                     timeseries_group = f['timeseries']
#                     info['timeseries_datasets'] = list(timeseries_group.keys())
#                     info['timeseries_stats'] = dict(timeseries_group.attrs)

#                     # Load phase-specific datasets
#                     phase_datasets = ['current_phase', 'led_type_used', 'cycle_number', 'phase_transition']
#                     info['phase_timeseries'] = {}
#                     for dataset_name in phase_datasets:
#                         if dataset_name in timeseries_group:
#                             info['phase_timeseries'][dataset_name] = timeseries_group[dataset_name][:]

#                 # Load phase analysis data
#                 if 'phase_analysis' in f:
#                     phase_group = f['phase_analysis']
#                     info['phase_analysis'] = {
#                         'transition_count': len(phase_group.keys()),
#                         'transition_records': list(phase_group.keys()),
#                         'analysis_attrs': dict(phase_group.attrs)
#                     }

#                 return info

#         except Exception as e:
#             raise RuntimeError(f"Failed to load phase-aware recording: {str(e)}")

#     @staticmethod
#     def get_phase_transitions(filepath: str) -> List[dict]:
#         """Extract all phase transitions from phase-aware recording file."""
#         try:
#             transitions = []
#             with h5py.File(filepath, 'r') as f:
#                 if 'phase_analysis' in f:
#                     phase_group = f['phase_analysis']
#                     for transition_name in phase_group.keys():
#                         if transition_name.startswith('transition_'):
#                             transition_json = phase_group[transition_name][()]
#                             if isinstance(transition_json, bytes):
#                                 transition_json = transition_json.decode('utf-8')
#                             transition_data = json.loads(transition_json)
#                             transitions.append(transition_data)

#                     # Sort by frame number
#                     transitions.sort(key=lambda x: x.get('frame_number', 0))

#             return transitions

#         except Exception as e:
#             raise RuntimeError(f"Failed to load phase transitions: {str(e)}")

#     # ========================================================================
#     # ✅ ENHANCED: File analysis and repair utilities
#     # ========================================================================

#     def close_file(self):
#         """Close the current HDF5 file with cleanup."""
#         if self.hdf5_file:
#             try:
#                 self.hdf5_file.close()
#             except:
#                 pass
#             finally:
#                 self.hdf5_file = None
#                 self.current_filepath = None
#                 self.frame_count = 0
#                 self.phase_transition_count = 0
#                 self.cycle_count = 0
#                 self.last_phase = None

#     def is_file_open(self) -> bool:
#         """Check if a file is currently open."""
#         return self.hdf5_file is not None

#     @staticmethod
#     def get_phase_aware_file_info(filepath: str) -> dict:
#         """Get comprehensive information about phase-aware HDF5 file."""
#         try:
#             with h5py.File(filepath, 'r') as f:
#                 info = {
#                     'filepath': filepath,
#                     'created': f.attrs.get('created', 0),
#                     'created_human': f.attrs.get('created_human', 'Unknown'),
#                     'experiment_name': f.attrs.get('experiment_name', 'Unknown'),
#                     'file_version': f.attrs.get('file_version', '1.0'),
#                     'software': f.attrs.get('software', 'Unknown'),
#                     'total_frames': f.attrs.get('actual_frames', 0),
#                     'duration_minutes': f.attrs.get('duration_minutes', 0),
#                     'interval_seconds': f.attrs.get('interval_seconds', 0),
#                     'groups': list(f.keys()),
#                     'file_size_mb': Path(filepath).stat().st_size / (1024 * 1024),
#                     'phase_support': f.attrs.get('phase_support', False),
#                     'phase_enabled': f.attrs.get('phase_enabled', False)
#                 }

#                 # Phase-specific information
#                 if info['phase_enabled']:
#                     info['phase_info'] = {
#                         'light_duration_min': f.attrs.get('light_duration_min', 0),
#                         'dark_duration_min': f.attrs.get('dark_duration_min', 0),
#                         'starts_with_light': f.attrs.get('starts_with_light', True),
#                         'transitions': f.attrs.get('phase_transitions', 0),
#                         'cycles_completed': f.attrs.get('cycles_completed', 0)
#                     }

#                 # Dataset counts
#                 for group_name in ['images', 'metadata', 'timeseries', 'phase_analysis']:
#                     if group_name in f:
#                         info[f'{group_name}_count'] = len(f[group_name].keys())

#                 # Timeseries dataset list
#                 if 'timeseries' in f:
#                     info['timeseries_datasets'] = list(f['timeseries'].keys())
#                     info['has_phase_datasets'] = any(name in f['timeseries'] for name in
#                                                    ['current_phase', 'led_type_used', 'cycle_number'])

#                 return info

#         except Exception as e:
#             raise RuntimeError(f"Failed to get phase-aware file info: {str(e)}")

#     @staticmethod
#     def load_frame(filepath: str, frame_number: int) -> tuple[np.ndarray, dict]:
#         """Load specific frame and metadata from phase-aware HDF5 file."""
#         try:
#             with h5py.File(filepath, 'r') as f:
#                 # Load image
#                 frame_dataset_name = f"frame_{frame_number:06d}"
#                 if frame_dataset_name not in f['images']:
#                     raise ValueError(f"Frame {frame_number} not found")

#                 frame = f['images'][frame_dataset_name][()]

#                 # Load comprehensive metadata including phase info
#                 metadata_dataset_name = f"metadata_{frame_number:06d}"
#                 if metadata_dataset_name in f['metadata']:
#                     metadata_json = f['metadata'][metadata_dataset_name][()]
#                     if isinstance(metadata_json, bytes):
#                         metadata_json = metadata_json.decode('utf-8')
#                     metadata = json.loads(metadata_json)
#                 else:
#                     metadata = {}

#                 # Add frame attributes to metadata
#                 frame_dataset = f['images'][frame_dataset_name]
#                 for attr_name, attr_value in frame_dataset.attrs.items():
#                     if isinstance(attr_value, bytes):
#                         attr_value = attr_value.decode('utf-8')
#                     metadata[f'frame_attr_{attr_name}'] = attr_value

#                 return frame, metadata

#         except Exception as e:
#             raise RuntimeError(f"Failed to load frame {frame_number}: {str(e)}")

#     @staticmethod
#     def fix_expected_intervals_in_phase_file(filepath: str, expected_interval: float):
#         """Fix expected_intervals in existing phase-aware HDF5 file."""
#         try:
#             with h5py.File(filepath, 'r+') as f:
#                 if 'timeseries' in f and 'expected_intervals' in f['timeseries']:
#                     dataset = f['timeseries']['expected_intervals']
#                     old_values = dataset[:5] if len(dataset) > 0 else []

#                     print(f"Fixing {len(dataset)} expected_intervals in phase-aware file:")
#                     print(f"  Old values (first 5): {old_values}")
#                     print(f"  New value: {expected_interval}s (constant for all frames)")

#                     dataset[:] = expected_interval
#                     dataset.attrs['fixed'] = True
#                     dataset.attrs['fix_timestamp'] = time.time()
#                     dataset.attrs['fix_description'] = f'Fixed to constant {expected_interval} seconds'
#                     dataset.attrs['units'] = 'seconds'
#                     dataset.attrs['phase_aware_fix'] = True

#                     print(f"✅ Phase-aware expected_intervals fixed to {expected_interval}s!")
#                     return True
#                 else:
#                     print("No timeseries/expected_intervals found in phase-aware file")
#                     return False
#         except Exception as e:
#             print(f"Error fixing phase-aware file: {e}")
#             return False

"""Phase-aware data manager for HDF5 file storage and metadata management with day/night cycle support
and memory optimization for 72-hour recordings - CORRECTED VERSION with unified methods and efficient operations."""

import h5py
import numpy as np
import time
import json
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterator
from qtpy.QtCore import QObject

# ✅ FIX: pyqtSignal Import with try/except
try:
    from qtpy.QtCore import pyqtSignal
except ImportError:
    from qtpy.QtCore import Signal as pyqtSignal

# Setup logging
logger = logging.getLogger(__name__)


class ChunkedTimeseriesWriter:
    """Efficient chunked writer for HDF5 timeseries datasets to avoid per-frame resize overhead."""

    def __init__(self, group: h5py.Group, chunk_size: int = 100):
        self.group = group
        self.chunk_size = chunk_size
        self.current_capacity = 0
        self.datasets = {}
        self.written_frames = 0
        self._lock = threading.Lock()

    def register_dataset(self, name: str, dataset: h5py.Dataset):
        """Register a dataset for chunked operations."""
        with self._lock:
            self.datasets[name] = dataset

    def ensure_capacity(self, required_size: int):
        """Resize datasets in chunks to avoid per-frame overhead."""
        if required_size >= self.current_capacity:
            new_capacity = ((required_size // self.chunk_size) + 1) * self.chunk_size
            logger.debug(f"Resizing datasets to {new_capacity} (from {self.current_capacity})")

            for name, dataset in self.datasets.items():
                try:
                    dataset.resize((new_capacity,))
                except Exception as e:
                    logger.error(f"Failed to resize dataset {name}: {e}")
                    continue

            self.current_capacity = new_capacity
            logger.info(
                f"Datasets resized to {new_capacity} frames (chunk size: {self.chunk_size})"
            )

    def write_frame_data(self, frame_num: int, data_dict: dict):
        """Write frame data with chunked resizing."""
        with self._lock:
            self.ensure_capacity(frame_num + 1)

            for dataset_name, value in data_dict.items():
                if dataset_name in self.datasets:
                    try:
                        self.datasets[dataset_name][frame_num] = value
                    except Exception as e:
                        logger.warning(f"Failed to write {dataset_name} at frame {frame_num}: {e}")
                        continue

            self.written_frames = max(self.written_frames, frame_num + 1)


class DataManager(QObject):
    """Memory-optimized phase-aware data manager with unified save operations and efficient dataset management."""

    # Unit definitions for clarity and scientific consistency
    UNITS = {
        "time": "seconds",
        "temperature": "celsius",
        "humidity": "percent",
        "led_power": "percent",
        "led_duration": "milliseconds",
        "frame_drift": "seconds",
        "intervals": "seconds",
        "phase_duration": "minutes",
        "cycle_number": "dimensionless",
    }

    # Signals
    file_created = pyqtSignal(str)  # filepath
    frame_saved = pyqtSignal(int)  # frame_number
    metadata_updated = pyqtSignal(dict)  # metadata
    error_occurred = pyqtSignal(str)  # error message
    phase_transition_detected = pyqtSignal(dict)  # phase transition info

    def __init__(self):
        super().__init__()
        self.hdf5_file = None
        self.current_filepath = None
        self.frame_count = 0
        self.recording_metadata = {}
        self.expected_frame_interval = 5.0  # Default 5 seconds

        # Phase tracking for transition detection
        self.last_phase = None
        self.phase_transition_count = 0
        self.cycle_count = 0

        # ✅ CRITICAL: Thread safety for HDF5 operations
        self._hdf5_lock = threading.Lock()

        # ✅ EFFICIENT: Chunked timeseries writer
        self.chunked_writer = None

        # ✅ MEMORY: Frame statistics cache for single-pass calculations
        self.last_timestamp = None
        self.recording_start_time = None

    def create_recording_file(
        self, output_dir: str, experiment_name: str = None, timestamped: bool = True
    ) -> str:
        """Create new HDF5 file for phase-aware recording with enhanced structure."""
        with self._hdf5_lock:
            # Generate filename
            if experiment_name is None:
                experiment_name = "nematostella_timelapse"

            timestamp = time.strftime("%Y%m%d_%H%M%S") if timestamped else ""
            filename = f"{experiment_name}_{timestamp}.h5" if timestamp else f"{experiment_name}.h5"

            # Create output directory if it doesn't exist
            output_path = Path(output_dir)
            if timestamped:
                # Create timestamped subdirectory
                timestamp_dir = time.strftime("%Y%m%d_%H%M%S")
                output_path = output_path / timestamp_dir

            output_path.mkdir(parents=True, exist_ok=True)

            self.current_filepath = output_path / filename

            try:
                # Create HDF5 file
                self.hdf5_file = h5py.File(self.current_filepath, "w")

                # Clean structure with phase support
                images_group = self.hdf5_file.create_group("images")
                metadata_group = self.hdf5_file.create_group("metadata")
                phase_group = self.hdf5_file.create_group("phase_analysis")

                # Create attributes for file metadata
                self.hdf5_file.attrs["created"] = time.time()
                self.hdf5_file.attrs["created_human"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.hdf5_file.attrs["experiment_name"] = experiment_name
                self.hdf5_file.attrs["file_version"] = "4.0"  # ✅ NEW: Corrected version
                self.hdf5_file.attrs["software"] = "napari-timelapse-capture-phase-aware-corrected"
                self.hdf5_file.attrs["structure"] = "phase_aware_timeseries_chunked"
                self.hdf5_file.attrs["phase_support"] = True
                self.hdf5_file.attrs["memory_optimized"] = True
                self.hdf5_file.attrs["chunked_datasets"] = True

                # Initialize frame and phase counters
                self.frame_count = 0
                self.phase_transition_count = 0
                self.cycle_count = 0
                self.last_phase = None

                # Initialize recording metadata with phase support
                self.recording_metadata = {
                    "start_time": time.time(),
                    "expected_frames": 0,
                    "actual_frames": 0,
                    "duration_minutes": 0,
                    "interval_seconds": 0,
                    "led_power": 0,
                    "camera_settings": {},
                    "esp32_settings": {},
                    "phase_enabled": False,
                    "phase_config": {},
                    "phase_transitions": 0,
                    "cycles_completed": 0,
                }

                self.file_created.emit(str(self.current_filepath))
                logger.info(f"Corrected phase-aware HDF5 file created: {self.current_filepath}")
                return str(self.current_filepath)

            except Exception as e:
                error_msg = f"Failed to create phase-aware HDF5 file: {str(e)}"
                self.error_occurred.emit(error_msg)
                raise RuntimeError(error_msg)

    # ========================================================================
    # ✅ UNIFIED SAVE METHOD - No more code duplication
    # ========================================================================

    def save_frame(
        self,
        frame: np.ndarray,
        frame_metadata: dict,
        esp32_timing: dict,
        python_timing: dict,
        memory_optimized: bool = True,
    ) -> bool:
        """Unified frame saving with optional memory optimization."""
        if not self.hdf5_file:
            raise RuntimeError("No HDF5 file open")

        frame_num = self.frame_count

        with self._hdf5_lock:
            try:
                logger.debug(
                    f"Saving frame {frame_num}: {frame.shape}, {frame.nbytes//1024}KB, "
                    f"memory_optimized={memory_optimized}"
                )

                # ✅ MEMORY: Pre-validate frame before any processing
                if frame is None or frame.size == 0:
                    raise ValueError("Invalid frame: None or empty")

                # Get group references
                images_group = self.hdf5_file["images"]
                metadata_group = self.hdf5_file["metadata"]

                # ✅ CRITICAL: Write frame to HDF5 immediately
                frame_dataset_name = f"frame_{frame_num:06d}"

                if memory_optimized:
                    # High compression for long recordings
                    compression_opts = 6
                    shuffle = True
                    fletcher32 = True
                else:
                    # Faster compression for shorter recordings
                    compression_opts = 1
                    shuffle = False
                    fletcher32 = False

                frame_dataset = images_group.create_dataset(
                    frame_dataset_name,
                    data=frame,
                    compression="gzip",
                    compression_opts=compression_opts,
                    shuffle=shuffle,
                    fletcher32=fletcher32,
                )

                # Add essential frame attributes
                frame_dataset.attrs["timestamp"] = frame_metadata.get("timestamp", time.time())
                frame_dataset.attrs["frame_number"] = frame_num
                frame_dataset.attrs["source"] = frame_metadata.get("source", "unknown")

                # Phase attributes (lightweight)
                if frame_metadata.get("phase_enabled", False):
                    frame_dataset.attrs["current_phase"] = frame_metadata.get(
                        "current_phase", "continuous"
                    )
                    frame_dataset.attrs["led_type_used"] = frame_metadata.get("led_type_used", "ir")
                    frame_dataset.attrs["cycle_number"] = frame_metadata.get("cycle_number", 1)

                # ✅ EFFICIENT: Create timeseries datasets on first frame with chunked writer
                if frame_num == 0:
                    self._create_chunked_timeseries_datasets()

                # ✅ EFFICIENT: Append to timeseries with chunked operations
                self._append_timeseries_data_chunked(
                    frame_num, frame, frame_metadata, esp32_timing, python_timing
                )

                # ✅ EFFICIENT: Save minimal metadata
                essential_metadata = self._create_essential_metadata(
                    frame_num, frame_metadata, esp32_timing, python_timing
                )

                metadata_dataset_name = f"metadata_{frame_num:06d}"
                metadata_json = json.dumps(
                    essential_metadata, separators=(",", ":")
                )  # Compact JSON
                metadata_dataset = metadata_group.create_dataset(
                    metadata_dataset_name,
                    data=metadata_json,
                    dtype=h5py.string_dtype(),
                    compression="gzip" if memory_optimized else None,
                    compression_opts=3 if memory_optimized else None,
                )

                # ✅ EFFICIENT: Handle phase transitions (lightweight processing)
                self._process_phase_transition_efficient(frame_num, frame_metadata)

                # Update counters
                self.frame_count += 1
                self.recording_metadata["actual_frames"] = self.frame_count

                # ✅ MEMORY: Flush to disk periodically for long recordings
                flush_interval = 5 if memory_optimized else 10
                if frame_num % flush_interval == 0:
                    self.hdf5_file.flush()

                # ✅ MEMORY: Memory usage logging for long recordings
                if memory_optimized and frame_num % 100 == 0:
                    self._log_memory_usage(frame_num)

                self.frame_saved.emit(frame_num)
                logger.debug(f"Frame {frame_num}: saved to HDF5 successfully")
                return True

            except Exception as e:
                error_msg = f"Save failed for frame {frame_num}: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False

    def save_frame_streaming(
        self, frame: np.ndarray, frame_metadata: dict, esp32_timing: dict, python_timing: dict
    ) -> bool:
        """Convenience method for memory-optimized streaming - calls unified save method."""
        return self.save_frame(
            frame, frame_metadata, esp32_timing, python_timing, memory_optimized=True
        )

    # ========================================================================
    # ✅ EFFICIENT HELPER METHODS
    # ========================================================================

    def _create_essential_metadata(
        self, frame_num: int, frame_metadata: dict, esp32_timing: dict, python_timing: dict
    ) -> dict:
        """Create minimal metadata object to avoid copying large dictionaries."""
        essential_metadata = {
            "frame_number": frame_num,
            "timestamp": frame_metadata.get("timestamp", time.time()),
            "source": frame_metadata.get("source", "unknown"),
            "led_power": esp32_timing.get("led_power_actual", 0),
            "temperature": esp32_timing.get("temperature", 0.0),
            "humidity": esp32_timing.get("humidity", 0.0),
            "phase_enabled": frame_metadata.get("phase_enabled", False),
        }

        # Add phase info only if enabled (avoid unnecessary data)
        if frame_metadata.get("phase_enabled", False):
            essential_metadata.update(
                {
                    "current_phase": frame_metadata.get("current_phase", "continuous"),
                    "led_type_used": frame_metadata.get("led_type_used", "ir"),
                    "cycle_number": frame_metadata.get("cycle_number", 1),
                }
            )

        return essential_metadata

    def _calculate_frame_stats_single_pass(self, frame: np.ndarray) -> dict:
        """True single-pass frame statistics calculation."""
        if frame is None or frame.size == 0:
            return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}

        try:
            # ✅ EFFICIENT: Single flatten operation, then all stats from same view
            flat_frame = frame.ravel()

            # Calculate all statistics in one pass where possible
            stats = {
                "mean": float(np.mean(flat_frame)),
                "min": float(np.min(flat_frame)),
                "max": float(np.max(flat_frame)),
                "std": float(np.std(flat_frame)),
            }

            # Immediate cleanup
            del flat_frame
            return stats

        except Exception as e:
            logger.warning(f"Frame statistics calculation failed: {e}")
            return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}

    def _log_memory_usage(self, frame_num: int):
        """Log memory usage during long recordings."""
        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            system_memory = psutil.virtual_memory()

            logger.info(
                f"Frame {frame_num}: Process memory: {memory_mb:.1f}MB, "
                f"System available: {system_memory.available/(1024**3):.1f}GB"
            )
        except ImportError:
            logger.debug(f"Frame {frame_num}: psutil not available for memory monitoring")
        except Exception as e:
            logger.debug(f"Memory usage logging failed: {e}")

    # ========================================================================
    # ✅ CHUNKED TIMESERIES OPERATIONS - Efficient dataset management
    # ========================================================================

    def _create_chunked_timeseries_datasets(self):
        """Create time-series datasets with chunked writer for efficiency."""
        try:
            # Create time-series group
            timeseries_group = self.hdf5_file.create_group("timeseries")

            # ✅ EFFICIENT: Initialize chunked writer
            self.chunked_writer = ChunkedTimeseriesWriter(timeseries_group, chunk_size=100)

            # Dataset definitions with proper dtypes
            datasets_config = {
                # Core frame indexing
                "frame_index": "i4",
                # Timing data (all in seconds)
                "frame_intervals": "f8",
                "capture_timestamps": "f8",
                "expected_timestamps": "f8",
                "frame_drift": "f8",
                "cumulative_drift": "f8",
                "actual_intervals": "f8",
                "expected_intervals": "f8",
                # LED control data
                "led_power_percent": "f4",
                "led_duration_ms": "f4",
                "led_sync_success": "bool",
                "led_type_used": h5py.string_dtype(),
                "led_type_numeric": "i1",  # 0=IR, 1=White
                # Environmental data
                "temperature": "f4",
                "humidity": "f4",
                # Frame statistics
                "frame_mean": "f4",
                "frame_max": "f4",
                "frame_min": "f4",
                "frame_std": "f4",
                # Capture method
                "capture_method": h5py.string_dtype(),
                # Phase datasets
                "current_phase": h5py.string_dtype(),
                "phase_numeric": "i1",  # 0=continuous, 1=light, 2=dark
                "phase_enabled": "bool",
                "phase_elapsed_min": "f4",
                "phase_remaining_min": "f4",
                "cycle_number": "i4",
                "total_cycles": "i4",
                "phase_transition": "bool",
                "transition_count": "i4",
            }

            # Create datasets and register with chunked writer
            for dataset_name, dtype in datasets_config.items():
                dataset = timeseries_group.create_dataset(
                    dataset_name,
                    shape=(0,),
                    maxshape=(None,),
                    dtype=dtype,
                    chunks=True,  # Enable chunking for efficient resizing
                    compression=(
                        "gzip"
                        if dataset_name in ["capture_method", "current_phase", "led_type_used"]
                        else None
                    ),
                )
                self.chunked_writer.register_dataset(dataset_name, dataset)

            # Group-level documentation
            timeseries_group.attrs["description"] = (
                "Phase-aware time-series data with chunked operations"
            )
            timeseries_group.attrs["x_axis"] = "frame_index"
            timeseries_group.attrs["phase_support"] = True
            timeseries_group.attrs["chunked_operations"] = True
            timeseries_group.attrs["chunk_size"] = self.chunked_writer.chunk_size

            # Unit definitions
            for unit_key, unit_value in self.UNITS.items():
                timeseries_group.attrs[f"units_{unit_key}"] = unit_value

            logger.info(
                f"Chunked phase-aware time-series datasets created with chunk size {self.chunked_writer.chunk_size}"
            )

        except Exception as e:
            error_msg = f"Error creating chunked time-series datasets: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)

    def _append_timeseries_data_chunked(
        self,
        frame_num: int,
        frame: np.ndarray,
        frame_metadata: dict,
        esp32_timing: dict,
        python_timing: dict,
    ):
        """Append data to time-series datasets using efficient chunked operations."""
        try:
            # ✅ EFFICIENT: Calculate timing values (lightweight operations)
            current_timestamp = frame_metadata.get("timestamp", time.time())
            expected_timestamp = python_timing.get("expected_time", current_timestamp)
            frame_drift = python_timing.get("frame_drift", 0.0)
            cumulative_drift = python_timing.get("cumulative_drift", 0.0)

            # Calculate intervals
            if frame_num == 0:
                actual_interval = 0.0
                self.last_timestamp = current_timestamp
                self.recording_start_time = current_timestamp
            else:
                actual_interval = current_timestamp - getattr(
                    self, "last_timestamp", current_timestamp
                )
                self.last_timestamp = current_timestamp

            expected_interval = self.expected_frame_interval
            frame_interval_from_start = current_timestamp - getattr(
                self, "recording_start_time", current_timestamp
            )

            # ✅ EFFICIENT: Single-pass frame statistics
            frame_stats = self._calculate_frame_stats_single_pass(frame)

            # ✅ EFFICIENT: Extract minimal phase info
            phase_str = frame_metadata.get("current_phase", "continuous")
            led_type_str = frame_metadata.get("led_type_used", "ir")
            phase_enabled = frame_metadata.get("phase_enabled", False)

            # Numeric conversions (lightweight)
            led_type_numeric = 1 if led_type_str.lower() == "white" else 0
            phase_numeric = 1 if phase_str == "light" else (2 if phase_str == "dark" else 0)

            # ✅ EFFICIENT: Create data dictionary with primitive types only
            datasets_data = {
                "frame_index": frame_num,
                "frame_intervals": frame_interval_from_start,
                "capture_timestamps": current_timestamp,
                "expected_timestamps": expected_timestamp,
                "frame_drift": frame_drift,
                "cumulative_drift": cumulative_drift,
                "actual_intervals": actual_interval,
                "expected_intervals": expected_interval,
                "led_power_percent": esp32_timing.get("led_power_actual", 0),
                "led_duration_ms": esp32_timing.get("led_duration_actual", 0),
                "led_sync_success": esp32_timing.get("led_duration_actual", 0) > 0,
                "led_type_used": led_type_str,
                "led_type_numeric": led_type_numeric,
                "temperature": esp32_timing.get("temperature", 0.0),
                "humidity": esp32_timing.get("humidity", 0.0),
                "frame_mean": frame_stats["mean"],
                "frame_max": frame_stats["max"],
                "frame_min": frame_stats["min"],
                "frame_std": frame_stats["std"],
                "capture_method": frame_metadata.get("source", "unknown"),
                "current_phase": phase_str,
                "phase_numeric": phase_numeric,
                "phase_enabled": phase_enabled,
                "phase_elapsed_min": frame_metadata.get("phase_elapsed_min", 0.0),
                "phase_remaining_min": frame_metadata.get("phase_remaining_min", 0.0),
                "cycle_number": frame_metadata.get("cycle_number", 1),
                "total_cycles": frame_metadata.get("total_cycles", 1),
                "phase_transition": frame_metadata.get("phase_transition", False),
                "transition_count": getattr(self, "phase_transition_count", 0),
            }

            # ✅ EFFICIENT: Use chunked writer for batch operations
            self.chunked_writer.write_frame_data(frame_num, datasets_data)

            # ✅ MEMORY: Clear local variables immediately
            del datasets_data, frame_stats

        except Exception as e:
            logger.error(f"Chunked timeseries append error: {e}")

    def _process_phase_transition_efficient(self, frame_num: int, frame_metadata: dict):
        """Efficient phase transition processing with minimal memory footprint."""
        current_phase = frame_metadata.get("current_phase", "continuous")
        is_transition = frame_metadata.get("phase_transition", False)

        if is_transition and current_phase != self.last_phase:
            self.phase_transition_count += 1

            if self.last_phase == "light" and current_phase == "dark":
                self.cycle_count += 1

            # ✅ EFFICIENT: Create minimal transition record (essential data only)
            transition_info = {
                "frame_number": frame_num,
                "timestamp": frame_metadata.get("timestamp", time.time()),
                "from_phase": self.last_phase or "initial",
                "to_phase": current_phase,
                "cycle_number": frame_metadata.get("cycle_number", 1),
                "transition_count": self.phase_transition_count,
            }

            try:
                phase_group = self.hdf5_file["phase_analysis"]
                transition_dataset_name = f"transition_{self.phase_transition_count:03d}"

                # Compact JSON with no whitespace
                transition_json = json.dumps(transition_info, separators=(",", ":"))
                transition_dataset = phase_group.create_dataset(
                    transition_dataset_name,
                    data=transition_json,
                    dtype=h5py.string_dtype(),
                    compression="gzip",
                )

                # Minimal attributes
                transition_dataset.attrs["frame_number"] = frame_num
                transition_dataset.attrs["from_phase"] = self.last_phase or "initial"
                transition_dataset.attrs["to_phase"] = current_phase

                logger.info(
                    f"Phase transition {self.phase_transition_count}: {self.last_phase} → {current_phase}"
                )

                # ✅ MEMORY: Emit signal but don't hold reference to transition_info
                self.phase_transition_detected.emit(transition_info.copy())

            except Exception as e:
                logger.error(f"Transition save error: {e}")

        self.last_phase = current_phase

    # ========================================================================
    # ✅ MEMORY-EFFICIENT LOADING AND ANALYSIS METHODS
    # ========================================================================

    @staticmethod
    def iter_frames(filepath: str, start_frame: int = 0, end_frame: int = None) -> Iterator[tuple]:
        """Memory-efficient frame iterator for analysis."""
        try:
            with h5py.File(filepath, "r") as f:
                if "images" not in f:
                    raise ValueError("No images group found in file")

                images_group = f["images"]
                frame_keys = sorted([k for k in images_group.keys() if k.startswith("frame_")])

                if end_frame is None:
                    end_frame = len(frame_keys)

                for i in range(start_frame, min(end_frame, len(frame_keys))):
                    frame_key = frame_keys[i]
                    frame_data = images_group[frame_key][()]

                    # Get frame attributes
                    attrs = dict(images_group[frame_key].attrs)

                    yield i, frame_data, attrs

        except Exception as e:
            raise RuntimeError(f"Failed to iterate frames: {str(e)}")

    @staticmethod
    def iter_phase_transitions(filepath: str) -> Iterator[dict]:
        """Memory-efficient phase transition iterator."""
        try:
            with h5py.File(filepath, "r") as f:
                if "timeseries" not in f:
                    return

                timeseries_group = f["timeseries"]
                if "current_phase" not in timeseries_group or "frame_index" not in timeseries_group:
                    return

                phase_data = timeseries_group["current_phase"]
                frame_indices = timeseries_group["frame_index"]

                last_phase = None
                for i in range(len(phase_data)):
                    current_phase = phase_data[i]
                    if isinstance(current_phase, bytes):
                        current_phase = current_phase.decode("utf-8")

                    if last_phase is not None and current_phase != last_phase:
                        yield {
                            "frame": int(frame_indices[i]),
                            "from_phase": last_phase,
                            "to_phase": current_phase,
                            "transition_index": i,
                        }

                    last_phase = current_phase

        except Exception as e:
            raise RuntimeError(f"Failed to iterate phase transitions: {str(e)}")

    @staticmethod
    def get_file_summary(filepath: str) -> dict:
        """Get file summary without loading large datasets into memory."""
        try:
            with h5py.File(filepath, "r") as f:
                summary = {
                    "filepath": filepath,
                    "created": f.attrs.get("created", 0),
                    "created_human": f.attrs.get("created_human", "Unknown"),
                    "experiment_name": f.attrs.get("experiment_name", "Unknown"),
                    "file_version": f.attrs.get("file_version", "1.0"),
                    "total_frames": f.attrs.get("actual_frames", 0),
                    "duration_minutes": f.attrs.get("duration_minutes", 0),
                    "interval_seconds": f.attrs.get("interval_seconds", 0),
                    "groups": list(f.keys()),
                    "file_size_mb": Path(filepath).stat().st_size / (1024 * 1024),
                    "phase_support": f.attrs.get("phase_support", False),
                    "phase_enabled": f.attrs.get("phase_enabled", False),
                    "memory_optimized": f.attrs.get("memory_optimized", False),
                    "chunked_datasets": f.attrs.get("chunked_datasets", False),
                }

                # Phase-specific information
                if summary["phase_enabled"]:
                    summary["phase_info"] = {
                        "light_duration_min": f.attrs.get("light_duration_min", 0),
                        "dark_duration_min": f.attrs.get("dark_duration_min", 0),
                        "starts_with_light": f.attrs.get("starts_with_light", True),
                        "transitions": f.attrs.get("phase_transitions", 0),
                        "cycles_completed": f.attrs.get("cycles_completed", 0),
                    }

                # Dataset counts (without loading data)
                for group_name in ["images", "metadata", "timeseries", "phase_analysis"]:
                    if group_name in f:
                        summary[f"{group_name}_count"] = len(f[group_name].keys())

                # Timeseries dataset list
                if "timeseries" in f:
                    summary["timeseries_datasets"] = list(f["timeseries"].keys())
                    summary["has_phase_datasets"] = any(
                        name in f["timeseries"]
                        for name in ["current_phase", "led_type_used", "cycle_number"]
                    )

                    # Get chunked writer info
                    ts_group = f["timeseries"]
                    if "chunk_size" in ts_group.attrs:
                        summary["chunk_size"] = ts_group.attrs["chunk_size"]

                return summary

        except Exception as e:
            raise RuntimeError(f"Failed to get file summary: {str(e)}")

    # ========================================================================
    # ✅ PRESERVED AND ENHANCED EXISTING METHODS
    # ========================================================================

    def update_recording_metadata(self, metadata: dict):
        """Update recording metadata with enhanced phase configuration support."""
        self.recording_metadata.update(metadata)

        # Update expected frame interval
        if "interval_seconds" in metadata:
            old_interval = self.expected_frame_interval
            self.expected_frame_interval = metadata["interval_seconds"]
            logger.info(
                f"Expected frame interval: {old_interval:.1f}s → {self.expected_frame_interval:.1f}s"
            )

        # Handle phase configuration metadata
        if "phase_config" in metadata:
            phase_config = metadata["phase_config"]
            self.recording_metadata["phase_enabled"] = phase_config.get("enabled", False)
            self.recording_metadata["light_duration_min"] = phase_config.get(
                "light_duration_min", 0
            )
            self.recording_metadata["dark_duration_min"] = phase_config.get("dark_duration_min", 0)
            self.recording_metadata["starts_with_light"] = phase_config.get(
                "start_with_light", True
            )

            logger.info(
                f"Phase configuration updated: enabled={self.recording_metadata['phase_enabled']}"
            )
            if self.recording_metadata["phase_enabled"]:
                logger.info(f"  - Light phase: {self.recording_metadata['light_duration_min']}min")
                logger.info(f"  - Dark phase: {self.recording_metadata['dark_duration_min']}min")

        self.metadata_updated.emit(self.recording_metadata.copy())

        # Save to HDF5 attributes
        if self.hdf5_file:
            with self._hdf5_lock:
                for key, value in metadata.items():
                    try:
                        self.hdf5_file.attrs[key] = value
                    except (TypeError, ValueError):
                        # Convert to string if can't store directly
                        self.hdf5_file.attrs[key] = str(value)

    def finalize_recording(self):
        """Finalize recording with comprehensive statistics."""
        if not self.hdf5_file:
            return

        with self._hdf5_lock:
            try:
                # Update final metadata
                self.recording_metadata["end_time"] = time.time()
                self.recording_metadata["total_duration"] = (
                    self.recording_metadata["end_time"] - self.recording_metadata["start_time"]
                )
                self.recording_metadata["actual_frames"] = self.frame_count
                self.recording_metadata["phase_transitions"] = self.phase_transition_count
                self.recording_metadata["cycles_completed"] = self.cycle_count

                # Save final metadata to attributes
                self.update_recording_metadata(self.recording_metadata)

                # Add statistics to timeseries group
                if "timeseries" in self.hdf5_file and self.frame_count > 0:
                    timeseries_group = self.hdf5_file["timeseries"]

                    # Basic recording statistics
                    timeseries_group.attrs["total_frames"] = self.frame_count
                    timeseries_group.attrs["recording_duration"] = self.recording_metadata[
                        "total_duration"
                    ]
                    timeseries_group.attrs["phase_transitions"] = self.phase_transition_count
                    timeseries_group.attrs["cycles_completed"] = self.cycle_count
                    timeseries_group.attrs["phase_enabled"] = self.recording_metadata.get(
                        "phase_enabled", False
                    )

                    # Chunked writer statistics
                    if self.chunked_writer:
                        timeseries_group.attrs["frames_written"] = (
                            self.chunked_writer.written_frames
                        )
                        timeseries_group.attrs["dataset_capacity"] = (
                            self.chunked_writer.current_capacity
                        )

                # Finalize phase analysis group
                self._finalize_phase_analysis()

                # Final summary
                duration_hours = self.recording_metadata["total_duration"] / 3600
                phase_text = (
                    f"({self.phase_transition_count} transitions, {self.cycle_count} cycles)"
                    if self.recording_metadata.get("phase_enabled", False)
                    else "(continuous mode)"
                )

                logger.info(f"\n=== CORRECTED PHASE-AWARE RECORDING FINALIZED ===")
                logger.info(f"Frames: {self.frame_count}")
                logger.info(f"Duration: {duration_hours:.1f} hours")
                logger.info(f"Phase cycling: {phase_text}")
                logger.info(f"Data structure: Chunked phase-aware timeseries")
                logger.info(f"File: {self.current_filepath}")

                # Close file
                self.hdf5_file.close()
                self.hdf5_file = None
                self.chunked_writer = None

            except Exception as e:
                error_msg = f"Error finalizing recording: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)

    def _finalize_phase_analysis(self):
        """Finalize phase analysis group with summary information."""
        try:
            if "phase_analysis" in self.hdf5_file:
                phase_group = self.hdf5_file["phase_analysis"]

                # Add summary attributes
                phase_group.attrs["total_transitions"] = self.phase_transition_count
                phase_group.attrs["total_cycles"] = self.cycle_count
                phase_group.attrs["phase_enabled"] = self.recording_metadata.get(
                    "phase_enabled", False
                )

                if self.recording_metadata.get("phase_enabled", False):
                    phase_group.attrs["light_duration_min"] = self.recording_metadata.get(
                        "light_duration_min", 0
                    )
                    phase_group.attrs["dark_duration_min"] = self.recording_metadata.get(
                        "dark_duration_min", 0
                    )
                    phase_group.attrs["starts_with_light"] = self.recording_metadata.get(
                        "starts_with_light", True
                    )

                logger.info(
                    f"Phase analysis finalized: {len(phase_group.keys())} transition records"
                )

        except Exception as e:
            logger.error(f"Error finalizing phase analysis: {e}")

    def get_recording_info(self) -> dict:
        """Get comprehensive recording information including phase status."""
        info = self.recording_metadata.copy()
        info["current_filepath"] = str(self.current_filepath) if self.current_filepath else None
        info["frames_saved"] = self.frame_count
        info["file_open"] = self.hdf5_file is not None
        info["phase_transitions"] = getattr(self, "phase_transition_count", 0)
        info["cycles_completed"] = getattr(self, "cycle_count", 0)
        info["memory_optimized"] = True
        info["chunked_operations"] = self.chunked_writer is not None
        return info

    def close_file(self):
        """Close the current HDF5 file with cleanup."""
        with self._hdf5_lock:
            if self.hdf5_file:
                try:
                    self.hdf5_file.close()
                except:
                    pass
                finally:
                    self.hdf5_file = None
                    self.current_filepath = None
                    self.frame_count = 0
                    self.phase_transition_count = 0
                    self.cycle_count = 0
                    self.last_phase = None
                    self.chunked_writer = None

    def is_file_open(self) -> bool:
        """Check if a file is currently open."""
        return self.hdf5_file is not None

    def force_memory_cleanup(self):
        """Force aggressive memory cleanup."""
        try:
            import gc

            # Force HDF5 flush
            if self.hdf5_file:
                with self._hdf5_lock:
                    self.hdf5_file.flush()

            # Clear chunked writer cache if it exists
            if self.chunked_writer:
                # Keep only essential references
                pass

            # Force garbage collection
            collected = gc.collect()
            logger.info(f"Forced memory cleanup: {collected} objects collected")

            return collected > 0
        except Exception as e:
            logger.error(f"Memory cleanup error: {e}")
            return False

    # ========================================================================
    # ✅ STATIC UTILITY METHODS FOR FILE REPAIR AND ANALYSIS
    # ========================================================================

    @staticmethod
    def fix_expected_intervals_in_file(filepath: str, expected_interval: float):
        """Fix expected_intervals in existing HDF5 file."""
        try:
            with h5py.File(filepath, "r+") as f:
                if "timeseries" in f and "expected_intervals" in f["timeseries"]:
                    dataset = f["timeseries"]["expected_intervals"]
                    old_values = dataset[:5] if len(dataset) > 0 else []

                    logger.info(f"Fixing {len(dataset)} expected_intervals:")
                    logger.info(f"  Old values (first 5): {old_values}")
                    logger.info(f"  New value: {expected_interval}s")

                    dataset[:] = expected_interval
                    dataset.attrs["fixed"] = True
                    dataset.attrs["fix_timestamp"] = time.time()
                    dataset.attrs["fix_description"] = (
                        f"Fixed to constant {expected_interval} seconds"
                    )

                    logger.info(f"✅ Expected_intervals fixed to {expected_interval}s!")
                    return True
                else:
                    logger.warning("No timeseries/expected_intervals found")
                    return False
        except Exception as e:
            logger.error(f"Error fixing file: {e}")
            return False
