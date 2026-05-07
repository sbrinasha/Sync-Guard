#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <SparkFunBME280.h>
#include <DHT.h>
#include "config.h"

// ===== GPIO Pins =====
#define LED_MQTT      14  //Blinking -Connecting, Solid - Connected
#define WIFI_LED_PIN  13  //Blinking -Connecting, Solid - Connected
#define LED_RED       12  
#define LED_YELLOW    11  
#define LED_GREEN     10  

#define SERVO_PIN     16  
#define RAIN_DO_PIN   22
#define RAIN_AO_PIN   34
#define BUTTON_PIN    15  // Button: GPIO 15 > Button > GND
#define DHT_PIN       42  // Placeholder - Change to actual GPIO pin later
#define DHT_TYPE      DHT22

// ===== BME280 Configuration (SparkFun) =====
#define BME280_I2C_ADDR 0x76  // Change to 0x77 if needed
#define BME280_SDA_PIN  8
#define BME280_SCL_PIN  9

// ===== MQTT Configuration =====
// --- SENT (ESP32 → Broker → Dashboard) ---
#define MQTT_TOPIC_STATUS      "syncguard/status"
#define MQTT_TOPIC_DATA        "syncguard/data"
#define MQTT_TOPIC_TEMPERATURE "syncguard/temperature"
#define MQTT_TOPIC_PRESSURE    "syncguard/pressure"
#define MQTT_TOPIC_RAIN        "syncguard/rain"
#define MQTT_TOPIC_RAIN_ANALOG "syncguard/rain_analog"
#define MQTT_TOPIC_HUMIDITY    "syncguard/humidity"
#define MQTT_TOPIC_HEARTBEAT   "syncguard/heartbeat"
#define MQTT_TOPIC_SERVO_POS   "syncguard/servo/state"

// --- RECEIVED (Dashboard → Broker → ESP32) ---
#define MQTT_TOPIC_SERVO_STATE "syncguard/servo/change-state"

// --- Publish Interval ---
#define MQTT_PUBLISH_INTERVAL  5000   // Interval (ms) for all sensors to publish data

// ===== Servo States =====
#define SERVO_OPEN    90
#define SERVO_CLOSED  180

// ===== Global Objects =====
WiFiClient espClient;
PubSubClient mqtt(espClient);
Servo myServo;
BME280 bme;
DHT dht(DHT_PIN, DHT_TYPE);

// ===== State Variables =====
bool wifiConnected = false;
bool mqttConnected = false;
bool bmpAvailable  = false;
bool servoOpen     = true;   // true = open (90°), false = closed (180°)
bool lastButtonState = HIGH; // Pull-up: unpressed = HIGH
unsigned long lastReconnectAttempt = 0;
unsigned long lastSensorRead = 0;
unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 15000;  // Heartbeat every 15 seconds

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  // Initialize LEDs
  pinMode(WIFI_LED_PIN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_MQTT, OUTPUT);

  digitalWrite(WIFI_LED_PIN, LOW);
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_YELLOW, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_MQTT, LOW);
  
  Serial.println("\n=== Sync Guard Starting ===");

  // Initialize Button (INPUT_PULLUP: unpressed = HIGH, pressed = LOW)
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.println("Button initialized.");

  // Initialize Servo - start at OPEN (90°)
  myServo.attach(SERVO_PIN);
  myServo.write(SERVO_OPEN);
  servoOpen = true;
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_RED, LOW);
  Serial.println("Servo initialized at OPEN (90°).");

  // Initialize Rain Sensor
  pinMode(RAIN_DO_PIN, INPUT);
  Serial.println("Rain sensor initialized.");

  // Initialize DHT
  dht.begin();
  Serial.println("DHT initialized.");

  // Initialize BME280 (SparkFun)
  Wire.begin(BME280_SDA_PIN, BME280_SCL_PIN);
  bme.setI2CAddress(0x76);
  
  bme.setI2CAddress(BME280_I2C_ADDR);
  if (bme.beginI2C()) {
    bmpAvailable = true;
    Serial.println("BME280 initialized.");
  } else {
    Serial.println("BME280 not found! Check wiring or I2C address.");
  }

  // Connect to WiFi
  connectWiFi();
  
  // Configure MQTT
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
}

void loop() {

  // Handle WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    digitalWrite(WIFI_LED_PIN, LOW);
    connectWiFi();
  } else if (!wifiConnected) {
    wifiConnected = true;
    digitalWrite(WIFI_LED_PIN, HIGH);  // Solid when connected
  }
  
  // Handle MQTT connection
  if (wifiConnected) {
    if (!mqtt.connected()) {
      mqttConnected = false;
      blinkLED(LED_MQTT, 250);  // Blink while connecting
      unsigned long now = millis();
      if (now - lastReconnectAttempt > 5000) {
        lastReconnectAttempt = now;
        connectMQTT();
      }
    } else {
      if (!mqttConnected) {
        mqttConnected = true;
        digitalWrite(LED_MQTT, HIGH);  // Solid when connected
        Serial.println("MQTT Connected!");
      }
      mqtt.loop();
    }
  }
  
  // Read and publish sensors periodically
  unsigned long now = millis();
  if (now - lastSensorRead >= MQTT_PUBLISH_INTERVAL) {
    lastSensorRead = now;
    readSensors();
  }

  // Handle button press (toggle servo state)
  handleButton();

  // Heartbeat
  if (now - lastHeartbeat >= HEARTBEAT_INTERVAL) {
    lastHeartbeat = now;
    sendHeartbeat();
  }

  delay(100);
}

