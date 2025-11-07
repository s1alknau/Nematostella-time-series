#include <Arduino.h>
#include "esp_task_wdt.h"
#include <DHT.h>

// ========================================================================
// NEMATOSTELLA ESP32 FIRMWARE - PYTHON-COMPATIBLE VERSION
// ========================================================================
// Version: 2.2 - Python Communication Compatible (Corrected)
// Date: 2025-11-03
// FIXES:
// - CMD_LED_ON now sends 0xAA (RESPONSE_LED_ON_ACK) for Python compatibility
// - CMD_LED_OFF now sends 0xAA for Python compatibility
// - All ACK responses properly aligned with Python code expectations
// - Default timing: 400ms stabilization + 20ms exposure
// - Improved serial buffer handling
// - Removed old 7-byte sendSyncResponse() - now only uses 15-byte format
// - Clarified timing: LED stays on for (stabilization_ms + exposure_ms) total
// ========================================================================

const bool DEBUG_ENABLED = false;

// PIN DEFINITIONS
const int ledIrPin     = 4;
const int ledWhitePin  = 15;
const int dhtPin       = 14;
#define DHTTYPE DHT22

// PWM CONFIG
const int PWM_CHANNEL_IR     = 0;
const int PWM_CHANNEL_WHITE  = 1;
const int PWM_FREQUENCY      = 15000;
const int PWM_RESOLUTION     = 10;

// COMMANDS
const byte CMD_LED_ON           = 0x01;
const byte CMD_LED_OFF          = 0x00;
const byte CMD_STATUS           = 0x02;
const byte CMD_SYNC_CAPTURE     = 0x0C;
const byte CMD_SET_LED_POWER    = 0x10;
const byte CMD_SET_TIMING       = 0x11;
const byte CMD_SET_CAMERA_TYPE  = 0x13;
const byte CMD_SET_IR_POWER     = 0x24;
const byte CMD_SET_WHITE_POWER  = 0x25;
const byte CMD_SYNC_CAPTURE_DUAL= 0x2C;
const byte CMD_SELECT_LED_IR    = 0x20;
const byte CMD_SELECT_LED_WHITE = 0x21;
const byte CMD_LED_DUAL_OFF     = 0x22;
const byte CMD_GET_LED_STATUS   = 0x23;

// RESPONSES
const byte RESPONSE_LED_ON_ACK      = 0xAA;  // ✅ Used for LED ON/OFF confirmation
const byte RESPONSE_SYNC_COMPLETE   = 0x1B;
const byte RESPONSE_TIMING_SET      = 0x21;
const byte RESPONSE_ACK_ON          = 0x01;
const byte RESPONSE_ACK_OFF         = 0x02;
const byte RESPONSE_STATUS_ON       = 0x11;
const byte RESPONSE_STATUS_OFF      = 0x10;
const byte RESPONSE_ERROR           = 0xFF;
const byte RESPONSE_LED_IR_SELECTED    = 0x30;
const byte RESPONSE_LED_WHITE_SELECTED = 0x31;
const byte RESPONSE_LED_STATUS         = 0x32;

// CAMERA TYPES
const byte CAMERA_TYPE_HIK_GIGE    = 1;
const byte CAMERA_TYPE_USB_GENERIC = 2;

// LED TYPES
const byte LED_TYPE_IR    = 0;
const byte LED_TYPE_WHITE = 1;

// DEFAULT TIMING
// NOTE: Total LED-on time = LED_STABILIZATION_MS + EXPOSURE_MS
// Default: 400ms stabilization + 20ms exposure = 420ms total LED-on time
static uint16_t LED_STABILIZATION_MS = 400;
static uint16_t EXPOSURE_MS          = 20;
static uint8_t  CAMERA_TYPE          = CAMERA_TYPE_HIK_GIGE;

static uint8_t  LED_POWER_PERCENT_IR    = 100;
static uint8_t  LED_POWER_PERCENT_WHITE = 100;
static uint8_t  LED_POWER_PERCENT       = 100;

static bool     ledIrState       = false;
static bool     ledWhiteState    = false;
static uint8_t  currentLedType   = LED_TYPE_IR;

DHT dht(dhtPin, DHTTYPE);

unsigned long lastSyncTime = 0;
unsigned long bootTime     = 0;
unsigned long lastBufferClear = 0;
const unsigned long BUFFER_CLEAR_INTERVAL = 30000;

struct SensorHistory {
  float temp_values[5];
  float hum_values[5];
  int   index;
  int   count;
  bool  initialized;
};
static SensorHistory sensor_history = {0};

// ========================================================================
// FUNCTION PROTOTYPES
// ========================================================================
void clearSerialBuffer();
void sendRawByte(byte b);
void sendStatus(byte code);
void sendStatusWithSensorData(byte code);
void sendSyncResponseWithDuration(float temp, float hum, uint16_t duration_ms);
void setLedState(bool state, uint8_t ledType);
void setCurrentLedState(bool state);
void updateLedOutput(uint8_t ledType);
void updateCurrentLedOutput();
void setLedPowerCurrent(uint8_t power);
void setIrPower(uint8_t power);
void setWhitePower(uint8_t power);
void performSyncCapture();
void performSyncCaptureDual();
void setTiming(uint16_t stabilization_ms, uint16_t exposure_ms);
void selectLed(uint8_t ledType);
void turnOffAllLeds();
void sendLedStatus();
bool readSensorsWithValidation(float &temperature, float &humidity);
void addToSensorHistory(float temp, float hum);
float getFilteredTemperature();
float getFilteredHumidity();

void debugPrint(const char* msg) { if (DEBUG_ENABLED) Serial.print(msg); }
void debugPrint(int val)         { if (DEBUG_ENABLED) Serial.print(val); }
void debugPrintln(const char* msg){ if (DEBUG_ENABLED) Serial.println(msg); }
void debugPrintln(int val)       { if (DEBUG_ENABLED) Serial.println(val); }

// ========================================================================
// SETUP
// ========================================================================
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);

  // Configure PWM
  ledcSetup(PWM_CHANNEL_IR, PWM_FREQUENCY, PWM_RESOLUTION);
  ledcSetup(PWM_CHANNEL_WHITE, PWM_FREQUENCY, PWM_RESOLUTION);
  ledcAttachPin(ledIrPin, PWM_CHANNEL_IR);
  ledcAttachPin(ledWhitePin, PWM_CHANNEL_WHITE);

  // Start with LEDs off
  ledcWrite(PWM_CHANNEL_IR, 0);
  ledcWrite(PWM_CHANNEL_WHITE, 0);

  // Init DHT
  dht.begin();
  delay(2000);  // DHT warmup

  // Read initial sensor values
  float temp, hum;
  readSensorsWithValidation(temp, hum);

  bootTime = millis();

  debugPrintln("ESP32 Nematostella Controller - Python Compatible v2.2");
  debugPrint("Default timing: ");
  debugPrint(LED_STABILIZATION_MS);
  debugPrint("ms stab + ");
  debugPrint(EXPOSURE_MS);
  debugPrint("ms exp = ");
  debugPrint(LED_STABILIZATION_MS + EXPOSURE_MS);
  debugPrintln("ms total");
}

