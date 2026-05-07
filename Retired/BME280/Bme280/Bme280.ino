#include <Wire.h>

#define SDA_PIN 8  // change these to test different pins
#define SCL_PIN 9

void setup() {
  Serial.begin(115200);
  delay(3000);

  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println("Scanning I2C bus...");
  Serial.println("-------------------");

  int deviceCount = 0;

  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Device found at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      deviceCount++;
    }
  }

  Serial.println("-------------------");
  if (deviceCount == 0) {
    Serial.println("No devices found on SDA:");
    Serial.print("SDA: GPIO"); Serial.println(SDA_PIN);
    Serial.print("SCL: GPIO"); Serial.println(SCL_PIN);
  } else {
    Serial.print(deviceCount);
    Serial.println(" device(s) found!");
  }
}

void loop() {}