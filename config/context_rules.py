"""
config/context_rules.py
------------------------
场景规则表（更新版）

新增：
- Scenario 8: Brief Absence（短暂离开 5 分钟）→ Curious（等待感）
- Long Absence 时间从 30 分钟调整为 45 分钟
- 修正：Relaxed 不再有 face tracking（在 realtime_pipeline 里控制）
"""

import datetime

CONTEXT_RULES = [

    # ── Scenario 1: Deep Focus ─────────────────────────────
    {
        "scenario": "Deep Focus",
        "emotion": "focus",
        "conditions": {
            "face_present": True,
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
            "input_rate": "high",
        },
        "min_duration_sec": 600,
    },

    # ── Scenario 2: High Energy ────────────────────────────
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

    # ── Scenario 3: Active Break ───────────────────────────
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

    # ── Scenario 4: On a Call ─────────────────────────────
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

    # ── Scenario 5: Late Night Work ────────────────────────
    {
        "scenario": "Late Night Work",
        "emotion": "tired",
        "conditions": {
            "face_present": True,
            "input_rate": ["low", "medium"],
        },
        "time_condition": {
            "hour_range": (0, 4)
        },
        "min_duration_sec": 0,
    },

    # ── Scenario 6: Stuck ─────────────────────────────────
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
        "min_duration_sec": 300,
    },

    # ── Scenario 7: Brief Absence（新增）──────────────────
    # 人短暂离开（5-45 分钟）→ Curious（等待感，耳朵朝前）
    {
        "scenario": "Brief Absence",
        "emotion": "curious",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 60,    # 离开 1 分钟后触发（测试用，生产改回 300）
        "max_duration_sec": 600,   # 测试用 10 分钟，生产改回 2700
    },

    # ── Scenario 8: Long Absence ──────────────────────────
    # 长时间不在（45 分钟+）→ Tired
    {
        "scenario": "Long Absence",
        "emotion": "tired",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 600,   # 测试用 10 分钟，生产改回 2700
    },

    # ── Default ───────────────────────────────────────────
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

        # 新增：max_duration_sec 检查（用于 Brief Absence）
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