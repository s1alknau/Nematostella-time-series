# ESP32-S3-BOX-3 Firmware Upload Guide

## Übersicht

Diese Firmware ist für den **ESP32-S3-BOX-3** mit DOCK konfiguriert.

### Hardware-Anforderungen
- ESP32-S3-BOX-3 Entwicklungsboard
- ESP32-S3-BOX-3-DOCK (für GPIO-Zugriff)
- USB-C Kabel (Daten, nicht nur Laden!)

### GPIO-Pin-Zuordnung

| Funktion | GPIO Pin | Pmod Header |
|----------|----------|-------------|
| IR LED (PWM) | GPIO 10 | Links, Row 1, Pin 1 |
| Weiße LED (PWM) | GPIO 11 | Links, Row 1, Pin 3 |
| DHT22 Sensor | GPIO 12 | Links, Row 2, Pin 3 |

---

## Firmware flashen

### Methode 1: PlatformIO (empfohlen)

#### 1. PlatformIO installieren
```bash
# In VS Code: Extension "PlatformIO IDE" installieren
# Oder via CLI:
pip install platformio
```

#### 2. Firmware kompilieren und hochladen
```bash
cd Firmware/LED_Nematostella

# Für ESP32-S3-BOX-3 (Standard):
pio run -e esp32-s3-box-3 --target upload

# Monitor starten (Serial-Ausgabe):
pio device monitor -e esp32-s3-box-3
```

#### 3. COM Port manuell auswählen (falls nötig)
```bash
# Verfügbare Ports anzeigen:
pio device list

# Mit spezifischem Port uploaden:
pio run -e esp32-s3-box-3 --target upload --upload-port COM3
```

---

### Methode 2: Arduino IDE

#### 1. Board Manager konfigurieren
1. Öffne Arduino IDE
2. `Datei` → `Voreinstellungen`
3. Füge zur "Zusätzliche Boardverwalter-URLs" hinzu:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
4. `Tools` → `Board` → `Boards Manager`
5. Suche "esp32" und installiere "esp32 by Espressif Systems"

#### 2. Board auswählen
1. `Tools` → `Board` → `ESP32 Arduino` → **ESP32S3 Dev Module**
2. Konfiguriere Board-Einstellungen:
   - **USB CDC On Boot**: `Enabled` ✅
   - **Partition Scheme**: `Default 4MB with spiffs`
   - **Flash Mode**: `QIO 80MHz`
   - **Flash Size**: `16MB`
   - **PSRAM**: `OPI PSRAM`
   - **Upload Speed**: `921600`

#### 3. Sketch öffnen und hochladen
1. `Datei` → `Öffnen` → `src/main.cpp`
2. ESP32-S3-BOX-3 via USB-C verbinden
3. `Tools` → `Port` → Richtigen COM Port auswählen
4. Klicke **Upload** (→ Button)

#### 4. Falls Upload fehlschlägt:
1. Halte **BOOT** Button auf ESP32-S3-BOX-3
2. Drücke kurz **RESET** Button
3. Lasse **BOOT** los
4. Klicke erneut auf Upload

---

## Firmware überprüfen

### Serial Monitor öffnen (115200 Baud)

**PlatformIO:**
```bash
pio device monitor -e esp32-s3-box-3
```

**Arduino IDE:**
- `Tools` → `Serial Monitor`
- Baud Rate: `115200`

### Erwartete Ausgabe
```
ESP32 Nematostella Controller - Python Compatible v2.2
Default timing: 400ms stab + 20ms exp = 420ms total
```

### Firmware testen

**Sende Befehle via Serial Monitor:**
```
STATUS       → Sollte Temperatur/Luftfeuchtigkeit zurückgeben
LED_ON       → Sollte aktuelle LED einschalten
LED_OFF      → Sollte LED ausschalten
```

---

## Hardware-Verkabelung

### Pmod Header Pin-Zuordnung (ESP32-S3-BOX-3-DOCK)

**Linker Pmod Header:**
```
Row 1: [G10]  [G14]  [G11]  [G43/TXD]  [GND]  [3V3]
        ↑              ↑
        IR LED         White LED

Row 2: [G13]  [G9]   [G12]  [G44/RXD]  [GND]  [3V3]
                       ↑
                       DHT22
```

### MOSFET-Verbindungen

