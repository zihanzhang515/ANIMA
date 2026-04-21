"""
config/emotions.py
------------------
Emotion parameters: servo angles + RGB light color for each emotion.

Servo angle reference (Arduino degrees):
  90 = neutral/center
  > 90 = one direction
  < 90 = other direction

Ear servo (45° installed, single DOF):
  0°  = folded back flat
  45° = neutral middle
  90° = perked forward

Head Yaw (left-right):
  90° = center
  70° = left
  110° = right

Head Pitch (up-down):
  90° = level
  100° = slight up
  75° = down / tired

ENTER + HOLD 两阶段说明：
  - 主参数（ear/yaw/pitch/r/g/b）是 ENTER 阶段目标姿态，执行一次动画过渡
  - hold_params 是 HOLD 阶段的持续 idle 定义，Arduino 进入 idle 循环直到收到新指令

NOTE: These are placeholder values - update after RQ1 results confirm
which expressions pass System 1 threshold.
"""

EMOTION_PARAMS = {

    # ── Tier 1: Contextual Expressions ────────────────────

    "curious": {
        "tier": 1,
        "ear": 90,          # Perked forward
        "yaw": 110,         # Turned slightly right (fast snap)
        "pitch": 100,       # Slight up
        "r": 0, "g": 206, "b": 209,   # Cyan
        "light_mode": "steady",
        "duration_ms": 3000,
        "movement_speed": "fast",     # snap to position
        "notes": "Fast snap to side then hold. Like hearing something.",
        "hold_params": {
            "idle_type": "head_sway",      # 轻微头部左右晃动
            "idle_range": 8,               # ±8度
            "idle_interval_ms": 3000,      # 每3秒动一下
            "r": 0, "g": 206, "b": 209,
            "light_mode": "steady"
        }
    },

    "happy": {
        "tier": 1,
        "ear": 70,          # Oscillate 45°↔90° (handled in animation)
        "yaw": 90,          # Center with wiggle (handled in animation)
        "pitch": 90,        # Level with nod (handled in animation)
        "r": 255, "g": 140, "b": 0,   # Orange
        "light_mode": "fast_pulse",   # 2Hz
        "duration_ms": 3000,
        "movement_speed": "fast",
        "notes": "Ear fans, head nods and wiggles. Excited dog energy.",
        "hold_params": {
            "idle_type": "ear_twitch",     # 小幅耳朵抖动
            "idle_range": 20,              # ±20度
            "idle_interval_ms": 2000,      # 每2秒动一下
            "r": 255, "g": 140, "b": 0,
            "light_mode": "slow_breath"    # 进入 hold 后从 fast_pulse 换成慢呼吸
        }
    },

    "focus": {
        "tier": 1,
        "ear": 0,           # Flat back
        "yaw": 90,          # Dead center, locked
        "pitch": 90,        # Level, locked
        "r": 0, "g": 0, "b": 139,     # Dim Blue
        "light_mode": "slow_breath",  # 0.2Hz - barely perceptible
        "duration_ms": 5000,
        "movement_speed": "slow",     # Ears slowly fold back
        "notes": "Cat in hunting stillness. Zero movement once settled.",
        "hold_params": {
            "idle_type": "none",           # 完全静止
            "idle_range": 0,
            "idle_interval_ms": 8000,
            "r": 0, "g": 0, "b": 100,
            "light_mode": "slow_breath"
        }
    },

    "relaxed": {
        "tier": 1,
        "ear": 45,          # Natural middle
        "yaw": 90,          # Center
        "pitch": 90,        # Level
        "r": 255, "g": 245, "b": 224, # Warm White
        "light_mode": "slow_breath",  # 0.3Hz
        "duration_ms": 4000,
        "movement_speed": "slow",
        "notes": "DEFAULT STATE. Idle motion active here only.",
        "is_default": True,
        "hold_params": {
            "idle_type": "gentle_scan",    # 缓慢左右小范围扫描
            "idle_range": 10,              # ±10度
            "idle_interval_ms": 4000,      # 每4秒动一下
            "r": 255, "g": 245, "b": 224,
            "light_mode": "slow_breath"
        }
    },

    "tired": {
        "tier": 1,
        "ear": 10,          # Near flat, drooping
        "yaw": 90,          # Center
        "pitch": 75,        # Head tilted down
        "r": 139, "g": 96, "b": 0,    # Dim Amber
        "light_mode": "fade_out",     # Gradually dimming
        "duration_ms": 5000,
        "movement_speed": "very_slow",  # Like losing neck muscle support
        "notes": "Very slow movement. Head sinks. Like exhaustion.",
        "hold_params": {
            "idle_type": "droop",          # 头部缓慢下沉感
            "idle_range": 5,               # ±5度
            "idle_interval_ms": 6000,      # 很慢，每6秒轻微一动
            "r": 100, "g": 70, "b": 0,
            "light_mode": "fade_out"
        }
    },

    "confused": {
        "tier": 1,
        "ear_asymmetric": True,
        "ear_left": 90,     # One ear up
        "ear_right": 0,     # One ear down
        "ear": 45,          # Fallback if only one servo
        "yaw": 90,          # Center
        "pitch": 95,        # Very slight up (thinking)
        "r": 106, "g": 13, "b": 173,  # Purple
        "light_mode": "steady_dim",
        "duration_ms": 4000,
        "movement_speed": "medium",
        "notes": "Asymmetric ears create visible imbalance. Head tilts slightly up.",
        "hold_params": {
            "idle_type": "head_tilt",      # 头部小角度歪动（不确定感）
            "idle_range": 5,               # ±5度
            "idle_interval_ms": 4000,
            "r": 80, "g": 10, "b": 130,
            "light_mode": "steady_dim"
        }
    },

    "listen": {
        "tier": 1,
        "ear": 90,          # Fully forward, still
        "yaw": 90,          # Tracks toward voice source (override with face_x)
        "pitch": 90,        # Level
        "r": 34, "g": 139, "b": 34,   # Green
        "light_mode": "steady",
        "duration_ms": 3000,
        "movement_speed": "medium",
        "notes": "Ears forward, locked still. Head toward voice source.",
        "hold_params": {
            "idle_type": "ear_track",      # 耳朵追踪声音方向的微小调整
            "idle_range": 5,               # ±5度
            "idle_interval_ms": 2000,
            "r": 34, "g": 139, "b": 34,
            "light_mode": "steady"
        }
    },

    # ── Tier 2: Reflexive Behaviors ───────────────────────
    # These don't enter the state machine
    # They execute as one-shot sequences then return to current emotion

    "reflex_alert": {
        "tier": 2,
        "ear": 90,          # Snap up
        "yaw_sequence": [-20, +20, 0],  # Fast scan left→right→center
        "pitch": 95,        # Slight up
        "r": 0, "g": 255, "b": 255,    # Brief Cyan flash
        "light_mode": "flash",
        "duration_ms": 800,
        "cooldown_sec": 10,
        "movement_speed": "very_fast",
        "notes": "Radar scan. Stop-motion feel, not smooth."
    },

    "reflex_shy": {
        "tier": 2,
        "ear": 0,           # Flat back
        "yaw": 70,          # Turn away (left)
        "pitch": 75,        # Look down
        "r": 100, "g": 0, "b": 50,    # Dim warm red pulse
        "light_mode": "soft_pulse",
        "duration_ms": 2000,
        "cooldown_sec": 30,
        "movement_speed": "slow",     # Shy is slow, not scared
        "notes": "Slow avoidance. Like a shy child. Distinct from fear."
    },

    "reflex_greeting": {
        "tier": 2,
        "ear": 90,          # 耳朵快速竖起
        "yaw": 90,          # 正视前方
        "pitch": 95,        # 微微抬头
        "r": 255, "g": 200, "b": 50,  # 暖金色
        "light_mode": "quick_pulse",
        "duration_ms": 1500,
        "cooldown_sec": 120,          # 2分钟内只触发一次
        "movement_speed": "fast",
        "notes": "Quick ear perk when user returns after >60s absence. 'I see you again.'"
    },
}


def get_emotion(name: str) -> dict:
    """Get parameters for an emotion. Returns relaxed if not found."""
    return EMOTION_PARAMS.get(name, EMOTION_PARAMS["relaxed"])


def get_default_emotion() -> dict:
    """Get the default (relaxed) state parameters."""
    return EMOTION_PARAMS["relaxed"]