// ========================================================================
// MAIN LOOP
// ========================================================================
void loop() {
  // Periodic buffer clear
  if (millis() - lastBufferClear > BUFFER_CLEAR_INTERVAL) {
    if (Serial.available() > 10) {
      clearSerialBuffer();
    }
    lastBufferClear = millis();
  }

  // Process commands
  if (Serial.available() > 0) {
    byte cmd = Serial.read();

    switch (cmd) {

      // ================================================================
      // ✅ LED ON - PYTHON COMPATIBLE
      // ================================================================
      case CMD_LED_ON:
          setCurrentLedState(true);
          sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Send 0xAA for Python
          debugPrintln("LED ON (ACK sent)");
          break;

      // ================================================================
      // ✅ LED OFF - PYTHON COMPATIBLE
      // ================================================================
      case CMD_LED_OFF:
          setCurrentLedState(false);
          sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Send 0xAA for Python
          debugPrintln("LED OFF (ACK sent)");
          break;

      // ================================================================
      // STATUS - Returns status + sensor data (5 bytes)
      // ================================================================
      case CMD_STATUS:
        if (ledIrState || ledWhiteState) {
          sendStatusWithSensorData(RESPONSE_STATUS_ON);
        } else {
          sendStatusWithSensorData(RESPONSE_STATUS_OFF);
        }
        debugPrintln("Status sent with sensor data");
        break;

      // ================================================================
      // SET TIMING
      // ================================================================
      case CMD_SET_TIMING:
        {
          debugPrintln("CMD_SET_TIMING received");

          // Wait for 4 bytes (2x uint16_t, big-endian)
          unsigned long wait_start = millis();
          while (Serial.available() < 4) {
            if (millis() - wait_start > 1000) {
              debugPrintln("Timeout waiting for timing data");
              sendStatus(RESPONSE_ERROR);
              break;
            }
            delay(1);
          }

          if (Serial.available() >= 4) {
            byte buf[4];
            Serial.readBytes(buf, 4);

            // Parse big-endian uint16
            uint16_t stab_ms = (buf[0] << 8) | buf[1];
            uint16_t exp_ms  = (buf[2] << 8) | buf[3];

            // Validate ranges
            if (stab_ms < 10) stab_ms = 10;
            if (stab_ms > 10000) stab_ms = 10000;
            if (exp_ms < 0) exp_ms = 0;
            if (exp_ms > 30000) exp_ms = 30000;

            // Update globals
            LED_STABILIZATION_MS = stab_ms;
            EXPOSURE_MS = exp_ms;

            debugPrint("Timing set: ");
            debugPrint(LED_STABILIZATION_MS);
            debugPrint("ms + ");
            debugPrint(EXPOSURE_MS);
            debugPrintln("ms");

            // Send ACK
            sendStatus(RESPONSE_TIMING_SET);
            Serial.flush();
          }
        }
        break;

      // ================================================================
      // SET LED POWER (current LED)
      // ================================================================
      case CMD_SET_LED_POWER:
        {
          unsigned long wait_start = millis();
          while (Serial.available() < 1) {
            if (millis() - wait_start > 500) break;
            delay(1);
          }
          if (Serial.available() >= 1) {
            uint8_t power = Serial.read();
            if (power > 100) power = 100;
            setLedPowerCurrent(power);
            sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Use 0xAA for consistency
            debugPrint("LED power set: ");
            debugPrintln(power);
          }
        }
        break;

      // ================================================================
      // SET IR POWER
      // ================================================================
      case CMD_SET_IR_POWER:
        {
          unsigned long wait_start = millis();
          while (Serial.available() < 1) {
            if (millis() - wait_start > 500) break;
            delay(1);
          }
          if (Serial.available() >= 1) {
            uint8_t power = Serial.read();
            if (power > 100) power = 100;
            setIrPower(power);
            sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Use 0xAA for consistency
            debugPrint("IR power set: ");
            debugPrintln(power);
          }
        }
        break;

      // ================================================================
      // SET WHITE POWER
      // ================================================================
      case CMD_SET_WHITE_POWER:
        {
          unsigned long wait_start = millis();
          while (Serial.available() < 1) {
            if (millis() - wait_start > 500) break;
            delay(1);
          }
          if (Serial.available() >= 1) {
            uint8_t power = Serial.read();
            if (power > 100) power = 100;
            setWhitePower(power);
            sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Use 0xAA for consistency
            debugPrint("White power set: ");
            debugPrintln(power);
          }
        }
        break;

      // ================================================================
      // SELECT LED IR
      // ================================================================
      case CMD_SELECT_LED_IR:
        selectLed(LED_TYPE_IR);
        sendStatus(RESPONSE_LED_IR_SELECTED);
        debugPrintln("IR LED selected");
        break;

      // ================================================================
      // SELECT LED WHITE
      // ================================================================
      case CMD_SELECT_LED_WHITE:
        selectLed(LED_TYPE_WHITE);
        sendStatus(RESPONSE_LED_WHITE_SELECTED);
        debugPrintln("White LED selected");
        break;

      // ================================================================
      // DUAL LED OFF
      // ================================================================
      case CMD_LED_DUAL_OFF:
        turnOffAllLeds();
        sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Use 0xAA for consistency
        debugPrintln("All LEDs OFF");
        break;

      // ================================================================
      // GET LED STATUS - Detailed response
      // ================================================================
      case CMD_GET_LED_STATUS:
        sendLedStatus();
        debugPrintln("LED status sent");
        break;

      // ================================================================
      // SYNC CAPTURE (SINGLE LED)
      // ================================================================
      case CMD_SYNC_CAPTURE:
        performSyncCapture();
        break;

      // ================================================================
      // SYNC CAPTURE DUAL
      // ================================================================
      case CMD_SYNC_CAPTURE_DUAL:
        performSyncCaptureDual();
        break;

      // ================================================================
      // SET CAMERA TYPE
      // ================================================================
      case CMD_SET_CAMERA_TYPE:
        {
          unsigned long wait_start = millis();
          while (Serial.available() < 1) {
            if (millis() - wait_start > 500) break;
            delay(1);
          }
          if (Serial.available() >= 1) {
            CAMERA_TYPE = Serial.read();
            sendStatus(RESPONSE_LED_ON_ACK);  // ✅ Use 0xAA for consistency
            debugPrint("Camera type set: ");
            debugPrintln(CAMERA_TYPE);
          }
        }
        break;

      // ================================================================
      // UNKNOWN COMMAND
      // ================================================================
      default:
        debugPrint("Unknown cmd: 0x");
        debugPrintln(cmd);
        sendStatus(RESPONSE_ERROR);
        break;
    }
  }
}

// ========================================================================
// HELPER FUNCTIONS
// ========================================================================

void clearSerialBuffer() {
  int bytesCleared = 0;
  while (Serial.available() > 0) {
    Serial.read();
    bytesCleared++;
  }
  if (bytesCleared > 0) {
    debugPrint("Cleared ");
    debugPrint(bytesCleared);
    debugPrintln(" bytes");
  }
}

void sendRawByte(byte b) {
  Serial.write(b);
  Serial.flush();
}

void sendStatus(byte code) {
  // For simple ACK responses, just send the byte
  sendRawByte(code);
}

void sendStatusWithSensorData(byte code) {
  // Send status byte + temperature + humidity (5 bytes total)
  // Format: [code][temp_high][temp_low][hum_high][hum_low]

  // Read sensors
  float temp, hum;
  readSensorsWithValidation(temp, hum);

  // Convert to int16 (scaled by 10 for 1 decimal precision)
  int16_t temp_scaled = (int16_t)(temp * 10.0);
  uint16_t hum_scaled = (uint16_t)(hum * 10.0);

  // Clamp values
  if (temp_scaled < -400) temp_scaled = -400;  // -40.0°C
  if (temp_scaled > 850) temp_scaled = 850;     // 85.0°C
  if (hum_scaled > 1000) hum_scaled = 1000;     // 100.0%

  // Send 5-byte packet
  sendRawByte(code);
  sendRawByte((temp_scaled >> 8) & 0xFF);  // temp high byte
  sendRawByte(temp_scaled & 0xFF);          // temp low byte
  sendRawByte((hum_scaled >> 8) & 0xFF);   // humidity high byte
  sendRawByte(hum_scaled & 0xFF);          // humidity low byte

  Serial.flush();
}

void sendSyncResponseWithDuration(float temp, float hum, uint16_t duration_ms) {
  // ========================================================================
  // Send 15-byte response matching Python expectations (esp32_commands.py)
  // ========================================================================
  // Byte 0:      0x1B (RESPONSE_SYNC_COMPLETE)
  // Bytes 1-2:   timing_ms (uint16 big-endian) - total LED-on duration
  // Bytes 3-6:   temperature (float, little-endian IEEE 754)
  // Bytes 7-10:  humidity (float, little-endian IEEE 754)
  // Byte 11:     led_type_used (0=IR, 1=White)
  // Bytes 12-13: led_duration_ms (uint16 big-endian) - same as timing_ms
  // Byte 14:     led_power_actual (0-100%)
  // ========================================================================

  // Byte 0: Response header
  sendRawByte(RESPONSE_SYNC_COMPLETE);

  // Bytes 1-2: timing_ms (big-endian uint16)
  sendRawByte((duration_ms >> 8) & 0xFF);
  sendRawByte(duration_ms & 0xFF);

  // Bytes 3-6: temperature as float (little-endian IEEE 754)
  union {
    float f;
    uint8_t bytes[4];
  } temp_union;
  temp_union.f = temp;
  for (int i = 0; i < 4; i++) {
    sendRawByte(temp_union.bytes[i]);
  }

  // Bytes 7-10: humidity as float (little-endian IEEE 754)
  union {
    float f;
    uint8_t bytes[4];
  } hum_union;
  hum_union.f = hum;
  for (int i = 0; i < 4; i++) {
    sendRawByte(hum_union.bytes[i]);
  }

  // Byte 11: led_type_used (0=IR, 1=White)
  sendRawByte(currentLedType);

  // Bytes 12-13: led_duration_ms (big-endian uint16)
  sendRawByte((duration_ms >> 8) & 0xFF);
  sendRawByte(duration_ms & 0xFF);

  // Byte 14: led_power_actual (0-100%)
  uint8_t current_power = (currentLedType == LED_TYPE_IR) ? LED_POWER_PERCENT_IR : LED_POWER_PERCENT_WHITE;
  sendRawByte(current_power);

  Serial.flush();

  debugPrint("Sent 15-byte sync response: temp=");
  debugPrint((int)temp);
  debugPrint(", hum=");
  debugPrint((int)hum);
  debugPrint(", duration=");
  debugPrint(duration_ms);
  debugPrint("ms, LED=");
  debugPrint(currentLedType == LED_TYPE_IR ? "IR" : "White");
  debugPrint(", power=");
  debugPrint(current_power);
  debugPrintln("%");
}

