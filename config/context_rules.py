"""
config/context_rules.py
------------------------
THE CORE MAPPING: Signal combinations → Scenario → Emotion

This is the "rulebook" that answers:
"Given what the sensors are seeing RIGHT NOW, what emotion should Anima show?"

How it works:
1. Each rule has "conditions" - what the signals must look like
2. Some rules have "requires_transition_from" - the state must have CHANGED from something
3. Some rules have "min_duration" - the state must have lasted long enough
4. Rules are checked in order - first match wins
5. If nothing matches → default to "relaxed"

Think of it like: IF (face=yes AND typing=fast AND quiet) THEN focus
"""

import time

# ─────────────────────────────────────────────────────────────
# CONTEXT RULES - checked in order, first match wins
# ─────────────────────────────────────────────────────────────

CONTEXT_RULES = [

    # ── Scenario 1: Deep Focus ─────────────────────────────
    # User has been typing quietly for a long time
    {
        "scenario": "Deep Focus",
        "emotion": "focus",
        "conditions": {
            "face_present": True,
            "speech_active": False,
            "audio_category": ["silence", "keyboard"],
            "input_rate": "high",
        },
        "min_duration_sec": 600,  # Must be doing this for 10+ minutes
    },

    # ── Scenario 2: High Energy ────────────────────────────
    # User is active, loud, energetic
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
    # User was working, now paused - transitional curiosity
    {
        "scenario": "Active Break",
        "emotion": "curious",
        "conditions": {
            "face_present": True,
            "input_rate": "low",
            "speech_active": False,
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]  # Must have been active before
        },
        "min_duration_sec": 0,
    },

    # ── Scenario 4: Listening to a Call ───────────────────
    # Speech nearby but user isn't typing - probably on a call
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
    # Working very late - tired
    {
        "scenario": "Late Night Work",
        "emotion": "tired",
        "conditions": {
            "face_present": True,
            "input_rate": ["low", "medium"],
        },
        "time_condition": {
            "hour_range": (0, 4)  # Midnight to 4am
        },
        "min_duration_sec": 0,
    },

    # ── Scenario 6: Stuck / Not Typing ────────────────────
    # Was active, now staring at screen doing nothing
    {
        "scenario": "Stuck",
        "emotion": "confused",
        "conditions": {
            "face_present": True,
            "input_rate": "low",
            "speech_active": False,
            "audio_category": ["silence", "keyboard"],
        },
        "requires_transition_from": {
            "input_rate": ["medium", "high"]
        },
        "min_duration_sec": 300,  # Must be stuck for 5+ minutes
    },

    # ── Scenario 7: Long Absence ──────────────────────────
    # Nobody home for a long time
    {
        "scenario": "Long Absence",
        "emotion": "tired",
        "conditions": {
            "face_present": False,
            "input_rate": "low",
            "speech_active": False,
        },
        "min_duration_sec": 1800,  # 30 minutes away
    },

    # ── Default / Fallback ─────────────────────────────────
    # User present but nothing specific happening
    {
        "scenario": "Idle Ambient",
        "emotion": "relaxed",
        "conditions": {
            "face_present": True,
        },
        "min_duration_sec": 0,
    },
]


# ─────────────────────────────────────────────────────────────
# MATCHING FUNCTION
# ─────────────────────────────────────────────────────────────

def match_context(current_state: dict, prev_state: dict, duration_sec: float) -> tuple:
    """
    Find the best matching rule for the current sensor state.
    
    Returns: (emotion_name, scenario_name)
    
    current_state: current readings from SensorState.get()
    prev_state: previous snapshot from SensorState.get_prev()
    duration_sec: how long current state has been active
    """
    import datetime
    current_hour = datetime.datetime.now().hour

    for rule in CONTEXT_RULES:
        # Check main conditions
        if not _check_conditions(current_state, rule["conditions"]):
            continue

        # Check time condition if present
        if "time_condition" in rule:
            hour_range = rule["time_condition"].get("hour_range")
            if hour_range:
                if not (hour_range[0] <= current_hour < hour_range[1]):
                    continue

        # Check transition requirement if present
        if "requires_transition_from" in rule:
            if not _check_transition(prev_state, rule["requires_transition_from"]):
                continue

        # Check minimum duration
        if duration_sec < rule.get("min_duration_sec", 0):
            continue

        # All checks passed - this rule matches
        return rule["emotion"], rule["scenario"]

    # No rule matched
    return "relaxed", "Default"


def _check_conditions(state: dict, conditions: dict) -> bool:
    """Check if current state matches all conditions in a rule."""
    for key, expected in conditions.items():
        actual = state.get(key)
        if actual is None:
            return False

        if isinstance(expected, list):
            # Condition accepts multiple values
            if actual not in expected:
                return False
        else:
            # Condition requires exact value
            if actual != expected:
                return False

    return True


def _check_transition(prev_state: dict, transition_conditions: dict) -> bool:
    """Check if the previous state matches the required 'came from' conditions."""
    return _check_conditions(prev_state, transition_conditions)
