/*
 * Adjusted code for ESP32 Rain Sensor
 * VCC is connected directly to 3.3V
 */

#define DO_PIN 32 // ESP32's pin GPIO34 connected to DO pin of the rain sensor

void setup() {
  // Initialize serial communication
  Serial.begin(9600);
  
  // Configure the digital pin as an input
  pinMode(DO_PIN, INPUT);
}

void loop() {
  // Read the state of the rain sensor (High = No Rain, Low = Rain)
  int rain_state = digitalRead(DO_PIN);

  if (rain_state == HIGH) {
    Serial.println("The rain is NOT detected");
  } else {
    Serial.println("The rain is detected!");
  }

  // 1-second delay for stability
  delay(1000);
}