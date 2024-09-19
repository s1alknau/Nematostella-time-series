#include <Arduino.h>

// Define the pin for LED control
const int ledPin = 4;  // Update this to a PWM pin if needed

void setup() {
  Serial.begin(115200);  // Start serial communication
  pinMode(ledPin, OUTPUT);  // Set LED pin as output
  digitalWrite(ledPin, LOW); // Ensure LED is off initially
}

void loop() {
  // Check if data is available on the serial port
  if (Serial.available() > 0) {
    byte command = Serial.read();  // Read the command byte

    // Process the command
    if (command == 0x01) {
      // Turn on the LED with maximum brightness
      digitalWrite(ledPin, HIGH);  // Turn on the LED
      delay(50);  // Small delay to ensure the LED is fully on
      Serial.write(0x01);  // Send acknowledgment for LED ON
    }
    else if (command == 0x00) {
      // Turn off the LED
      digitalWrite(ledPin, LOW);  // Turn off the LED
      delay(50);  // Small delay to ensure the LED is fully off
      Serial.write(0x00);  // Send acknowledgment for LED OFF
    }
    else {
      // Unknown command, send an error response or ignore
      Serial.write(0xFF);  // Optional: send error code for unknown command
    }
  }

  // Optional: Add some delay if you want to prevent rapid command processing
  delay(10);
}
