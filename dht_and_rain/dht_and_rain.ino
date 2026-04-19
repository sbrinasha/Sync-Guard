#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// --- WiFi & MQTT Configuration ---
// You can create a config.h file or uncomment and set these directly:
const char* ssid = "Dexter's 13P";
const char* password = "02022002ds";
const char* mqtt_server = "172.20.10.4";

#define DHT_TYPE DHT22
DHT dht(18, DHT_TYPE);

// --- Pin Definitions ---
const int DHT_PIN = 18;       // DHT22 strictly on its distinct pin
const int RAIN_AO_PIN = 34;  // Rain sensor Analog Output (AO) pin

// LED Pins
const int LED_GREEN = 25;    // Safe / Dry
const int LED_YELLOW = 26;   // Caution / Light Rain
const int LED_RED = 27;      // Danger / Heavy Rain

WiFiClient espClient;
PubSubClient client(espClient);

// --- MQTT Callback Function ---
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("MQTT Message [");
  Serial.print(topic);
  Serial.print("]: ");
  
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println(message);
  
  // Handle LED test commands
  if (String(topic) == "esp32/test/led/red" && message == "BLINK3") {
    blinkLED(LED_RED, "RED");
  }
  else if (String(topic) == "esp32/test/led/green" && message == "BLINK3") {
    blinkLED(LED_GREEN, "GREEN");
  }
  else if (String(topic) == "esp32/test/led/yellow" && message == "BLINK3") {
    blinkLED(LED_YELLOW, "YELLOW");
  }
}

// --- Blink LED Function ---
void blinkLED(int ledPin, String colorName) {
  Serial.print("Blinking ");
  Serial.print(colorName);
  Serial.println(" LED 3 times...");
  
  for (int i = 0; i < 3; i++) {
    digitalWrite(ledPin, HIGH);
    delay(200);
    digitalWrite(ledPin, LOW);
    delay(200);
  }
  
  Serial.print(colorName);
  Serial.println(" LED blink complete!");
}

// --- WiFi Setup Function ---
void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

// --- MQTT Reconnect Function ---
void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    if (client.connect(clientId.c_str())) {
      Serial.println("connected!");
      
      // Subscribe to LED test topics
      client.subscribe("esp32/test/led/red");
      client.subscribe("esp32/test/led/green");
      client.subscribe("esp32/test/led/yellow");
      
      Serial.println("Subscribed to LED test topics");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" retry in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  // Initialize Sensors
  dht.begin();
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
  
  // Setup WiFi and MQTT
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  // Handle MQTT connection
  if (!client.connected()) {
    reconnect();
  }
  client.loop();
  
  // --- 1. Read Sensors ---
  int rain_analog_val = analogRead(RAIN_AO_PIN);
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

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
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("DHT22 Error: Failed to read sensor!");
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
