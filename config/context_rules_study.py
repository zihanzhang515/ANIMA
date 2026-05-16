"""
config/context_rules_study.py
------------------------------
Study版本的场景规则表

所有时间阈值按20分钟session压缩。
生产版本在 context_rules.py（不要改那个）。

切换方式：
  from config.context_rules_study import CONTEXT_RULES, match_context
  替代原来的：
  from config.context_rules import CONTEXT_RULES, match_context

时间对照：
  场景              生产版     Study版
  Deep Focus       600s       60s
  Stuck/Confused   300s       30s
  Brief Absence    300s       20s
  Long Absence     2700s      120s
  High Energy      0s         0s
  Late Night       0s         0s（时间条件改为全天）
"""

import datetime

# ── 冷却时间（情绪切换后的最短间隔）──────────────────────────
# 防止同一情绪在短时间内反复触发
EMOTION_COOLDOWN_SEC = {
    "focus":    30,   # 生产: 120s
    "tired":    30,
    "curious":  20,
    "happy":    20,
    "listen":   10,
    "confused": 30,
    "relaxed":  0,    # relaxed 没有冷却
}

# ── 情绪持续后回 Relaxed 的超时 ────────────────────────────────
# 条件消失后等待这么多秒再回 Relaxed
RETURN_TO_RELAXED_DELAY_SEC = {
    "focus":    20,   # 生产: 60s
    "tired":    15,
    "curious":  15,
    "happy":    20,
    "listen":   10,
    "confused": 20,
}

CONTEXT_RULES = [

    # ── Scenario 1: Deep Focus ─────────────────────────────────
    {
        "scenario": "Deep Focus",
        "emotion": "focus",
        "conditions": {
            "face_present": True,
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
            "input_rate": "high",
        },
        "min_duration_sec": 60,      # 生产: 600s
    },

    # ── Scenario 2: High Energy ────────────────────────────────
    {
        "scenario": "High Energy",
        "emotion": "happy",
        "conditions": {
            "face_present": True,
            "audio_category": ["speech", "music"],
            "input_rate": ["medium", "high"],
        },
        "min_duration_sec": 0,
    },

    # ── Scenario 3: Active Break ───────────────────────────────
    {
        "scenario": "Active Break",
        "emotion": "curious",
        "conditions": {
            "face_present": True,
            "input_rate": "low",
            "speech_active": False,
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]
        },
        "min_duration_sec": 0,
    },

    # ── Scenario 4: On a Call ──────────────────────────────────
    {
        "scenario": "On a Call",
        "emotion": "listen",
        "conditions": {
            "speech_active": True,
            "audio_category": "speech",
            "input_rate": "low",
        },
        "min_duration_sec": 0,
    },

    # ── Scenario 5: Late Night Work ────────────────────────────
    # Study版本：去掉 hour_range 限制，任何时间都可触发
    # 改为：持续工作 8 分钟以上 + 打字率 medium/low
    {
        "scenario": "Sustained Work",
        "emotion": "tired",
        "conditions": {
            "face_present": True,
            "input_rate": ["low", "medium"],
        },
        "min_duration_sec": 0,
        "requires_transition_from": {
            "input_rate": "high"    # 必须从高活跃降下来才触发
        },
    },

    # ── Scenario 6: Stuck ─────────────────────────────────────
    {
        "scenario": "Stuck",
        "emotion": "confused",
        "conditions": {
            "face_present": True,
            "input_rate": "low",
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]
        },
        "min_duration_sec": 30,      # 生产: 300s
    },

    # ── Scenario 7: Brief Absence ─────────────────────────────
    {
        "scenario": "Brief Absence",
        "emotion": "curious",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 20,      # 生产: 300s
        "max_duration_sec": 120,     # 生产: 2700s
    },

    # ── Scenario 8: Long Absence ──────────────────────────────
    {
        "scenario": "Long Absence",
        "emotion": "tired",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 120,     # 生产: 2700s
    },

    # ── Default ───────────────────────────────────────────────
    {
        "scenario": "Idle Ambient",
        "emotion": "relaxed",
        "conditions": {
            "face_present": True,
        },
        "min_duration_sec": 0,
    },
]


def match_context(current_state: dict, prev_state: dict, duration_sec: float) -> tuple:
    current_hour = datetime.datetime.now().hour

    for rule in CONTEXT_RULES:
        if not _check_conditions(current_state, rule["conditions"]):
            continue

        if "time_condition" in rule:
            hour_range = rule["time_condition"].get("hour_range")
            if hour_range and not (hour_range[0] <= current_hour < hour_range[1]):
                continue

        if "requires_transition_from" in rule:
            if not _check_transition(prev_state, rule["requires_transition_from"]):
                continue

        if duration_sec < rule.get("min_duration_sec", 0):
            continue

        if "max_duration_sec" in rule:
            if duration_sec > rule["max_duration_sec"]:
                continue

        return rule["emotion"], rule["scenario"]

    return "relaxed", "Default"


def _check_conditions(state: dict, conditions: dict) -> bool:
    for key, expected in conditions.items():
        actual = state.get(key)
        if actual is None:
            return False
        if isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False
    return True


def _check_transition(prev_state: dict, transition_conditions: dict) -> bool:
    return _check_conditions(prev_state, transition_conditions)
