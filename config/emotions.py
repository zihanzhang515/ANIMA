"""
config/emotions.py — Final calibrated values
─────────────────────────────────────────────
Calibration (2026-05-01):
  Yaw:   60° = straight ahead, range 0–180°
  Pitch: 25° = horizontal neutral, range 0–40° (physical limit ≈ ±20°)
  Right ear: 0° = forward, higher values fold further back
  Left ear:  physical angle = 90 - logical angle  (EAR_L_NEUTRAL = 90)
"""

CALIBRATION = {
    "pitch_base": 25,   # Horizontal neutral (matches Arduino basePitch)
    "pitch_min":  0,    # Full tilt up
    "pitch_max":  40,   # Full tilt down
    "yaw_center": 60,   # Straight ahead
    "yaw_min":    0,
    "yaw_max":    180,
}

EMOTION_PARAMS = {

    # ── Tier 1: Sustained emotions ────────────────────────────────────────

    "relaxed": {
        "tier": 1,
        "ear":          0,
        "yaw":          60,     # Straight ahead
        "pitch_offset": 0,      # 25° (horizontal neutral)
        "r": 255, "g": 245, "b": 224,
        "is_default": True,
    },

    "curious": {
        "tier": 1,
        "ear":          0,
        "yaw":          45,     # 15° left turn
        "pitch_offset": -5,     # 20° (slight head raise)
        "r": 0, "g": 200, "b": 200,
    },

    "happy": {
        "tier": 1,
        "ear":          0,      # Ears animate during idle (flap to 8°)
        "yaw":          60,     # Centre; idle oscillates ±8° (52°↔68°)
        "pitch_offset": 0,      # 25° (horizontal neutral)
        "r": 255, "g": 140, "b": 0,
    },

    "focus": {
        "tier": 1,
        "ear":          90,     # Ears folded back
        "yaw":          60,     # Locked centre
        "pitch_offset": 0,      # 25° (horizontal neutral)
        "r": 0, "g": 50, "b": 180,
    },

    "tired": {
        "tier": 1,
        "ear":          110,    # Ears heavily folded back
        "yaw":          60,
        "pitch_offset": 15,     # 40° (head drooped, near limit)
        "r": 120, "g": 70, "b": 0,   # Dim amber
    },

    "confused": {
        "tier": 1,
        "ear_left":     0,      # Left ear forward (open)
        "ear_right":    70,     # Right ear folded back
        "ear":          40,     # Fallback (symmetric)
        "yaw":          50,     # Slight left turn (60-10)
        "pitch_offset": -3,     # 22° (slight head raise, thinking posture)
        "r": 120, "g": 0, "b": 180,
    },

    "listen": {
        "tier": 1,
        "ear":          0,
        "yaw":          75,     # 15° right turn (60+15); face tracking overrides this
        "pitch_offset": -2,     # 23° (slightly raised)
        "r": 0, "g": 160, "b": 50,
    },

    # ── Tier 2: Reflex behaviours ─────────────────────────────────────────

    "reflex_alert": {
        "tier": 2,
        "ear":          0,      # Ears snap forward at reflex start
        "yaw":          60,
        "pitch_offset": -5,     # 20° (slight raise)
        "r": 0, "g": 255, "b": 255,
        "cooldown_sec": 8,
        "scan_left":  20,       # Scan leftmost yaw
        "scan_right": 100,      # Scan rightmost yaw
    },

    "reflex_shy": {
        "tier": 2,
        "ear":          100,
        "yaw":          90,     # Turn right (60+30)
        "pitch_offset": 10,     # 35° (head lowered)
        "r": 255, "g": 0, "b": 0,   # Hard red (overrides in animShy)
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