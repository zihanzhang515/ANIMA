/*
 * src/main.cpp — ANIMA v3（情绪持续 + 情绪专属 Idle）
 * -----------------------------------------------
 * 设计逻辑：
 *   1. 每个情绪动画只做"进入动作"，结束后停在目标位置
 *   2. 不自动回归 Relaxed，等 Python 场景判断发新情绪才切换
 *   3. idle 命令根据当前情绪做该情绪范围内的微动
 *      → 用户感知到 ANIMA 一直"在"这个情绪里
 *
 * 情绪专属 Idle 设计：
 *   Relaxed  → 头部漂移 ±5°，耳朵微抖
 *   Curious  → 轻微重新定位侧头
 *   Happy    → 耳朵小幅扇动一次
 *   Focus    → 几乎静止，偶尔 Pitch ±1° 微动
 *   Tired    → 头部缓慢再沉一点，然后微微回弹
 *   Confused → 右耳轻微颤动
 *   Listen   → 轻微调整朝向（等待感）
 *
 * 校准坐标系：
 *   耳朵：0°=朝前(Relaxed)，数字越大越往后折
 *   左耳物理 = EAR_L_NEUTRAL - 逻辑角度
 *   Yaw：60°=正前方，<60°向左，>60°向右
 *   Pitch：25°=水平，范围 10-40°（硬限制）
 */

#include <Arduino.h>
#include <Servo.h>
#include <ArduinoJson.h>
#include <FastLED.h>

// ─── 引脚 ───────────────────────────────────────────────────
#define PIN_EAR_LEFT   3
#define PIN_EAR_RIGHT  5
#define PIN_HEAD_YAW   9
#define PIN_HEAD_PITCH 10
#define PIN_LED        6

// ─── LED ────────────────────────────────────────────────────
#define NUM_LEDS       12
#define LED_BRIGHTNESS 100

// ─── 安全范围 ────────────────────────────────────────────────
#define EAR_MIN    0
#define EAR_MAX    150
#define YAW_MIN    20
#define YAW_MAX    110
#define PITCH_MIN  10
#define PITCH_MAX  40

// ─── 左耳镜像 ────────────────────────────────────────────────
#define EAR_L_NEUTRAL 90

// ─── 速度常量 ────────────────────────────────────────────────
#define SPEED_SNAP       150
#define SPEED_FAST       600
#define SPEED_MEDIUM    1500
#define SPEED_SLOW      3000
#define SPEED_VERY_SLOW 5000

// ─── 舵机 + LED ────────────────────────────────────────────
Servo earLeft, earRight, headYaw, headPitch;
CRGB leds[NUM_LEDS];

// ─── 当前状态 ───────────────────────────────────────────────
int curEar = 0, curYaw = 60, curPitch = 25;
int curR = 255, curG = 245, curB = 224;
char currentEmotion[20] = "relaxed";  // 记录当前情绪名

// ─── 串口缓冲 ───────────────────────────────────────────────
const int BUFFER_SIZE = 256;
char inputBuffer[BUFFER_SIZE];
int  bufferIndex = 0;

// ─── 工具函数 ───────────────────────────────────────────────

int leftEarPhysical(int logical) {
  return constrain(EAR_L_NEUTRAL - logical, 0, 180);
}
int clampYaw(int v)   { return constrain(v, YAW_MIN, YAW_MAX); }
int clampPitch(int v) { return constrain(v, PITCH_MIN, PITCH_MAX); }
int clampEar(int v)   { return constrain(v, EAR_MIN, EAR_MAX); }

void writeAll(int ear, int yaw, int pitch) {
  earLeft.write(leftEarPhysical(ear));
  earRight.write(clampEar(ear));
  headYaw.write(clampYaw(yaw));
  headPitch.write(clampPitch(pitch));
}

float sineEaseOut(float t) { return sin(t * PI / 2.0); }

void smoothMove(int tEar, int tYaw, int tPitch, int durationMs) {
  tEar   = clampEar(tEar);
  tYaw   = clampYaw(tYaw);
  tPitch = clampPitch(tPitch);

  int sE = curEar, sY = curYaw, sP = curPitch;
  int steps = max(1, durationMs / 16);

  for (int i = 1; i <= steps; i++) {
    float ease = sineEaseOut((float)i / steps);
    earLeft.write(leftEarPhysical(sE + (int)((tEar - sE) * ease)));
    earRight.write(clampEar(       sE + (int)((tEar - sE) * ease)));
    headYaw.write(clampYaw(        sY + (int)((tYaw - sY) * ease)));
    headPitch.write(clampPitch(    sP + (int)((tPitch - sP) * ease)));
    delay(16);
  }

  curEar = tEar; curYaw = tYaw; curPitch = tPitch;
  writeAll(curEar, curYaw, curPitch);
}

