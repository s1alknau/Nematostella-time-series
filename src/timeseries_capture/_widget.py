import os
import sys
import time
import traceback

import h5py
import numpy as np
import serial
from napari.layers import Image
from PIL import Image as PILImage  # Pillow library for saving TIFF files
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports  # Import for detecting available ports


class NematostellaTimeSeriesCapture(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer  # Store the Napari viewer instance

        # Create the main layout
        layout = QVBoxLayout()

        # Recording duration input (in minutes)
        self.duration_label = QLabel("Recording Duration (minutes):")
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Enter duration in minutes")
        layout.addWidget(self.duration_label)
        layout.addWidget(self.duration_input)

        # Interval between frames input (in seconds)
        self.interval_label = QLabel("Interval Between Frames (seconds):")
        self.interval_input = QLineEdit()
        self.interval_input.setPlaceholderText("Enter interval in seconds")
        layout.addWidget(self.interval_label)
        layout.addWidget(self.interval_input)

        # Checkbox for saving metadata
        self.save_metadata_checkbox = QCheckBox("Save Metadata")
        layout.addWidget(self.save_metadata_checkbox)

        # Checkbox for saving as TIFF files
        self.save_as_tiff_checkbox = QCheckBox("Save Frames as TIFF Files")
        layout.addWidget(self.save_as_tiff_checkbox)

        # Directory selection button and label
        self.select_dir_button = QPushButton("Select Save Directory")
        self.select_dir_button.clicked.connect(self.select_directory)
        layout.addWidget(self.select_dir_button)

        self.selected_dir_label = QLabel("No directory selected")
        layout.addWidget(self.selected_dir_label)

        # Manual LED control buttons
        self.led_control_label = QLabel("Manual LED Control:")
        layout.addWidget(self.led_control_label)

        self.led_on_button = QPushButton("Turn LED On")
        self.led_on_button.clicked.connect(
            lambda: self.send_esp32_command(0x01)
        )  # Send 0x01 for ON
        layout.addWidget(self.led_on_button)

        self.led_off_button = QPushButton("Turn LED Off")
        self.led_off_button.clicked.connect(
            lambda: self.send_esp32_command(0x00)
        )  # Send 0x00 for OFF
        layout.addWidget(self.led_off_button)

        # Record button
        self.record_button = QPushButton("Start Recording")
        self.record_button.clicked.connect(self.start_recording_thread)
        layout.addWidget(self.record_button)

        # Stop button
        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setEnabled(False)  # Initially disabled, enabled during recording
        self.stop_button.clicked.connect(self.stop_recording)
        layout.addWidget(self.stop_button)

        self.setLayout(layout)

        # Initialize selected directory variable
        self.selected_directory = None
        self.led_is_on = False  # Flag to track the LED state
        self.stop_requested = False  # Flag to stop recording safely

        # Setup serial connection to ESP32
        self.serial_port = None
        self.serial_port_name = None
        self.init_serial_connection()  # Initialize serial connection during widget setup

    def init_serial_connection(self):
        """Initialize the serial connection to the ESP32."""
        try:
            self.serial_port_name = self.get_serial_port_name()
            print(f"Detected platform: {sys.platform}")
            print(f"Attempting to open serial port: {self.serial_port_name}")
            self.serial_port = serial.Serial(
                self.serial_port_name,
                115200,
                timeout=1,
                dsrdtr=False,
                rtscts=False,
                xonxoff=False,
                write_timeout=1,
            )

            # Set DTR and RTS to False after opening the port
            self.serial_port.dtr = False
            self.serial_port.rts = False

            time.sleep(2)  # Wait for ESP32 to finish booting
            self.serial_port.reset_input_buffer()  # Discard any initial data
            print("Serial port opened and initialized.")
        except serial.SerialException as e:
            self.show_error_message(
                f"Failed to open serial port {self.serial_port_name}: {e}"
            )
            self.serial_port = None
            self.record_button.setEnabled(False)  # Disable recording if serial port fails

    def start_recording_thread(self):
        """Starts recording in a separate thread."""
        if not self.selected_directory:
            self.show_error_message(
                "Please select a directory to save the files before starting the recording."
            )
            return
        self.stop_requested = False  # Reset stop flag
        self.start_recording()

    def stop_recording(self):
        """Stop the recording process safely."""
        self.stop_requested = True
        if self.hdf5_file:
            self.hdf5_file.flush()
            self.hdf5_file.close()
        self.record_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        print("Recording stopped.")

    def get_serial_port_name(self):
        """Automatically detect and return the serial port name based on available ports."""
        ports = list_ports.comports()
        for port in ports:
            print(f"Found port: {port.device}")
            # Optionally, check port description or manufacturer to match specific device
            return port.device
        # Default case if no ports are found
        self.show_error_message("No serial ports found. Ensure the ESP32 is connected.")
        return None

    def select_directory(self):
        """Open a dialog to select a directory for saving the HDF5 or TIFF files."""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            self.selected_directory = directory
            self.selected_dir_label.setText(f"Selected Directory: {directory}")
        else:
            self.selected_dir_label.setText("No directory selected")

    def send_esp32_command(self, command):
        """Sends a binary command to the ESP32 over the serial port with retries."""
        retry_count = 0
        max_retries = 3 # Number of retries for sending commands

        if not self.serial_port or not self.serial_port.is_open:
            print("Serial port is not available, attempting to reinitialize...")
            self.init_serial_connection()  # Attempt to reinitialize the connection
            if not self.serial_port or not self.serial_port.is_open:
                self.show_error_message("Failed to communicate with ESP32.")
                return False

        while retry_count < max_retries:
            try:
                # Clear input buffer before sending a new command
                self.serial_port.reset_input_buffer()

                # Send the binary command (0x01 for ON, 0x00 for OFF)
                self.serial_port.write(bytes([command]))
                print(f"Sent binary command to ESP32: {command:#04x}")

                # Read 1 byte response with a short timeout
                response = self.serial_port.read(1)
                if response:
                    response_value = int.from_bytes(response, byteorder="big")
                    print(f"ESP32 Response: {response_value:#04x}")

                    # Handle different response values
                    if (command == 0x01 and response_value == 0x01) or (command == 0x00 and response_value == 0x02):
                        self.led_is_on = command == 0x01  # Update LED status flag
                        return True  # Successful response
                    elif response_value == 0xFE:
                        print("Buffer overflow detected on ESP32.")
                    elif response_value == 0xFD:
                        print("Timeout error detected on ESP32.")
                    elif response_value == 0xFC:
                        print("Invalid command detected on ESP32.")
                    else:
                        print("Unexpected response or error.")
                else:
                    print("No response from ESP32.")
                retry_count += 1  # Increment retry count if response is not as expected

            except serial.SerialException as e:
                self.show_error_message(f"Error communicating with ESP32: {e}")
                return False

        # If maximum retries are reached, show error
        print(f"Failed to communicate with ESP32 after {max_retries} retries.")
        self.show_error_message(
            f"Failed to communicate with ESP32 after {max_retries} retries."
        )
        return False

    def start_recording(self):
        """Starts the recording process, synchronizing LED and frame capturing."""
        self.record_button.setEnabled(False)
        self.stop_button.setEnabled(True)  # Enable stop button during recording

        # Input validation
        if not self.validate_inputs():
            self.record_button.setEnabled(True)
            return

        try:
            # Convert duration from minutes to seconds
            duration = float(self.duration_input.text()) * 60
            self.interval = float(self.interval_input.text())

            if duration <= 0 or self.interval <= 0:
                raise ValueError("All input values must be greater than zero.")
        except ValueError:
            self.show_error_message(
                "Invalid input values! Ensure all inputs are valid positive numbers."
            )
            self.record_button.setEnabled(True)
            return

        # Check if the live view layer exists before starting
        live_view_layer = next(
            (
                layer
                for layer in self.viewer.layers
                if isinstance(layer, Image)
            ),
            None,
        )
        if live_view_layer is None:
            available_layers = [layer.name for layer in self.viewer.layers]
            self.show_error_message(
                f"Live view layer not found. Available layers: {available_layers}"
            )
            self.record_button.setEnabled(True)
            return

        # Initialize recording variables
        self.current_frame = 0
        self.total_frames = int(
            duration / self.interval
        )  # Total frames to capture based on duration and interval

        # Get the expected frame shape
        frame_shape = live_view_layer.data.shape
        if len(frame_shape) == 3:
            frame_height, frame_width, frame_channels = frame_shape
            self.resolution = (
                frame_height,
                frame_width,
            )  # Use actual frame dimensions
            self.color_channels = frame_channels  # RGB
        else:
            self.show_error_message(
                "Live view layer data does not have the expected shape."
            )
            self.record_button.setEnabled(True)
            return

        # Open the first HDF5 file
        self.open_new_hdf5_file(
            num_frames=self.total_frames,
            height=self.resolution[0],
            width=self.resolution[1],
        )

        # Start capturing frames
        self.capture_next_frame()

    def open_new_hdf5_file(self, num_frames, height, width):
        """Open a new HDF5 file for storing frames."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        hdf5_filename = os.path.join(
            self.selected_directory, f"recorded_frames_{timestamp}.h5"
        )

        try:
            self.hdf5_file = h5py.File(hdf5_filename, "w")

            # Create the dataset with the correct shape
            self.dataset = self.hdf5_file.create_dataset(
                "frames",
                shape=(
                    num_frames,
                    height,
                    width,
                    self.color_channels,
                ),  # (total_frames, height, width, channels)
                dtype=np.uint8,
                chunks=(1, height, width, self.color_channels),
                compression="gzip",
            )

            print(f"Opened new HDF5 file: {hdf5_filename}")
            print(f"HDF5 dataset shape: {self.dataset.shape}")
            print(f"Color channels: {self.color_channels}")

        except (OSError, ValueError) as e:
            print(f"Exception during HDF5 file creation: {e}")
            traceback.print_exc()
            self.show_error_message(f"Error creating HDF5 file: {e}")
            self.record_button.setEnabled(True)

    def capture_next_frame(self):
        """Capture the next frame in the time series."""
        if self.stop_requested:
            # If stop is requested, safely terminate the recording process
            self.stop_recording()
            return

        if self.current_frame >= self.total_frames:
            # Recording complete
            self.hdf5_file.flush()
            self.hdf5_file.close()
            print("Recording complete.")
            self.record_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return

        # Turn on LED
        if self.send_esp32_command(0x01):
            print("LED turned ON.")
            # Delay for 1 second to ensure LED is stable and bright
            QTimer.singleShot(1000, self.capture_frame)
        else:
            print("Error: Failed to turn on the LED.")
            self.schedule_next_frame()

    def capture_frame(self):
        """Capture the current frame from the live view."""
        try:
            # Ensure LED is on before capturing the frame
            if not self.led_is_on:
                print("LED is off, skipping frame capture.")
                self.schedule_next_frame()
                return

            live_view_layer = next(
                (
                    layer
                    for layer in self.viewer.layers
                    if isinstance(layer, Image)
                ),
                None,
            )
            if live_view_layer is None:
                print(
                    f"Skipping frame {self.current_frame + 1} due to missing live view layer."
                )
                self.schedule_next_frame()
                return

            # Capture the full frame data and make a copy
            frame = (
                live_view_layer.data.copy()
            )  # Copy the data to ensure no live data is altered
            print(f"Captured frame shape: {frame.shape}")

            # Ensure the captured frame has the right dimensions
            if frame.shape == (
                self.resolution[0],
                self.resolution[1],
                self.color_channels,
            ):
                # The frame is already in the correct shape, so no reshaping is needed
                print("Frame is in the correct shape.")
            else:
                raise ValueError(f"Frame has unexpected shape: {frame.shape}")

            # Print frame data type
            print(f"Frame data type: {frame.dtype}")

            # Convert frame to np.uint8 if necessary
            if frame.dtype != np.uint8:
                print("Converting frame to np.uint8")
                frame = frame.astype(np.uint8)

            # Turn off LED
            if self.send_esp32_command(0x00):
                print("LED turned OFF.")
            else:
                print("Error: Failed to turn off the LED.")

            # Save frame to HDF5
            try:
                print(f"Dataset shape: {self.dataset.shape}")
                print(f"Current frame index: {self.current_frame}")
                self.dataset[self.current_frame, ...] = frame
                print(f"Frame {self.current_frame} written to HDF5 dataset.")
            except (OSError, ValueError, IndexError) as e:
                print(
                    f"Error writing frame {self.current_frame} to HDF5 dataset: {e}"
                )
                traceback.print_exc()

            # Save frame as TIFF if the checkbox is checked
            if self.save_as_tiff_checkbox.isChecked():
                tiff_filename = os.path.join(
                    self.selected_directory,
                    f"frame_{self.current_frame + 1:04d}.tiff",
                )
                PILImage.fromarray(frame).save(tiff_filename)
                print(f"Saved frame as TIFF: {tiff_filename}")

            print(f"Captured frame {self.current_frame + 1}")

        except (OSError, ValueError, RuntimeError) as e:
            print(f"Exception during frame capture: {e}")
            traceback.print_exc()

        # Schedule next frame
        self.current_frame += 1
        QTimer.singleShot(int(self.interval * 1000), self.capture_next_frame)

    def schedule_next_frame(self):
        """Schedules the next frame capture based on the interval."""
        QTimer.singleShot(int(self.interval * 1000), self.capture_next_frame)

    def validate_inputs(self):
        """Validates the input fields and returns whether the inputs are valid."""
        if not self.duration_input.text() or not self.interval_input.text():
            self.show_error_message(
                "Please enter valid duration and interval values."
            )
            return False
        try:
            duration = float(self.duration_input.text()) * 60
            interval = float(self.interval_input.text())
            if duration <= 0 or interval <= 0:
                self.show_error_message(
                    "Duration and interval must be greater than zero."
                )
                return False
        except ValueError:
            self.show_error_message(
                "Please enter numeric values for duration and interval."
            )
            return False
        if not self.selected_directory:
            self.show_error_message(
                "Please select a directory to save the files."
            )
            return False
        return True

    def show_error_message(self, message):
        """Display error messages to the user."""
        error_msg = QMessageBox(self)
        error_msg.setIcon(QMessageBox.Critical)
        error_msg.setWindowTitle("Error")
        error_msg.setText(message)
        error_msg.exec_()