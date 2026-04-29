// =============================================================================
// MODE SELECTION
// Set WIFI_MODE to true  → connect to WiFi and publish directly to MQTT broker
// Set WIFI_MODE to false → offline mode, sensor data is printed to Serial only
//                          (use serializer.py on your PC to bridge Serial → MQTT)
// =============================================================================
#define WIFI_MODE false

#if WIFI_MODE
#include <WiFi.h>
#include <PubSubClient.h>

// --- Configuration (now in config.h) ---
const char* ssid        = WIFI_SSID;
const char* password    = WIFI_PASS;
const char* mqtt_server = MQTT_SERVER;

WiFiClient espClient;
PubSubClient client(espClient);
#endif

#include <DHT.h>
#include <ESP32Servo.h>
#include "config.h"

// LED Pins
#define LED_RED 27      // GPIO27 for Red LED
#define LED_YELLOW 26   // GPIO26 for Yellow LED
#define LED_GREEN 25    // GPIO25 for Green LED

// Sensor Pins
#define DHT_PIN 18       // GPIO18 for DHT22
#define DHT_TYPE DHT22  // DHT22 sensor type
#define RAIN_SENSOR 35  // GPIO34 for Rain sensor (analog)
#define BUTTON_PIN 15   // GPIO14 for push button (button → GND)

// Initialize DHT sensor
DHT dht(DHT_PIN, DHT_TYPE);

Servo sg90;
#define SERVO_PIN 12

bool state = false; // false = 90°, true = 180°

unsigned long lastMsg = 0;
unsigned long lastStatusMsg = 0;
unsigned long heartbeatCount = 0;
unsigned long lastWifiLed = 0;
bool wifiLedState = false;

// Button + servo state
bool servoOpen = false;          // false = 0°, true = 90°
bool lastButtonState = HIGH;     // INPUT_PULLUP: idle = HIGH
unsigned long lastDebounce = 0;
#define DEBOUNCE_MS 50
#define MSG_BUFFER_SIZE (96)
#if WIFI_MODE
char statusMsg[MSG_BUFFER_SIZE];
#endif

// --- MQTT Log Helper ---
void mqttLog(String message) {
  Serial.println(message);
  #if WIFI_MODE
  if (client.connected()) {
    client.publish("esp32/system/logs", message.c_str());
  }
  #endif
}

// --- Functions ---
#if WIFI_MODE
void blinkLED(int ledPin, String colorName) {
  mqttLog("Blinking " + colorName + " LED 3 times...");
  
  for (int i = 0; i < 3; i++) {
    digitalWrite(ledPin, HIGH);
    delay(200);
    digitalWrite(ledPin, LOW);
    delay(200);
  }
  
  mqttLog(colorName + " LED blink complete!");
}

void callback(char* topic, byte* payload, unsigned int length) {
  // Convert payload to string
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  mqttLog("Message arrived [" + String(topic) + "]: " + message);
  
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
  Serial.println("Connecting to " + String(ssid));

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  mqttLog("WiFi connected");
  mqttLog("IP address: " + WiFi.localIP().toString());
}

void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Create a random client ID
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);

    // Last Will & Testament — broker publishes this if ESP32 drops unexpectedly
    const char* lwtPayload = "{\"status\":\"offline\"}";

    // Attempt to connect with LWT
    if (client.connect(clientId.c_str(), NULL, NULL, "esp32/status", 0, false, lwtPayload)) {
      Serial.println("connected");
      // Publish online announcement as JSON
      unsigned long uptimeSec = millis() / 1000;
      snprintf(statusMsg, MSG_BUFFER_SIZE, "{\"status\":\"online\",\"uptime\":%lu}", uptimeSec);
      client.publish("esp32/status", statusMsg);
      
      client.subscribe("esp32/test/led/red");
      mqttLog("Subscribed to esp32/test/led/red");
      
      client.subscribe("esp32/test/led/green");
      mqttLog("Subscribed to esp32/test/led/green");
      
      client.subscribe("esp32/test/led/yellow");
      mqttLog("Subscribed to esp32/test/led/yellow");
      
      mqttLog("=== SyncGuard ESP32 MQTT Connected ===");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}
#endif // WIFI_MODE

