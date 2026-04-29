#include <DHT.h>
#include <ESP32Servo.h>

//All variables

// LED Pins
#define LED_RED 27      // Red LED
#define LED_YELLOW 26   // Yellow LED
#define LED_GREEN 25    // Green LED

// Sensor Pins
// #define DHT_PIN 18       // DHT22
// #define DHT_TYPE DHT22  // DHT22 sensor type

#define RAIN_SENSOR 35  //  Rain sensor (analog)
#define BUTTON_PIN 18   // Push button (button → GND)

// Initialize DHT sensor
// DHT dht(DHT_PIN, DHT_TYPE);

#define SERVO_PIN 13
bool state = false; // false = 90°, true = 180°
Servo sg90;

bool lastButtonState = HIGH;
unsigned long lastDebounce = 0;
#define DEBOUNCE_MS 50


void setup() {
  delay(300); 
  Serial.begin(115200);
  Serial.println("[SYSTEM]: Setup Starting");

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);

  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_YELLOW, LOW);

  // Setup sensors
  pinMode(RAIN_SENSOR, INPUT);
  // dht.begin();

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

  delay(300);

  for (int i = 0; i < 3; i++) {
    delay(1000); 
    digitalWrite(testLeds[i], LOW);
  }

  Serial.println("[SYSTEM]: Setup Complete");
  delay(1000); 
}

void loop(){
  bool currentButtonState = digitalRead(BUTTON_PIN);

  if (currentButtonState == LOW && lastButtonState == HIGH) {
    if (millis() - lastDebounce > DEBOUNCE_MS) {
      Serial.println("[BUTTON]: Pressed");
      state = !state;
      sg90.write(state ? 180 : 90);
      Serial.print("[SERVO]: Moved to ");Serial.print(state ? "180" : "90");Serial.println(" degrees");
      lastDebounce = millis();
    }
  }

  lastButtonState = currentButtonState;
}