void setLight(int r, int g, int b) {
  fill_solid(leds, NUM_LEDS, CRGB(r, g, b));
  FastLED.show();
  curR = r; curG = g; curB = b;
}

// ─── 情绪进入动画（只做进入，不回归）──────────────────────

void enterRelaxed() {
  smoothMove(0, 60, 25, SPEED_SLOW);
}

void enterCurious() {
  // 快速侧头（听到什么的感觉）
  smoothMove(0, 35, 30, SPEED_FAST);  // Yaw 35° = 偏转 25°，更明显
}

void enterHappy() {
  for (int i = 0; i < 3; i++) {
    earLeft.write(leftEarPhysical(0));  earRight.write(0);
    headYaw.write(52); delay(150);
    earLeft.write(leftEarPhysical(35)); earRight.write(35);
    headYaw.write(68); delay(150);
  }
  // 停在 Happy 的目标位
  earLeft.write(leftEarPhysical(0)); earRight.write(0);
  headYaw.write(60);
  curEar = 0; curYaw = 60; curPitch = 25;
}

void enterFocus() {
  smoothMove(150, 60, 25, SPEED_VERY_SLOW);
}

void enterTired() {
  smoothMove(120, 60, 37, SPEED_VERY_SLOW);
  // 叹气微动
  delay(500);
  int sigh = clampPitch(curPitch + 2);
  headPitch.write(sigh); delay(800);
  headPitch.write(curPitch);
}

void enterConfused() {
  smoothMove(0, 60, 20, SPEED_MEDIUM);
  delay(200);
  // 右耳缓慢折到 150°
  for (int i = 0; i <= 150; i += 2) {
    earRight.write(i); delay(10);
  }
  curEar = 75;
}

void enterListen() {
  smoothMove(0, 60, 25, SPEED_MEDIUM);
}

// ─── 情绪专属 Idle（在当前情绪范围内微动）──────────────────

void idleRelaxed() {
  // 头部温和漂移 ±5°，耳朵微抖 ±5°
  int dy = random(-5, 6);
  int dp = random(-2, 3);
  int de = random(-4, 5);
  smoothMove(
    clampEar(0 + de),
    clampYaw(60 + dy),
    clampPitch(25 + dp),
    2000
  );
}

void idleCurious() {
  // 轻微重新定向，像在调整聆听角度
  int dy = random(-8, 9);  // 在侧头基础上小幅调整
  smoothMove(
    0,
    clampYaw(35 + dy),  // idle 在 35° 基础上微动
    clampPitch(30),
    1200
  );
}

void idleHappy() {
  // 耳朵小扇一次，然后回来
  earLeft.write(leftEarPhysical(25)); earRight.write(25);
  delay(200);
  earLeft.write(leftEarPhysical(0));  earRight.write(0);
  delay(200);
}

void idleFocus() {
  // 几乎静止，偶尔 Pitch ±1° 微动（像在呼吸）
  int dp = random(-1, 2);
  int tp = clampPitch(25 + dp);
  // 极缓慢
  int steps = 60;
  int startP = curPitch;
  for (int i = 1; i <= steps; i++) {
    float ease = sineEaseOut((float)i / steps);
    headPitch.write(clampPitch(startP + (int)((tp - startP) * ease)));
    delay(25);
  }
  curPitch = tp;
}

void idleTired() {
  // 头再慢慢沉一点，然后微微回弹
  int sinkTo = clampPitch(curPitch + 3);
  headPitch.write(sinkTo); delay(1200);
  headPitch.write(curPitch); delay(600);
}

void idleConfused() {
  // 右耳轻微颤动（2-3 次），左耳保持 0°
  for (int i = 0; i < 2; i++) {
    earRight.write(145); delay(150);
    earRight.write(155); delay(150);
  }
  earRight.write(150);
}

void idleListen() {
  // 轻微调整朝向，像在更仔细聆听
  int dy = random(-6, 7);
  int steps = 40;
  int startY = curYaw;
  int targetY = clampYaw(60 + dy);
  for (int i = 1; i <= steps; i++) {
    float ease = sineEaseOut((float)i / steps);
    headYaw.write(clampYaw(startY + (int)((targetY - startY) * ease)));
    delay(20);
  }
  curYaw = targetY;
}