void setup() {
  delay(300); 
  Serial.begin(115200);

  delay(1000); 
  Serial.println("Setting Up Components");
  
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);

  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_YELLOW, LOW);
  
  // Setup sensors
  pinMode(RAIN_SENSOR, INPUT);
  dht.begin();

  // Setup SG90 servo
  sg90.setPeriodHertz(50);           // SG90 runs at 50Hz
  sg90.attach(SERVO_PIN, 500, 2400); // SG90 pulse range: 500–2400µs
  sg90.write(90); // start at 90

  // Setup push button
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // --- Startup test: blink all LEDs once + sweep servo ---
  int testLeds[] = { LED_RED, LED_YELLOW, LED_GREEN};
  for (int i = 0; i < 3; i++) {
    delay(1000); 
    digitalWrite(testLeds[i], HIGH);
  }

  sg90.write(180);

  delay(300);

  for (int i = 0; i < 3; i++) {
    delay(1000); 
    digitalWrite(testLeds[i], LOW);
  }

  Serial.println("Finish Setting up");
  delay(1000); 

  Serial.println("SyncGuard ESP32 Starting");
  #if WIFI_MODE
  Serial.println("--- Mode: WiFi + MQTT ---");
  Serial.println("WiFi SSID  : " + String(ssid));
  Serial.println("MQTT Server: " + String(mqtt_server));
  Serial.println("MQTT Port  : " + String(MQTT_PORT));
  #else

  Serial.println("--- Mode: Offline (Serial only) ---");
  Serial.println("Sensor data printed as SENSOR:{...} for serializer.py");
  #endif
  Serial.println("DHT22 sensor initialized");
  Serial.println("Rain sensor initialized");

  #if WIFI_MODE
  setup_wifi();
  client.setServer(mqtt_server, MQTT_PORT);
  client.setCallback(callback);  // Set callback for incoming messages
  #endif
}

void loop() {
  #if WIFI_MODE
  if (!client.connected()) {
    reconnect();
  }
  client.loop();
  #endif

  unsigned long now = millis();

  #if WIFI_MODE
  // Publish heartbeat every 5 seconds
  if (now - lastStatusMsg > 5000) {
    lastStatusMsg = now;
    heartbeatCount++;
    unsigned long uptimeSec = now / 1000;
    snprintf(statusMsg, MSG_BUFFER_SIZE, "{\"status\":\"heartbeat\",\"uptime\":%lu,\"count\":%lu}", uptimeSec, heartbeatCount);
    client.publish("esp32/status", statusMsg);
    mqttLog("Heartbeat #" + String(heartbeatCount) + " uptime=" + String(uptimeSec) + "s");
  }
  #endif

  if (digitalRead(BUTTON_PIN) == LOW) {
    Serial.println("[BUTTON] Pressed");
    state = !state;
    sg90.write(state ? 180 : 90);
    delay(1000);
  }

  // Push button → toggle servo (debounced)
  bool reading = digitalRead(BUTTON_PIN);
  if (reading != lastButtonState) {
    lastDebounce = now;
  }
  if ((now - lastDebounce) >= DEBOUNCE_MS && reading == LOW && lastButtonState == HIGH) {
    servoOpen = !servoOpen;
    int angle = servoOpen ? 180 : 90;
    sg90.write(angle);
    Serial.println("[BUTTON] Pressed! Servo → " + String(angle) + "°");
    mqttLog("Button pressed → servo " + String(angle) + "°");
  }
  lastButtonState = reading;

  // Read and display sensor data every 2 seconds
  if (now - lastMsg > 2000) {
    lastMsg = now;

    // Read DHT22 sensor
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    
    // Read rain sensor (analog value 0-4095 on ESP32)
    int rainValue = analogRead(RAIN_SENSOR);
    
    // DHT22 readings
    if (isnan(temperature) || isnan(humidity)) {
      mqttLog("[ERROR] DHT22: Failed to read sensor!");
    } else {
      mqttLog("Temperature: " + String(temperature, 1) + " °C");
      mqttLog("Humidity: " + String(humidity, 1) + " %");
    }
    
    // Rain sensor reading + interpretation
    String rainStatus;
    if (rainValue > 3000) {
      rainStatus = "Dry";
    } else if (rainValue > 1500) {
      rainStatus = "Light Rain";
    } else {
      rainStatus = "Heavy Rain";
    }
    mqttLog("Rain Sensor: " + String(rainValue) + " (" + rainStatus + ")");

    // --- Always print a SENSOR: JSON line so serializer.py can parse it ---
    // This works in BOTH modes: offline (serializer reads it) and WiFi (logged to MQTT too)
    if (!isnan(temperature) && !isnan(humidity)) {
      String sensorJson = "SENSOR:{\"temperature\":" + String(temperature, 1)
                        + ",\"humidity\":" + String(humidity, 1)
                        + ",\"rain\":" + String(rainValue)
                        + ",\"rain_status\":\"" + rainStatus + "\"}"; 
      Serial.println(sensorJson);
    }

    #if WIFI_MODE
    // Publish real sensor data to MQTT
    if (!isnan(temperature) && !isnan(humidity)) {
      char tempStr[16], humStr[16];
      dtostrf(temperature, 1, 2, tempStr);
      dtostrf(humidity, 1, 2, humStr);
      client.publish("esp32/sensor_data/temperature", tempStr);
      client.publish("esp32/sensor_data/humidity", humStr);
      String rainPayload = "{\"value\":" + String(rainValue) + ",\"status\":\"" + rainStatus + "\"}";
      client.publish("esp32/sensor_data/rain", rainPayload.c_str());
      mqttLog("Published sensor data to MQTT");
    }
    #endif
  }
}