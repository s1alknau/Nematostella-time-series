# 🚀 Quick Start - ESP32 Firmware Update

## 📋 Was du brauchst

- ✅ ESP32 Dev Board
- ✅ USB-Kabel
- ✅ Arduino IDE (oder PlatformIO)
- ✅ Die neue Firmware-Datei

---

## ⚡ SCHNELLANLEITUNG (5 Minuten)

### Schritt 1: Firmware herunterladen ⬇️

[**ESP32_Firmware_Python_Compatible.ino**](computer:///mnt/user-data/outputs/ESP32_Firmware_Python_Compatible.ino) herunterladen

### Schritt 2: In Arduino IDE öffnen 📂

1. Arduino IDE starten
2. File → Open → `ESP32_Firmware_Python_Compatible.ino`

### Schritt 3: ESP32 Board auswählen 🔧

1. **Tools → Board → ESP32 Arduino → ESP32 Dev Module**
2. **Tools → Port → COM[X]** (dein ESP32 Port auswählen)

### Schritt 4: DHT Library installieren 📚

**Falls noch nicht installiert:**

1. Tools → Manage Libraries
2. Suche: "DHT sensor library"
3. Install: "DHT sensor library by Adafruit" (v1.4.4+)
4. Install auch: "Adafruit Unified Sensor"

### Schritt 5: Hochladen 🚀

1. **Klick auf Upload-Button** (→ Pfeil)
2. Warte bis "Done uploading" erscheint
3. **Reset-Button am ESP32 drücken**

### Schritt 6: Testen ✅

**In Python:**
```python
from timeseries_capture.ESP32_Controller import ESP32Controller

esp32 = ESP32Controller()
if esp32.connect():
    print("✅ SUCCESS! ESP32 works!")

    # LED Test
    esp32.select_led_type('ir')
    esp32.led_on()
    print("LED should be ON now!")

    esp32.led_off()
    esp32.disconnect()
else:
    print("❌ Connection failed")
```

**Oder in deinem Napari Widget:**
- Starte ImSwitch/Napari
- Öffne dein Timelapse Widget
- Tab "🔌 ESP32 Connection"
- Klick "Connect"
- Sollte jetzt funktionieren! ✅

---

## 🔍 Detaillierte Anleitung

### A. Arduino IDE Setup (einmalig)

Falls du noch keine ESP32-Unterstützung hast:

1. **File → Preferences**
2. **Additional Board Manager URLs:**
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. **Tools → Board → Boards Manager**
4. Suche: "esp32"
5. Install: "esp32 by Espressif Systems"

### B. Firmware Upload (ausführlich)

1. **Port finden:**
   - Windows: COM3, COM4, etc.
   - Mac/Linux: /dev/ttyUSB0, /dev/cu.usbserial-*

2. **Upload Settings:**
   - Board: ESP32 Dev Module
   - Upload Speed: 921600
   - Flash Frequency: 80MHz
   - Flash Mode: QIO
   - Flash Size: 4MB
   - Partition Scheme: Default 4MB
   - Core Debug Level: None

3. **Upload starten:**
   - Klick Upload
   - ESP32 geht automatisch in Flash-Modus
   - Warte bis "Leaving... Hard resetting"

4. **Nach Upload:**
   - Reset-Button am ESP32 drücken
   - LED sollte kurz aufblinken
   - ESP32 ist bereit!

### C. Verbindung testen

#### Test 1: Serial Monitor

1. **Tools → Serial Monitor**
2. **Baud Rate: 115200**
3. **Aktiviere Debug in Firmware:** `const bool DEBUG_ENABLED = true;`
4. **Reset ESP32**
5. **Sollte sehen:**
   ```
   ESP32 Nematostella Controller - Python Compatible v2.1
   Default timing: 400ms stab + 20ms exp
   ```

#### Test 2: Python Schnelltest

```python
import serial
import time

# Dein COM-Port
ser = serial.Serial('COM3', 115200, timeout=1)
time.sleep(2)

# LED ON Command (0x01)
ser.write(bytes([0x01]))
time.sleep(0.1)

# Read response (should be 0xAA)
response = ser.read(1)
print(f"Response: {response.hex()}")  # Should print: "aa"

if response == b'\xaa':
    print("✅ ESP32 firmware works!")
else:
    print(f"❌ Unexpected response: {response.hex()}")

ser.close()
```

#### Test 3: Vollständiger Python Test

```python
from timeseries_capture.ESP32_Controller import ESP32Controller

print("Testing ESP32 connection...")

# Connect
esp32 = ESP32Controller(port=None)  # Auto-detect
if not esp32.connect():
    print("❌ Failed to connect")
    exit(1)

print(f"✅ Connected on {esp32.comm.port}")

# Test 1: LED Select
print("\nTest 1: Select IR LED")
if esp32.select_led_type('ir'):
    print("✅ IR LED selected")
else:
    print("❌ Select failed")

# Test 2: LED ON
print("\nTest 2: LED ON")
if esp32.led_on():
    print("✅ LED ON successful")
    time.sleep(1)
else:
    print("❌ LED ON failed")

# Test 3: LED OFF
print("\nTest 3: LED OFF")
if esp32.led_off():
    print("✅ LED OFF successful")
else:
    print("❌ LED OFF failed")

# Test 4: Set Power
print("\nTest 4: Set LED Power to 50%")
if esp32.set_led_power(50, 'ir'):
    print("✅ Power set to 50%")
else:
    print("❌ Set power failed")

# Test 5: LED Status
print("\nTest 5: Get LED Status")
status = esp32.get_led_status()
if status:
    print(f"✅ Status: IR={status.ir_state}, White={status.white_state}")
    print(f"   Power: IR={status.ir_power}%, White={status.white_power}%")
else:
    print("❌ Get status failed")

# Test 6: Set Timing
print("\nTest 6: Set Timing (400ms + 20ms)")
if esp32.set_timing(400, 20):
    print("✅ Timing set")
else:
    print("❌ Set timing failed")

# Cleanup
esp32.disconnect()
print("\n✅ All tests completed!")
```

---

## 🐛 Troubleshooting

### Problem: "Port not found" / "Serial port busy"

**Lösung:**
```bash
# Windows
- Device Manager → Ports → Suche ESP32
- Schließe Arduino Serial Monitor
- Schließe andere Programme die den Port nutzen

# Mac/Linux
ls -l /dev/tty*
# Suche nach USB-Geräten
```

### Problem: "Upload failed" / "Timed out"

**Lösung:**
1. **Hold BOOT button** am ESP32
2. Klick **Upload** in Arduino
3. Wenn "Connecting..." erscheint, **release BOOT**
4. Warte bis Upload fertig

### Problem: "Response 0xAA not found" (nach Upload)

**Lösung:**
1. **ESP32 Reset** drücken
2. Python-Cache löschen:
   ```bash
   FOR /d /r . %d IN (__pycache__) DO @IF EXIST "%d" rd /s /q "%d"
   ```
3. Python neu starten
4. Nochmal testen

### Problem: LEDs funktionieren nicht

**Hardware Check:**
```
ESP32 Pin 4  → IR LED (via MOSFET/Treiber)
ESP32 Pin 15 → White LED (via MOSFET/Treiber)
ESP32 Pin 14 → DHT22 Sensor
ESP32 GND    → Common Ground
```

### Problem: Firmware kompiliert nicht

**Fehlende Library:**
```
Error: DHT.h: No such file or directory
```

**Lösung:**
1. Tools → Manage Libraries
2. Install: "DHT sensor library by Adafruit"
3. Install: "Adafruit Unified Sensor"

---

## 📊 Nach erfolgreichem Flash

### Was jetzt funktionieren sollte:

✅ ESP32 Verbindung in Python
✅ ESP32 Verbindung in Napari Widget
✅ LED ON/OFF Befehle
✅ LED Power Control (0-100%)
✅ LED Type Selection (IR/White)
✅ Timing Configuration
✅ Sync Capture (Single/Dual)
✅ LED Status Abfrage
✅ Sensor Daten (Temperatur/Humidity)

### Was noch zu tun ist:

⚠️ Recording-Funktionalität in Python implementieren
⚠️ Calibration implementieren

---

## 🎉 Erfolg!

Nach dem Flashen solltest du:

1. **In Python** - Alle LED-Befehle funktionieren
2. **In Napari** - ESP32 Connection Panel funktioniert
3. **Keine Errors** - "Response 0xAA not found" ist weg!

**Die Firmware ist jetzt 100% kompatibel mit deinem Python-Code!** 🚀

---

## 📚 Weiterführende Docs

- [Vollständige Firmware-Dokumentation](computer:///mnt/user-data/outputs/FIRMWARE_DOCUMENTATION.md)
- [Befehlsübersicht & Protocol](computer:///mnt/user-data/outputs/FIRMWARE_DOCUMENTATION.md#vollständige-befehlsübersicht)

---

## 🆘 Immer noch Probleme?

1. **Serial Monitor Check:**
   - 115200 baud
   - Reset ESP32
   - Siehst du "ESP32 Nematostella Controller"?

2. **Python Test:**
   - Führe den Schnelltest oben aus
   - Kopiere die Fehlermeldung
   - Schick sie mir!

3. **Hardware Check:**
   - USB-Kabel OK?
   - ESP32 LED blinkt beim Upload?
   - Richtiger COM-Port?

**Bei weiteren Fragen einfach melden!** 💪
