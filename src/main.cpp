#include <Arduino.h>
#include <Servo.h>
#include <ArduinoJson.h>
#include <FastLED.h>

#define PIN_EAR_LEFT   3
#define PIN_EAR_RIGHT  5
#define PIN_HEAD_YAW   9
#define PIN_HEAD_PITCH 10
#define PIN_LED        6
#define NUM_LEDS       12
#define LED_BRIGHTNESS 100

// ─── 校准后的物理限制（2026-05-01）────────────────────────────
// Yaw:   60° = 正前方，0-180° 全范围
// Pitch: 20° = 水平中立，0-40° 是物理极限（±20°）
// 右耳:  0° = 朝前，数字越大越往后折
// 左耳:  物理角度 = EAR_L_NEUTRAL(90) - 逻辑角度
#define EAR_MIN        0
#define EAR_MAX        150
#define YAW_MIN        0
#define YAW_MAX        180
#define YAW_CENTER     60    // 正前方
#define EAR_L_NEUTRAL  90

int pitchMin  = 0;    // 抬头极限
int pitchMax  = 40;   // 低头极限
int basePitch = 20;   // 水平中立

#define SPEED_FAST       600
#define SPEED_MEDIUM    1500
#define SPEED_SLOW      3000
#define SPEED_VERY_SLOW 5000

Servo earLeft, earRight, headYaw, headPitch;
CRGB leds[NUM_LEDS];

int curEar = 0, curYaw = YAW_CENTER, curPitch = 0;
int curR = 255, curG = 245, curB = 224;
char currentEmotion[20] = "relaxed";
bool busyMoving = false;

const int BUFFER_SIZE = 512;
char inputBuffer[BUFFER_SIZE];
int  bufferIndex = 0;

// ─── 工具 ────────────────────────────────────────────────────
int leftEarPhysical(int l) { return constrain(EAR_L_NEUTRAL - l, 0, 180); }
int clampYaw(int v)        { return constrain(v, YAW_MIN, YAW_MAX); }
int clampPitch(int v)      { return constrain(v, pitchMin, pitchMax); }
int clampEar(int v)        { return constrain(v, EAR_MIN, EAR_MAX); }

void writeAll(int ear, int yaw, int pitch) {
  earLeft.write(leftEarPhysical(ear));
  earRight.write(clampEar(ear));
  headYaw.write(clampYaw(yaw));
  headPitch.write(clampPitch(pitch));
}

float sineEaseOut(float t) { return sin(t * (PI / 2.0)); }

void smoothMove(int tE, int tY, int tP, int dMs) {
  tE = clampEar(tE); tY = clampYaw(tY); tP = clampPitch(tP);
  int sE = curEar, sY = curYaw, sP = curPitch;
  int steps = max(1, dMs / 16);
  for (int i = 1; i <= steps; i++) {
    float e = sineEaseOut((float)i / steps);
    earLeft.write(leftEarPhysical(sE + (int)((tE-sE)*e)));
    earRight.write(clampEar(sE + (int)((tE-sE)*e)));
    headYaw.write(clampYaw(sY + (int)((tY-sY)*e)));
    headPitch.write(clampPitch(sP + (int)((tP-sP)*e)));
    delay(16);
  }
  curEar = tE; curYaw = tY; curPitch = tP;
  writeAll(curEar, curYaw, curPitch);
}

void setLight(int r, int g, int b) {
  fill_solid(leds, NUM_LEDS, CRGB(r, g, b));
  FastLED.show();
  curR = r; curG = g; curB = b;
}

// ─── 情绪进入动画（基于校准坐标系）──────────────────────────

void enterRelaxed() {
  smoothMove(0, YAW_CENTER, basePitch, SPEED_SLOW);
}

void enterCurious() {
  // 侧转向左（YAW_CENTER - 15 = 45°），微微抬头（basePitch - 5 = 15°）
  smoothMove(0, 45, basePitch - 5, SPEED_FAST);
}

void enterHappy() {
  // 耳朵快速扇动 3 次，头部在 CENTER ±8°（52°↔68°）内摆动
  for (int i = 0; i < 3; i++) {
    earLeft.write(leftEarPhysical(0));  earRight.write(0);
    headYaw.write(clampYaw(YAW_CENTER - 8)); delay(130);  // 52°
    earLeft.write(leftEarPhysical(30)); earRight.write(30);
    headYaw.write(clampYaw(YAW_CENTER + 8)); delay(130);  // 68°
  }
  earLeft.write(leftEarPhysical(0)); earRight.write(0);
  headYaw.write(YAW_CENTER);
  curEar = 0; curYaw = YAW_CENTER; curPitch = basePitch;
}

void enterFocus() {
  // 耳朵缓慢折后 90°，头部锁在中心
  smoothMove(90, YAW_CENTER, basePitch, SPEED_VERY_SLOW);
}

void enterTired() {
  // 耳朵大幅折后 110°，低头到接近极限（basePitch + 15 = 35°）
  smoothMove(110, YAW_CENTER, basePitch + 15, SPEED_VERY_SLOW);
  delay(400);
  // 叹气微动：再沉 2°，但不超过极限
  headPitch.write(clampPitch(curPitch + 2)); delay(600);
  headPitch.write(clampPitch(curPitch));
}

