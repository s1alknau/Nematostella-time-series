#include <Arduino.h>
#include "esp_task_wdt.h"  // ESP32 Watchdog
#include <DHT.h>           // DHT22-Library

// -------- PIN- UND KOMMANDODEFINITION --------
const int ledPin   = 4;    // GPIO4, LED-Ausgang
const int dhtPin   = 27;   // GPIO27, DHT22-Datenpin
#define DHTTYPE   DHT22

// Zusätzlicher Parameter für LED-Warmup
static const uint32_t LED_WARMUP_MS = 50;  // Zeit, um LED auf volle Helligkeit zu bringen

// Befehls-Bytes
const byte CMD_LED_ON           = 0x01;  // LED einschalten (Einzel-Command)
const byte CMD_LED_OFF          = 0x00;  // LED ausschalten (Einzel-Command)
const byte CMD_STATUS           = 0x02;  // Statusabfrage (LED an/aus)
const byte CMD_START_TIMELAPSE  = 0x03;  // Starte automatischen Timelapse-Modus
const byte CMD_STOP_TIMELAPSE   = 0x04;  // Stoppe Timelapse-Modus

// Antwort-Bytes (LED Acknowledge / Status)
const byte RESPONSE_ACK_ON       = 0x01;  // LED wurde eingeschaltet (Einzel-Command)
const byte RESPONSE_ACK_OFF      = 0x02;  // LED wurde ausgeschaltet (Einzel-Command)
const byte RESPONSE_STATUS_ON    = 0x11;  // Antwort: LED ist an
const byte RESPONSE_STATUS_OFF   = 0x10;  // Antwort: LED ist aus

// Zusätzliche Timelapse-Antwort­Bytes
const byte RESPONSE_TIMELAPSE_ACK    = 0xA3;  // Timelapse startet
const byte RESPONSE_TIMELAPSE_STOP   = 0xA4;  // Timelapse stoppt

// Fehler-/Timeout-Codes
const byte RESPONSE_ERROR             = 0xFF;  // Genereller Sende-Fehler
const byte RESPONSE_BUFFER_OVERFLOW   = 0xFE;  // Mehr als 1 Byte im Puffer
const byte RESPONSE_TIMEOUT           = 0xFD;  // Kein Byte innerhalb TIMEOUT empfangen
const byte RESPONSE_INVALID_CMD       = 0xFC;  // Unbekanntes Kommando

// Kommunikationsparameter
const unsigned long SERIAL_TIMEOUT      = 1000;  // Maximal 1000 ms auf eingehendes Byte warten
const int            RETRY_LIMIT         = 3;    // Versuche, ein Antwort-Byte zu senden
const int            MAX_COMMAND_SIZE    = 1;    // Wir erwarten strikt 1 Byte pro Kommando
const unsigned long  WRITE_WAIT_TIMEOUT  = 200;  // Maximal 200 ms, um Platz im TX-Puffer zu schaffen

// Timelapse-Variablen
bool           timelapseRunning = false;
uint32_t       interval_ms      = 0;  // Gesamtes Intervall in ms (z. B. 5000 für 5 s)
uint32_t       exposure_ms      = 0;  // Belichtungsdauer in ms (z. B. 1000 für 1 s)

// DHT-Instanz
DHT dht(dhtPin, DHTTYPE);

// ---------- WATCHDOG INITIALISIERUNG ----------
void enableWatchdog() {
    esp_task_wdt_init(10, false);  // 10 s, kein Panic, nur Idle-Task
    esp_task_wdt_add(NULL);
}

// ---------- SENDEN EINER ANTWORT (1 Byte) ----------
void sendResponse(byte response) {
    // Versuche bis zu WRITE_WAIT_TIMEOUT ms, Platz im TX-Puffer zu bekommen
    unsigned long start = millis();
    while (Serial.availableForWrite() == 0 && (millis() - start) < WRITE_WAIT_TIMEOUT) {
        esp_task_wdt_reset();
        delay(1);
    }
    if (Serial.availableForWrite() > 0) {
        Serial.write(response);
        Serial.flush();
    } else {
        // Falls nach WRITE_WAIT_TIMEOUT immer noch kein Platz: sende generellen Fehler
        if (Serial.availableForWrite() > 0) {
            Serial.write(RESPONSE_ERROR);
            Serial.flush();
        }
    }
}

