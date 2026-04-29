#include <WiFi.h>
#include <PubSubClient.h>
// #include "soc/soc.h"
// #include "soc/rtc_cntl_reg.h"

// --- Hardcoded Configuration ---
const char* ssid        = "TP-Link_DX02";
const char* password    = "02022002Ds@";
const char* mqtt_server = "192.168.1.105";

// const char* ssid        = "Dexter13P";
// const char* password    = "02022002ds";
// const char* mqtt_server = "172.20.10.2";

#define MQTT_PORT    1883

WiFiClient   espClient;
PubSubClient client(espClient);

unsigned long lastStatusMsg  = 0;
unsigned long heartbeatCount = 0;
#define STATUS_BUFFER_SIZE 96
char statusMsg[STATUS_BUFFER_SIZE];

// ---------------------------------------------------------------------------
void setup_wifi() {
  Serial.println();
  Serial.println("Connecting to " + String(ssid));
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  WiFi.setTxPower(WIFI_POWER_7dBm);  // Reduce power ~30% (78mA -> ~50mA)

  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(100);
    yield();  // Feed the watchdog to prevent TG1WDT_SYS_RESET
    if (millis() - startTime > 15000) {
      Serial.println("\nFailed to connect. Restarting...");
      ESP.restart();
    }
  }

  // Solid LED — connected
  Serial.println();
  Serial.println("WiFi connected — IP: " + WiFi.localIP().toString());
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");

    String clientId = "ESP32Test-";
    clientId += String(random(0xffff), HEX);

    // LWT — broker publishes this if ESP32 drops unexpectedly
    const char* lwtPayload = "{\"status\":\"offline\"}";

    if (client.connect(clientId.c_str(), NULL, NULL, "esp32/status", 0, false, lwtPayload)) {
      Serial.println("connected");

      // Announce online
      unsigned long uptimeSec = millis() / 1000;
      snprintf(statusMsg, STATUS_BUFFER_SIZE,
               "{\"status\":\"online\",\"uptime\":%lu}", uptimeSec);
      client.publish("esp32/status", statusMsg);
      Serial.println("Published: " + String(statusMsg));
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" — retrying in 5 seconds");
      delay(5000);
    }
  }
}

// ---------------------------------------------------------------------------
void setup() {
  // WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Disable brownout detector

  Serial.begin(115200);

  Serial.println("=== SyncGuard WiFi Test ===");
  Serial.println("--- Configuration ---");
  Serial.println("WiFi SSID  : " + String(ssid));
  Serial.println("MQTT Server: " + String(mqtt_server));
  Serial.println("MQTT Port  : " + String(MQTT_PORT));
  Serial.println("---------------------");

  setup_wifi();
  client.setServer(mqtt_server, MQTT_PORT);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();

  // Publish heartbeat every 5 seconds
  if (now - lastStatusMsg > 5000) {
    lastStatusMsg = now;
    heartbeatCount++;
    unsigned long uptimeSec = now / 1000;
    snprintf(statusMsg, STATUS_BUFFER_SIZE,
             "{\"status\":\"heartbeat\",\"uptime\":%lu,\"count\":%lu}",
             uptimeSec, heartbeatCount);
    client.publish("esp32/status", statusMsg);
    Serial.println("Heartbeat #" + String(heartbeatCount) +
                   " uptime=" + String(uptimeSec) + "s");
  }
}