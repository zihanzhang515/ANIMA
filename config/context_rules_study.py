"""
config/context_rules_study.py
------------------------------
Study 3 auto-sensor rule table (compressed thresholds for 20-minute sessions).

Production rules are in config/context_rules.py — do not modify that file.

To switch (one line in understand/context_pipeline.py):
  from config.context_rules_study import CONTEXT_RULES, match_context

Emotion trigger logic (redesigned to resolve curious/tired/confused overlap):

  Emotion     Core distinction                          When triggered
  ─────────────────────────────────────────────────────────────────────
  focus      Still typing fast (high input)             Active work for 60s+
  happy      Music playing while typing fast            Active with audio stimulus
  listen     Speech detected, not typing                On a call / in a meeting
  curious    Fully stopped typing (low), just stopped   Spacing out (20-60s)
  confused   Fully stopped typing (low), long pause     Stuck (60s+)
  tired      Typing slowly (medium), sustained           Fatigue slowdown

  Key distinction:
    curious / confused → input = LOW  (not typing at all)
    tired              → input = MEDIUM (typing, but slow)
"""

import datetime

# ── Cooldown: minimum interval between emotion triggers ──────────────────
EMOTION_COOLDOWN_SEC = {
    "focus":    30,    # Production: 120s
    "tired":    30,
    "curious":  20,
    "happy":    20,
    "listen":   10,
    "confused": 30,
    "relaxed":  0,
}

# ── Delay before returning to Relaxed after a condition disappears ────────
RETURN_TO_RELAXED_DELAY_SEC = {
    "focus":    20,    # Production: 60s
    "tired":    15,
    "curious":  15,
    "happy":    20,
    "listen":   10,
    "confused": 20,
}

CONTEXT_RULES = [

    # ── Scenario 1: Deep Focus ─────────────────────────────────────────────
    # High typing rate, quiet environment, no speech
    {
        "scenario": "Deep Focus",
        "emotion": "focus",
        "conditions": {
            "face_present": True,
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
            "input_rate": "high",
        },
        "min_duration_sec": 0,       # Duration gate handled by pipeline active_secs check
    },

    # ── Scenario 2: High Energy ────────────────────────────────────────────
    # Strict: music (not speech) + high typing rate; speech environment → listen, not happy
    {
        "scenario": "High Energy",
        "emotion": "happy",
        "conditions": {
            "face_present": True,
            "audio_category": "music",   # Explicit music only; speech excluded
            "input_rate": "high",        # High rate required; medium causes too many false positives
        },
        "min_duration_sec": 0,           # Duration gate handled by pipeline
    },

    # ── Scenario 3: On a Call ──────────────────────────────────────────────
    # Speech detected + not typing → call or meeting
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

    # ── Scenario 4: Daydreaming / Spacing Out ─────────────────────────────
    # User was active, then fully stopped typing for 20-60s
    {
        "scenario": "Daydreaming",
        "emotion": "curious",
        "conditions": {
            "face_present": True,
            "input_rate": "low",       # Fully stopped
            "speech_active": False,
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]  # Must come from an active state
        },
        "min_duration_sec": 20,        # Ignore brief pauses under 20s
        "max_duration_sec": 60,        # Beyond 60s → escalate to confused
    },

    # ── Scenario 5: Stuck / Confused ──────────────────────────────────────
    # Same low-input state as curious but sustained for 60s+
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
        "min_duration_sec": 60,
    },

    # ── Scenario 6: Fatigue / Slowdown ────────────────────────────────────
    # Still typing but noticeably slower (medium, not low)
    # Key distinction from curious/confused: user IS typing, just fatigued
    {
        "scenario": "Fatigue",
        "emotion": "tired",
        "conditions": {
            "face_present": True,
            "input_rate": "medium",    # Slowed but not stopped
            "speech_active": False,
            "audio_category": ["silence", "ambient"],
        },
        "min_duration_sec": 0,         # Duration gate handled by pipeline
    },

    # ── Scenario 7: Brief Absence ─────────────────────────────────────────
    # User stepped away briefly; ANIMA looks around waiting
    {
        "scenario": "Brief Absence",
        "emotion": "curious",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 20,        # Production: 300s
        "max_duration_sec": 120,
    },

    # ── Scenario 8: Long Absence ──────────────────────────────────────────
    # Extended absence; ANIMA enters low-energy drowsy state
    {
        "scenario": "Long Absence",
        "emotion": "tired",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 120,       # Production: 2700s
    },

    # ── Default ───────────────────────────────────────────────────────────
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
