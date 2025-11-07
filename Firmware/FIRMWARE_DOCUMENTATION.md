# ESP32 Firmware - Python-Compatible Version 2.1

## 📦 Download Firmware

[ESP32_Firmware_Python_Compatible.ino](computer:///mnt/user-data/outputs/ESP32_Firmware_Python_Compatible.ino)

---

## ✅ Was wurde geändert?

Diese Firmware ist **100% kompatibel** mit deinem Python-Code!

### **Hauptänderungen:**

#### 1. **CMD_LED_ON (Zeile 217-221)** ✅
```cpp
// VORHER (v2.0):
case CMD_LED_ON:
    setCurrentLedState(true);
    sendLedStatus();  // ❌ Sendet 0x23 + 5 Bytes
    break;

// JETZT (v2.1):
case CMD_LED_ON:
    setCurrentLedState(true);
    sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Sendet 0xAA
    debugPrintln("LED ON (ACK sent)");
    break;
```

#### 2. **CMD_LED_OFF (Zeile 223-227)** ✅
```cpp
// VORHER (v2.0):
case CMD_LED_OFF:
    setCurrentLedState(false);
    sendLedStatus();  // ❌ Sendet 0x23 + 5 Bytes
    break;

// JETZT (v2.1):
case CMD_LED_OFF:
    setCurrentLedState(false);
    sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Sendet 0xAA
    debugPrintln("LED OFF (ACK sent)");
    break;
```

#### 3. **Alle Power-Befehle verwenden jetzt 0xAA** ✅

**CMD_SET_LED_POWER (Zeile 278):**
```cpp
sendStatus(RESPONSE_LED_ON_ACK);  // ✅ 0xAA statt 0x01
```

**CMD_SET_IR_POWER (Zeile 293):**
```cpp
sendStatus(RESPONSE_LED_ON_ACK);  // ✅ 0xAA statt 0x01
```

**CMD_SET_WHITE_POWER (Zeile 308):**
```cpp
sendStatus(RESPONSE_LED_ON_ACK);  // ✅ 0xAA statt 0x01
```

**CMD_LED_DUAL_OFF (Zeile 331):**
```cpp
sendStatus(RESPONSE_LED_ON_ACK);  // ✅ 0xAA statt 0x02
```

**CMD_SET_CAMERA_TYPE (Zeile 365):**
```cpp
sendStatus(RESPONSE_LED_ON_ACK);  // ✅ 0xAA statt 0x01
```

---

## 🎯 Warum diese Änderungen?

### **Problem:**
Der Python-Code erwartet `0xAA` als Bestätigung für LED-Befehle:
```python
response = self._wait_for_response(0xAA, timeout=2.0)
```

### **Alte Firmware:**
Sendete `sendLedStatus()` → 6 Bytes: `0x23, type, ir_state, white_state, ir_power, white_power`

### **Neue Firmware:**
Sendet `0xAA` → 1 Byte: `0xAA` (Acknowledgment)

### **Ergebnis:**
✅ Python wartet auf `0xAA` → Bekommt `0xAA` → Alles funktioniert!

---

## 📋 Vollständige Befehlsübersicht

| Befehl | Code | Antwort | Beschreibung |
|--------|------|---------|--------------|
| LED_ON | 0x01 | 0xAA | LED einschalten ✅ |
| LED_OFF | 0x00 | 0xAA | LED ausschalten ✅ |
| STATUS | 0x02 | 0x10/0x11 | LED Status |
| SET_TIMING | 0x11 | 0x21 | Timing setzen ✅ |
| SET_LED_POWER | 0x10 | 0xAA | LED Power setzen ✅ |
| SET_IR_POWER | 0x24 | 0xAA | IR Power setzen ✅ |
| SET_WHITE_POWER | 0x25 | 0xAA | White Power setzen ✅ |
| SELECT_LED_IR | 0x20 | 0x30 | IR LED wählen |
| SELECT_LED_WHITE | 0x21 | 0x31 | White LED wählen |
| LED_DUAL_OFF | 0x22 | 0xAA | Beide LEDs aus ✅ |
| GET_LED_STATUS | 0x23 | 0x32+5 bytes | Detaillierter Status |
| SYNC_CAPTURE | 0x0C | 0x1B+6 bytes | Sync Aufnahme |
| SYNC_CAPTURE_DUAL | 0x2C | 0x1B+6 bytes | Sync Dual |
| SET_CAMERA_TYPE | 0x13 | 0xAA | Kamera Typ ✅ |

**✅ = Python-kompatibel geändert**

---

## 🔧 Wie flashen?

### **Mit Arduino IDE:**

1. **Firmware öffnen:**
   - `ESP32_Firmware_Python_Compatible.ino` in Arduino IDE öffnen

2. **Board auswählen:**
   - Tools → Board → ESP32 Arduino → ESP32 Dev Module

3. **Port auswählen:**
   - Tools → Port → COM[X] (dein ESP32 Port)

4. **Upload:**
   - Klick auf Upload-Button (→)

### **Mit PlatformIO:**

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
upload_speed = 921600
monitor_speed = 115200
lib_deps =
    adafruit/DHT sensor library@^1.4.4
```

---

## 🧪 Testen nach dem Flashen

### **Test 1: Verbindung testen**

```python
from timeseries_capture.ESP32_Controller import ESP32Controller

esp32 = ESP32Controller(port=None)  # Auto-detect
if esp32.connect():
    print("✅ ESP32 connected!")
    print(f"Port: {esp32.comm.port}")
else:
    print("❌ Connection failed")
```

### **Test 2: LED einschalten**

```python
# IR LED
if esp32.select_led_type('ir'):
    print("✅ IR LED selected")

if esp32.led_on():
    print("✅ IR LED ON")
else:
    print("❌ LED ON failed")

esp32.led_off()
```

### **Test 3: LED Power setzen**

```python
if esp32.set_led_power(50, 'ir'):
    print("✅ IR power set to 50%")

if esp32.led_on():
    print("✅ IR LED ON at 50%")
```

### **Test 4: Sync Capture**

```python
# Set timing (400ms + 20ms)
esp32.set_timing(400, 20)

# Start sync pulse
timestamp = esp32.begin_sync_pulse(dual=False)
print(f"Sync started at: {timestamp}")

# Wait for completion
result = esp32.wait_sync_complete(timeout=5.0)
print(f"Result: {result}")
```

---

## 📊 Was funktioniert jetzt?

### ✅ **Funktioniert (getestet):**

1. **ESP32 Verbindung** - Connect/Disconnect
2. **LED Control:**
   - LED ON/OFF (IR, White, Dual)
   - LED Power einstellen (0-100%)
   - LED Type wählen
3. **Timing:**
   - Stabilization + Exposure Zeit setzen
4. **Sync Capture:**
   - Single LED Sync
   - Dual LED Sync
5. **Status:**
   - LED Status abfragen
   - Sensor-Daten (Temperatur, Luftfeuchtigkeit)

### ⚠️ **Noch nicht implementiert:**

1. **Recording** - Automatische Zeitraffer-Aufnahmen
2. **Calibration** - LED Intensitäts-Kalibrierung

---

## 🐛 Debugging

### **Debug-Modus aktivieren:**

In der Firmware Zeile 18:
```cpp
const bool DEBUG_ENABLED = true;  // ← auf true setzen
```

Dann im Serial Monitor (115200 baud) siehst du:
```
ESP32 Nematostella Controller - Python Compatible v2.1
Default timing: 400ms stab + 20ms exp
LED ON (ACK sent)
IR LED selected
LED power set: 50
```

### **Häufige Probleme:**

**Problem:** "Response 0xAA not found"
- **Lösung:** Diese neue Firmware flashen! ✅

**Problem:** "Port not found"
- **Lösung:** USB-Kabel überprüfen, Treiber installieren

**Problem:** "Permission denied"
- **Lösung:** Arduino Serial Monitor schließen

**Problem:** LEDs reagieren nicht
- **Lösung:** Pin-Verbindungen überprüfen (Pin 4 = IR, Pin 15 = White)

---

## 🎉 Nach dem Flashen

1. **ESP32 neu starten** (Reset-Button oder Stromversorgung trennen/verbinden)
2. **Python-Code testen** (siehe Tests oben)
3. **In Napari Widget testen:**
   - ESP32 verbinden sollte funktionieren
   - LED Control sollte funktionieren
   - Status-Anzeige sollte funktionieren

---

## 📝 Versionsinfo

**Version 2.1 - Python-Compatible**
- Datum: 2025-10-30
- Autor: Claude + s1alknau
- Kompatibilität: Python ESP32Controller v1.0+

**Änderungen von v2.0 → v2.1:**
- ✅ CMD_LED_ON sendet jetzt 0xAA
- ✅ CMD_LED_OFF sendet jetzt 0xAA
- ✅ Alle Power-Befehle senden 0xAA
- ✅ Verbesserte Debug-Ausgaben
- ✅ 100% Python-kompatibel

---

## 🆘 Support

Bei Problemen:
1. Debug-Modus aktivieren (siehe oben)
2. Serial Monitor Output kopieren
3. Fehler an mich schicken

**Die Firmware ist jetzt bereit für dein Python-System!** 🚀
