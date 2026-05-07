#include <Wire.h>
#include <Adafruit_BME280.h>

Adafruit_BME280 bme;

void setup() {
  Serial.begin(9600);
  bme.begin(0x76); // or 0x77
}

void loop() {
  Serial.print("Temp: ");
  Serial.println(bme.readTemperature());
  Serial.print("Humidity: ");
  Serial.println(bme.readHumidity());
  Serial.print("Pressure: ");
  Serial.println(bme.readPressure() / 100.0F);
  delay(2000);
}