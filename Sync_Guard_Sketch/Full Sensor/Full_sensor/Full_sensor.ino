#include <DHT.h>
#include <ESP32Servo.h>

// --- Pin Definitions ---
// #define DHTPIN 19           // Digital pin connected to the DHT sensor
#define RAIN_PIN 34        // Analog pin connected to the Rain Sensor (A0)
#define SERVO_PIN 18       // Digital pin connected to the Servo signal wire

// LED Pins
#define RED_LED 25
#define YELLOW_LED 26
#define GREEN_LED 27

// --- Thresholds ---
// A dry sensor reads high (around 4095). A wet sensor reads lower.
const int RAIN_THRESHOLD = 3000; 

// --- Object Initializations ---
DHT dht(22, DHT22);
Servo myServo;

void setup() {
  Serial.begin(115200);
  Serial.println("Starting ESP32 Weather Station...");

  // Initialize DHT22
  dht.begin();

  // Initialize Rain Sensor pin
  pinMode(RAIN_PIN, INPUT);

  // Initialize LED pins
  pinMode(RED_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);

  // Set initial LED states (all off)
  digitalWrite(RED_LED, LOW);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(GREEN_LED, LOW);

  // Initialize Servo
  // ESP32Servo requires allocating timers
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  
  // Attach servo to pin with standard min/max pulse widths
  myServo.setPeriodHertz(50); 
  myServo.attach(SERVO_PIN, 500, 2400); 
  
  // Set servo to initial "Open" position
  myServo.write(0); 
}

void loop() {
  // 1. Read DHT22 
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  // 2. Read Rain Sensor
  int rainValue = analogRead(RAIN_PIN);

  // Check if DHT reads failed and exit early
  // if (isnan(humidity) || isnan(temperature)) {
  //   Serial.println("Failed to read from DHT sensor!");
  //   delay(2000);
  //   return;
  // }

  // 3. Print Data to Serial Monitor
  Serial.print("Temp: ");
  Serial.print(temperature);
  Serial.print(" °C | Humidity: ");
  Serial.print(humidity);
  Serial.print(" % | Rain Value: ");
  Serial.print(rainValue);

  // 4. Actuate Servo and LEDs based on rain
  if (rainValue < RAIN_THRESHOLD) {
    Serial.println(" -> Status: RAINING! Closing cover. (RED LED ON)");
    
    myServo.write(90);             // Close cover
    digitalWrite(RED_LED, HIGH);   // Turn on Red
    digitalWrite(GREEN_LED, LOW);  // Turn off Green
    
  } else {
    Serial.println(" -> Status: Dry. Cover open. (GREEN LED ON)");
    
    myServo.write(0);              // Open cover
    digitalWrite(GREEN_LED, HIGH); // Turn on Green
    digitalWrite(RED_LED, LOW);    // Turn off Red
  }

  // Note: YELLOW_LED is defined and initialized, but remains unused for now 
  // as per your instructions.

  // Wait 2 seconds before the next loop
  delay(2000);
}