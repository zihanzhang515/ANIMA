#include <Arduino.h>
#include <Servo.h>

Servo headYaw;

void setup() {
  Serial.begin(9600);
  headYaw.attach(10);
  headYaw.write(90);
  Serial.println("Ready");
}

void loop() {
  headYaw.write(70);
  delay(1000);
  headYaw.write(90);
  delay(1000);
  headYaw.write(110);
  delay(1000);
  headYaw.write(90);
  delay(1000);
}
