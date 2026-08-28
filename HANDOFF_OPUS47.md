# Kontext-Übergabe für Opus 4.7

**Projekt:** Nematostella Time-Series Recording System
**Repo:** `s1alknau/Nematostella-time-series`, Branch `Nematostella-time-series-IR`
**Arbeitsverzeichnis:** `c:\Users\akkna\OneDrive\Dokumente\GitHub\New_Imswitch\ImSwitch\nematostella-time-series`
**Letzter Commit:** `c6e8b38` – alle Änderungen committed und gepushed

---

## Was das System macht

Ein Python/Qt-Plugin für ImSwitch, das Langzeit-Zeitreihen-Aufnahmen von Nematostella-Embryonen steuert:
- Kamera (über ImSwitch `DetectorsManager`) nimmt Frames in konfigurierbaren Intervallen auf
- ESP32-Mikrocontroller steuert IR- und Weißlicht-LEDs, liest DHT22-Sensor (Temperatur/Luftfeuchte)
- Frames + Telemetrie werden als HDF5 oder Zarr gespeichert
- GUI in ImSwitch (Napari-basiert)

---

## Zuletzt gelöste Probleme (letzten zwei Sessions)

### 1. Frame-Intervall-Spikes (bis 105 s)
**Ursache:** `serial.read(1, timeout=0.1)` blockierte `_comm_lock` auf Windows-USB-Treiber weit über timeout hinaus.

**Fix in `ESP32_Controller/esp32_communication.py`:**
```python
def read_until_response(self, expected_byte, timeout=2.0, max_bytes=100):
    start_time = time.time()
    bytes_read = 0
    while (time.time() - start_time) < timeout and bytes_read < max_bytes:
        with self._comm_lock:
            if not self.is_connected():
                return False
            try:
                waiting = self.serial_connection.in_waiting
            except Exception:
                return False
            if waiting > 0:
                chunk_size = min(waiting, max_bytes - bytes_read)
                data = self.serial_connection.read(chunk_size)
                for byte in data:
                    bytes_read += 1
                    if byte == expected_byte:
                        return True
                continue
        time.sleep(0.010)  # Lock NICHT gehalten während sleep
    logger.warning(f"Response 0x{expected_byte:02X} not found within timeout")
    self.clear_buffers()  # stale bytes flushen
    return False
```

**Fix in `ESP32_Controller/esp32_controller.py`:** Timeouts reduziert:
- `select_led_type`, `led_on`, `set_timing`: 2.0 s → 0.5 s
- `begin_sync_pulse` ACK: → 1.0 s
- `get_sensor_data` read_bytes: → 1.0 s

### 2. Async Disk I/O
Frames werden in eine Queue geschrieben; separater Worker-Thread schreibt auf Disk.
- `AsyncHDF5Writer` in `Datamanager/data_manager_hdf5.py`
- `AsyncZarrWriter` in `Datamanager/data_manager_zarr.py`
- Metadaten backward-compat: `metadata.get("exposure_ms", metadata.get("camera_trigger_latency_ms", 20))`

### 3. Kamera-Exposure aus ImSwitch lesen (nicht hardcoded)
`NapariViewerCameraAdapter.get_exposure_ms()` in `camera_adapters.py` scannt jetzt via `gc.get_objects()` nach ImSwitch `DetectorsManager`:
```python
def get_exposure_ms(self) -> float:
    try:
        import gc
        for obj in gc.get_objects():
            if (type(obj).__name__ == "DetectorsManager"
                    and hasattr(obj, "_subManagers")
                    and hasattr(obj, "getAllDeviceNames")):
                names = obj.getAllDeviceNames()
                if not names:
                    continue
                detector = obj[names[0]]
                if hasattr(detector, "getParameter"):
                    value = detector.getParameter("exposure")
                    return float(value)
    except Exception as e:
        logger.debug(f"get_exposure_ms via gc scan failed: {e}")
    return 10.0  # fallback
```

`recording_manager.py` liest Exposure **nach** `disable_auto_settings()` (AGC-Freeze) neu ein.

### 4. Log-Panel
`GUI/log_panel.py`: Cap bei 5000 Zeilen, Batch-Trimming à 500 Zeilen.

---

## Aktueller Stand der geänderten Dateien

| Datei | Status |
|-------|--------|
| `ESP32_Controller/esp32_communication.py` | ✅ committed |
| `ESP32_Controller/esp32_controller.py` | ✅ committed |
| `Datamanager/data_manager_hdf5.py` | ✅ committed |
| `Datamanager/data_manager_zarr.py` | ✅ committed |
| `Recorder/recording_manager.py` | ✅ committed |
| `Recorder/frame_capture.py` | ✅ committed |
| `camera_adapters.py` | ✅ committed |
| `esp32_gui_controller.py` | ✅ committed |
| `GUI/log_panel.py` | ✅ committed |
| `main_widget.py` | ✅ committed |

Unstaged (nicht committet, nicht relevant für System):
- `.claude/settings.local.json`
- `figure1_single_led.tex`, `figure2_dual_led_resized.tex`, `figure3_complete_workflow.tex`
- `nematostella_perplexity_draft_platform_test_Backup.tex`
- `scripts/test_camera_zero_frame_recovery.py`

---

## Wichtige Architektur-Details

- **HDF5 vs Zarr:** Beide Formate sind per Recording exklusiv (nicht redundant). STANDARD-Modus hat keine internen redundanten Felder.
- **AGC:** Auto-Gain-Control ist schädlich für Frame-Differenz-ROI-Analyse (globaler Gain-Drift erzeugt Artefakte in allen ROIs gleichzeitig). Wird daher vor Recording deaktiviert.
- **Timing:** Deadline-basiert: `start_time + frame_number * interval_sec` — kein Drift-Aufbau.
- **Schedule Planner:** Alle Timeout-Reduzierungen gelten auch für Schedule-basierte Aufnahmen.
- **Pre-commit Hooks:** `mixed-line-ending` und `ruff-format` laufen bei jedem Commit. Falls Hooks Dateien ändern → re-stagen und nochmal committen.

---

## Nächste mögliche Aufgaben

Die `.tex`-Dateien im Root sind TikZ-Timing-Diagramme für eine wissenschaftliche Publikation über die Plattform. Der User könnte daran weiterarbeiten wollen.

`scripts/test_camera_zero_frame_recovery.py` ist ein neues Testskript (noch nicht committed).

---

## Wie neue Konversation starten

Öffne ein neues Chat-Fenster mit **Claude Opus 4.7** (`claude-opus-4-7`) und füge dieses Dokument als ersten Kontext ein, z.B.:

> "Hier ist der Kontext unseres Projekts: [Inhalt dieser Datei einfügen]. Ich möchte an [Aufgabe] weiterarbeiten."