void enterConfused() {
  // 先到中位，然后左耳单独折后 80°（右耳保持 0°=朝前），微抬头
  smoothMove(0, YAW_CENTER, basePitch - 5, SPEED_MEDIUM);
  delay(150);
  for (int i = 0; i <= 80; i += 3) {
    earLeft.write(leftEarPhysical(i)); delay(12);
  }
  curEar = 40;
}

void enterListen() {
  smoothMove(0, YAW_CENTER, basePitch, SPEED_MEDIUM);
}

// ─── Idle 动作（≤800ms，pitch 范围极小只有 ±3-5°）────────────

void idleRelaxed() {
  // Yaw ±4°（56-64°），Pitch ±2°（18-22°，在 0-40 范围内安全）
  int dy = random(-4, 5);
  int dp = random(-2, 3);
  smoothMove(
    clampEar(random(-2, 3)),
    clampYaw(YAW_CENTER + dy),
    clampPitch(basePitch + dp),
    800
  );
}

void idleCurious() {
  // 在 45° 侧头基础上 ±4°（41-49°）
  int newYaw = clampYaw(45 + random(-4, 5));
  int startY = curYaw, steps = 30;
  for (int i = 1; i <= steps; i++) {
    headYaw.write(clampYaw(startY + (int)((newYaw-startY)*sineEaseOut((float)i/steps))));
    delay(16);
  }
  curYaw = newYaw;
}

void idleHappy() {
  earLeft.write(leftEarPhysical(0));  earRight.write(0);  delay(80);
  earLeft.write(leftEarPhysical(25)); earRight.write(25); delay(100);
  earLeft.write(leftEarPhysical(0));  earRight.write(0);  delay(80);
}

void idleFocus() {
  // Pitch ±1°，在 0-40 范围内极细微
  int tp = clampPitch(basePitch + random(-1, 2));
  int sp = curPitch, steps = 40;
  for (int i = 1; i <= steps; i++) {
    headPitch.write(clampPitch(sp + (int)((tp-sp)*sineEaseOut((float)i/steps))));
    delay(16);
  }
  curPitch = tp;
}

void idleTired() {
  // 微沉 2°（受限于 pitchMax=40，所以如果已经是 35° 就只能再沉 2° 到 37°）
  int sinkP = clampPitch(curPitch + 2);
  headPitch.write(sinkP); delay(500);
  headPitch.write(clampPitch(curPitch)); delay(200);
}

void idleConfused() {
  for (int i = 0; i <= 12; i += 4) { earRight.write(i); delay(25); }
  delay(150);
  for (int i = 12; i >= 0; i -= 4) { earRight.write(i); delay(25); }
}

void idleListen() {
  int newYaw = clampYaw(YAW_CENTER + random(-4, 5));
  int startY = curYaw, steps = 30;
  for (int i = 1; i <= steps; i++) {
    headYaw.write(clampYaw(startY + (int)((newYaw-startY)*sineEaseOut((float)i/steps))));
    delay(16);
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

// ─── 反射 ────────────────────────────────────────────────────
void animAlert(int r, int g, int b) {
  busyMoving = true;
  earLeft.write(leftEarPhysical(0)); earRight.write(0);
  headPitch.write(clampPitch(basePitch - 5));  // 微抬头（15°）
  setLight(r, g, b);
  // 扫描：CENTER→左(20°)→右(100°)→回CENTER(60°)
  for (int y = curYaw; y >= 20; y -= 3)  { headYaw.write(y); delay(12); }
  delay(200);
  for (int y = 20; y <= 100; y += 3)     { headYaw.write(y); delay(12); }
  delay(200);
  for (int y = 100; y >= YAW_CENTER; y -= 2) { headYaw.write(y); delay(10); }
  curYaw = YAW_CENTER; curPitch = clampPitch(basePitch - 5);
  delay(400);
  writeAll(curEar, curYaw, curPitch);
  setLight(curR, curG, curB);
  busyMoving = false;
}

void animShy(int r, int g, int b) {
  busyMoving = true;
  setLight(r, g, b);
  for (int i = 0; i <= 100; i += 4) {
    earLeft.write(leftEarPhysical(i)); earRight.write(i); delay(8);
  }
  // 头转开（向右，YAW_CENTER + 30 = 90°）并低头（basePitch + 10 = 30°）
  smoothMove(100, YAW_CENTER + 30, clampPitch(basePitch + 10), SPEED_FAST);
  delay(1000);
  writeAll(curEar, curYaw, curPitch);
  setLight(curR, curG, curB);
  busyMoving = false;
}

// ─── 命令处理 ─────────────────────────────────────────────────
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
    if (doc.containsKey("ear"))   curEar   = doc["ear"];
    if (doc.containsKey("yaw"))   curYaw   = doc["yaw"];
    if (doc.containsKey("pitch")) curPitch = doc["pitch"];

    earLeft.write(leftEarPhysical(0)); earRight.write(0); delay(150);

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
        // face_x 0-1 → Yaw 20-100°（CENTER ±40°）
        int yaw = clampYaw(20 + (int)(doc["face_x"].as<float>() * 80));
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

// ─── Setup ───────────────────────────────────────────────────
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

// ─── Loop ────────────────────────────────────────────────────
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