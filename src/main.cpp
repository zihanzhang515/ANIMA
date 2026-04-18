/*
 * anima_controller.ino (migrated to src/main.cpp for PlatformIO)
 * --------------------
 * Arduino side: receives JSON commands from Python via USB Serial,
 * controls 4 servos + WS2812B RGB LED ring.
 *
 * Pin assignments:
 *   Pin 3  → Left ear servo (small)
 *   Pin 5  → Right ear servo (small) - comment out if only 1 ear servo
 *   Pin 9  → Head Yaw servo (MG996R - left/right rotation)
 *   Pin 10 → Head Pitch servo (MG996R - up/down tilt)
 *   Pin 6  → RGB LED ring data (WS2812B) via 470Ω resistor
 */

#include <Arduino.h>
#include <Servo.h>
#include <ArduinoJson.h>
#include <FastLED.h>

// ─── Pin Configuration ─────────────────────────────────────
#define PIN_EAR_LEFT    3
#define PIN_EAR_RIGHT   5    // Comment out if only 1 ear servo
#define PIN_HEAD_YAW    9
#define PIN_HEAD_PITCH  10
#define PIN_LED         6

// ─── LED Configuration ─────────────────────────────────────
#define NUM_LEDS        12   // Adjust to your ring size
#define LED_BRIGHTNESS  120  // 0-255, keep under 150 for desk use

// ─── Function Prototypes ───────────────────────────────────
void processCommand(const char* json);
void setServos(int ear, int yaw, int pitch);
void smoothMove(int targetEar, int targetYaw, int targetPitch, int durationMs);
void setLight(int r, int g, int b);
void playAlertReflex(int ear, int r, int g, int b);
void playShyReflex(int r, int g, int b);

// ─── Servo Objects ─────────────────────────────────────────
Servo earLeft;
Servo earRight;
Servo headYaw;
Servo headPitch;

// ─── LED Array ─────────────────────────────────────────────
CRGB leds[NUM_LEDS];

// ─── Current State ─────────────────────────────────────────
int currentEar   = 45;
int currentYaw   = 90;
int currentPitch = 90;
int currentR = 255, currentG = 245, currentB = 224;  // Warm white (relaxed)

// ─── Serial Buffer ─────────────────────────────────────────
const int BUFFER_SIZE = 256;
char inputBuffer[BUFFER_SIZE];
int bufferIndex = 0;

// ─── Setup ─────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  // Attach servos
  earLeft.attach(PIN_EAR_LEFT);
  earRight.attach(PIN_EAR_RIGHT);
  headYaw.attach(PIN_HEAD_YAW);
  headPitch.attach(PIN_HEAD_PITCH);

  // Initialize LEDs
  FastLED.addLeds<WS2812B, PIN_LED, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(LED_BRIGHTNESS);

  // Start in relaxed position
  setServos(45, 90, 90);
  setLight(255, 245, 224);

  Serial.println("ANIMA ready");
}

// ─── Main Loop ─────────────────────────────────────────────
void loop() {
  // Read serial input character by character
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      // Full command received - process it
      inputBuffer[bufferIndex] = '\0';
      processCommand(inputBuffer);
      bufferIndex = 0;  // Reset buffer
    } else if (bufferIndex < BUFFER_SIZE - 1) {
      inputBuffer[bufferIndex++] = c;
    }
  }
}

// ─── Command Processing ────────────────────────────────────
void processCommand(const char* json) {
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, json);

  if (error) {
    Serial.print("JSON error: ");
    Serial.println(error.c_str());
    return;
  }

  const char* type = doc["type"];

  if (strcmp(type, "emotion") == 0) {
    // Full emotion change with smooth transition
    int ear   = doc["ear"]   | 45;
    int yaw   = doc["yaw"]   | 90;
    int pitch = doc["pitch"] | 90;
    int r = doc["r"] | 255;
    int g = doc["g"] | 245;
    int b = doc["b"] | 224;

    smoothMove(ear, yaw, pitch, 3000);  // 3 second transition
    setLight(r, g, b);

  } else if (strcmp(type, "track") == 0) {
    // Real-time face tracking - only update yaw, fast
    int yaw = doc["yaw"] | 90;
    headYaw.write(yaw);
    currentYaw = yaw;

  } else if (strcmp(type, "reflex") == 0) {
    // One-shot reflex behavior
    const char* name = doc["name"];
    int ear = doc["ear"] | 90;
    int r = doc["r"] | 0;
    int g = doc["g"] | 255;
    int b = doc["b"] | 255;

    if (strcmp(name, "alert") == 0) {
      playAlertReflex(ear, r, g, b);
    } else if (strcmp(name, "shy") == 0) {
      playShyReflex(r, g, b);
    }

    // Return to previous state after reflex
    delay(500);
    setServos(currentEar, currentYaw, currentPitch);
    setLight(currentR, currentG, currentB);

  } else if (strcmp(type, "idle") == 0) {
    // Micro idle motion
    int ear   = doc["ear"]   | currentEar;
    int yaw   = doc["yaw"]   | currentYaw;
    int pitch = doc["pitch"] | currentPitch;
    smoothMove(ear, yaw, pitch, 2000);
  }

  Serial.println("OK");
}

// ─── Servo Control ─────────────────────────────────────────
void setServos(int ear, int yaw, int pitch) {
  earLeft.write(ear);
  earRight.write(ear);   // Comment out if only 1 ear
  headYaw.write(yaw);
  headPitch.write(pitch);
  currentEar   = ear;
  currentYaw   = yaw;
  currentPitch = pitch;
}

void smoothMove(int targetEar, int targetYaw, int targetPitch, int durationMs) {
  // Simple linear interpolation over duration
  int steps = durationMs / 20;  // Update every 20ms
  if (steps < 1) steps = 1;

  float earStep   = (targetEar   - currentEar)   / (float)steps;
  float yawStep   = (targetYaw   - currentYaw)   / (float)steps;
  float pitchStep = (targetPitch - currentPitch) / (float)steps;

  for (int i = 0; i < steps; i++) {
    earLeft.write(currentEar   + (int)(earStep   * i));
    earRight.write(currentEar  + (int)(earStep   * i));
    headYaw.write(currentYaw   + (int)(yawStep   * i));
    headPitch.write(currentPitch + (int)(pitchStep * i));
    delay(20);
  }

  setServos(targetEar, targetYaw, targetPitch);
}

// ─── LED Control ───────────────────────────────────────────
void setLight(int r, int g, int b) {
  fill_solid(leds, NUM_LEDS, CRGB(r, g, b));
  FastLED.show();
  currentR = r; currentG = g; currentB = b;
}

// ─── Reflex Animations ─────────────────────────────────────
void playAlertReflex(int ear, int r, int g, int b) {
  // Snap ears up + fast scan left-right + flash
  earLeft.write(ear);
  earRight.write(ear);
  setLight(r, g, b);

  // Quick scan: left → pause → right → center
  headYaw.write(70);  delay(200);
  headYaw.write(110); delay(200);
  headYaw.write(90);
}

void playShyReflex(int r, int g, int b) {
  // Slow avoidance: ears flat, head turns away and down
  earLeft.write(0);
  earRight.write(0);
  setLight(r, g, b);

  // Slow movement
  for (int i = 90; i >= 70; i -= 2) {
    headYaw.write(i);
    delay(30);
  }
  for (int i = 90; i >= 78; i -= 2) {
    headPitch.write(i);
    delay(30);
  }
}