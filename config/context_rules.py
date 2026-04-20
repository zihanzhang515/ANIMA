"""
config/context_rules.py
------------------------
信号组合 → 场景 → 情绪 的核心规则表。

v2 改动：
  - 修复 Tired 时间条件（23:00+，而非 0-4am）
  - 新增 Tired session duration 触发（连续在场 30 分钟）
  - 修复 Confused min_duration（180s，而非 300s）
  - 修复 Happy 条件（需要 audio_category=music 且 input_rate=high）
  - 优化规则优先级顺序，与最终规则表一致

规则匹配逻辑：
  1. 按顺序检查每条规则
  2. 第一条完全匹配的规则胜出
  3. 无匹配 → 默认 relaxed

注意：Curious vs Confused 的时间维度区分在 context_pipeline.py 里处理，
      这里的规则只负责基础信号匹配。
"""

import time
import datetime


# ─────────────────────────────────────────────────────────────
# 规则表（优先级从上到下）
# ─────────────────────────────────────────────────────────────

CONTEXT_RULES = [

    # ── 优先级1：Alert（实时层处理，这里不包含）──────────────
    # Alert 在 realtime_pipeline.py 里响应，不走这里

    # ── 优先级2：Happy ────────────────────────────────────────
    # 用户高活跃 + 高能量音频（听音乐/笑声同时快速工作）
    {
        "scenario": "High Energy",
        "emotion": "happy",
        "conditions": {
            "face_present":   True,
            "audio_category": "music",   # S4=music/energetic
            "input_rate":     "high",    # S5=高活跃
        },
        "min_duration_sec": 30,          # 持续30秒才触发
    },

    # ── 优先级3：Listen ───────────────────────────────────────
    # 附近有说话声，但用户自己没在打字
    {
        "scenario": "On a Call",
        "emotion": "listen",
        "conditions": {
            "speech_active":  True,
            "audio_category": "speech",
            "input_rate":     "low",     # 用户没在打字，在听
        },
    },

    # ── 优先级4：Focus ────────────────────────────────────────
    # 持续高活跃打字，安静无语音，10分钟以上
    {
        "scenario": "Deep Focus",
        "emotion": "focus",
        "conditions": {
            "face_present":   True,
            "speech_active":  False,
            "audio_category": ["silence", "keyboard"],
            "input_rate":     "high",
        },
        "min_duration_sec": 600,         # 10分钟
    },

    # ── 优先级5：Curious（基础匹配，时间维度在 pipeline 里处理）──
    # 之前在活跃，刚停下来
    {
        "scenario": "Active Break",
        "emotion": "curious",
        "conditions": {
            "face_present":   True,
            "speech_active":  False,
            "audio_category": ["silence", "keyboard"],
            "input_rate":     "low",
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]
        },
    },

    # ── 优先级6：Confused（基础匹配，时间维度在 pipeline 里处理）──
    # 之前活跃，停下来很久了
    # 注：pipeline 会根据 inactive_duration 决定是 curious 还是 confused
    {
        "scenario": "Stuck",
        "emotion": "confused",
        "conditions": {
            "face_present":   True,
            "speech_active":  False,
            "audio_category": ["silence", "keyboard"],
            "input_rate":     "low",
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]
        },
        "min_duration_sec": 180,         # 停下来 3 分钟以上
    },

    # ── 优先级7a：Tired（深夜版）─────────────────────────────
    # 23:00 以后还在工作
    {
        "scenario": "Late Night Work",
        "emotion": "tired",
        "conditions": {
            "face_present":   True,
            "input_rate":     ["low", "medium"],
        },
        "time_condition": {
            "hour_min": 23    # 23:00 以后
        },
    },

    # ── 优先级8：Relaxed（兜底默认）─────────────────────────
    # 用户在场，但没有特别的事情发生
    {
        "scenario": "Idle Ambient",
        "emotion": "relaxed",
        "conditions": {
            "face_present":   True,
        },
    },
]


# ─────────────────────────────────────────────────────────────
# 匹配函数
# ─────────────────────────────────────────────────────────────

def match_context(
    current_state: dict,
    prev_state: dict,
) -> tuple:
    """
    根据当前信号状态匹配最合适的规则。

    返回: (emotion_name, scenario_name)

    current_state:        SensorState.get() 的结果
    prev_state:           SensorState.get_prev() 的结果
    duration_sec:         当前状态已持续多少秒
    session_duration_sec: 用户本次在场的累计秒数
    """
    now_hour = datetime.datetime.now().hour

    for rule in CONTEXT_RULES:

        # 检查主要信号条件
        if not _check_conditions(current_state, rule["conditions"]):
            continue

        # 检查时间条件
        if "time_condition" in rule:
            hour_min = rule["time_condition"].get("hour_min")
            hour_range = rule["time_condition"].get("hour_range")
            if hour_min is not None:
                if now_hour < hour_min:
                    continue
            if hour_range is not None:
                if not (hour_range[0] <= now_hour < hour_range[1]):
                    continue

        # 检查 transition 条件（前一帧状态）
        if "requires_transition_from" in rule:
            if not _check_conditions(prev_state, rule["requires_transition_from"]):
                continue



        # 所有条件通过
        return rule["emotion"], rule["scenario"]

    return "relaxed", "Default"


def _check_conditions(state: dict, conditions: dict) -> bool:
    """检查 state 是否满足 conditions 里的所有条件。"""
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