void setLedState(bool state, uint8_t ledType) {
  if (ledType == LED_TYPE_IR) {
    ledIrState = state;
    updateLedOutput(LED_TYPE_IR);
  } else if (ledType == LED_TYPE_WHITE) {
    ledWhiteState = state;
    updateLedOutput(LED_TYPE_WHITE);
  }
}

void setCurrentLedState(bool state) {
  setLedState(state, currentLedType);
}

void updateLedOutput(uint8_t ledType) {
  uint16_t maxValue = (1 << PWM_RESOLUTION) - 1;

  if (ledType == LED_TYPE_IR) {
    if (ledIrState) {
      uint16_t pwmValue = map(LED_POWER_PERCENT_IR, 0, 100, 0, maxValue);
      ledcWrite(PWM_CHANNEL_IR, pwmValue);
    } else {
      ledcWrite(PWM_CHANNEL_IR, 0);
    }
  } else if (ledType == LED_TYPE_WHITE) {
    if (ledWhiteState) {
      uint16_t pwmValue = map(LED_POWER_PERCENT_WHITE, 0, 100, 0, maxValue);
      ledcWrite(PWM_CHANNEL_WHITE, pwmValue);
    } else {
      ledcWrite(PWM_CHANNEL_WHITE, 0);
    }
  }
}

void updateCurrentLedOutput() {
  updateLedOutput(currentLedType);
}

void setLedPowerCurrent(uint8_t power) {
  if (power > 100) power = 100;

  if (currentLedType == LED_TYPE_IR) {
    LED_POWER_PERCENT_IR = power;
  } else {
    LED_POWER_PERCENT_WHITE = power;
  }

  LED_POWER_PERCENT = power;

  if ((currentLedType == LED_TYPE_IR && ledIrState) ||
      (currentLedType == LED_TYPE_WHITE && ledWhiteState)) {
    updateCurrentLedOutput();
  }
}

void setIrPower(uint8_t power) {
  if (power > 100) power = 100;
  LED_POWER_PERCENT_IR = power;
  if (ledIrState) {
    updateLedOutput(LED_TYPE_IR);
  }
}

void setWhitePower(uint8_t power) {
  if (power > 100) power = 100;
  LED_POWER_PERCENT_WHITE = power;
  if (ledWhiteState) {
    updateLedOutput(LED_TYPE_WHITE);
  }
}

void selectLed(uint8_t ledType) {
  // Change LED selection without affecting LED states
  // This allows switching between IR and White without turning LEDs off
  currentLedType = ledType;

  debugPrint("LED selected: ");
  debugPrintln(ledType == LED_TYPE_IR ? "IR (Night)" : "White (Day)");
}

void turnOffAllLeds() {
  ledIrState = false;
  ledWhiteState = false;
  updateLedOutput(LED_TYPE_IR);
  updateLedOutput(LED_TYPE_WHITE);
}

void sendLedStatus() {
  sendRawByte(RESPONSE_LED_STATUS);
  sendRawByte(currentLedType);
  sendRawByte(ledIrState ? 1 : 0);
  sendRawByte(ledWhiteState ? 1 : 0);
  sendRawByte(LED_POWER_PERCENT_IR);
  sendRawByte(LED_POWER_PERCENT_WHITE);
  Serial.flush();
}

void setTiming(uint16_t stabilization_ms, uint16_t exposure_ms) {
  LED_STABILIZATION_MS = stabilization_ms;
  EXPOSURE_MS = exposure_ms;
}

// ========================================================================
// SYNC CAPTURE FUNCTIONS
// ========================================================================

void performSyncCapture() {
  debugPrintln("=== SYNC_CAPTURE START ===");
  debugPrint("LED type: ");
  debugPrintln(currentLedType == LED_TYPE_IR ? "IR" : "White");

  unsigned long startTime = millis();

  // Turn on current LED
  setCurrentLedState(true);

  // Send ACK immediately so Python knows LED is on
  sendRawByte(RESPONSE_LED_ON_ACK);
  Serial.flush();

  // Wait for LED stabilization + camera exposure
  // Total LED-on time = LED_STABILIZATION_MS + EXPOSURE_MS
  unsigned long totalDuration = LED_STABILIZATION_MS + EXPOSURE_MS;
  delay(totalDuration);

  // Turn off LED
  setCurrentLedState(false);

  unsigned long actualDuration = millis() - startTime;

  // Read sensors after LED is off
  float temp, hum;
  readSensorsWithValidation(temp, hum);

  // Send 15-byte sync complete response
  sendSyncResponseWithDuration(temp, hum, (uint16_t)actualDuration);

  debugPrint("=== SYNC_CAPTURE COMPLETE: ");
  debugPrint(actualDuration);
  debugPrintln("ms ===");
}

void performSyncCaptureDual() {
  debugPrintln("=== SYNC_CAPTURE_DUAL START ===");
  debugPrintln("Both LEDs: IR + White");

  unsigned long startTime = millis();

  // Turn on BOTH LEDs simultaneously
  ledIrState = true;
  ledWhiteState = true;
  updateLedOutput(LED_TYPE_IR);
  updateLedOutput(LED_TYPE_WHITE);

  // Send ACK immediately so Python knows LEDs are on
  sendRawByte(RESPONSE_LED_ON_ACK);
  Serial.flush();

  // Wait for LED stabilization + camera exposure
  // Total LED-on time = LED_STABILIZATION_MS + EXPOSURE_MS
  unsigned long totalDuration = LED_STABILIZATION_MS + EXPOSURE_MS;
  delay(totalDuration);

  // Turn off both LEDs
  ledIrState = false;
  ledWhiteState = false;
  updateLedOutput(LED_TYPE_IR);
  updateLedOutput(LED_TYPE_WHITE);

  unsigned long actualDuration = millis() - startTime;

  // Read sensors after LEDs are off
  float temp, hum;
  readSensorsWithValidation(temp, hum);

  // Send 15-byte sync complete response
  sendSyncResponseWithDuration(temp, hum, (uint16_t)actualDuration);

  debugPrint("=== SYNC_CAPTURE_DUAL COMPLETE: ");
  debugPrint(actualDuration);
  debugPrintln("ms ===");
}

// ========================================================================
// SENSOR FUNCTIONS
// ========================================================================

bool readSensorsWithValidation(float &temperature, float &humidity) {
  // Save LED states
  bool irWasOn = ledIrState;
  bool whiteWasOn = ledWhiteState;
  uint16_t maxValue = (1 << PWM_RESOLUTION) - 1;
  uint16_t savedIrPwm = 0;
  uint16_t savedWhitePwm = 0;

  // Turn off LEDs for sensor reading
  if (irWasOn || whiteWasOn) {
    savedIrPwm = map(LED_POWER_PERCENT_IR, 0, 100, 0, maxValue);
    savedWhitePwm = map(LED_POWER_PERCENT_WHITE, 0, 100, 0, maxValue);
    ledcWrite(PWM_CHANNEL_IR, 0);
    ledcWrite(PWM_CHANNEL_WHITE, 0);
    delay(50);
  }

  // Read sensor (retry up to 3 times)
  float h = NAN, t = NAN;
  for (int attempt = 0; attempt < 3; attempt++) {
    h = dht.readHumidity();
    t = dht.readTemperature();

    if (!isnan(h) && !isnan(t) &&
        h >= 0.0 && h <= 100.0 &&
        t >= -40.0 && t <= 85.0) {
      break;
    }

    if (attempt < 2) {
      delay(100);
    }
  }

  // Restore LED states
  if (irWasOn) ledcWrite(PWM_CHANNEL_IR, savedIrPwm);
  if (whiteWasOn) ledcWrite(PWM_CHANNEL_WHITE, savedWhitePwm);

  // Check if valid
  bool valid = (!isnan(h) && !isnan(t) &&
                h >= 0.0 && h <= 100.0 &&
                t >= -40.0 && t <= 85.0);

  if (valid) {
    addToSensorHistory(t, h);
    temperature = getFilteredTemperature();
    humidity = getFilteredHumidity();
    return true;
  } else {
    temperature = getFilteredTemperature();
    humidity = getFilteredHumidity();
    return false;
  }
}

