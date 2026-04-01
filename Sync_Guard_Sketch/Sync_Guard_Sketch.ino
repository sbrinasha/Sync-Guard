#include <WiFi.h>
#include <PubSubClient.h>

// --- Configuration ---
const char* ssid = "TP-Link_DX02";
const char* password = "02022002Ds@";
const char* mqtt_server = "192.168.1.100"; // Your Mac's IP running Mosquitto

// Built-in LED
#define LED_BUILTIN 2  // GPIO2 for most ESP32 boards

WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastMsg = 0;
unsigned long lastStatusMsg = 0;
#define MSG_BUFFER_SIZE (50)
char msg[MSG_BUFFER_SIZE];

// --- Functions ---
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
  
  // Handle button test command
  if (String(topic) == "esp32/button_test" && message == "BLINK") {
    Serial.println("Button test received! Blinking LED 3 times...");
    
    // Blink LED 3 times
    for (int i = 0; i < 3; i++) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(200);
      digitalWrite(LED_BUILTIN, LOW);
      delay(200);
    }
    
    Serial.println("LED blink complete!");
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
      // Subscribe to button test topic
      client.subscribe("esp32/button_test");
      Serial.println("Subscribed to esp32/button_test");
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
  
  // Setup LED pin
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  
  setup_wifi();
  client.setServer(mqtt_server, 1883);
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
  
  // Publish sensor data every 2 seconds
  if (now - lastMsg > 2000) {
    lastMsg = now;

    // --- Replace this with your actual sensor reading ---
    float sensorValue = random(20, 30); // Simulated temperature data
    
    // Convert float to string
    dtostrf(sensorValue, 1, 2, msg);
    
    Serial.print("Publishing sensor data: ");
    Serial.println(msg);
    
    // Publish to the topic your Flask app will subscribe to
    client.publish("esp32/sensor_data", msg);
  }
}