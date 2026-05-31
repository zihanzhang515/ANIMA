#include <Arduino.h>
#include <Servo.h>
#include <ArduinoJson.h>
#include <FastLED.h>

#define PIN_EAR_LEFT   3
#define PIN_EAR_RIGHT  5
#define PIN_HEAD_YAW   9
#define PIN_HEAD_PITCH 10
#define PIN_LED        6
#define NUM_LEDS       24
#define LED_BRIGHTNESS 70

// ─── Calibrated physical limits (2026-05-01) ────────────────────────────
// Yaw:   60° = straight ahead, full range 0-180°
// Pitch: 25° = horizontal neutral, 0-40° is the physical limit (±20°)
// Right ear: 0° = forward, higher values fold further back
// Left ear:  physical angle = EAR_L_NEUTRAL(90) - logical angle
#define EAR_MIN        0
#define EAR_MAX        150
#define YAW_MIN        0
#define YAW_MAX        180
#define YAW_CENTER     60    // 正前方
#define EAR_L_NEUTRAL  90

int pitchMin  = 0;    // Full tilt up
int pitchMax  = 40;   // Full tilt down
int basePitch = 25;   // Horizontal neutral

#define SPEED_FAST       600
#define SPEED_MEDIUM    1500
#define SPEED_SLOW      3000
#define SPEED_VERY_SLOW 5000

Servo earLeft, earRight, headYaw, headPitch;
CRGB leds[NUM_LEDS];

int curEar = 0, curEarL = 0, curEarR = 0, curYaw = YAW_CENTER, curPitch = 0;
int curR = 255, curG = 245, curB = 224;
char currentEmotion[20] = "relaxed";
bool busyMoving = false;

const int BUFFER_SIZE = 512;
char inputBuffer[BUFFER_SIZE];
int  bufferIndex = 0;

// ─── Utility functions ───────────────────────────────────────────────────
int leftEarPhysical(int l) { return constrain(EAR_L_NEUTRAL - l, 0, 180); }
int clampYaw(int v)        { return constrain(v, YAW_MIN, YAW_MAX); }
int clampPitch(int v)      { return constrain(v, pitchMin, pitchMax); }
int clampEar(int v)        { return constrain(v, EAR_MIN, EAR_MAX); }

// Write symmetric ear + head position
void writeAll(int ear, int yaw, int pitch) {
  earLeft.write(leftEarPhysical(ear));
  earRight.write(clampEar(ear));
  headYaw.write(clampYaw(yaw));
  headPitch.write(clampPitch(pitch));
  curEarL = ear; curEarR = ear;
}

// Write asymmetric ear + head position (left and right ears independent)
void writeAllAsym(int eL, int eR, int yaw, int pitch) {
  earLeft.write(leftEarPhysical(eL));
  earRight.write(clampEar(eR));
  headYaw.write(clampYaw(yaw));
  headPitch.write(clampPitch(pitch));
  curEarL = eL; curEarR = eR;
}

float sineEaseOut(float t) { return sin(t * (PI / 2.0)); }

// Smooth symmetric move (continuous interpolation from current position, no forced reset)
void smoothMove(int tE, int tY, int tP, int dMs) {
  tE = clampEar(tE); tY = clampYaw(tY); tP = clampPitch(tP);
  int sE = curEar, sY = curYaw, sP = curPitch;
  int steps = max(1, dMs / 16);
  for (int i = 1; i <= steps; i++) {
    float e = sineEaseOut((float)i / steps);
    int nowE = sE + (int)((tE-sE)*e);
    earLeft.write(leftEarPhysical(nowE));
    earRight.write(clampEar(nowE));
    headYaw.write(clampYaw(sY + (int)((tY-sY)*e)));
    headPitch.write(clampPitch(sP + (int)((tP-sP)*e)));
    delay(16);
  }
  curEar = tE; curEarL = tE; curEarR = tE;
  curYaw = tY; curPitch = tP;
  writeAll(curEar, curYaw, curPitch);
}

