"""
config/emotions.py — 最终校准版
────────────────────────────────
校准结果（2026-05-01）：
  Yaw：60° = 正前方，范围 0-180°
  Pitch：20° = 水平中立，范围 0-40°（物理限制，约 ±20°）
  右耳：0° = 朝前，数字越大越往后折
  左耳：物理角度 = 90 - 逻辑角度（EAR_L_NEUTRAL = 90）
"""

CALIBRATION = {
    "pitch_base": 20,   # 水平中立
    "pitch_min":  0,    # 抬头极限
    "pitch_max":  40,   # 低头极限
    "yaw_center": 60,   # 正前方
    "yaw_min":    0,
    "yaw_max":    180,
}

EMOTION_PARAMS = {

    # ── Tier 1：持续情绪 ──────────────────────────────────────

    "relaxed": {
        "tier": 1,
        "ear":          0,
        "yaw":          60,     # 正前方
        "pitch_offset": 0,      # 20°（水平）
        "r": 255, "g": 245, "b": 224,
        "is_default": True,
    },

    "curious": {
        "tier": 1,
        "ear":          0,
        "yaw":          45,     # 左转 15°
        "pitch_offset": -5,     # 15°（微抬头）
        "r": 0, "g": 200, "b": 200,
    },

    "happy": {
        "tier": 1,
        "ear":          0,      # 配合扇动动画
        "yaw":          60,     # 居中，配合 ±8° 摆动（52°↔68°）
        "pitch_offset": 0,      # 20°（水平）
        "r": 255, "g": 140, "b": 0,
    },

    "focus": {
        "tier": 1,
        "ear":          90,     # 耳朵折后
        "yaw":          60,     # 中心锁定
        "pitch_offset": 0,      # 20°（水平）
        "r": 0, "g": 50, "b": 180,
    },

    "tired": {
        "tier": 1,
        "ear":          110,    # 大幅折后
        "yaw":          60,
        "pitch_offset": 15,     # 35°（低头，接近极限）
        "r": 120, "g": 70, "b": 0,   # 暗黄色（欲警）
    },

    "confused": {
        "tier": 1,
        "ear_left":     80,     # 左耳折后
        "ear_right":    0,      # 右耳朝前
        "ear":          40,     # fallback
        "yaw":          60,
        "pitch_offset": -5,     # 15°（微抬头，思考姿态）
        "r": 140, "g": 0, "b": 200,
    },

    "listen": {
        "tier": 1,
        "ear":          0,
        "yaw":          60,     # face tracking 会覆盖
        "pitch_offset": 0,
        "r": 0, "g": 160, "b": 50,
    },

    # ── Tier 2：反射行为 ──────────────────────────────────────

    "reflex_alert": {
        "tier": 2,
        "ear":          0,
        "yaw":          60,
        "pitch_offset": -5,     # 微抬头
        "r": 30, "g": 200, "b": 80,  # 偏绿但不如 listen 那么鲜绿
        "cooldown_sec": 8,
        "scan_left":  20,       # 扫描到 20°
        "scan_right": 100,      # 扫描到 100°
    },

    "reflex_shy": {
        "tier": 2,
        "ear":          100,
        "yaw":          90,     # 右转（60+30=90°）
        "pitch_offset": 10,     # 30°（低头）
        "r": 100, "g": 0, "b": 50,
        "cooldown_sec": 45,
    },
}

SERVO_LIMITS = {
    "ear": (0,   150),
    "yaw": (0,   180),
}


def get_emotion(name: str) -> dict:
    params = EMOTION_PARAMS.get(name, EMOTION_PARAMS["relaxed"]).copy()
    offset = params.pop("pitch_offset", 0)
    target_pitch = CALIBRATION["pitch_base"] + offset
    target_pitch = max(CALIBRATION["pitch_min"],
                       min(CALIBRATION["pitch_max"], target_pitch))
    params["pitch"] = target_pitch
    params["name"]  = name
    return params


def update_calibration(base_pitch: int, pitch_min: int, pitch_max: int):
    CALIBRATION["pitch_base"] = base_pitch
    CALIBRATION["pitch_min"]  = pitch_min
    CALIBRATION["pitch_max"]  = pitch_max