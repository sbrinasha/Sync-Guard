#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include "config.h"

// --- Configuration (now in config.h) ---
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASS;
const char* mqtt_server = MQTT_SERVER;

// LED Pins
#define LED_BUILTIN 2   // GPIO2 for built-in LED
#define LED_RED 27      // GPIO27 for Red LED
#define LED_YELLOW 26   // GPIO26 for Yellow LED
#define LED_GREEN 25    // GPIO25 for Green LED

// Sensor Pins
#define DHT_PIN 18       // GPIO18 for DHT22
#define DHT_TYPE DHT22  // DHT22 sensor type
#define RAIN_SENSOR 35  // GPIO34 for Rain sensor (analog)

// Initialize DHT sensor
DHT dht(DHT_PIN, DHT_TYPE);

WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastMsg = 0;
unsigned long lastStatusMsg = 0;
#define MSG_BUFFER_SIZE (50)
char msg[MSG_BUFFER_SIZE];

// --- Functions ---
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

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");
  
  // Convert payload to string
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println(message);
  
  // Handle button test command (original)
  if (String(topic) == "esp32/button_test" && message == "BLINK") {
    Serial.println("Button test received! Blinking built-in LED 3 times...");
    
    // Blink built-in LED 3 times
    for (int i = 0; i < 3; i++) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(200);
      digitalWrite(LED_BUILTIN, LOW);
      delay(200);
    }
    
    Serial.println("Built-in LED blink complete!");
  }
  
  // Handle LED test commands (new)
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

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Create a random client ID
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    // Attempt to connect
    if (client.connect(clientId.c_str())) {
      Serial.println("connected");
      // Once connected, publish an announcement...
      client.publish("esp32/status", "online");
      
      // Subscribe to topics
      client.subscribe("esp32/button_test");
      Serial.println("Subscribed to esp32/button_test");
      
      client.subscribe("esp32/test/led/red");
      Serial.println("Subscribed to esp32/test/led/red");
      
      client.subscribe("esp32/test/led/green");
      Serial.println("Subscribed to esp32/test/led/green");
      
      client.subscribe("esp32/test/led/yellow");
      Serial.println("Subscribed to esp32/test/led/yellow");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  // Setup LED pins
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  
  // Initialize all LEDs to OFF
  digitalWrite(LED_BUILTIN, LOW);
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_YELLOW, LOW);
  
  // Setup sensors
  pinMode(RAIN_SENSOR, INPUT);
  dht.begin();
  
  Serial.println("=== SyncGuard ESP32 Starting ===");
  Serial.println("DHT22 sensor initialized");
  Serial.println("Rain sensor initialized");
  
  setup_wifi();
  client.setServer(mqtt_server, MQTT_PORT);
  client.setCallback(callback);  // Set callback for incoming messages
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  
  // Publish status heartbeat every 5 seconds
  if (now - lastStatusMsg > 5000) {
    lastStatusMsg = now;
    client.publish("esp32/status", "online");
    Serial.println("Status: online");
  }
  
  // Read and display sensor data every 2 seconds
  if (now - lastMsg > 2000) {
    lastMsg = now;

    // Read DHT22 sensor
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    
    // Read rain sensor (analog value 0-4095 on ESP32)
    int rainValue = analogRead(RAIN_SENSOR);
    
    // Print sensor data to Serial Monitor
    Serial.println("========== Sensor Readings ==========");
    
    // DHT22 readings
    if (isnan(temperature) || isnan(humidity)) {
      Serial.println("[ERROR] DHT22: Failed to read sensor!");
    } else {
      Serial.print("Temperature: ");
      Serial.print(temperature);
      Serial.println(" °C");
      
      Serial.print("Humidity: ");
      Serial.print(humidity);
      Serial.println(" %");
    }
    
    // Rain sensor reading
    Serial.print("Rain Sensor: ");
    Serial.print(rainValue);
    Serial.print(" (");
    
    // Interpret rain sensor value
    if (rainValue > 3000) {
      Serial.println("Dry)");
    } else if (rainValue > 1500) {
      Serial.println("Light Rain)");
    } else {
      Serial.println("Heavy Rain)");
    }
    
    Serial.println("====================================\n");
    
    // --- Still publish simulated data to MQTT for now ---
    float sensorValue = random(20, 30); // Simulated temperature data
    dtostrf(sensorValue, 1, 2, msg);
    client.publish("esp32/sensor_data", msg);
  }
}