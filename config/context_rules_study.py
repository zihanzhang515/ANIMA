"""
config/context_rules_study.py
------------------------------
Study 3 自动版场景规则表（20 分钟 session 压缩阈值）

生产版本在 config/context_rules.py，不要改那个。

切换方式（在 understand/context_pipeline.py 里改一行）：
  from config.context_rules_study import CONTEXT_RULES, match_context

情绪触发逻辑重新设计（解决 curious/tired/confused 重叠问题）：

  情绪        核心区分                          触发时机
  ──────────────────────────────────────────────────────
  focus      还在高速打字（high input）          专注工作 60s+
  happy      听音乐/说话同时在打字               有声音环境下活跃
  listen     有人声，不在打字                    正在通话/开会
  curious    完全停止打字（low），刚停20~60s      发呆介入
  confused   完全停止打字（low），超过60s         卡住了
  tired      还在打字但变慢（medium），持续90s    疲劳减速
  ──────────────────────────────────────────────────────
  关键区分：
    curious / confused  → input = LOW（完全没在打）
    tired               → input = MEDIUM（还在打，但慢了）
"""

import datetime

# ── 冷却时间（情绪切换后的最短间隔）──────────────────────────
EMOTION_COOLDOWN_SEC = {
    "focus":    30,    # 生产: 120s
    "tired":    30,
    "curious":  20,
    "happy":    20,
    "listen":   10,
    "confused": 30,
    "relaxed":  0,
}

# ── 条件消失后回 Relaxed 的延迟 ───────────────────────────────
RETURN_TO_RELAXED_DELAY_SEC = {
    "focus":    20,    # 生产: 60s
    "tired":    15,
    "curious":  15,
    "happy":    20,
    "listen":   10,
    "confused": 20,
}

CONTEXT_RULES = [

    # ── Scenario 1: Deep Focus ─────────────────────────────────
    # 用户专注打字：high input + 安静 + 持续 60s
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
    # 非常严格：必须在播放音乐（非 speech）且高速打字，持续 30s
    # 写作 session 中 speech 场景应该是 listen，不是 happy
    {
        "scenario": "High Energy",
        "emotion": "happy",
        "conditions": {
            "face_present": True,
            "audio_category": "music",   # 只有明确的音乐，不包括 speech
            "input_rate": "high",        # 必须高速打字，medium 太容易误触
        },
        "min_duration_sec": 30,          # 持续 30s 才触发
    },

    # ── Scenario 3: On a Call ──────────────────────────────────
    # 用户在通话/会议中：有人声 + 不在打字
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

    # ── Scenario 4: Daydreaming / Spacing Out ─────────────────
    # 用户发呆（刚停下来）：从活跃 → 完全停止打字，20~60s 内
    # ANIMA 介入，表达好奇："你在想什么呢？"
    # 注意：max_duration_sec=60，超过60s自动升级为 confused
    {
        "scenario": "Daydreaming",
        "emotion": "curious",
        "conditions": {
            "face_present": True,
            "input_rate": "low",       # 完全没在打字
            "speech_active": False,
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]  # 必须从活跃状态转来
        },
        "min_duration_sec": 20,        # 发呆 20s 才触发（排除短暂停顿）
        "max_duration_sec": 60,        # 发呆超 60s → 升级为 confused
    },

    # ── Scenario 5: Stuck / Confused ──────────────────────────
    # 用户发呆更久，可能卡住了：same low input，但持续 60s 以上
    # ANIMA 表现困惑："是遇到什么问题了吗？"
    {
        "scenario": "Stuck",
        "emotion": "confused",
        "conditions": {
            "face_present": True,
            "input_rate": "low",       # 完全没在打字（同 curious）
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]
        },
        "min_duration_sec": 60,        # 发呆 60s 以上才触发
    },

    # ── Scenario 6: Fatigue / Slowdown ────────────────────────
    # 用户还在打字但速度明显变慢（medium，不是 low）
    # 关键区分：curious/confused 是完全不打字，tired 是还在打但疲惫
    # ANIMA 表现疲惫："你是不是有点累了？"
    {
        "scenario": "Fatigue",
        "emotion": "tired",
        "conditions": {
            "face_present": True,
            "input_rate": "medium",    # 还在打字，但变慢了（不是 low）
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
        },
        "requires_transition_from": {
            "input_rate": "high"       # 必须从高速打字降下来
        },
        "min_duration_sec": 90,        # 持续变慢 90s（生产: 480s）
    },

    # ── Scenario 7: Brief Absence ─────────────────────────────
    # 用户短暂离开座位：ANIMA 左右张望，等你回来
    {
        "scenario": "Brief Absence",
        "emotion": "curious",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 20,        # 生产: 300s
        "max_duration_sec": 120,
    },

    # ── Scenario 8: Long Absence ──────────────────────────────
    # 用户长时间不在：ANIMA 进入低能耗困倦状态
    {
        "scenario": "Long Absence",
        "emotion": "tired",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 120,       # 生产: 2700s
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