// Smooth asymmetric move (left/right ears have independent targets)
void smoothMoveAsym(int tEL, int tER, int tY, int tP, int dMs) {
  tEL = clampEar(tEL); tER = clampEar(tER);
  tY = clampYaw(tY); tP = clampPitch(tP);
  int sEL = curEarL, sER = curEarR, sY = curYaw, sP = curPitch;
  int steps = max(1, dMs / 16);
  for (int i = 1; i <= steps; i++) {
    float e = sineEaseOut((float)i / steps);
    earLeft.write(leftEarPhysical(sEL + (int)((tEL-sEL)*e)));
    earRight.write(clampEar(sER + (int)((tER-sER)*e)));
    headYaw.write(clampYaw(sY + (int)((tY-sY)*e)));
    headPitch.write(clampPitch(sP + (int)((tP-sP)*e)));
    delay(16);
  }
  curEarL = tEL; curEarR = tER; curEar = (tEL + tER) / 2;
  curYaw = tY; curPitch = tP;
  writeAllAsym(curEarL, curEarR, curYaw, curPitch);
}

void setLight(int r, int g, int b) {
  fill_solid(leds, NUM_LEDS, CRGB(r, g, b));
  FastLED.show();
  curR = r; curG = g; curB = b;
}

// ─── Emotion enter animations (calibrated coordinate system) ────────────

void enterRelaxed() {
  smoothMove(0, YAW_CENTER, basePitch, SPEED_SLOW);
}

void enterCurious() {
  // Ears fold back 55° during head turn, then settle into a scanning sweep
  smoothMoveAsym(55, 55, YAW_CENTER - 25, basePitch - 5, SPEED_MEDIUM); // Ears fold + turn left
  delay(180);
  smoothMoveAsym(55, 55, YAW_CENTER + 20, basePitch - 5, SPEED_MEDIUM); // Hold fold + turn right
  delay(150);
  smoothMoveAsym(40, 40, YAW_CENTER - 15, basePitch - 5, SPEED_MEDIUM); // Settle left, ears at 40°
}

void enterHappy() {
  // Ear flap + head oscillation ±8° from centre (no pre-reset; continuous from current position)
  for (int i = 0; i < 3; i++) {
    earLeft.write(leftEarPhysical(0));   earRight.write(0);
    headYaw.write(clampYaw(YAW_CENTER - 8)); delay(120);
    earLeft.write(leftEarPhysical(18));  earRight.write(18);
    headYaw.write(clampYaw(YAW_CENTER + 8)); delay(120);
  }
  earLeft.write(leftEarPhysical(0)); earRight.write(0);
  headYaw.write(YAW_CENTER);
  curEarL = 0; curEarR = 0; curEar = 0;
  curYaw = YAW_CENTER; curPitch = basePitch;
}

void enterFocus() {
  // Ears fold back to 90° very slowly; head locked to centre
  smoothMove(90, YAW_CENTER, basePitch, SPEED_VERY_SLOW);
}

void enterTired() {
  // Head and ears slowly droop together (VERY_SLOW) — fatigued sinking motion
  smoothMove(110, YAW_CENTER, basePitch + 15, SPEED_VERY_SLOW);
  delay(400);
  // Sigh micro-motion: sink 2° then recover
  headPitch.write(clampPitch(curPitch + 2)); delay(800);
  headPitch.write(clampPitch(curPitch));
}

void enterConfused() {
  // Head turns slightly left (-10°); left ear forward (0), right ear back (70) — asymmetry signals confusion
  smoothMoveAsym(0, 70, YAW_CENTER - 10, basePitch - 3, SPEED_MEDIUM);
}

void enterListen() {
  // Head turns right 15°; ears fully forward (0); slight head raise for attentive posture
  smoothMoveAsym(0, 0, YAW_CENTER + 15, basePitch - 2, SPEED_MEDIUM);
}

