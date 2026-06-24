/**
 * MAHINDRA ELECTRIC - CLOUD TELEMETRY FIRMWARE FOR ESP32
 * 
 * This firmware establishes a Wi-Fi link and transmits live cell pack telemetry
 * (Voltage, Current, Temperature, SoC, SoH) to the Battery Passport backend.
 * Uses standard Arduino ESP32 libraries.
 */

#include <WiFi.h>
#include <HTTPClient.h>

// --- WI-FI CONFIGURATION ---
const char* ssid = "MAHINDRA_WIFI_SSID";     // Replace with your Wi-Fi SSID
const char* password = "WIFI_PASSWORD_HERE"; // Replace with your Wi-Fi Password

// --- API CONFIGURATION ---
// Replace with the IP address of your host machine running backend/server.py
const char* serverUrl = "http://192.168.1.100:8000/api/telemetry"; 

// --- PIN ASSIGNMENTS (If reading physical sensors) ---
// Example: Analog pins or I2C INA219 current/voltage sensor
const int VOLTAGE_SENSOR_PIN = 34;
const int TEMP_SENSOR_PIN = 35;

// Simulated variables for demo fallback
float mockVoltage = 322.5; 
float mockCurrent = -15.2; 
float mockTemperature = 28.5;
float mockSoC = 85.0;
float mockSoH = 78.2;       // Critical decision factor (70-79% is second life)
int mockCycles = 920;
float mockIR = 1.45;

void setup() {
  Serial.begin(115200);
  
  // Connect to Wi-Fi
  Serial.print("Connecting to Wi-Fi network: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("Wi-Fi Connected successfully.");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Check Wi-Fi connection status
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    
    // Begin HTTP connection to the backend telemetry endpoint
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    // 1. Reading sensor values (simulating a discharge drift for demo)
    mockSoC -= 0.05; // slowly discharge over time
    if (mockSoC <= 10.0) {
      mockSoC = 100.0; // reset to full charged
      mockVoltage = 338.0;
      mockCurrent = 0.0; // reset
    } else {
      mockVoltage = 290.0 + (mockSoC / 100.0) * 45.0 - (abs(mockCurrent) * 0.05); // voltage curve relation
      mockCurrent = -15.0 + sin(millis() / 5000.0) * 5.0; // oscillating discharge current
      mockTemperature = 28.5 + (abs(mockCurrent) * 0.15) + random(-5, 5)/10.0; // heat up based on current
    }

    // 2. Construct JSON payload
    // Size estimated using ArduinoJson Assistant or static buffers
    String jsonPayload = "{";
    jsonPayload += "\"voltage\":" + String(mockVoltage, 1) + ",";
    jsonPayload += "\"current\":" + String(mockCurrent, 1) + ",";
    jsonPayload += "\"temperature\":" + String(mockTemperature, 1) + ",";
    jsonPayload += "\"soc\":" + String(mockSoC, 1) + ",";
    jsonPayload += "\"soh\":" + String(mockSoH, 2) + ",";
    jsonPayload += "\"cycle_count\":" + String(mockCycles) + ",";
    jsonPayload += "\"internal_resistance_mohm\":" + String(mockIR, 3);
    jsonPayload += "}";

    Serial.print("Sending Telemetry: ");
    Serial.println(jsonPayload);

    // 3. Send HTTP POST request
    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);
      Serial.print("Server reply: ");
      Serial.println(response);
    } else {
      Serial.print("Error sending HTTP POST: ");
      Serial.println(httpResponseCode);
    }
    
    // Free resources
    http.end();
  } else {
    Serial.println("Wi-Fi Disconnected. Reconnecting...");
    WiFi.begin(ssid, password);
  }

  // Send updates every 1 second
  delay(1000);
}