// ─── Idle 调度（根据当前情绪选择对应的 idle）──────────────
void playIdleForCurrentEmotion() {
  if      (!strcmp(currentEmotion, "relaxed"))  idleRelaxed();
  else if (!strcmp(currentEmotion, "curious"))  idleCurious();
  else if (!strcmp(currentEmotion, "happy"))    idleHappy();
  else if (!strcmp(currentEmotion, "focus"))    idleFocus();
  else if (!strcmp(currentEmotion, "tired"))    idleTired();
  else if (!strcmp(currentEmotion, "confused")) idleConfused();
  else if (!strcmp(currentEmotion, "listen"))   idleListen();
  else                                           idleRelaxed();
}

// ─── Alert / Shy 反射 ───────────────────────────────────────

void animAlert(int r, int g, int b) {
  earLeft.write(leftEarPhysical(0));
  earRight.write(0);
  headPitch.write(clampPitch(22));
  setLight(r, g, b);
  headYaw.write(30); delay(250);  // 更大幅度，更慢
  headYaw.write(90); delay(250);  // 右转到 90°
  headYaw.write(60); delay(150);  // 回中
  curYaw = 60; curPitch = 22;
  // 反射结束回到当前情绪位置
  delay(500);
  writeAll(curEar, curYaw, curPitch);
  setLight(curR, curG, curB);
}

void animShy(int r, int g, int b) {
  setLight(r, g, b);
  for (int i = 0; i <= 100; i += 4) {
    earLeft.write(leftEarPhysical(i));
    earRight.write(i);
    delay(8);
  }
  smoothMove(100, 40, 35, SPEED_FAST);
  delay(1000);
  // 回到当前情绪
  writeAll(curEar, curYaw, curPitch);
  setLight(curR, curG, curB);
}

// ─── 命令处理 ───────────────────────────────────────────────
void processCommand(const char* json) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, json)) return;

  const char* type = doc["type"];

  if (!strcmp(type, "emotion")) {
    const char* name = doc["name"] | "relaxed";
    int r = doc["r"] | 255, g = doc["g"] | 245, b = doc["b"] | 224;

    // 存储当前情绪名
    strncpy(currentEmotion, name, sizeof(currentEmotion) - 1);
    // 广播当前情绪给 Dashboard
    Serial.print("EMOTION:"); Serial.println(name);
    setLight(r, g, b);

    if      (!strcmp(name, "curious"))  enterCurious();
    else if (!strcmp(name, "happy"))    enterHappy();
    else if (!strcmp(name, "focus"))    enterFocus();
    else if (!strcmp(name, "tired"))    enterTired();
    else if (!strcmp(name, "confused")) enterConfused();
    else if (!strcmp(name, "listen"))   enterListen();
    else                                enterRelaxed();

  } else if (!strcmp(type, "track")) {
    // 仅在 Relaxed / Listen / Curious 时追踪脸部
    if (!strcmp(currentEmotion, "relaxed") ||
        !strcmp(currentEmotion, "listen")  ||
        !strcmp(currentEmotion, "curious")) {
      int yaw = clampYaw(doc["yaw"] | 60);
      headYaw.write(yaw);
      curYaw = yaw;
    }

  } else if (!strcmp(type, "reflex")) {
    const char* name = doc["name"] | "";
    int r = doc["r"] | 0, g = doc["g"] | 255, b = doc["b"] | 255;
    if      (!strcmp(name, "alert")) animAlert(r, g, b);
    else if (!strcmp(name, "shy"))   animShy(r, g, b);

  } else if (!strcmp(type, "idle")) {
    // 情绪专属 Idle — Python 定时触发
    playIdleForCurrentEmotion();
  }

  Serial.println("OK");
}

// ─── Setup ─────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  earLeft.attach(PIN_EAR_LEFT);
  earRight.attach(PIN_EAR_RIGHT);
  headYaw.attach(PIN_HEAD_YAW);
  headPitch.attach(PIN_HEAD_PITCH);

  FastLED.addLeds<WS2812B, PIN_LED, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(LED_BRIGHTNESS);

  // 强制归零
  earLeft.write(leftEarPhysical(0));
  earRight.write(0);
  headYaw.write(60);
  headPitch.write(25);
  delay(1500);

  smoothMove(0, 60, 25, 2000);
  setLight(255, 245, 224);
  Serial.println("ANIMA ready");
}

// ─── Loop ──────────────────────────────────────────────────
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