// ===== WiFi Functions =====
void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    blinkLED(WIFI_LED_PIN, 250);  // Blink while connecting
    Serial.print(".");
    attempts++;
  }
  
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi Connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    digitalWrite(WIFI_LED_PIN, HIGH);
  } else {
    Serial.println("WiFi Failed!");
  }
}

// ===== MQTT Functions =====
void connectMQTT() {
  Serial.print("Connecting to MQTT...");
  
  String clientId = "SyncGuard-" + String(WiFi.macAddress());
  
  if (mqtt.connect(clientId.c_str())) {
    Serial.println("Connected!");
    mqtt.publish(MQTT_TOPIC_STATUS, "online");
    mqtt.subscribe(MQTT_TOPIC_DATA);
    mqtt.subscribe(MQTT_TOPIC_SERVO_STATE);  // Receive servo commands from dashboard
  } else {
    Serial.print("Failed, rc=");
    Serial.println(mqtt.state());
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Convert payload to string
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("[RECEIVED] Topic: ");
  Serial.print(topic);
  Serial.print(" | Message: ");
  Serial.println(message);

  // --- Handle servo command ---
  if (String(topic) == MQTT_TOPIC_SERVO_STATE) {
    if (message == "open" || message == "90") {
      if (!servoOpen) toggleServo();
    } else if (message == "close" || message == "closed" || message == "180") {
      if (servoOpen) toggleServo();
    }
  }
}

// ===== Sensor Functions =====
void readSensors() {
  // --- DHT (Humidity only) ---
  float humidity = dht.readHumidity();
  if (!isnan(humidity)) {
    Serial.print("Humidity: "); Serial.print(humidity); Serial.println(" %");
    if (mqttConnected) {
      char buf[16];
      snprintf(buf, sizeof(buf), "%.2f", humidity);
      mqtt.publish(MQTT_TOPIC_HUMIDITY, buf);
    }
  } else {
    Serial.println("DHT read failed!");
  }

  // --- Rain Sensor ---
  bool isRaining = (digitalRead(RAIN_DO_PIN) == LOW);  // LOW = rain detected
  int rainAnalog = analogRead(RAIN_AO_PIN);            // 0-4095, lower = wetter

  Serial.print("Rain: ");
  Serial.print(isRaining ? "Yes" : "No");
  Serial.print(" | Analog: ");
  Serial.println(rainAnalog);

  if (mqttConnected) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%d", rainAnalog);
    mqtt.publish(MQTT_TOPIC_RAIN, isRaining ? "1" : "0");
    mqtt.publish(MQTT_TOPIC_RAIN_ANALOG, buf);
  }

  // --- BME280 ---
  if (bmpAvailable) {
    float temperature = bme.readTempC();              // Celsius
    float pressure    = bme.readFloatPressure() / 100.0F; // hPa

    Serial.print("Temp: ");     Serial.print(temperature); Serial.print(" C | ");
    Serial.print("Pressure: "); Serial.print(pressure);    Serial.println(" hPa");

    if (mqttConnected) {
      char buf[64];
      snprintf(buf, sizeof(buf), "%.2f", temperature);
      mqtt.publish(MQTT_TOPIC_TEMPERATURE, buf);

      snprintf(buf, sizeof(buf), "%.2f", pressure);
      mqtt.publish(MQTT_TOPIC_PRESSURE, buf);
    }
  // --- Servo State ---
  if (mqttConnected) {
    mqtt.publish(MQTT_TOPIC_SERVO_POS, servoOpen ? "open" : "closed");
  }
}

void sendHeartbeat() {
  if (!mqttConnected) return;

  char buf[32];
  snprintf(buf, sizeof(buf), "%lu", millis() / 1000);  // Uptime in seconds
  mqtt.publish(MQTT_TOPIC_HEARTBEAT, buf);

  Serial.print("Heartbeat sent | Uptime: ");
  Serial.print(buf);
  Serial.println("s");
}

void setServoAngle(int angle) {
  angle = constrain(angle, 0, 180);
  myServo.write(angle);
  Serial.print("Servo set to: ");
  Serial.println(angle);
}

void toggleServo() {
  if (servoOpen) {
    // Close it
    servoOpen = false;
    myServo.write(SERVO_CLOSED);
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_RED, HIGH);
    Serial.println("Servo: CLOSED (180°)");
    if (mqttConnected) mqtt.publish(MQTT_TOPIC_SERVO_POS, "closed");
  } else {
    // Open it
    servoOpen = true;
    myServo.write(SERVO_OPEN);
    digitalWrite(LED_RED, LOW);
    digitalWrite(LED_GREEN, HIGH);
    Serial.println("Servo: OPEN (90°)");
    if (mqttConnected) mqtt.publish(MQTT_TOPIC_SERVO_POS, "open");
  }
}

void handleButton() {
  bool currentState = digitalRead(BUTTON_PIN);
  // Detect falling edge (HIGH -> LOW = button pressed)
  if (lastButtonState == HIGH && currentState == LOW) {
    delay(50);  // Debounce
    if (digitalRead(BUTTON_PIN) == LOW) {
      toggleServo();
    }
  }
  lastButtonState = currentState;
}

// ===== Utility Functions =====
void blinkLED(int pin, int delayMs) {
  digitalWrite(pin, !digitalRead(pin));
  delay(delayMs);
}
