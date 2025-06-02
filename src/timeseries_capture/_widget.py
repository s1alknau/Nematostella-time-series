import os
import sys
import time
import traceback
import struct

import h5py
import numpy as np
import serial
from napari.layers import Image
from PIL import Image as PILImage
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
from serial.tools import list_ports  # Import für serielle Port-Erkennung


def napari_experimental_provide_dock_widget():
    """Stellt das Widget als Dock in Napari bereit."""
    return NematostellaTimeSeriesCapture


class NematostellaTimeSeriesCapture(QWidget):
    """
    Napari-Widget zur synchronisierten LED-Ansteuerung und Timelapse-Aufnahme (mit DHT22).
    Unterstützt variable Belichtungszeit (Exposure) und Intervall, speichert Framefolge
    zuverlässig als HDF5 (Mono oder RGB) sowie optional TIFF und Metadaten (Temperatur/Luftfeuchte).
    """

    # Protokoll-Bezeichner
    CMD_LED_ON           = 0x01
    CMD_LED_OFF          = 0x00
    CMD_STATUS           = 0x02
    CMD_START_TIMELAPSE  = 0x03
    CMD_STOP_TIMELAPSE   = 0x04

    RESPONSE_ACK_ON         = 0x01
    RESPONSE_ACK_OFF        = 0x02
    RESPONSE_STATUS_ON      = 0x11
    RESPONSE_STATUS_OFF     = 0x10
    RESPONSE_ERROR          = 0xFF
    RESPONSE_BUFFER_OVERFLOW= 0xFE
    RESPONSE_TIMEOUT        = 0xFD
    RESPONSE_INVALID_CMD    = 0xFC

    RESPONSE_TIMELAPSE_ACK  = 0xA3
    RESPONSE_TIMELAPSE_STOP = 0xA4

    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer

        # Initialisierung der Parameter
        self.selected_directory = None
        self.serial_port = None
        self.serial_port_name = None
        self.stop_requested = False
        self.timelapse_running = False

        self.duration      = None  # in Sekunden
        self.interval_s    = None  # in Sekunden
        self.exposure_ms   = None  # in Millisekunden
        self.total_frames  = None
        self.current_frame = 0

        self.is_rgb = None  # True = RGB, False = Monochrom

        # UI-Aufbau
        layout = QVBoxLayout()

        # Recording Duration
        layout.addWidget(QLabel("Recording Duration (minutes):"))
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Enter duration in minutes")
        layout.addWidget(self.duration_input)

        # Interval Between Frames
        layout.addWidget(QLabel("Interval Between Frames (seconds):"))
        self.interval_input = QLineEdit()
        self.interval_input.setPlaceholderText("Enter interval in seconds")
        layout.addWidget(self.interval_input)

        # Exposure Time
        layout.addWidget(QLabel("Exposure Time (milliseconds):"))
        self.exposure_input = QLineEdit()
        self.exposure_input.setPlaceholderText("Enter exposure in ms")
        layout.addWidget(self.exposure_input)

        # Checkboxes
        self.save_metadata_checkbox = QCheckBox("Save Metadata")
        layout.addWidget(self.save_metadata_checkbox)
        self.save_as_tiff_checkbox = QCheckBox("Save Frames as TIFF Files")
        layout.addWidget(self.save_as_tiff_checkbox)

        # Verzeichnis-Auswahl
        self.select_dir_button = QPushButton("Select Save Directory")
        self.select_dir_button.clicked.connect(self.select_directory)
        layout.addWidget(self.select_dir_button)
        self.selected_dir_label = QLabel("No directory selected")
        layout.addWidget(self.selected_dir_label)

        # Manuelle LED-Kontrolle
        layout.addWidget(QLabel("Manual LED Control (Einfach):"))
        self.led_on_button = QPushButton("Turn LED On")
        self.led_on_button.clicked.connect(lambda: self.send_simple_command(self.CMD_LED_ON))
        layout.addWidget(self.led_on_button)
        self.led_off_button = QPushButton("Turn LED Off")
        self.led_off_button.clicked.connect(lambda: self.send_simple_command(self.CMD_LED_OFF))
        layout.addWidget(self.led_off_button)

        # Start / Stop Buttons
        self.record_button = QPushButton("Start Recording")
        self.record_button.clicked.connect(self.start_recording_thread)
        layout.addWidget(self.record_button)

        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_recording)
        layout.addWidget(self.stop_button)

        self.setLayout(layout)

        # Serielle Verbindung initialisieren
        self.init_serial_connection()

        # Timer für serielle Polling
        self.serial_timer = QTimer(self)
        self.serial_timer.setInterval(10)
        self.serial_timer.timeout.connect(self.handle_serial_response)

    def init_serial_connection(self):
        """Initialisiert die serielle Kommunikation mit dem ESP32."""
        try:
            self.serial_port_name = self.get_serial_port_name()
            self.serial_port = serial.Serial(
                self.serial_port_name,
                115200,
                timeout=0.1,
                write_timeout=1,
                dsrdtr=False,
                rtscts=False,
                xonxoff=False,
            )
            self.serial_port.dtr = False
            self.serial_port.rts = False
            time.sleep(2)  # ESP32 braucht Zeit zum Booten
            self.serial_port.reset_input_buffer()
            print(f"Serial port {self.serial_port_name} initialized.")
        except Exception as e:
            self.show_error_message(f"Could not open serial port {self.serial_port_name}: {e}")
            self.record_button.setEnabled(False)

    def get_serial_port_name(self):
        """Gibt automatisch den ersten verfügbaren COM-Port zurück."""
        ports = list_ports.comports()
        for port in ports:
            return port.device
        raise serial.SerialException("No serial ports found.")

    def select_directory(self):
        """Öffnet Dialog zum Auswählen des Speicherverzeichnisses."""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            self.selected_directory = directory
            self.selected_dir_label.setText(f"Selected Directory: {directory}")
        else:
            self.selected_dir_label.setText("No directory selected")

    def send_simple_command(self, cmd_byte):
        """
        Sendet ein einzelnes Byte (z.B. LED_ON) und liest 1 Byte Antwort (für manuellen Test).
        """
        if not self.serial_port or not self.serial_port.is_open:
            self.init_serial_connection()
            if not self.serial_port or not self.serial_port.is_open:
                self.show_error_message("Failed to communicate with ESP32.")
                return False

        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.write(bytes([cmd_byte]))
            resp = self.serial_port.read(1)
            if resp:
                val = resp[0]
                print(f"Manual Response: 0x{val:02X}")
                return True
            else:
                print("No response for simple command.")
                return False
        except Exception as e:
            self.show_error_message(f"Error communicating with ESP32: {e}")
            return False

    def start_recording_thread(self):
        """Wird aufgerufen, wenn der User auf 'Start Recording' klickt."""
        if not self.selected_directory:
            self.show_error_message("Please select a directory before starting.")
            return
        self.stop_requested = False
        self.start_recording()

    def start_recording(self):
        """
        Bereitet alles vor, liest Parameter (Duration, Interval, Exposure),
        öffnet HDF5 (Mono oder RGB), sendet START_TIMELAPSE-Paket und startet Timer.
        """
        self.record_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        if not self.validate_inputs():
            self.record_button.setEnabled(True)
            return

        # Duration und Interval einlesen
        duration_min = float(self.duration_input.text())
        self.duration   = duration_min * 60.0  # in Sekunden
        self.interval_s = float(self.interval_input.text())
        try:
            self.exposure_ms = int(self.exposure_input.text())
        except:
            self.show_error_message("Exposure time must be an integer (ms).")
            self.record_button.setEnabled(True)
            return

        if self.exposure_ms <= 0:
            self.show_error_message("Exposure must be > 0 ms.")
            self.record_button.setEnabled(True)
            return

        if self.interval_s <= 0:
            self.show_error_message("Interval must be > 0.")
            self.record_button.setEnabled(True)
            return

        interval_ms = int(self.interval_s * 1000)
        if self.exposure_ms > interval_ms:
            self.show_error_message("Exposure cannot exceed interval.")
            self.record_button.setEnabled(True)
            return

        # Anzahl Frames berechnen
        self.total_frames  = int(self.duration / self.interval_s)
        self.current_frame = 0

        # Live-View-Layer prüfen und Shape auslesen
        live_layer = next((l for l in self.viewer.layers if isinstance(l, Image)), None)
        if live_layer is None:
            self.show_error_message("Live view layer not found.")
            self.record_button.setEnabled(True)
            return

        frame0 = live_layer.data.copy()
        # Mono vs. RGB
        if frame0.ndim == 2:
            self.is_rgb = False
            height, width = frame0.shape
            channels = 1
        elif frame0.ndim == 3 and frame0.shape[2] == 3:
            self.is_rgb = True
            height, width, _ = frame0.shape
            channels = 3
        else:
            self.show_error_message(
                f"Unsupported frame shape: {frame0.shape}. Must be (H,W) or (H,W,3)."
            )
            self.record_button.setEnabled(True)
            return

        # HDF5-Datei öffnen (dynamisch Mono oder RGB)
        self.open_new_hdf5_file(self.total_frames, height, width, channels)

        # START_TIMELAPSE-Paket erstellen und senden
        packet = bytearray()
        packet.append(self.CMD_START_TIMELAPSE)
        packet += struct.pack(">I", interval_ms)
        packet += struct.pack(">I", self.exposure_ms)

        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.write(packet)
        except Exception as e:
            self.show_error_message(f"Failed to send START_TIMELAPSE: {e}")
            self.record_button.setEnabled(True)
            return

        # Auf RESPONSE_TIMELAPSE_ACK (0xA3) warten (Timeout 2 s)
        start_time = time.time()
        ack = b""
        while (time.time() - start_time) < 2.0:
            data = self.serial_port.read(1)
            if data:
                ack = data
                break

        if not ack or ack[0] != self.RESPONSE_TIMELAPSE_ACK:
            self.show_error_message("No Timelapse-ACK from ESP32 (0xA3). Abbruch.")
            self.record_button.setEnabled(True)
            return

        # Timer starten, der alle 10 ms nach ACK_ON+Temp+Hum sucht
        self.timelapse_running = True
        self.serial_timer.start()

    def open_new_hdf5_file(self, num_frames, height, width, channels):
        """
        Öffnet HDF5. Für Monochrom (channels=1) = (frames, H, W).
        Für RGB (channels=3) = (frames, H, W, 3).
        """
        ts = time.strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.selected_directory, f"recorded_frames_{ts}.h5")
        try:
            self.hdf5_file = h5py.File(filepath, 'w')
            if channels == 1:
                self.dataset = self.hdf5_file.create_dataset(
                    'frames',
                    shape=(num_frames, height, width),
                    dtype=np.uint8,
                    chunks=(1, height, width),
                    compression='gzip'
                )
            else:
                self.dataset = self.hdf5_file.create_dataset(
                    'frames',
                    shape=(num_frames, height, width, 3),
                    dtype=np.uint8,
                    chunks=(1, height, width, 3),
                    compression='gzip'
                )
            print(f"Opened new HDF5: {filepath}, shape {self.dataset.shape}")
        except Exception as e:
            print(f"Exception creating HDF5: {e}")
            traceback.print_exc()
            self.show_error_message(f"Error creating HDF5 file: {e}")
            self.record_button.setEnabled(True)

    def handle_serial_response(self):
        """
        Wird alle 10 ms aufgerufen, solange timelapse_running True ist.
        Liest 3 Bytes: [ACK_ON | temp | hum]. Sobald ACK_ON erkannt wird,
        captured das aktuelle Frame von Napari und speichert es (Mono oder RGB).
        """
        if not self.timelapse_running:
            return

        if self.serial_port.in_waiting < 3:
            return

        try:
            chunk = self.serial_port.read(3)
            if len(chunk) < 3:
                return
            ack_byte, temp_byte, hum_byte = chunk

            if ack_byte != self.RESPONSE_ACK_ON:
                # Unerwartetes Byte, ignorieren
                print(f"Unexpected byte: 0x{ack_byte:02X}, ignored.")
                return

            # Nun das Frame aus dem Napari-Layer abgreifen
            live_layer = next((l for l in self.viewer.layers if isinstance(l, Image)), None)
            if live_layer is None:
                print(f"Skipping frame {self.current_frame+1}: no live view.")
            else:
                frame = live_layer.data.copy()
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8)

                # Speicherung je nach Mono/RGB
                if not self.is_rgb:
                    # Monochrom erwartet (H,W)
                    if frame.ndim == 2:
                        self.dataset[self.current_frame, :, :] = frame
                    elif frame.ndim == 3 and frame.shape[2] == 3:
                        # Falls versehentlich 3-Kanal rein, nehme ersten Kanal
                        gray = frame[:, :, 0]
                        self.dataset[self.current_frame, :, :] = gray
                    else:
                        print(f"Unexpected frame shape for monochrome: {frame.shape}")
                else:
                    # RGB erwartet (H,W,3)
                    if frame.ndim == 3 and frame.shape[2] == 3:
                        self.dataset[self.current_frame, ...] = frame
                    else:
                        # Falls Mono rein, konvertiere zu RGB (dreimal mono-Kanal)
                        if frame.ndim == 2:
                            rgb = np.stack([frame]*3, axis=2)
                            self.dataset[self.current_frame, ...] = rgb
                        else:
                            print(f"Unexpected frame shape for RGB: {frame.shape}")

                # Optional: TIFF exportieren
                if self.save_as_tiff_checkbox.isChecked():
                    if not self.is_rgb:
                        # Monochrom-TIFF
                        img = frame if frame.ndim == 2 else frame[:, :, 0]
                        fname = os.path.join(
                            self.selected_directory,
                            f"frame_{self.current_frame+1:04d}.tiff"
                        )
                        PILImage.fromarray(img).save(fname)
                    else:
                        # RGB-TIFF
                        fname = os.path.join(
                            self.selected_directory,
                            f"frame_{self.current_frame+1:04d}.tiff"
                        )
                        PILImage.fromarray(frame).save(fname)

                # Metadaten (Temperatur, Luftfeuchte) speichern
                if self.save_metadata_checkbox.isChecked():
                    grp = self.hdf5_file.require_group("metadata")
                    stamp = time.time()
                    grp.attrs[f"frame_{self.current_frame+1:04d}_timestamp"] = stamp
                    grp.attrs[f"frame_{self.current_frame+1:04d}_temp"] = int(temp_byte)
                    grp.attrs[f"frame_{self.current_frame+1:04d}_hum"]  = int(hum_byte)

                print(
                    f"Captured frame {self.current_frame+1}/{self.total_frames}, "
                    f"Temp={int(temp_byte)}°C, Hum={int(hum_byte)}%"
                )

            self.current_frame += 1

            # Prüfen, ob wir fertig sind oder Abbruch gewünscht
            if self.current_frame >= self.total_frames or self.stop_requested:
                self.serial_timer.stop()
                self.timelapse_running = False
                try:
                    self.serial_port.write(bytes([self.CMD_STOP_TIMELAPSE]))
                except Exception as e:
                    print(f"Error sending STOP_TIMELAPSE: {e}")

                if hasattr(self, 'hdf5_file') and self.hdf5_file:
                    self.hdf5_file.flush()
                    self.hdf5_file.close()

                self.record_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                print("Timelapse completed or aborted.")
                return

        except Exception:
            traceback.print_exc()
            return

    def stop_recording(self):
        """Wird aufgerufen, wenn der User auf ‘Stop Recording’ klickt."""
        self.stop_requested = True
        # Der Timer bemerkt es in handle_serial_response() und sendet STOP_TIMELAPSE.

    def validate_inputs(self):
        """Validiert Duration, Interval, Exposure und das gespeicherte Verzeichnis."""
        if not self.duration_input.text() or not self.interval_input.text() or not self.exposure_input.text():
            self.show_error_message("Please enter duration, interval, and exposure.")
            return False
        try:
            d = float(self.duration_input.text())
            i = float(self.interval_input.text())
            e = int(self.exposure_input.text())
            if d <= 0 or i <= 0 or e <= 0:
                raise ValueError
        except ValueError:
            self.show_error_message("Duration and interval must be positive numbers; exposure must be positive integer.")
            return False
        if not self.selected_directory:
            self.show_error_message("Select a save directory.")
            return False
        return True

    def show_error_message(self, message):
        """Zeigt einen Error-Dialog an."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Error")
        msg.setText(message)
        msg.exec_()
