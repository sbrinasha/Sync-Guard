#include "DHTesp.h"

DHTesp dht;

// --- Pin Definitions ---
const int DHT_PIN = 18;       // Blue DHT11 Data pin
const int WATER_PIN = 35;    // Water sensor Signal (S) pin

// --- Thresholds ---
// Adjust this number after testing. 
// 0 is usually bone dry. Anything above 1000 usually means it's wet.
const int WATER_THRESHOLD = 1000; 

void setup() {
  Serial.begin(9600);
  
  // Initialize DHT11
  dht.setup(DHT_PIN, DHTesp::DHT22);
  Serial.println("DHT22 initializing...");
  
  // Initialize Water Sensor
  pinMode(WATER_PIN, INPUT);
  Serial.println("Water sensor initializing...");
  
  Serial.println("Adaptive Safety System Ready!");
  Serial.println("----------------------------------");
  delay(1000); 
}

void loop() {
  // --- Read Sensors ---
  
  // 1. Read Water Level (Analog value between 0 and 4095)
  int water_level = analogRead(WATER_PIN);
  
  // 2. Read Temperature and Humidity
  float humidity = dht.getHumidity();
  float temperature = dht.getTemperature();

  // --- Print Water Status ---
  Serial.print("Water Level: ");
  Serial.print(water_level);
  
  // Trigger the safety alert if the water level crosses the threshold
  if (water_level > WATER_THRESHOLD) {
    Serial.print(" (STATUS: LEAK DETECTED) | ");
  } else {
    Serial.print(" (STATUS: DRY)           | ");
  }

  // --- Print DHT11 Status ---
  if (dht.getStatus() != DHTesp::ERROR_NONE) {
    Serial.println("DHT11 Error: " + String(dht.getStatusString()));
  } else {
    Serial.print("Temp: ");
    Serial.print(temperature);
    Serial.print("°C | Humidity: ");
    Serial.print(humidity);
    Serial.println("%");
  }

  delay(2000); 
}