**IR LED (GPIO 10):**
```
ESP32-S3 GPIO 10 (Pmod) ──→ IRLZ34N Gate
12V PSU (+) ────────────→ IRLZ34N Drain
IRLZ34N Source ─────────→ Common Ground (WAGO #3)
IR LED Strip (+) ───────→ 12V PSU (+) via WAGO #1
IR LED Strip (-) ───────→ Common Ground (WAGO #3)
```

**Weiße LED (GPIO 11):**
```
ESP32-S3 GPIO 11 (Pmod) ──→ IRLZ34N Gate
24V PSU (+) ────────────→ IRLZ34N Drain
IRLZ34N Source ─────────→ Common Ground (WAGO #3)
White LED Strip (+) ────→ 24V PSU (+) via WAGO #2
White LED Strip (-) ────→ Common Ground (WAGO #3)
```

**DHT22 Sensor (GPIO 12):**
```
DHT22 VCC  → ESP32-S3-DOCK 3V3 (Pmod Header)
DHT22 Data → ESP32-S3-DOCK GPIO 12
DHT22 GND  → ESP32-S3-DOCK GND (Pmod Header)
```

**⚠️ WICHTIG: Gemeinsame Masse!**
```
WAGO #3 (Common Ground Hub):
├─ 12V PSU GND (-)
├─ 24V PSU GND (-)
├─ ESP32-S3-DOCK GND (via Pmod)
├─ IR MOSFET Source
├─ White MOSFET Source
├─ IR LED Strip (-)
└─ White LED Strip (-)
```

---

## Fehlersuche

### Problem: ESP32-S3-BOX-3 wird nicht erkannt

**Lösung:**
1. Prüfe USB-C Kabel (muss Daten übertragen können!)
2. Installiere CH340/CP210x USB-Treiber
3. Aktiviere "USB CDC On Boot" in Board-Einstellungen
4. Versuche anderen USB-Port

### Problem: Upload schlägt fehl

**Lösung:**
1. Halte BOOT + drücke RESET
2. Verringere Upload-Speed auf `115200`
3. Prüfe Board-Auswahl: "ESP32S3 Dev Module"
4. Schließe Serial Monitor vor Upload

### Problem: LEDs reagieren nicht

**Lösung:**
1. Prüfe GPIO 10/11 Verkabelung mit Multimeter
2. Teste PWM-Signal mit Oszilloskop (0-3.3V, 15kHz)
3. Prüfe MOSFET-Gate-Verbindungen
4. Bestätige gemeinsame Masse (WAGO #3)

### Problem: DHT22 zeigt 0.0°C / 0.0%

**Lösung:**
1. Verwende 3.3V vom **Pmod Header**, nicht intern!
2. Prüfe GPIO 12 Verbindung
3. Stelle sicher DHT22-Board hat Pull-Up-Widerstand
4. Warte 2 Sekunden nach ESP32-Boot für DHT22-Warmup

### Problem: Display zeigt Müll

**Lösung:**
- Das ist normal und beeinträchtigt die Funktion nicht!
- Display wird nicht verwendet (nur LEDs/Sensor/Serial)
- Display kann ignoriert werden

---

## Alternative Pin-Konfigurationen

Falls GPIO 10/11/12 nicht verfügbar sind:

**Option 2:**
```cpp
const int ledIrPin     = 38;
const int ledWhitePin  = 39;
const int dhtPin       = 40;
```

**Option 3:**
```cpp
const int ledIrPin     = 13;
const int ledWhitePin  = 14;
const int dhtPin       = 9;
```

**⚠️ NICHT VERWENDEN (intern belegt):**
- GPIO 4-7 (Display Controller)
- GPIO 15, 17, 45, 46 (Audio System)
- GPIO 18, 8 (I²C Bus)

---

## Firmware-Version

**Aktuelle Version:** v2.2 (ESP32-S3-BOX-3 kompatibel)

**Änderungen gegenüber ESP32:**
- ✅ GPIO-Pins geändert: 4→10, 15→11, 14→12
- ✅ USB CDC aktiviert für Serial über USB-C
- ✅ PSRAM-Unterstützung aktiviert
- ✅ Kompatibel mit Python-Plugin

---

## Support

- **Dokumentation:** [ESP32-S3-BOX-3_CONFIGURATION.md](../../docs/ESP32-S3-BOX-3_CONFIGURATION.md)
- **Hauptdokumentation:** [README.md](../../README.md)
- **Espressif Docs:** https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/

---

**Letzte Aktualisierung:** 2025-12-15