void addToSensorHistory(float temp, float hum) {
  if (!sensor_history.initialized) {
    for (int i = 0; i < 5; i++) {
      sensor_history.temp_values[i] = temp;
      sensor_history.hum_values[i] = hum;
    }
    sensor_history.count = 5;
    sensor_history.initialized = true;
  } else {
    sensor_history.temp_values[sensor_history.index] = temp;
    sensor_history.hum_values[sensor_history.index] = hum;
    sensor_history.index = (sensor_history.index + 1) % 5;
    if (sensor_history.count < 5) sensor_history.count++;
  }
}

float getFilteredTemperature() {
  if (!sensor_history.initialized) return 25.0;
  float sum = 0;
  for (int i = 0; i < sensor_history.count; i++) {
    sum += sensor_history.temp_values[i];
  }
  return sum / sensor_history.count;
}

float getFilteredHumidity() {
  if (!sensor_history.initialized) return 50.0;
  float sum = 0;
  for (int i = 0; i < sensor_history.count; i++) {
    sum += sensor_history.hum_values[i];
  }
  return sum / sensor_history.count;
}

// Zum Testen der Hardware ohne Plugin

// Test Tempsensor
// #include <DHT.h>
// DHT dht(14, DHT22);

// void setup() {
//     Serial.begin(115200);
//     dht.begin();
// }

// void loop() {
//     float h = dht.readHumidity();
//     float t = dht.readTemperature();

//     Serial.print("Raw: T=");
//     Serial.print(t);
//     Serial.print("°C H=");
//     Serial.print(h);
//     Serial.println("%");

//     delay(2000);
// }

// Lampen Test
// #include <Arduino.h>

// // -------- PIN DEFINITIONS --------
// const int ledIrPin    = 4;     // GPIO4, IR LED MOSFET gate
// const int ledWhitePin = 15;    // GPIO15, White LED MOSFET gate

// // PWM Configuration
// const int PWM_CHANNEL_IR     = 0;            // IR LED LEDC channel
// const int PWM_CHANNEL_WHITE  = 1;            // White LED LEDC channel
// const int PWM_FREQUENCY      = 15000;         // 5 kHz frequency
// const int PWM_RESOLUTION     = 10;           // 10-bit resolution (0–1023 steps)

// // Test phases
// enum TestPhase {
//     DIGITAL_TEST,
//     PWM_RAMP_TEST,
//     PWM_LEVELS_TEST,
//     ALTERNATING_TEST,
//     DAY_NIGHT_CYCLE,
//     MANUAL_TEST
// };

// TestPhase currentPhase = DIGITAL_TEST;
// unsigned long phaseStartTime = 0;
// unsigned long lastActionTime = 0;
// int testStep = 0;

// // Function declarations
// void runDigitalTest(unsigned long currentTime);
// void runPWMRampTest(unsigned long currentTime);
// void runPWMLevelsTest(unsigned long currentTime);
// void runAlternatingTest(unsigned long currentTime);
// void runDayNightCycle(unsigned long currentTime);
// void runManualTest(unsigned long currentTime);
// void setupPWM();
// void startNextPhase();
// void handleManualCommand(char cmd);

// void setup() {
//     Serial.begin(115200);
//     delay(1000);
//     Serial.println("=== COMPLETE DUAL LED PWM TEST ===");
//     Serial.println("IR LED: GPIO4, White LED: GPIO15");
//     Serial.println("Full functionality test with PWM control");
//     Serial.println();

//     // Start with digital pins
//     pinMode(ledIrPin, OUTPUT);
//     pinMode(ledWhitePin, OUTPUT);
//     digitalWrite(ledIrPin, LOW);
//     digitalWrite(ledWhitePin, LOW);

//     Serial.println("Starting comprehensive test sequence...\n");
//     lastActionTime = millis();
// }

// void loop() {
//     unsigned long currentTime = millis();

//     switch (currentPhase) {
//         case DIGITAL_TEST:
//             runDigitalTest(currentTime);
//             break;
//         case PWM_RAMP_TEST:
//             runPWMRampTest(currentTime);
//             break;
//         case PWM_LEVELS_TEST:
//             runPWMLevelsTest(currentTime);
//             break;
//         case ALTERNATING_TEST:
//             runAlternatingTest(currentTime);
//             break;
//         case DAY_NIGHT_CYCLE:
//             runDayNightCycle(currentTime);
//             break;
//         case MANUAL_TEST:
//             runManualTest(currentTime);
//             break;
//     }

//     delay(50);
// }

// void runDigitalTest(unsigned long currentTime) {
//     if (currentTime - lastActionTime < 2000) return;

//     switch (testStep) {
//         case 0:
//             Serial.println("=== PHASE 1: DIGITAL ON/OFF TEST ===");
//             testStep++;
//             break;
//         case 1:
//             Serial.println("Both LEDs OFF");
//             digitalWrite(ledIrPin, LOW);
//             digitalWrite(ledWhitePin, LOW);
//             testStep++;
//             break;
//         case 2:
//             Serial.println("White LED ON - Should see bright white light");
//             digitalWrite(ledWhitePin, HIGH);
//             testStep++;
//             break;
//         case 3:
//             Serial.println("IR LED ON, White OFF - Should see IR with phone camera");
//             digitalWrite(ledIrPin, HIGH);
//             digitalWrite(ledWhitePin, LOW);
//             testStep++;
//             break;
//         case 4:
//             Serial.println("Both LEDs ON - Should see both white and IR");
//             digitalWrite(ledIrPin, HIGH);
//             digitalWrite(ledWhitePin, HIGH);
//             testStep++;
//             break;
//         case 5:
//             Serial.println("Both LEDs OFF");
//             digitalWrite(ledIrPin, LOW);
//             digitalWrite(ledWhitePin, LOW);
//             Serial.println("Digital test complete!\n");
//             startNextPhase();
//             break;
//     }
//     lastActionTime = currentTime;
// }

// void runPWMRampTest(unsigned long currentTime) {
//     if (testStep == 0) {
//         Serial.println("=== PHASE 2: PWM SETUP AND RAMP TEST ===");
//         setupPWM();
//         testStep = 1;
//         lastActionTime = currentTime;
//         return;
//     }

//     if (currentTime - lastActionTime < 300) return;

//     static int pwmValue = 0;
//     static bool testingWhite = true;

//     if (testStep == 1) {
//         Serial.println("WHITE LED PWM Ramp 0->100%:");
//         testStep = 2;
//     }

//     if (testStep == 2 && testingWhite) {
//         ledcWrite(PWM_CHANNEL_WHITE, pwmValue);
//         ledcWrite(PWM_CHANNEL_IR, 0);
//         Serial.print("White: ");
//         Serial.print((pwmValue * 100) / 1023);
//         Serial.println("%");

//         pwmValue += 85;
//         if (pwmValue > 1023) {
//             pwmValue = 0;
//             testingWhite = false;
//             testStep = 3;
//             Serial.println("IR LED PWM Ramp 0->100%:");
//         }
//     } else if (testStep >= 3 && !testingWhite) {
//         ledcWrite(PWM_CHANNEL_IR, pwmValue);
//         ledcWrite(PWM_CHANNEL_WHITE, 0);
//         Serial.print("IR: ");
//         Serial.print((pwmValue * 100) / 1023);
//         Serial.println("%");

//         pwmValue += 85;
//         if (pwmValue > 1023) {
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             Serial.println("PWM ramp test complete!\n");
//             startNextPhase();
//         }
//     }

//     lastActionTime = currentTime;
// }

// void runPWMLevelsTest(unsigned long currentTime) {
//     if (testStep == 0) {
//         Serial.println("=== PHASE 3: PWM LEVELS TEST ===");
//         Serial.println("Testing different brightness levels");
//         testStep = 1;
//     }

//     if (currentTime - lastActionTime < 1500) return;

//     static int levelIndex = 0;
//     int pwmLevels[] = {10, 25, 50, 75, 100}; // Percentages
//     static bool testingWhite = true;

//     if (testingWhite) {
//         int pwmValue = map(pwmLevels[levelIndex], 0, 100, 0, 1023);
//         ledcWrite(PWM_CHANNEL_WHITE, pwmValue);
//         ledcWrite(PWM_CHANNEL_IR, 0);
//         Serial.print("White LED at ");
//         Serial.print(pwmLevels[levelIndex]);
//         Serial.println("%");