// ---------- SENDEN DER DHT22-DATEN (2 Bytes: [int8 Temp] [uint8 Humidity]) ----------
void sendDHTData() {
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h)) h = 0.0f;
    if (isnan(t)) t = 0.0f;

    int8_t  tempInt = (int8_t)round(t);
    if (tempInt < -128) tempInt = -128;
    if (tempInt > 127)  tempInt = 127;

    uint8_t humInt = (uint8_t)round(h);
    if (humInt > 100) humInt = 100;

    // 1) Warte, bis Puffer Platz hat
    unsigned long start = millis();
    while (Serial.availableForWrite() == 0 && (millis() - start < WRITE_WAIT_TIMEOUT)) {
        esp_task_wdt_reset();
        delay(1);
    }
    // 2) Temp-Byte senden
    if (Serial.availableForWrite() > 0) {
        Serial.write((uint8_t)tempInt);
        Serial.flush();
    }
    // 3) Warte kurz für 2. Byte
    start = millis();
    while (Serial.availableForWrite() == 0 && (millis() - start < WRITE_WAIT_TIMEOUT)) {
        esp_task_wdt_reset();
        delay(1);
    }
    // 4) Humidity-Byte senden
    if (Serial.availableForWrite() > 0) {
        Serial.write(humInt);
        Serial.flush();
    }
}

// ---------- Puffer LEEREN ----------
void clearSerialBuffer() {
    while (Serial.available() > 0) {
        Serial.read();
    }
}

// ---------- EINZEL-KOMMANDO BEARBEITUNG (LED + STATUS + DHT) ----------
void handleSingleCommand(byte command) {
    switch (command) {
        case CMD_LED_ON:
            if (digitalRead(ledPin) == LOW) {
                digitalWrite(ledPin, HIGH);
                delay(LED_WARMUP_MS);  // LED kurz auf maximale Helligkeit bringen
            }
            sendResponse(RESPONSE_ACK_ON);
            sendDHTData();
            break;

        case CMD_LED_OFF:
            if (digitalRead(ledPin) == HIGH) {
                digitalWrite(ledPin, LOW);
            }
            sendResponse(RESPONSE_ACK_OFF);
            sendDHTData();
            break;

        case CMD_STATUS:
            if (digitalRead(ledPin) == HIGH) {
                sendResponse(RESPONSE_STATUS_ON);
            } else {
                sendResponse(RESPONSE_STATUS_OFF);
            }
            sendDHTData();
            break;

        default:
            sendResponse(RESPONSE_INVALID_CMD);
            // Bei ungültigem Kommando keine DHT-Daten senden
            break;
    }
}

// ---------- TIMELAPSE-SCHLEIFE IN DER FIRMWARE ----------
void runTimelapse() {
    // Sicherstellen, dass exposure_ms ≤ interval_ms
    if (exposure_ms > interval_ms) {
        exposure_ms = interval_ms;
    }

    // absolute Zeit, zu der das erste LED-ON-Ereignis ansteht
    uint32_t nextTrigger = millis();

    while (timelapseRunning) {
        // 1) LED einschalten und Warmup abwarten
        digitalWrite(ledPin, HIGH);
        delay(LED_WARMUP_MS);

        // 2) Sendet ein „Capture-Ready“-Signal an den Host:
        //    - Wir nutzen RESPONSE_ACK_ON, um zu sagen, dass LED voll hell ist.
        sendResponse(RESPONSE_ACK_ON);
        //    - Gleichzeitig DHT22 auslesen und senden (2 Byte)
        sendDHTData();

        // 3) Belichtungsdauer: LED weiter eingeschaltet lassen
        //    => exposure_ms beinhaltet bereits die Warmup-Phase oder nicht?
        //    Hier rechnen wir so, dass exposure_ms die *gesamte* Zeit ist,
        //    inklusive Warmup. Wenn ihr exposure_ms = 1000 ms gebt, und
        //    LED_WARMUP_MS = 50 ms, dann: 
        //      - erste 50 ms = Warmup,
        //      - weitere 950 ms = „tatsächliche Belichtung“, 
        //    In Summe 1000 ms LED ON.
        uint32_t remainingExposure = 0;
        if (exposure_ms > LED_WARMUP_MS) {
            remainingExposure = exposure_ms - LED_WARMUP_MS;
        }
        if (remainingExposure > 0) {
            delay(remainingExposure);
        }

        // 4) LED ausschalten
        digitalWrite(ledPin, LOW);

        // 5) Nächsten Zyklus terminieren
        nextTrigger += interval_ms;
        long now    = (long)millis();
        long toWait = (long)nextTrigger - now;

        // Falls Stop-Kommando gekommen ist, break
        if (!timelapseRunning) break;

        // 6) Warten, bis wir das Intervall erreicht haben
        if (toWait > 0) {
            unsigned long wakeup = millis() + toWait;
            while (millis() < wakeup && timelapseRunning) {
                esp_task_wdt_reset();
                delay(10);
            }
        }
        // Falls toWait ≤ 0, war Belichtungszeit plus DHT-Übertragung länger
        // als interval_ms → nächster Zyklus startet sofort.
    }

    // 7) Nachdem timelapseRunning = false wurde, LED sicher abschalten
    digitalWrite(ledPin, LOW);
}