// ─── Settle: return to the current sustained emotion posture after a reflex ─
// Skips the full enter animation; just smoothly moves to the target position.
void settleToEmotion() {
  // Look up colour from currentEmotion string directly — do not trust curR/G/B (may be polluted by reflex)
  int r = 255, g = 245, b = 224;   // 默认 relaxed 暖白
  if      (!strcmp(currentEmotion, "focus"))    { r=0;   g=0;   b=200; }
  else if (!strcmp(currentEmotion, "tired"))    { r=120; g=70;  b=0;   }
  else if (!strcmp(currentEmotion, "curious"))  { r=0;   g=200; b=200; }
  else if (!strcmp(currentEmotion, "happy"))    { r=255; g=165; b=0;   }
  else if (!strcmp(currentEmotion, "listen"))   { r=0;   g=180; b=80;  }
  else if (!strcmp(currentEmotion, "confused")) { r=120; g=0;   b=180; }
  setLight(r, g, b);
  curR = r; curG = g; curB = b;  // Keep in sync

  if      (!strcmp(currentEmotion, "curious"))  smoothMoveAsym(40, 40, YAW_CENTER - 15, basePitch - 5, SPEED_MEDIUM);
  else if (!strcmp(currentEmotion, "happy"))    smoothMove(0, YAW_CENTER, basePitch, SPEED_MEDIUM);
  else if (!strcmp(currentEmotion, "focus"))    smoothMove(90, YAW_CENTER, basePitch, SPEED_SLOW);
  else if (!strcmp(currentEmotion, "tired"))    smoothMove(110, YAW_CENTER, basePitch + 15, SPEED_SLOW);
  else if (!strcmp(currentEmotion, "confused")) smoothMoveAsym(0, 70, YAW_CENTER - 10, basePitch - 3, SPEED_MEDIUM);
  else if (!strcmp(currentEmotion, "listen"))   smoothMoveAsym(0, 0, YAW_CENTER + 15, basePitch - 2, SPEED_MEDIUM);
  else                                          smoothMove(0, YAW_CENTER, basePitch, SPEED_MEDIUM); // relaxed
}

// ─── Idle animations (small amplitude, slow and natural) ────────────────

void idleRelaxed() {
  // Gentle breathing feel + subtle ear micro-motion
  int dy = random(-2, 3);
  int dp = random(-1, 2);
  int de = random(0, 7);   // Ear micro-motion 0°–6°
  smoothMove(
    clampEar(de),
    clampYaw(YAW_CENTER + dy),
    clampPitch(basePitch + dp),
    1200
  );
}

void idleCurious() {
  // Small left/right drift around current yaw (±3°)
  int newYaw = clampYaw(curYaw + random(-3, 4));
  int startY = curYaw, steps = 50;  // More steps = slower, more natural
  for (int i = 1; i <= steps; i++) {
    headYaw.write(clampYaw(startY + (int)((newYaw-startY)*sineEaseOut((float)i/steps))));
    delay(18);
  }
  curYaw = newYaw;
}

void idleHappy() {
  // Gentle ear flap (8° only — a light, subtle flutter)
  earLeft.write(leftEarPhysical(0));  earRight.write(0);  delay(100);
  earLeft.write(leftEarPhysical(8));  earRight.write(8);  delay(150);
  earLeft.write(leftEarPhysical(0));  earRight.write(0);  delay(100);
}

void idleFocus() {
  // Very subtle pitch breathing ±1°
  int tp = clampPitch(curPitch + random(-1, 2));
  int sp = curPitch, steps = 60;  // More steps = even slower
  for (int i = 1; i <= steps; i++) {
    headPitch.write(clampPitch(sp + (int)((tp-sp)*sineEaseOut((float)i/steps))));
    delay(18);
  }
  curPitch = tp;
}

void idleTired() {
  // Subtle droop (+1° only) — a light sigh
  int sinkP = clampPitch(curPitch + 1);
  headPitch.write(sinkP); delay(600);
  headPitch.write(clampPitch(curPitch)); delay(300);
}

