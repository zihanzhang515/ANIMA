"""
config/emotions.py
------------------
舵机参数（基于实物校准后的数值）

校准结果：
  耳朵：0° = 朝前（自然/Relaxed），数字越大越往后折，范围 0-180°
  Yaw：60° = 正对前方，<60° 向左，>60° 向右，范围 0-180°
  Pitch：25° = 水平中立，范围 10-40°（物理限制，只能微动约 ±15°）

注意：Pitch 如果低头抬头方向搞反了，在 Arduino 里直接
      把 pitch 改为 50 - pitch 即可翻转方向。
"""

EMOTION_PARAMS = {

    # ── Tier 1：持续情绪 ────────────────────────────────────

    "curious": {
        "tier": 1,
        "ear":   0,       # 耳朵完全朝前，最大注意力
        "yaw":   45,      # 头转向一侧 15°（60-15=45），听到声音的感觉
        "pitch": 30,      # 微微抬头 5°（25+5=30），好奇姿态
        "r": 0, "g": 206, "b": 209,    # Cyan
        "light_mode": "steady",
        "move_speed": "fast",           # 快速定位，然后保持
        "duration_ms": 600,
    },

    "happy": {
        "tier": 1,
        "ear":   0,       # 朝前，搭配快速扇动动画
        "yaw":   60,      # 中心
        "pitch": 25,      # 水平，搭配点头动画
        "r": 255, "g": 140, "b": 0,    # Orange
        "light_mode": "fast_pulse",
        "move_speed": "medium",
        "duration_ms": 1000,
        # 动画参数：耳朵 0→25→0 快速扇动，头部小幅摆动
        "anim_ear_swing": 25,          # 耳朵扇动幅度
        "anim_yaw_swing": 8,           # 头部左右晃动幅度
        "anim_pitch_nod": 5,           # 点头幅度（在 pitch 基础上±5）
    },

    "focus": {
        "tier": 1,
        "ear":   90,      # 耳朵折后，完全静止
        "yaw":   60,      # 正前方，锁定
        "pitch": 25,      # 水平，锁定
        "r": 0, "g": 0, "b": 139,      # Dim Blue
        "light_mode": "slow_breath",
        "move_speed": "very_slow",      # 非常缓慢进入
        "duration_ms": 4000,
    },

    "relaxed": {
        "tier": 1,
        "ear":   0,       # 自然朝前，放松中位
        "yaw":   60,      # 正前方
        "pitch": 25,      # 水平
        "r": 255, "g": 245, "b": 224,  # Warm White
        "light_mode": "slow_breath",
        "move_speed": "slow",
        "duration_ms": 3000,
        "is_default": True,
        # Idle 微动参数
        "idle_yaw_range":   5,         # Yaw 微漂：±5°（60±5）
        "idle_pitch_range": 3,         # Pitch 微漂：±3°（25±3，在安全范围内）
        "idle_ear_range":   5,         # 耳朵微抖：±5°
    },

    "tired": {
        "tier": 1,
        "ear":   110,     # 耳朵大幅折后，疲态
        "yaw":   60,      # 正前方
        "pitch": 37,      # 低头（25+12=37，接近40上限但留余量）
        "r": 139, "g": 96, "b": 0,     # Dim Amber
        "light_mode": "fade_out",
        "move_speed": "very_slow",      # 像失去颈部支撑那样慢慢沉下去
        "duration_ms": 5000,
        # 叹气动作：pitch 到达目标后再下沉 2°，然后停
        "anim_sigh_extra": 2,
    },

    "confused": {
        "tier": 1,
        "ear_left":  0,   # 左耳朝前
        "ear_right": 80,  # 右耳折后，产生不对称视觉
        "ear":       40,  # 单耳机时的 fallback
        "yaw":       60,  # 正前方
        "pitch":     20,  # 微微抬头 5°（25-5=20），思考姿态
        "r": 106, "g": 13, "b": 173,   # Purple
        "light_mode": "steady_dim",
        "move_speed": "medium",
        "duration_ms": 2000,
    },

    "listen": {
        "tier": 1,
        "ear":   0,       # 完全朝前，全神贯注
        "yaw":   60,      # 朝向声音来源（Face tracking 会覆盖这个值）
        "pitch": 25,      # 水平，专注
        "r": 34, "g": 139, "b": 34,    # Green
        "light_mode": "steady",
        "move_speed": "medium",
        "duration_ms": 1500,
    },

    # ── Tier 2：反射行为 ────────────────────────────────────

    "reflex_alert": {
        "tier": 2,
        "ear":   0,       # 耳朵立刻竖起
        "yaw":   60,      # 中心，然后扫描动画
        "pitch": 22,      # 微微抬头
        "r": 0, "g": 255, "b": 255,    # Cyan flash
        "light_mode": "flash",
        "move_speed": "snap",           # 最快，瞬间到位
        "duration_ms": 800,
        "cooldown_sec": 10,
        # 扫描参数：左 45° → 停 0.2s → 右 75° → 回 60°
        "scan_left":  45,
        "scan_right": 75,
        "scan_pause": 200,
    },

    "reflex_shy": {
        "tier": 2,
        "ear":   100,     # 耳朵折后
        "yaw":   40,      # 头转开（向左躲避，60-20=40）
        "pitch": 33,      # 低头（25+8=33）
        "r": 100, "g": 0, "b": 50,     # Dim warm red
        "light_mode": "soft_pulse",
        "move_speed": "slow",           # 害羞是慢动作，不是受惊
        "duration_ms": 2000,
        "cooldown_sec": 30,
    },
}


# ── 安全范围（超出这个范围的角度会被截断）────────────────
SERVO_LIMITS = {
    "ear":   (0,   150),   # 耳朵安全范围
    "yaw":   (20,  110),   # Yaw 安全范围（比物理极限留10°余量）
    "pitch": (10,  40),    # Pitch 安全范围（物理限制！绝不能超出）
}


def get_emotion(name: str) -> dict:
    params = EMOTION_PARAMS.get(name, EMOTION_PARAMS["relaxed"]).copy()
    params["name"] = name
    return params


def get_default_emotion() -> dict:
    return EMOTION_PARAMS["relaxed"]


def clamp_servo(axis: str, value: int) -> int:
    """把角度限制在安全范围内"""
    lo, hi = SERVO_LIMITS.get(axis, (0, 180))
    return max(lo, min(hi, value))
