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
int basePitch = 25 ;   // 水平中立

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

// ─── 工具 ────────────────────────────────────────────────────
int leftEarPhysical(int l) { return constrain(EAR_L_NEUTRAL - l, 0, 180); }
int clampYaw(int v)        { return constrain(v, YAW_MIN, YAW_MAX); }
int clampPitch(int v)      { return constrain(v, pitchMin, pitchMax); }
int clampEar(int v)        { return constrain(v, EAR_MIN, EAR_MAX); }

// 统一写入（对称耳朵）
void writeAll(int ear, int yaw, int pitch) {
  earLeft.write(leftEarPhysical(ear));
  earRight.write(clampEar(ear));
  headYaw.write(clampYaw(yaw));
  headPitch.write(clampPitch(pitch));
  curEarL = ear; curEarR = ear;
}

// 独立写入左右耳
void writeAllAsym(int eL, int eR, int yaw, int pitch) {
  earLeft.write(leftEarPhysical(eL));
  earRight.write(clampEar(eR));
  headYaw.write(clampYaw(yaw));
  headPitch.write(clampPitch(pitch));
  curEarL = eL; curEarR = eR;
}

float sineEaseOut(float t) { return sin(t * (PI / 2.0)); }

// 对称耳朵平滑运动（从当前位置连续插值，不强制回中立）
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

// 不对称耳朵平滑运动（左右耳独立目标，从当前位置连续插值）
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

// ─── 情绪进入动画（基于校准坐标系）──────────────────────────

void enterRelaxed() {
  smoothMove(0, YAW_CENTER, basePitch, SPEED_SLOW);
}

void enterCurious() {
  // 耳朵在转头时明显往后折 55°，再远头的扫视动作
  smoothMoveAsym(55, 55, YAW_CENTER - 25, basePitch - 5, SPEED_MEDIUM); // 耳朵明显后折 + 左转
  delay(180);
  smoothMoveAsym(55, 55, YAW_CENTER + 20, basePitch - 5, SPEED_MEDIUM); // 耳朵保持后折 + 右转
  delay(150);
  smoothMoveAsym(40, 40, YAW_CENTER - 15, basePitch - 5, SPEED_MEDIUM); // 安定在左偄，耳朵出40°
}

void enterHappy() {
  // 直接从当前位置做耳朵快速扇动，头在 CENTER ±8° 摆动
  // （去掉了之前的预先平滑到中立位的动作，不再有多一个和生涩）
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
  // 耳朵极缓慢折后 90°（VERY_SLOW），头部锁在中心，从当前位置连续过渡
  smoothMove(90, YAW_CENTER, basePitch, SPEED_VERY_SLOW);
}

void enterTired() {
  // 头和耳朵一起缓慢往下，全程 VERY_SLOW，像疲惫地沉下去
  smoothMove(110, YAW_CENTER, basePitch + 15, SPEED_VERY_SLOW);
  delay(400);
  // 叹气微动：再沉 2°
  headPitch.write(clampPitch(curPitch + 2)); delay(800);
  headPitch.write(clampPitch(curPitch));
}

void enterConfused() {
  // 头微微左转（-10°，表达迷惑/思考）
  // 左耳朝前展开（ear=0），右耳往后折（ear=70）——不对称表示迷惑
  smoothMoveAsym(0, 70, YAW_CENTER - 10, basePitch - 3, SPEED_MEDIUM);
}

void enterListen() {
  // 头转向右 15°，耳朵微微挥起朝前（ear 目标为 0，已是最朝前）
  // 头跟微抬起一点表示专注，如或 pitch -2
  smoothMoveAsym(0, 0, YAW_CENTER + 15, basePitch - 2, SPEED_MEDIUM);
}

// ─── 情绪子定位：反射结束后返回当前持续情绪的最终姿态 ────
// 不做全部入场动画，只做平滑进入目标位置
void settleToEmotion() {
  setLight(curR, curG, curB);
  if      (!strcmp(currentEmotion, "curious"))  smoothMoveAsym(40, 40, YAW_CENTER - 15, basePitch - 5, SPEED_MEDIUM);
  else if (!strcmp(currentEmotion, "happy"))    smoothMove(0, YAW_CENTER, basePitch, SPEED_MEDIUM);
  else if (!strcmp(currentEmotion, "focus"))    smoothMove(90, YAW_CENTER, basePitch, SPEED_SLOW);
  else if (!strcmp(currentEmotion, "tired"))    smoothMove(110, YAW_CENTER, basePitch + 15, SPEED_SLOW);
  else if (!strcmp(currentEmotion, "confused")) smoothMoveAsym(0, 70, YAW_CENTER - 10, basePitch - 3, SPEED_MEDIUM);
  else if (!strcmp(currentEmotion, "listen"))   smoothMoveAsym(0, 0, YAW_CENTER + 15, basePitch - 2, SPEED_MEDIUM);
  else                                          smoothMove(0, YAW_CENTER, basePitch, SPEED_MEDIUM); // relaxed
}

// ─── Idle 动作（幇轻微小幅度，更慢更自然）──────────────