//         levelIndex++;
//         if (levelIndex >= 5) {
//             levelIndex = 0;
//             testingWhite = false;
//             Serial.println("Now testing IR LED levels:");
//         }
//     } else {
//         int pwmValue = map(pwmLevels[levelIndex], 0, 100, 0, 1023);
//         ledcWrite(PWM_CHANNEL_IR, pwmValue);
//         ledcWrite(PWM_CHANNEL_WHITE, 0);
//         Serial.print("IR LED at ");
//         Serial.print(pwmLevels[levelIndex]);
//         Serial.println("%");

//         levelIndex++;
//         if (levelIndex >= 5) {
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             Serial.println("PWM levels test complete!\n");
//             startNextPhase();
//         }
//     }

//     lastActionTime = currentTime;
// }

// void runAlternatingTest(unsigned long currentTime) {
//     if (testStep == 0) {
//         Serial.println("=== PHASE 4: ALTERNATING LED TEST ===");
//         Serial.println("2-second cycles between White and IR at full power");
//         testStep = 1;
//     }

//     if (currentTime - lastActionTime < 2000) return;

//     static bool whiteActive = true;
//     static int cycleCount = 0;

//     whiteActive = !whiteActive;

//     if (whiteActive) {
//         ledcWrite(PWM_CHANNEL_WHITE, 1023);
//         ledcWrite(PWM_CHANNEL_IR, 0);
//         Serial.println(">>> WHITE LED ON (Day lighting)");
//     } else {
//         ledcWrite(PWM_CHANNEL_IR, 1023);
//         ledcWrite(PWM_CHANNEL_WHITE, 0);
//         Serial.println(">>> IR LED ON (Night lighting)");
//     }

//     cycleCount++;
//     if (cycleCount >= 8) {
//         Serial.println("Alternating test complete!\n");
//         startNextPhase();
//     }

//     lastActionTime = currentTime;
// }

// void runDayNightCycle(unsigned long currentTime) {
//     if (testStep == 0) {
//         Serial.println("=== PHASE 5: DAY/NIGHT SIMULATION ===");
//         Serial.println("Simulating realistic day/night photography cycle");
//         testStep = 1;
//         lastActionTime = currentTime;
//     }

//     if (currentTime - lastActionTime < 1000) return;

//     static int cycleStep = 0;
//     static int cycleCount = 0;

//     switch (cycleStep) {
//         case 0:
//             Serial.println("DAY PHASE - White LED stabilization");
//             ledcWrite(PWM_CHANNEL_WHITE, 1023);
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             break;
//         case 1:
//             Serial.println("DAY PHASE - LED stable (camera trigger time)");
//             break;
//         case 2:
//             Serial.println("TRANSITION - LEDs off");
//             ledcWrite(PWM_CHANNEL_WHITE, 0);
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             break;
//         case 3:
//             Serial.println("NIGHT PHASE - IR LED stabilization");
//             ledcWrite(PWM_CHANNEL_IR, 1023);
//             ledcWrite(PWM_CHANNEL_WHITE, 0);
//             break;
//         case 4:
//             Serial.println("NIGHT PHASE - LED stable (camera trigger time)");
//             break;
//         case 5:
//             Serial.println("CYCLE COMPLETE - LEDs off\n");
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             ledcWrite(PWM_CHANNEL_WHITE, 0);
//             cycleStep = -1; // Will become 0 after increment
//             cycleCount++;
//             break;
//     }

//     cycleStep++;
//     if (cycleCount >= 3) {
//         Serial.println("Day/Night simulation complete!\n");
//         startNextPhase();
//     }

//     lastActionTime = currentTime;
// }

// void runManualTest(unsigned long currentTime) {
//     if (testStep == 0) {
//         Serial.println("=== PHASE 6: MANUAL CONTROL MODE ===");
//         Serial.println("Commands:");
//         Serial.println("'w' - White LED ON (full power)");
//         Serial.println("'i' - IR LED ON (full power)");
//         Serial.println("'b' - Both LEDs ON");
//         Serial.println("'0' - All LEDs OFF");
//         Serial.println("'1'-'9' - Set PWM level (1=10%, 9=90%)");
//         Serial.println("'W' - White LED at current PWM level");
//         Serial.println("'I' - IR LED at current PWM level");
//         Serial.println("'r' - Restart all tests");
//         Serial.println("Send commands now...\n");
//         testStep = 1;
//     }

//     if (Serial.available()) {
//         char cmd = Serial.read();
//         handleManualCommand(cmd);
//     }
// }

// void handleManualCommand(char cmd) {
//     static int pwmLevel = 1023; // Default full power

//     switch (cmd) {
//         case 'w':
//             ledcWrite(PWM_CHANNEL_WHITE, 1023);
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             Serial.println("White LED ON (full power)");
//             break;
//         case 'i':
//             ledcWrite(PWM_CHANNEL_IR, 1023);
//             ledcWrite(PWM_CHANNEL_WHITE, 0);
//             Serial.println("IR LED ON (full power)");
//             break;
//         case 'W':
//             ledcWrite(PWM_CHANNEL_WHITE, pwmLevel);
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             Serial.print("White LED ON at ");
//             Serial.print((pwmLevel * 100) / 1023);
//             Serial.println("%");
//             break;
//         case 'I':
//             ledcWrite(PWM_CHANNEL_IR, pwmLevel);
//             ledcWrite(PWM_CHANNEL_WHITE, 0);
//             Serial.print("IR LED ON at ");
//             Serial.print((pwmLevel * 100) / 1023);
//             Serial.println("%");
//             break;
//         case 'b':
//             ledcWrite(PWM_CHANNEL_WHITE, pwmLevel);
//             ledcWrite(PWM_CHANNEL_IR, pwmLevel);
//             Serial.print("Both LEDs ON at ");
//             Serial.print((pwmLevel * 100) / 1023);
//             Serial.println("%");
//             break;
//         case '0':
//             ledcWrite(PWM_CHANNEL_WHITE, 0);
//             ledcWrite(PWM_CHANNEL_IR, 0);
//             Serial.println("All LEDs OFF");
//             break;
//         case '1':
//         case '2':
//         case '3':
//         case '4':
//         case '5':
//         case '6':
//         case '7':
//         case '8':
//         case '9':
//             pwmLevel = map(cmd - '0', 1, 9, 100, 920); // 10% to 90%
//             Serial.print("PWM level set to ");
//             Serial.print((pwmLevel * 100) / 1023);
//             Serial.println("%");
//             break;
//         case 'r':
//             Serial.println("Restarting all tests...\n");
//             ESP.restart();
//             break;
//         default:
//             Serial.println("Unknown command. Use w/i/W/I/b/0/1-9/r");
//             break;
//     }
// }

// void setupPWM() {
//     ledcSetup(PWM_CHANNEL_IR, PWM_FREQUENCY, PWM_RESOLUTION);
//     ledcAttachPin(ledIrPin, PWM_CHANNEL_IR);
//     ledcSetup(PWM_CHANNEL_WHITE, PWM_FREQUENCY, PWM_RESOLUTION);
//     ledcAttachPin(ledWhitePin, PWM_CHANNEL_WHITE);

//     ledcWrite(PWM_CHANNEL_IR, 0);
//     ledcWrite(PWM_CHANNEL_WHITE, 0);

//     Serial.println("PWM channels configured:");
//     Serial.print("Frequency: ");
//     Serial.print(PWM_FREQUENCY);
//     Serial.println(" Hz");
//     Serial.print("Resolution: ");
//     Serial.print(PWM_RESOLUTION);
//     Serial.println(" bits (0-1023)");
// }

// void startNextPhase() {
//     currentPhase = (TestPhase)((int)currentPhase + 1);
//     if (currentPhase > MANUAL_TEST) currentPhase = DIGITAL_TEST;

//     testStep = 0;
//     phaseStartTime = millis();
//     lastActionTime = millis();

//     // Turn off all LEDs between phases
//     if (currentPhase == DIGITAL_TEST) {
//         digitalWrite(ledIrPin, LOW);
//         digitalWrite(ledWhitePin, LOW);
//     } else {
//         ledcWrite(PWM_CHANNEL_IR, 0);
//         ledcWrite(PWM_CHANNEL_WHITE, 0);
//     }
// }
// #include <Arduino.h>
// #include "esp_task_wdt.h"  // ESP32 Watchdog
// #include <DHT.h>           // DHT22-Library

