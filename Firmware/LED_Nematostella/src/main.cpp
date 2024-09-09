#include <Arduino.h>

// Define the GPIO pin connected to the MOSFET gate
const int ledPin = 5;  // Adjust this to the GPIO pin you're using

// Optional debounce time to avoid rapid toggling (in milliseconds)
const unsigned long debounceDelay = 100;
unsigned long lastToggleTime = 0;

void setup() {
  // Initialize serial communication at 115200 baud rate
  Serial.begin(115200);

  // Initialize the MOSFET pin (LED control) as an output
  pinMode(ledPin, OUTPUT);

  // Turn off the LED strip initially (set the MOSFET gate low)
  digitalWrite(ledPin, LOW);

  // Print an initialization message to serial
  Serial.println("ESP32 LED Controller Initialized.");
}

void loop() {
  // Check if data is available on the serial port
  if (Serial.available() > 0) {
    // Read the incoming data
    String command = Serial.readStringUntil('\n');
    command.trim();  // Remove any trailing newlines or spaces

    // Handle the command with debounce
    unsigned long currentTime = millis();
    if (currentTime - lastToggleTime >= debounceDelay) {
      handleCommand(command);
      lastToggleTime = currentTime;
    }
  }
}

void handleCommand(String command) {
  // Convert the command to uppercase for case-insensitive comparison
  command.toUpperCase();

  // Check for the "ON" command
  if (command.startsWith("ON")) {
    Serial.println("Turning LED ON");
    digitalWrite(ledPin, HIGH);  // Set the MOSFET gate high, turning on the LED strip
    Serial.println("LED ON");
  }
  // Check for the "OFF" command
  else if (command.startsWith("OFF")) {
    Serial.println("Turning LED OFF");
    digitalWrite(ledPin, LOW);   // Set the MOSFET gate low, turning off the LED strip
    Serial.println("LED OFF");
  }
  // Optional: Check for a timed ON command (e.g., "ON for 5")
  else if (command.startsWith("ON FOR")) {
    // Extract the time from the command string
    int onTime = command.substring(7).toInt();  // Get the time in seconds
    if (onTime > 0) {
      Serial.print("Turning LED ON for ");
      Serial.print(onTime);
      Serial.println(" seconds");

      digitalWrite(ledPin, HIGH);
      delay(onTime * 1000);  // Wait for the specified time (in milliseconds)
      digitalWrite(ledPin, LOW);
      Serial.println("LED OFF after timed ON");
    } else {
      Serial.println("Invalid time for ON command.");
    }
  }
  // If the command is unrecognized, send an error message
  else {
    Serial.println("Unknown command. Please use 'ON', 'OFF', or 'ON FOR <seconds>'.");
  }
}
