/*
 * ANIMA 舵机校准代码 v2
 * ----------------------
 * 解决问题：
 * 1. 四个舵机分别独立校准，全范围 0-180°
 * 2. 耳朵镜像补偿（左右耳安装方向相反时自动换算）
 * 3. 记录每个舵机的真实中位偏移量
 *
 * 命令格式：
 *   l90        → 左耳直接发送 90°（原始值）
 *   r90        → 右耳直接发送 90°（原始值）
 *   y90        → Yaw 直接发送 90°
 *   p90        → Pitch 直接发送 90°
 *   mirror     → 切换右耳镜像模式（开/关）
 *   offset p5  → 设置 Pitch 偏移量（在所有指令基础上+5）
 *   s          → 所有舵机回各自的中位（考虑偏移）
 *   ?          → 打印当前所有状态
 *   raw        → 打印发送给每个舵机的实际原始角度
 */

#include <Arduino.h>
#include <Servo.h>

Servo earLeft, earRight, headYaw, headPitch;

#define PIN_EAR_LEFT   3
#define PIN_EAR_RIGHT  5
#define PIN_HEAD_YAW   9
#define PIN_HEAD_PITCH 10

// ── 逻辑中位（你期望的"中间"对应的逻辑值）──────────────
int neutral_l = 45;    // 左耳逻辑中位
int neutral_r = 45;    // 右耳逻辑中位（镜像前的值）
int neutral_y = 90;    // Yaw 中位
int neutral_p = 90;    // Pitch 中位

// ── 偏移量（安装误差补偿，加到实际发送值上）────────────
int offset_l = 0;
int offset_r = 0;
int offset_y = 0;
int offset_p = 0;

// ── 镜像模式（右耳安装相反时开启）───────────────────────
bool mirror_r = false;   // 右耳镜像：实际发送 = 180 - 逻辑值

// ── 当前逻辑角度 ─────────────────────────────────────────
int cur_l = 45, cur_r = 45, cur_y = 90, cur_p = 90;

// ── 实际发送给舵机的值 ───────────────────────────────────
int raw_l, raw_r, raw_y, raw_p;

int toRaw_L(int logical) { return constrain(logical + offset_l, 0, 180); }
int toRaw_R(int logical) {
  int v = mirror_r ? (180 - logical) : logical;
  return constrain(v + offset_r, 0, 180);
}
int toRaw_Y(int logical) { return constrain(logical + offset_y, 0, 180); }
int toRaw_P(int logical) { return constrain(logical + offset_p, 0, 180); }

void applyAll() {
  raw_l = toRaw_L(cur_l); earLeft.write(raw_l);
  raw_r = toRaw_R(cur_r); earRight.write(raw_r);
  raw_y = toRaw_Y(cur_y); headYaw.write(raw_y);
  raw_p = toRaw_P(cur_p); headPitch.write(raw_p);
}

void moveTo_L(int v) { cur_l = constrain(v, 0, 180); raw_l = toRaw_L(cur_l); earLeft.write(raw_l); }
void moveTo_R(int v) { cur_r = constrain(v, 0, 180); raw_r = toRaw_R(cur_r); earRight.write(raw_r); }
void moveTo_Y(int v) { cur_y = constrain(v, 0, 180); raw_y = toRaw_Y(cur_y); headYaw.write(raw_y); }
void moveTo_P(int v) { cur_p = constrain(v, 0, 180); raw_p = toRaw_P(cur_p); headPitch.write(raw_p); }

void printStatus() {
  Serial.println("─────────────────────────────────────");
  Serial.print("左耳  (Pin3)  逻辑:"); Serial.print(cur_l);
  Serial.print("° → 实际发送:"); Serial.print(raw_l); Serial.println("°");

  Serial.print("右耳  (Pin5)  逻辑:"); Serial.print(cur_r);
  Serial.print("° → 实际发送:"); Serial.print(raw_r);
  Serial.print("°"); if(mirror_r) Serial.print(" [镜像ON]"); Serial.println();

  Serial.print("Yaw   (Pin9)  逻辑:"); Serial.print(cur_y);
  Serial.print("° → 实际发送:"); Serial.print(raw_y); Serial.println("°");

  Serial.print("Pitch (Pin10) 逻辑:"); Serial.print(cur_p);
  Serial.print("° → 实际发送:"); Serial.print(raw_p); Serial.println("°");

  Serial.print("偏移量: l="); Serial.print(offset_l);
  Serial.print(" r="); Serial.print(offset_r);
  Serial.print(" y="); Serial.print(offset_y);
  Serial.print(" p="); Serial.println(offset_p);
  Serial.println("─────────────────────────────────────");
}