// // -------- PIN AND COMMAND DEFINITIONS --------
// const int   ledIrPin     = 4;    // GPIO4, IR LED output (night/existing)
// const int   ledWhitePin  = 15;    // GPIO5, White COB LED output (day/new)
// const int   dhtPin       = 14;   // GPIO14, DHT22 data pin
// #define DHTTYPE   DHT22

// // PWM Configuration - IMPROVED: Higher frequency to reduce interference
// const int PWM_CHANNEL_IR     = 0;            // IR LED LEDC channel
// const int PWM_CHANNEL_WHITE  = 1;            // White LED LEDC channel
// const int PWM_FREQUENCY      = 15000;         // 15 kHz frequency
// const int PWM_RESOLUTION     = 10;           // 10-bit resolution (0–1023 steps)

// // Command bytes (matching Python widget)
// const byte CMD_LED_ON         = 0x01;
// const byte CMD_LED_OFF        = 0x00;
// const byte CMD_STATUS         = 0x02;
// const byte CMD_SYNC_CAPTURE   = 0x0C;
// const byte CMD_SET_LED_POWER  = 0x10;
// const byte CMD_SET_TIMING     = 0x11;
// const byte CMD_SET_CAMERA_TYPE= 0x13;

// // ✅ NEW: Dual LED Commands
// const byte CMD_SELECT_LED_IR    = 0x20;
// const byte CMD_SELECT_LED_WHITE = 0x21;
// const byte CMD_LED_DUAL_OFF     = 0x22;
// const byte CMD_GET_LED_STATUS   = 0x23;

// // Response bytes (matching Python widget)
// const byte RESPONSE_SYNC_COMPLETE = 0x1B;
// const byte RESPONSE_TIMING_SET    = 0x21;
// const byte RESPONSE_ACK_ON        = 0x01;
// const byte RESPONSE_ACK_OFF       = 0x02;
// const byte RESPONSE_STATUS_ON     = 0x11;
// const byte RESPONSE_STATUS_OFF    = 0x10;
// const byte RESPONSE_ERROR         = 0xFF;

// // ✅ NEW: LED Selection Response
// const byte RESPONSE_LED_IR_SELECTED    = 0x30;
// const byte RESPONSE_LED_WHITE_SELECTED = 0x31;
// const byte RESPONSE_LED_STATUS         = 0x32;

// // Camera types (matching Python widget)
// const byte CAMERA_TYPE_HIK_GIGE   = 1;
// const byte CAMERA_TYPE_USB_GENERIC= 2;

// // LED Types
// const byte LED_TYPE_IR    = 0;
// const byte LED_TYPE_WHITE = 1;

// // Timing parameters
// static uint16_t LED_STABILIZATION_MS = 300;  // LED stabilization time
// static uint16_t TRIGGER_DELAY_MS      = 10;  // Default trigger delay
// static uint8_t LED_POWER_PERCENT      = 100; // LED power (0-100%)
// static uint8_t CAMERA_TYPE            = CAMERA_TYPE_HIK_GIGE;

// // ✅ NEW: Dual LED state tracking
// static bool ledIrState = false;
// static bool ledWhiteState = false;
// static uint8_t currentLedType = LED_TYPE_IR;  // Default to IR LED (backward compatibility)

// // Communication timeout values
// const unsigned long SERIAL_TIMEOUT     = 2000;  // 2s wait for new command
// const unsigned long WRITE_WAIT_TIMEOUT = 500;   // 500ms TX buffer wait

// // DHT sensor instance
// DHT dht(dhtPin, DHTTYPE);

// // Timing variables
// unsigned long lastSyncTime = 0;
// unsigned long bootTime = 0;  // Track boot time for timestamps

// // ✅ Sensor history for filtering interference
// struct SensorHistory {
//     float temp_values[5];
//     float hum_values[5];
//     int index;
//     int count;
//     bool initialized;
// };

// static SensorHistory sensor_history = {0};

// // Function prototypes
// void sendStatus(byte code);
// void sendRawByte(byte b);
// void sendSyncResponse();
// void sendSyncResponseWithValues(float temperature, float humidity);
// void setLedPower(uint8_t power);
// void setLedState(bool state, uint8_t ledType);
// void setCurrentLedState(bool state);
// void updateLedOutput(uint8_t ledType);
// void updateCurrentLedOutput();
// void performSyncCapture();
// void setTiming(uint16_t stabilization_ms, uint16_t delay_ms);
// void selectLed(uint8_t ledType);
// void turnOffAllLeds();
// void sendLedStatus();

// // Enhanced sensor functions
// bool readSensorsWithValidation(float &temperature, float &humidity);
// void addToSensorHistory(float temp, float hum);
// float getFilteredTemperature();
// float getFilteredHumidity();

// // ✅ NEW: Enhanced sensor reading with dual PWM interference prevention
// bool readSensorsWithValidation(float &temperature, float &humidity) {
//     // Temporarily disable ALL PWM during sensor reading
//     bool irWasOn = ledIrState;
//     bool whiteWasOn = ledWhiteState;
//     uint16_t savedIrPwmValue = 0;
//     uint16_t savedWhitePwmValue = 0;

//     if (irWasOn || whiteWasOn) {
//         // Save current PWM values
//         savedIrPwmValue = map(LED_POWER_PERCENT, 0, 100, 0, (1 << PWM_RESOLUTION) - 1);
//         savedWhitePwmValue = savedIrPwmValue;  // Same power for both LEDs

//         // Turn off ALL PWM completely
//         ledcWrite(PWM_CHANNEL_IR, 0);
//         ledcWrite(PWM_CHANNEL_WHITE, 0);
//         delay(50);  // Let sensor stabilize
//         // DEBUG DISABLED: Serial.println("All PWM disabled for sensor reading");
//     }

//     // Read DHT22 with retries
//     float h = NAN, t = NAN;
//     for (int attempt = 0; attempt < 3; attempt++) {
//         h = dht.readHumidity();
//         t = dht.readTemperature();

//         // Basic validation
//         if (!isnan(h) && !isnan(t) && h >= 0.0 && h <= 100.0 && t >= -10.0 && t <= 50.0) {
//             // DEBUG DISABLED: Serial.print("Sensor read successful on attempt ");
//             // DEBUG DISABLED: Serial.println(attempt + 1);
//             break;  // Good reading
//         }

//         if (attempt < 2) {
//             // DEBUG DISABLED: Serial.print("Sensor read failed, retrying... ");
//             // DEBUG DISABLED: Serial.print("T=");
//             // DEBUG DISABLED: Serial.print(t);
//             // DEBUG DISABLED: Serial.print(" H=");
//             // DEBUG DISABLED: Serial.println(h);
//             delay(100);  // Wait before retry
//         }
//     }

//     // Restore LED states
//     if (irWasOn) {
//         ledcWrite(PWM_CHANNEL_IR, savedIrPwmValue);
//     }
//     if (whiteWasOn) {
//         ledcWrite(PWM_CHANNEL_WHITE, savedWhitePwmValue);
//     }
//     if (irWasOn || whiteWasOn) {
//         // DEBUG DISABLED: Serial.println("PWM restored");
//     }

//     // Validate readings
//     bool validReading = (!isnan(h) && !isnan(t) &&
//                         h >= 0.0 && h <= 100.0 &&
//                         t >= -10.0 && t <= 50.0);

//     if (validReading) {
//         // Add to history for filtering
//         addToSensorHistory(t, h);
//         temperature = getFilteredTemperature();
//         humidity = getFilteredHumidity();
//         // DEBUG DISABLED: Serial.print("Valid sensor reading: T=");
//         // DEBUG DISABLED: Serial.print(temperature);
//         // DEBUG DISABLED: Serial.print("°C, H=");
//         // DEBUG DISABLED: Serial.print(humidity);
//         // DEBUG DISABLED: Serial.println("%");
//         return true;
//     } else {
//         // Use last known good values
//         temperature = getFilteredTemperature();
//         humidity = getFilteredHumidity();
//         // DEBUG DISABLED: Serial.print("Invalid sensor reading, using filtered values: T=");
//         // DEBUG DISABLED: Serial.print(temperature);
//         // DEBUG DISABLED: Serial.print("°C, H=");
//         // DEBUG DISABLED: Serial.print(humidity);
//         // DEBUG DISABLED: Serial.println("%");
//         return false;
//     }
// }

// // Sensor history management (unchanged)
// void addToSensorHistory(float temp, float hum) {
//     if (!sensor_history.initialized) {
//         for (int i = 0; i < 5; i++) {
//             sensor_history.temp_values[i] = temp;
//             sensor_history.hum_values[i] = hum;
//         }
//         sensor_history.count = 5;
//         sensor_history.initialized = true;
//         // DEBUG DISABLED: Serial.println("Sensor history initialized");
//     } else {
//         sensor_history.temp_values[sensor_history.index] = temp;
//         sensor_history.hum_values[sensor_history.index] = hum;
//         sensor_history.index = (sensor_history.index + 1) % 5;
//         if (sensor_history.count < 5) sensor_history.count++;
//     }
// }