// ---------- SETUP ----------
void setup() {
    // Serielle Schnittstelle initialisieren
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0 < 2000)) {
        esp_task_wdt_reset();
        delay(10);
    }

    // LED-Pin initialisieren
    pinMode(ledPin, OUTPUT);
    digitalWrite(ledPin, LOW);

    // DHT22 initialisieren
    dht.begin();

    // Watchdog aktivieren
    enableWatchdog();
}

// ---------- HAUPTSCHLEIFE ----------
void loop() {
    // Watchdog zurücksetzen
    esp_task_wdt_reset();

    // 1) Wenn Timelapse-Modus aktiv, sofort dorthin springen
    if (timelapseRunning) {
        runTimelapse();
        return;  // Sobald runTimelapse() fertig ist, kommen wir wieder here zurück
    }

    // 2) Sonst: Einzel-Kommando-Verarbeitung
    unsigned long startTime = millis();
    while (!Serial.available() && (millis() - startTime < SERIAL_TIMEOUT)) {
        esp_task_wdt_reset();
        delay(1);
    }
    if (!Serial.available()) {
        sendResponse(RESPONSE_TIMEOUT);
        return;
    }

    if (Serial.available() > MAX_COMMAND_SIZE) {
        sendResponse(RESPONSE_BUFFER_OVERFLOW);
        clearSerialBuffer();
        return;
    }

    // 3) Genau 1 Byte vorhanden: Kommando lesen
    byte cmd = Serial.read();
    switch (cmd) {
        case CMD_START_TIMELAPSE:
            {
                // Warte, bis die 8 Parameter-Bytes eingetroffen sind
                unsigned long t0 = millis();
                while (Serial.available() < 8 && (millis() - t0 < SERIAL_TIMEOUT)) {
                    esp_task_wdt_reset();
                    delay(1);
                }
                if (Serial.available() < 8) {
                    sendResponse(RESPONSE_TIMEOUT);
                    clearSerialBuffer();
                    break;
                }
                // 4 Bytes interval_ms (MSB zuerst)
                uint32_t recv_interval = 0;
                for (int i = 0; i < 4; i++) {
                    recv_interval <<= 8;
                    recv_interval |= (uint8_t)Serial.read();
                }
                // 4 Bytes exposure_ms
                uint32_t recv_exposure = 0;
                for (int i = 0; i < 4; i++) {
                    recv_exposure <<= 8;
                    recv_exposure |= (uint8_t)Serial.read();
                }

                // Übergabe in globale Variablen
                interval_ms = recv_interval;
                exposure_ms = recv_exposure;
                if (interval_ms == 0) interval_ms = 1;         // Absicherung
                if (exposure_ms > interval_ms) exposure_ms = interval_ms;

                timelapseRunning = true;
                sendResponse(RESPONSE_TIMELAPSE_ACK);  // 0xA3
            }
            break;

        case CMD_STOP_TIMELAPSE:
            timelapseRunning = false;
            sendResponse(RESPONSE_TIMELAPSE_STOP);  // 0xA4
            break;

        default:
            handleSingleCommand(cmd);
            break;
    }

    delay(10);
}