void idleConfused() {
  // Left ear folds back 20°; right ear opens forward 20° — opposing directions for visible asymmetry
  int steps = 35;
  for (int i = 1; i <= steps; i++) {
    float e = sineEaseOut((float)i / steps);
    // Left ear: fold back 20° from curEarL (=0)
    earLeft.write(leftEarPhysical((int)(curEarL + 20 * e)));
    // Right ear: open forward 20° from curEarR (=70; lower value = more forward)
    earRight.write(clampEar((int)(curEarR - 20 * e)));
    delay(18);
  }
  delay(250);
  for (int i = steps; i >= 0; i--) {
    float e = sineEaseOut((float)i / steps);
    earLeft.write(leftEarPhysical((int)(curEarL + 20 * e)));
    earRight.write(clampEar((int)(curEarR - 20 * e)));
    delay(18);
  }
  // curEarL/R unchanged — animation returns to original positions
}

void idleListen() {
  // Small head drift (±3°) — slower and more natural
  int newYaw = clampYaw(curYaw + random(-3, 4));
  int startY = curYaw, steps = 50;
  for (int i = 1; i <= steps; i++) {
    headYaw.write(clampYaw(startY + (int)((newYaw-startY)*sineEaseOut((float)i/steps))));
    delay(18);
  }
  curYaw = newYaw;
}

void playIdleForCurrentEmotion() {
  busyMoving = true;
  if      (!strcmp(currentEmotion, "relaxed"))  idleRelaxed();
  else if (!strcmp(currentEmotion, "curious"))  idleCurious();
  else if (!strcmp(currentEmotion, "happy"))    idleHappy();
  else if (!strcmp(currentEmotion, "focus"))    idleFocus();
  else if (!strcmp(currentEmotion, "tired"))    idleTired();
  else if (!strcmp(currentEmotion, "confused")) idleConfused();
  else if (!strcmp(currentEmotion, "listen"))   idleListen();
  else idleRelaxed();
  busyMoving = false;
}

// ─── Reflex animations ───────────────────────────────────────────────────
void animAlert(int r, int g, int b) {
  busyMoving = true;
  // Save pre-reflex position so we can restore it precisely afterwards
  int savedEarL = curEarL, savedEarR = curEarR;
  int savedYaw = curYaw, savedPitch = curPitch;
  int savedR = curR, savedG = curG, savedB = curB;

  earLeft.write(leftEarPhysical(0)); earRight.write(0);
  headPitch.write(clampPitch(basePitch - 5));
  setLight(r, g, b);
  // Scan: current → left (20°) → right (100°) → back to centre
  for (int y = savedYaw; y >= 20; y -= 3)    { headYaw.write(y); delay(12); }
  delay(200);
  for (int y = 20; y <= 100; y += 3)         { headYaw.write(y); delay(12); }
  delay(200);
  for (int y = 100; y >= YAW_CENTER; y -= 2) { headYaw.write(y); delay(10); }
  curYaw = YAW_CENTER; curPitch = clampPitch(basePitch - 5);
  delay(400);
  // Restore the original emotion colour before settling — otherwise setLight reads the reflex colour
  curR = savedR; curG = savedG; curB = savedB;
  settleToEmotion();
  busyMoving = false;
}

void animShy(int r, int g, int b) {
  busyMoving = true;
  int savedR = curR, savedG = curG, savedB = curB;
  setLight(255, 0, 0);  // 强制正红
  smoothMove(100, YAW_CENTER + 30, clampPitch(basePitch + 10), SPEED_FAST);
  delay(1200);
  // 先恢复原来的情绪颜色，再 settle
  curR = savedR; curG = savedG; curB = savedB;
  settleToEmotion();
  busyMoving = false;
}

