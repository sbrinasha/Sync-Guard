#include <DHT.h>
#include <ESP32Servo.h>
#include <WiFi.h>

// WiFi Credentials
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// Button Pin
#define BUTTON_PIN 21

// Servo Pin
#define SERVO_PIN 18

// Rain Sensor Pins
#define RAIN_AO 36    //Analog Pin
#define RAIN_DIGITAL 37  //Digital Pin

// LED Pins
#define LED_RED 12
#define LED_YELLOW 11
#define LED_GREEN 10
#define LED_WIFI 13  // Change this to your WiFi LED pin
bool state = false; // false = 90°, true = 180°
bool raining = false;
Servo sg90;

void blinkLED(int pin, int times) {
  for(int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH);
    delay(200);
    digitalWrite(pin, LOW);
    delay(200);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000); // give time for Serial to connect

  Serial.println("Starting Setup");

  sg90.setPeriodHertz(50);           // SG90 runs at 50Hz
  sg90.attach(SERVO_PIN, 500, 2400); // SG90 pulse range: 500–2400µs
  sg90.write(90); // start at 90

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(RAIN_DIGITAL, INPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_WIFI, OUTPUT);

  // Connect to WiFi
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  
  // Blink LED while connecting
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_WIFI, HIGH);
    delay(250);
    digitalWrite(LED_WIFI, LOW);
    delay(250);
    Serial.print(".");
  }
  
  // Keep LED on when connected
  digitalWrite(LED_WIFI, HIGH);
  Serial.println("");
  Serial.println("WiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  delay(300);

  Serial.println("Setup Complete!");
}

void loop() {

  if (digitalRead(BUTTON_PIN) == LOW) {  // LOW = pressed
    Serial.println("Button Pressed!");
    delay(300);
    if(state){
        sg90.write(90);
        state = false;
        delay(100);
    } else {
        sg90.write(180);
        state = true;
        delay(100);
    }
  }

  // Testing Serial 
  if (Serial.available()) {           // check if data is waiting
    String msg = Serial.readStringUntil('\n');  // read until Enter key
    msg.trim();                       // remove extra spaces/newlines

    if(msg == "rain_start"){
        raining = true;
        Serial.println("Rain sensor started");
    } else if(msg == "rain_stop"){
        raining = false;
        Serial.println("Rain sensor stopped");
    } else if(msg == "red"){
        Serial.println("Blinking RED");
        blinkLED(LED_RED, 3);
    } else if(msg == "yellow"){
        Serial.println("Blinking YELLOW");
        blinkLED(LED_YELLOW, 3);
    } else if(msg == "green"){
        Serial.println("Blinking GREEN");
        blinkLED(LED_GREEN, 3);
    } else {
        Serial.print("You sent: ");
        Serial.println(msg);
    }
  }

  // Check rain sensor continuously when active
  if(raining) {
    delay(100);
    int analog = analogRead(RAIN_AO);
    int digital = digitalRead(RAIN_DIGITAL);
    Serial.print("Rain level (Pin 36): ");
    Serial.print(analog);  // 0 = very wet, 4095 = dry
    Serial.print(" | Digital (Pin 37): ");
    Serial.println(digital); // 0 = wet, 1 = dry
  }
  
  // Monitor WiFi connection - turn off LED if disconnected
  if(WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_WIFI, LOW);
  } else {
    digitalWrite(LED_WIFI, HIGH);
  }
  
  delay(50);  // Prevent watchdog timeout
}