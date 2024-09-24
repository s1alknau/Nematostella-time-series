#include <Arduino.h>
#include "esp_task_wdt.h"  // Include the ESP task watchdog library

// Define the pin for LED control
const int ledPin = 4;  // Update this to a PWM pin if needed

// Define constants for commands and responses
const byte CMD_LED_ON = 0x01;
const byte CMD_LED_OFF = 0x00;
const byte RESPONSE_ACK_ON = 0x01;  // Response for LED ON command
const byte RESPONSE_ACK_OFF = 0x02; // Response for LED OFF command
const byte RESPONSE_ERROR = 0xFF;
const byte RESPONSE_BUFFER_OVERFLOW = 0xFE;
const byte RESPONSE_TIMEOUT = 0xFD;
const byte RESPONSE_INVALID_CMD = 0xFC;

// Define timeouts, retry limits, and buffer size
const unsigned long SERIAL_TIMEOUT = 1000;  // Timeout for serial communication in milliseconds
const int RETRY_LIMIT = 3;  // Number of retries for failed commands
const int MAX_COMMAND_SIZE = 1;  // Maximum size of the command byte expected

// Function to send a response with retries
void sendResponse(byte response) {
  for (int retry = 0; retry < RETRY_LIMIT; retry++) {
    if (Serial.write(response) == 1) { // Check if write is successful
      Serial.flush(); // Ensure the response is sent before returning
      return;  // Exit if response sent successfully
    }
    delay(10);  // Short delay before retrying
  }
  // If all retries failed, indicate error
  Serial.write(RESPONSE_ERROR);
  Serial.flush();
}

// Function to handle LED command
void handleLEDCommand(byte command) {
  if (command == CMD_LED_ON) {
    digitalWrite(ledPin, HIGH);  // Turn on the LED
    delay(50);  // Ensure LED is fully on
    sendResponse(RESPONSE_ACK_ON);  // Send unique acknowledgment for LED ON
  }
  else if (command == CMD_LED_OFF) {
    digitalWrite(ledPin, LOW);  // Turn off the LED
    delay(50);  // Ensure LED is fully off
    sendResponse(RESPONSE_ACK_OFF);  // Send unique acknowledgment for LED OFF
  }
  else {
    sendResponse(RESPONSE_INVALID_CMD);  // Unknown command, send invalid command error
  }
}

// Function to clear serial buffer in case of overflow
void clearSerialBuffer() {
  while (Serial.available() > 0) {
    Serial.read();  // Discard all bytes in the serial buffer
  }
}

// Function to check for watchdog timeout and reset
void enableWatchdog() {
  // Initialize watchdog with a 10-second timeout, do not panic on trigger (false), and apply to idle task only (true)
  esp_task_wdt_init(10, false);  
  esp_task_wdt_add(NULL);        // Add current task to the watchdog
}

void setup() {
  Serial.begin(115200);  // Start serial communication
  pinMode(ledPin, OUTPUT);  // Set LED pin as output
  digitalWrite(ledPin, LOW); // Ensure LED is off initially
  enableWatchdog();          // Enable watchdog timer

  // Remove debugging messages to avoid ASCII characters being sent
  // Serial.println("ESP32 Ready");
}

void loop() {
  // Feed the watchdog timer to prevent reset
  esp_task_wdt_reset();

  // Check if data is available on the serial port with timeout
  unsigned long startTime = millis();
  while (!Serial.available()) {
    if (millis() - startTime >= SERIAL_TIMEOUT) {
      // Serial timeout, send timeout response and return
      sendResponse(RESPONSE_TIMEOUT);
      return;
    }
  }

  // Check for buffer overflow (if more data than expected is available)
  if (Serial.available() > MAX_COMMAND_SIZE) {
    sendResponse(RESPONSE_BUFFER_OVERFLOW);  // Send buffer overflow error
    clearSerialBuffer();  // Clear buffer to prevent future issues
    return;  // Exit the loop to prevent further processing of invalid data
  }

  // Read the command byte
  byte command = Serial.read();
  
  // Handle the received command
  handleLEDCommand(command);

  // Optional: Small delay to avoid rapid command processing
  delay(10);
}