void idleRelaxed() {
  // 小幅度呼吸感 + 耳朵轻微抗动
  int dy = random(-2, 3);
  int dp = random(-1, 2);
  int de = random(0, 7);   // 耳朵微当 0°~6°微动
  smoothMove(
    clampEar(de),
    clampYaw(YAW_CENTER + dy),
    clampPitch(basePitch + dp),
    1200
  );
}

void idleCurious() {
  // 在当前中心小幅度左右微动（±3°）
  int newYaw = clampYaw(curYaw + random(-3, 4));
  int startY = curYaw, steps = 50;  // 加长 steps 使动作更缓
  for (int i = 1; i <= steps; i++) {
    headYaw.write(clampYaw(startY + (int)((newYaw-startY)*sineEaseOut((float)i/steps))));
    delay(18);
  }
  curYaw = newYaw;
}

void idleHappy() {
  // 耳朵轻微一抟（只动 8°，幗轻轻的一下）
  earLeft.write(leftEarPhysical(0));  earRight.write(0);  delay(100);
  earLeft.write(leftEarPhysical(8));  earRight.write(8);  delay(150);
  earLeft.write(leftEarPhysical(0));  earRight.write(0);  delay(100);
}

void idleFocus() {
  // 非常细微的呼吸 Pitch ±1°
  int tp = clampPitch(curPitch + random(-1, 2));
  int sp = curPitch, steps = 60;  // 连续更慢
  for (int i = 1; i <= steps; i++) {
    headPitch.write(clampPitch(sp + (int)((tp-sp)*sineEaseOut((float)i/steps))));
    delay(18);
  }
  curPitch = tp;
}

void idleTired() {
  // 微微沉一下（只沉 1°，更轻微的叹气感）
  int sinkP = clampPitch(curPitch + 1);
  headPitch.write(sinkP); delay(600);
  headPitch.write(clampPitch(curPitch)); delay(300);
}

void idleConfused() {
  // 左耳明显往后折 20°，右耳明显往前 20°（相反方向，确保肢体都能看到变化）
  int steps = 35;
  for (int i = 1; i <= steps; i++) {
    float e = sineEaseOut((float)i / steps);
    // 左耳：从当前 curEarL(=0) 往后折 20°
    earLeft.write(leftEarPhysical((int)(curEarL + 20 * e)));
    // 右耳：从当前 curEarR(=70) 往前 20°（数字减小=朝前）
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
  // 保持 curEarL/R 不变（張弝回原始位置）
}

void idleListen() {
  // 在当前中心小幅度微动（±3°），动作更缓
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

// ─── 反射 ────────────────────────────────────────────────────
void animAlert(int r, int g, int b) {
  busyMoving = true;
  // 保存反射前的情绪位置，反射结束后精确恢复
  int savedEarL = curEarL, savedEarR = curEarR;
  int savedYaw = curYaw, savedPitch = curPitch;
  int savedR = curR, savedG = curG, savedB = curB;

  earLeft.write(leftEarPhysical(0)); earRight.write(0);
  headPitch.write(clampPitch(basePitch - 5));
  setLight(r, g, b);
  // 扫描：当前位置→左(20°)→右(100°)→回 CENTER
  for (int y = savedYaw; y >= 20; y -= 3)  { headYaw.write(y); delay(12); }
  delay(200);
  for (int y = 20; y <= 100; y += 3)       { headYaw.write(y); delay(12); }
  delay(200);
  for (int y = 100; y >= YAW_CENTER; y -= 2) { headYaw.write(y); delay(10); }
  curYaw = YAW_CENTER; curPitch = clampPitch(basePitch - 5);
  delay(400);
  // 反射结束——不管之前是什么情绪（包括 shy 等其他反射），都回到当前持续情绪
  settleToEmotion();
  busyMoving = false;
}

void animShy(int r, int g, int b) {
  busyMoving = true;
  int savedR = curR, savedG = curG, savedB = curB;
  setLight(255, 0, 0);  // 强制正红
  smoothMove(100, YAW_CENTER + 30, clampPitch(basePitch + 10), SPEED_FAST);
  delay(1200);
  // 不管之前是什么情绪（包括另一个反射），都回到当前持续情绪的安定位置
  settleToEmotion();
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
    // 不强制回到中立位，保留当前位置作为下一段动画的起点
    // curEar/curYaw/curPitch 保持不变，enter 函数从这里连续过渡

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
        // Listen：镜像追踪——人脸偏左，头转右（镜像）
        // face_x: 0=左, 1=右 → 镜像后: 0=右, 1=左
        // 头部范围：CENTER ± 30°（30°~90°），Curious/Listen 各自已有偏移
        float fx = doc["face_x"].as<float>();
        float mirrored = 1.0f - fx;  // 镜像
        int yaw;
        if (!strcmp(currentEmotion, "listen")) {
          // Listen 的追踪中心在 YAW_CENTER + 15，镜像范围 ±20°
          yaw = clampYaw((int)(YAW_CENTER + 15 + (mirrored - 0.5f) * 40));
        } else {
          // Curious 的追踪中心在 YAW_CENTER - 10，镜像范围 ±20°
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