// ─── Command processing ──────────────────────────────────────────────────
void processCommand(const char* json) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) {
    Serial.print("JSON_ERR:"); Serial.println(err.c_str()); return;
  }

  const char* type = doc["type"];

  if (!strcmp(type, "emotion")) {
    const char* name = doc["name"] | "unknown";
    int r = doc["r"]|255, g = doc["g"]|245, b = doc["b"]|224;
    // Do not reset to neutral — keep current position as the start of the next animation
    // curEar/curYaw/curPitch are preserved; enter functions interpolate continuously from here

    strncpy(currentEmotion, name, sizeof(currentEmotion)-1);
    Serial.print("EMOTION:"); Serial.println(name);
    setLight(r, g, b);

    busyMoving = true;
    if      (!strcmp(name, "curious"))  enterCurious();
    else if (!strcmp(name, "happy"))    enterHappy();
    else if (!strcmp(name, "focus"))    enterFocus();
    else if (!strcmp(name, "tired"))    enterTired();
    else if (!strcmp(name, "confused")) enterConfused();
    else if (!strcmp(name, "listen"))   enterListen();
    else                                enterRelaxed();
    busyMoving = false;

  } else if (!strcmp(type, "track")) {
    if (!busyMoving) {
      if (!strcmp(currentEmotion, "listen") || !strcmp(currentEmotion, "curious")) {
        // Mirror tracking: face left → head turns right
        // face_x: 0=left, 1=right → mirrored: 0=right, 1=left
        // Head range: CENTER ±20°, offset per emotion
        float fx = doc["face_x"].as<float>();
        float mirrored = 1.0f - fx;
        int yaw;
        if (!strcmp(currentEmotion, "listen")) {
          // Listen tracking centre: YAW_CENTER + 15, range ±20°
          yaw = clampYaw((int)(YAW_CENTER + 15 + (mirrored - 0.5f) * 40));
        } else {
          // Curious tracking centre: YAW_CENTER - 10, range ±20°
          yaw = clampYaw((int)(YAW_CENTER - 10 + (mirrored - 0.5f) * 40));
        }
        headYaw.write(yaw); curYaw = yaw;
      }
    }

  } else if (!strcmp(type, "reflex")) {
    const char* name = doc["name"] | "";
    int r = doc["r"]|0, g = doc["g"]|255, b = doc["b"]|255;
    if      (!strcmp(name, "alert")) animAlert(r, g, b);
    else if (!strcmp(name, "shy"))   animShy(r, g, b);

  } else if (!strcmp(type, "idle")) {
    playIdleForCurrentEmotion();

  } else if (!strcmp(type, "calibrate")) {
    if (doc.containsKey("base_pitch")) basePitch = doc["base_pitch"];
    if (doc.containsKey("min_pitch"))  pitchMin  = doc["min_pitch"];
    if (doc.containsKey("max_pitch"))  pitchMax  = doc["max_pitch"];
    busyMoving = true;
    smoothMove(curEar, curYaw, basePitch, SPEED_FAST);
    busyMoving = false;
    Serial.print("CALIB: base="); Serial.print(basePitch);
    Serial.print(" ["); Serial.print(pitchMin); Serial.print(",");
    Serial.print(pitchMax); Serial.println("]");
  }

  Serial.println("OK");
}

// ─── Setup ───────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  earLeft.attach(PIN_EAR_LEFT);
  earRight.attach(PIN_EAR_RIGHT);
  headYaw.attach(PIN_HEAD_YAW);
  headPitch.attach(PIN_HEAD_PITCH);
  FastLED.addLeds<WS2812B, PIN_LED, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(LED_BRIGHTNESS);

  curPitch = basePitch;
  earLeft.write(leftEarPhysical(0));
  earRight.write(0);
  headYaw.write(YAW_CENTER);
  headPitch.write(basePitch);
  delay(1500);
  smoothMove(0, YAW_CENTER, basePitch, 2000);
  setLight(255, 245, 224);
  Serial.println("ANIMA ready");
}

// ─── Loop ────────────────────────────────────────────────────────────────
void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      inputBuffer[bufferIndex] = '\0';
      processCommand(inputBuffer);
      bufferIndex = 0;
    } else if (bufferIndex < BUFFER_SIZE - 1) {
      inputBuffer[bufferIndex++] = c;
    }
  }
}