// float getFilteredTemperature() {
//     if (!sensor_history.initialized) return 25.0;
//     float sum = 0;
//     for (int i = 0; i < sensor_history.count; i++) {
//         sum += sensor_history.temp_values[i];
//     }
//     return sum / sensor_history.count;
// }

// float getFilteredHumidity() {
//     if (!sensor_history.initialized) return 50.0;
//     float sum = 0;
//     for (int i = 0; i < sensor_history.count; i++) {
//         sum += sensor_history.hum_values[i];
//     }
//     return sum / sensor_history.count;
// }

// void setup() {
//     Serial.begin(115200);
//     // DEBUG DISABLED: Serial.println("ESP32_DUAL_LED_SYNC_v4.0_DAY_NIGHT");
//     unsigned long t0 = millis();
//     while (!Serial && (millis() - t0 < 1000)) delay(10);

//     bootTime = millis();

//     // ✅ Configure PWM for BOTH LEDs
//     ledcSetup(PWM_CHANNEL_IR, PWM_FREQUENCY, PWM_RESOLUTION);
//     ledcAttachPin(ledIrPin, PWM_CHANNEL_IR);

//     ledcSetup(PWM_CHANNEL_WHITE, PWM_FREQUENCY, PWM_RESOLUTION);
//     ledcAttachPin(ledWhitePin, PWM_CHANNEL_WHITE);

//     // Initialize both LEDs off
//     setLedState(false, LED_TYPE_IR);
//     setLedState(false, LED_TYPE_WHITE);

//     // Initialize DHT
//     dht.begin();
//     // DEBUG DISABLED: Serial.println("DHT22 sensor initialized");

//     // Watchdog
//     esp_task_wdt_init(30, false);
//     esp_task_wdt_add(NULL);

//     // Initialize sensor history
//     delay(2000);
//     float temp, hum;
//     if (readSensorsWithValidation(temp, hum)) {
//         // DEBUG DISABLED: Serial.println("Initial sensor calibration successful");
//     } else {
//         // DEBUG DISABLED: Serial.println("Initial sensor calibration failed, using defaults");
//     }

//     // DEBUG DISABLED: Serial.println("ESP32_DUAL_LED_DAY_NIGHT_READY");
//     // DEBUG DISABLED: Serial.print("IR LED: GPIO");
//     // DEBUG DISABLED: Serial.print(ledIrPin);
//     // DEBUG DISABLED: Serial.print(", White LED: GPIO");
//     // DEBUG DISABLED: Serial.println(ledWhitePin);
//     // DEBUG DISABLED: Serial.print("Current LED: ");
//     // DEBUG DISABLED: Serial.println(currentLedType == LED_TYPE_IR ? "IR (Night)" : "White (Day)");

//     // KEEP THIS: Required for firmware detection
//     Serial.println("READY");
//     Serial.flush();
// }

// void loop() {
//     esp_task_wdt_reset();
//     if (!Serial.available()) {
//         delay(5);
//         return;
//     }

//     byte cmd = Serial.read();

//     switch (cmd) {
//         case CMD_LED_ON:
//             setCurrentLedState(true);
//             sendStatus(RESPONSE_ACK_ON);
//             delay(LED_STABILIZATION_MS);
//             break;

//         case CMD_LED_OFF:
//             setCurrentLedState(false);
//             sendStatus(RESPONSE_ACK_OFF);
//             break;

//         case CMD_STATUS:
//             sendStatus((ledIrState || ledWhiteState) ? RESPONSE_STATUS_ON : RESPONSE_STATUS_OFF);
//             break;

//         case CMD_SYNC_CAPTURE:
//             performSyncCapture();
//             break;

//         case CMD_SET_LED_POWER:
//             if (Serial.available()) {
//                 setLedPower(Serial.read());
//                 sendRawByte(RESPONSE_ACK_ON);
//             }
//             else sendRawByte(RESPONSE_ERROR);
//             break;

//         case CMD_SET_TIMING:
//             if (Serial.available() >= 4) {
//                 uint16_t stab = (Serial.read() << 8) | Serial.read();
//                 uint16_t del  = (Serial.read() << 8) | Serial.read();
//                 setTiming(stab, del);
//                 sendRawByte(RESPONSE_TIMING_SET);
//             } else sendRawByte(RESPONSE_ERROR);
//             break;

//         case CMD_SET_CAMERA_TYPE:
//             if (Serial.available()) {
//                 CAMERA_TYPE = Serial.read();
//                 sendRawByte(RESPONSE_ACK_ON);
//             }
//             else sendRawByte(RESPONSE_ERROR);
//             break;

//         // ✅ NEW: Dual LED Commands
//         case CMD_SELECT_LED_IR:
//             selectLed(LED_TYPE_IR);
//             sendRawByte(RESPONSE_LED_IR_SELECTED);
//             break;

//         case CMD_SELECT_LED_WHITE:
//             selectLed(LED_TYPE_WHITE);
//             sendRawByte(RESPONSE_LED_WHITE_SELECTED);
//             break;

//         case CMD_LED_DUAL_OFF:
//             turnOffAllLeds();
//             sendRawByte(RESPONSE_ACK_OFF);
//             break;

//         case CMD_GET_LED_STATUS:
//             sendLedStatus();
//             break;

//         default:
//             sendRawByte(RESPONSE_ERROR);
//             break;
//     }
// }

// // ✅ NEW: LED Selection and Control Functions
// void selectLed(uint8_t ledType) {
//     currentLedType = ledType;
//     // DEBUG DISABLED: Serial.print("LED selected: ");
//     // DEBUG DISABLED: Serial.println(ledType == LED_TYPE_IR ? "IR (Night phase)" : "White (Day phase)");
// }

// void setCurrentLedState(bool state) {
//     setLedState(state, currentLedType);
// }

// void setLedState(bool state, uint8_t ledType) {
//     if (ledType == LED_TYPE_IR) {
//         ledIrState = state;
//         updateLedOutput(LED_TYPE_IR);
//         // DEBUG DISABLED: Serial.print("IR LED ");
//         // DEBUG DISABLED: Serial.println(state ? "ON" : "OFF");
//     } else {
//         ledWhiteState = state;
//         updateLedOutput(LED_TYPE_WHITE);
//         // DEBUG DISABLED: Serial.print("White LED ");
//         // DEBUG DISABLED: Serial.println(state ? "ON" : "OFF");
//     }
// }

// void updateCurrentLedOutput() {
//     updateLedOutput(currentLedType);
// }

// void setLedPower(uint8_t power) {
//     LED_POWER_PERCENT = (power > 100 ? 100 : power);
//     // Update current LED output if it's on
//     if ((currentLedType == LED_TYPE_IR && ledIrState) ||
//         (currentLedType == LED_TYPE_WHITE && ledWhiteState)) {
//         updateCurrentLedOutput();
//     }
// }

// void updateLedOutput(uint8_t ledType) {
//     uint16_t maxValue = (1 << PWM_RESOLUTION) - 1;  // 1023 for 10-bit
//     uint16_t pwmValue = map(LED_POWER_PERCENT, 0, 100, 0, maxValue);

//     if (ledType == LED_TYPE_IR) {
//         ledcWrite(PWM_CHANNEL_IR, ledIrState ? pwmValue : 0);
//     } else {
//         ledcWrite(PWM_CHANNEL_WHITE, ledWhiteState ? pwmValue : 0);
//     }
// }

// void turnOffAllLeds() {
//     setLedState(false, LED_TYPE_IR);
//     setLedState(false, LED_TYPE_WHITE);
//     // DEBUG DISABLED: Serial.println("All LEDs turned OFF");
// }

// void sendLedStatus() {
//     // Send LED status: [RESPONSE_LED_STATUS][current_type][ir_state][white_state][power]
//     uint8_t packet[5] = {
//         RESPONSE_LED_STATUS,
//         currentLedType,
//         ledIrState ? 1 : 0,
//         ledWhiteState ? 1 : 0,
//         LED_POWER_PERCENT
//     };

//     Serial.write(packet, 5);
//     Serial.flush();

