#include "DHTesp.h"

DHTesp dht;

// --- Pin Definitions ---
const int DHT_PIN = 18;       // DHT22 strictly on its distinct pin
const int RAIN_AO_PIN = 34;  // Rain sensor Analog Output (AO) pin

// LED Pins
const int LED_GREEN = 25;    // Safe / Dry
const int LED_YELLOW = 26;   // Caution / Light Rain
const int LED_RED = 27;      // Danger / Heavy Rain

void setup() {
  Serial.begin(9600);
  
  // Initialize Sensors
  dht.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(RAIN_AO_PIN, INPUT);
  
  // Initialize LEDs as Outputs
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  
  Serial.println("Adaptive Safety Prototype Ready!");
  Serial.println("----------------------------------");
  
  // Flash all LEDs once to confirm they work on startup
  setLEDs(HIGH, HIGH, HIGH);
  delay(1000);
  setLEDs(LOW, LOW, LOW);
  delay(1000); 
}

void loop() {
  // --- 1. Read Sensors ---
  int rain_analog_val = analogRead(RAIN_AO_PIN);
  float humidity = dht.getHumidity();
  float temperature = dht.getTemperature();

  // --- 2. Print Sensor Data ---
  Serial.print("Rain Value: ");
  Serial.print(rain_analog_val);

  // --- 3. Evaluate Logic & Update LEDs ---
  if (rain_analog_val > 3500) {
    // Bone Dry -> SAFE
    Serial.print(" (SAFE)         | ");
    setLEDs(HIGH, LOW, LOW);     // Turn on GREEN
  } 
  else if (rain_analog_val > 2000) {
    // Slight moisture -> CAUTION
    Serial.print(" (WARNING)      | ");
    setLEDs(LOW, HIGH, LOW);     // Turn on YELLOW
  } 
  else {
    // Very wet -> DANGER
    Serial.print(" (RAINING!)     | ");
    setLEDs(LOW, LOW, HIGH);     // Turn on RED
  }

  // --- 4. Print DHT22 Data ---
  if (dht.getStatus() != DHTesp::ERROR_NONE) {
    Serial.println("DHT22 Error: " + String(dht.getStatusString()));
  } else {
    Serial.print("Temp: ");
    Serial.print(temperature);
    Serial.print("°C | Humidity: ");
    Serial.print(humidity);
    Serial.println("%");
  }

  // 2-second delay for DHT22 stability
  delay(2000); 
}

// Helper function to easily switch all three LEDs at once
void setLEDs(int greenState, int yellowState, int redState) {
  digitalWrite(LED_GREEN, greenState);
  digitalWrite(LED_YELLOW, yellowState);
  digitalWrite(LED_RED, redState);
}