void setup() {
  Serial.begin(9600);
  earLeft.attach(PIN_EAR_LEFT);
  earRight.attach(PIN_EAR_RIGHT);
  headYaw.attach(PIN_HEAD_YAW);
  headPitch.attach(PIN_HEAD_PITCH);

  applyAll();
  delay(500);

  Serial.println("====== ANIMA 舵机校准 v2 ======");
  Serial.println("命令: l/r/y/p + 角度(0-180)");
  Serial.println("      mirror  = 切换右耳镜像");
  Serial.println("      offset p5 = 设置Pitch偏移+5");
  Serial.println("      s = 回中位  ? = 查看状态");
  Serial.println("注意: 现在是全范围 0-180°，无限制");
  printStatus();
}

void loop() {
  if (!Serial.available()) return;

  String input = Serial.readStringUntil('\n');
  input.trim();
  if (input.length() == 0) return;

  Serial.print(">>> "); Serial.println(input);

  // mirror 命令
  if (input == "mirror") {
    mirror_r = !mirror_r;
    Serial.print("右耳镜像: "); Serial.println(mirror_r ? "ON（180-逻辑值）" : "OFF（直接发送）");
    moveTo_R(cur_r);
    printStatus();
    return;
  }

  // s = 回中位
  if (input == "s") {
    cur_l = neutral_l; cur_r = neutral_r;
    cur_y = neutral_y; cur_p = neutral_p;
    applyAll();
    Serial.println("回到中位");
    printStatus();
    return;
  }

  // ? = 查看状态
  if (input == "?") { printStatus(); return; }

  // offset 命令：offset p5 / offset y-3 / offset l0
  if (input.startsWith("offset ")) {
    String sub = input.substring(7);
    char axis = sub.charAt(0);
    int val = sub.substring(1).toInt();
    if (axis=='l'||axis=='L') offset_l = val;
    else if (axis=='r'||axis=='R') offset_r = val;
    else if (axis=='y'||axis=='Y') offset_y = val;
    else if (axis=='p'||axis=='P') offset_p = val;
    applyAll();
    Serial.print("偏移已更新: "); Serial.print(axis); Serial.println(val);
    printStatus();
    return;
  }

  // neutral 命令：neutral p90（设置中位）
  if (input.startsWith("neutral ")) {
    String sub = input.substring(8);
    char axis = sub.charAt(0);
    int val = sub.substring(1).toInt();
    if (axis=='l'||axis=='L') { neutral_l = val; cur_l = val; }
    else if (axis=='r'||axis=='R') { neutral_r = val; cur_r = val; }
    else if (axis=='y'||axis=='Y') { neutral_y = val; cur_y = val; }
    else if (axis=='p'||axis=='P') { neutral_p = val; cur_p = val; }
    applyAll();
    Serial.print("中位已更新: "); Serial.print(axis); Serial.println(val);
    printStatus();
    return;
  }

  // 普通移动命令
  char axis = input.charAt(0);
  int angle = input.substring(1).toInt();

  switch (axis) {
    case 'l': case 'L': moveTo_L(angle); break;
    case 'r': case 'R': moveTo_R(angle); break;
    case 'y': case 'Y': moveTo_Y(angle); break;
    case 'p': case 'P': moveTo_P(angle); break;
    default:
      Serial.println("未知命令");
      return;
  }

  Serial.print("移动完成 → 实际发送: ");
  switch (axis) {
    case 'l': case 'L': Serial.print(raw_l); break;
    case 'r': case 'R': Serial.print(raw_r); break;
    case 'y': case 'Y': Serial.print(raw_y); break;
    case 'p': case 'P': Serial.print(raw_p); break;
  }
  Serial.println("°");
  printStatus();
}