//     // DEBUG DISABLED: Serial.print("LED Status - Current: ");
//     // DEBUG DISABLED: Serial.print(currentLedType == LED_TYPE_IR ? "IR" : "White");
//     // DEBUG DISABLED: Serial.print(", IR: ");
//     // DEBUG DISABLED: Serial.print(ledIrState ? "ON" : "OFF");
//     // DEBUG DISABLED: Serial.print(", White: ");
//     // DEBUG DISABLED: Serial.print(ledWhiteState ? "ON" : "OFF");
//     // DEBUG DISABLED: Serial.print(", Power: ");
//     // DEBUG DISABLED: Serial.print(LED_POWER_PERCENT);
//     // DEBUG DISABLED: Serial.println("%");
// }

// // ✅ IMPROVED: Enhanced performSyncCapture with dual LED support
// void performSyncCapture() {
//     unsigned long startUs = micros();

//     // DEBUG DISABLED: Serial.println("=== DUAL LED SYNC CAPTURE START ===");
//     // DEBUG DISABLED: Serial.print("Active LED: ");
//     // DEBUG DISABLED: Serial.println(currentLedType == LED_TYPE_IR ? "IR (Night)" : "White (Day)");

//     // Read sensors BEFORE LED activity
//     float pre_temp, pre_hum;
//     bool pre_valid = readSensorsWithValidation(pre_temp, pre_hum);
//     // DEBUG DISABLED: Serial.print("Pre-LED sensor read: ");
//     // DEBUG DISABLED: Serial.println(pre_valid ? "SUCCESS" : "FAILED");

//     // LED ON (current LED only)
//     setCurrentLedState(true);
//     delay(LED_STABILIZATION_MS);

//     // Trigger delay
//     delay(TRIGGER_DELAY_MS);

//     // LED OFF
//     setCurrentLedState(false);

//     // Wait for stabilization, then read sensors again
//     delay(100);
//     float post_temp, post_hum;
//     bool post_valid = readSensorsWithValidation(post_temp, post_hum);
//     // DEBUG DISABLED: Serial.print("Post-LED sensor read: ");
//     // DEBUG DISABLED: Serial.println(post_valid ? "SUCCESS" : "FAILED");

//     // Choose best sensor values (same logic as before)
//     float final_temp = pre_temp;
//     float final_hum = pre_hum;

//     if (pre_valid && post_valid) {
//         float temp_diff = abs(pre_temp - post_temp);
//         float hum_diff = abs(pre_hum - post_hum);

//         if (temp_diff < 2.0 && hum_diff < 5.0) {
//             final_temp = (pre_temp + post_temp) / 2.0;
//             final_hum = (pre_hum + post_hum) / 2.0;
//             // DEBUG DISABLED: Serial.println("Using averaged sensor values");
//         } else {
//             // DEBUG DISABLED: Serial.println("Using pre-LED sensor values (large difference detected)");
//         }
//     } else if (post_valid && !pre_valid) {
//         final_temp = post_temp;
//         final_hum = post_hum;
//         // DEBUG DISABLED: Serial.println("Using post-LED sensor values");
//     }

//     unsigned long endUs = micros();
//     uint16_t totalTimingMs = (endUs - startUs) / 1000;

//     // DEBUG DISABLED: Serial.print("Total sync timing: ");
//     // DEBUG DISABLED: Serial.print(totalTimingMs);
//     // DEBUG DISABLED: Serial.println("ms");

//     sendSyncResponseWithValues(final_temp, final_hum);

//     lastSyncTime = millis();
//     // DEBUG DISABLED: Serial.println("=== DUAL LED SYNC CAPTURE END ===");
// }

// // Enhanced sendSyncResponse and sendStatus functions
// void sendSyncResponseWithValues(float temperature, float humidity) {
//     int16_t temp10 = (int16_t)round(temperature * 10.0f);
//     uint16_t hum10 = (uint16_t)round(humidity * 10.0f);

//     // Enhanced clamping
//     if (temp10 < -400) temp10 = -400;
//     if (temp10 > 800) temp10 = 800;
//     if (hum10 > 1000) hum10 = 1000;
//     if (hum10 < 0) hum10 = 0;

//     uint16_t timing = LED_STABILIZATION_MS + TRIGGER_DELAY_MS;

//     uint8_t packet[7] = {
//         RESPONSE_SYNC_COMPLETE,
//         (uint8_t)(timing >> 8),
//         (uint8_t)(timing & 0xFF),
//         (uint8_t)(temp10 >> 8),
//         (uint8_t)(temp10 & 0xFF),
//         (uint8_t)(hum10 >> 8),
//         (uint8_t)(hum10 & 0xFF)
//     };

//     // DEBUG DISABLED: Serial.print("Sending sync response: T=");
//     // DEBUG DISABLED: Serial.print(temperature);
//     // DEBUG DISABLED: Serial.print("°C, H=");
//     // DEBUG DISABLED: Serial.print(humidity);
//     // DEBUG DISABLED: Serial.print("%, timing=");
//     // DEBUG DISABLED: Serial.print(timing);
//     // DEBUG DISABLED: Serial.print("ms, LED=");
//     // DEBUG DISABLED: Serial.println(currentLedType == LED_TYPE_IR ? "IR" : "White");

//     unsigned long start = millis();
//     while (Serial.availableForWrite() < 7 && (millis() - start) < WRITE_WAIT_TIMEOUT) {
//         esp_task_wdt_reset();
//         delay(1);
//     }

//     if (Serial.availableForWrite() >= 7) {
//         Serial.write(packet, 7);
//         Serial.flush();
//     } else {
//         sendRawByte(RESPONSE_ERROR);
//     }
// }

// void sendStatus(byte code) {
//     float temperature, humidity;
//     bool sensor_valid = readSensorsWithValidation(temperature, humidity);

//     // DEBUG DISABLED: if (!sensor_valid) {
//     //     Serial.println("Status: Using filtered sensor values due to read failure");
//     // }

//     int16_t temp10 = (int16_t)round(temperature * 10.0f);
//     uint16_t hum10 = (uint16_t)round(humidity * 10.0f);

//     if (temp10 < -400) temp10 = -400;
//     if (temp10 > 800) temp10 = 800;
//     if (hum10 > 1000) hum10 = 1000;
//     if (hum10 < 0) hum10 = 0;

//     uint8_t packet[5] = {
//         code,
//         (uint8_t)(temp10 >> 8),
//         (uint8_t)(temp10 & 0xFF),
//         (uint8_t)(hum10 >> 8),
//         (uint8_t)(hum10 & 0xFF)
//     };

//     // DEBUG DISABLED: Serial.print("Status response: code=0x");
//     // DEBUG DISABLED: Serial.print(code, HEX);
//     // DEBUG DISABLED: Serial.print(", T=");
//     // DEBUG DISABLED: Serial.print(temperature);
//     // DEBUG DISABLED: Serial.print("°C, H=");
//     // DEBUG DISABLED: Serial.print(humidity);
//     // DEBUG DISABLED: Serial.print("%, Active LED=");
//     // DEBUG DISABLED: Serial.println(currentLedType == LED_TYPE_IR ? "IR" : "White");

//     unsigned long start = millis();
//     while (Serial.availableForWrite() < 5 && (millis() - start) < WRITE_WAIT_TIMEOUT) {
//         esp_task_wdt_reset();
//         delay(1);
//     }

//     if (Serial.availableForWrite() >= 5) {
//         Serial.write(packet, 5);
//         Serial.flush();
//     } else {
//         sendRawByte(RESPONSE_ERROR);
//     }
// }

// void sendSyncResponse() {
//     float temperature, humidity;
//     readSensorsWithValidation(temperature, humidity);
//     sendSyncResponseWithValues(temperature, humidity);
// }

// void setTiming(uint16_t stabilization_ms, uint16_t delay_ms) {
//     LED_STABILIZATION_MS = (stabilization_ms < 10 ? 10 :
//                            (stabilization_ms > 10000 ? 10000 : stabilization_ms));
//     TRIGGER_DELAY_MS = (delay_ms > 1000 ? 1000 : delay_ms);

//     // DEBUG DISABLED: Serial.print("Timing updated - Stabilization: ");
//     // DEBUG DISABLED: Serial.print(LED_STABILIZATION_MS);
//     // DEBUG DISABLED: Serial.print("ms, Delay: ");
//     // DEBUG DISABLED: Serial.print(TRIGGER_DELAY_MS);
//     // DEBUG DISABLED: Serial.println("ms");
// }

// void sendRawByte(byte b) {
//     unsigned long start = millis();
//     while (Serial.availableForWrite() == 0 && (millis() - start) < WRITE_WAIT_TIMEOUT) {
//         esp_task_wdt_reset();
//         delay(1);
//     }
//     if (Serial.availableForWrite() > 0) {
//         Serial.write(b);
//         Serial.flush();
//     }
// }
