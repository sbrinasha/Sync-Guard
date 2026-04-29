#include <WiFi.h>

const char* ssid = "TP-Link_DX02";
const char* password = "02022002Ds@";

void setup() {
  Serial.begin(115200);
  Serial.println("ESP32 Simple WiFi Test");
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    yield();
  }
  
  Serial.println("\nWiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Reconnecting...");
    WiFi.reconnect();
    
    while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
      yield();
    }
    
    Serial.println("\nReconnected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  }
  
  yield();
  delay(1000);
}