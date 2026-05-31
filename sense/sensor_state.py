"""
sense/sensor_state.py
---------------------
Thread-safe shared state for all 5 sensor signals.

Changes in v2:
  - Added audio_spike field (required by Alert reflex)
  - Added internal time tracking: last_high_activity_time / input_zero_since / session_start_time
  - Added query methods: get_inactive_duration() / was_recently_active() / get_session_duration()
  - update() maintains time tracking automatically; external modules need no extra calls
"""

import threading
import time


class SensorState:
    def __init__(self):
        self._lock = threading.Lock()

        # ── Five core signals ──
        self._state = {
            "face_present":   False,      # S1
            "face_x":         0.5,        # S2  (0.0=left / 0.5=centre / 1.0=right)
            "face_size":      0.0,        # S2b  apparent face size (bbox.width), proxy for proximity
            "speech_active":  False,      # S3
            "audio_category": "silence",  # S4  silence/speech/music/alert_spike
            "audio_spike":    False,      # S4b  sudden sound burst, used by Alert reflex
            "audio_rms":      0.0,
            "input_rate":     "low",      # S5  low/medium/high
            "current_emotion": "relaxed",
            "last_updated":   time.time(),
        }

        # ── Previous-frame snapshot (used for transition detection) ──
        self._prev_state = self._state.copy()

        # ── Internal time tracking (not exposed in _state) ──
        # Timestamp of the last high/medium input_rate event
        self._last_high_activity_time: float = 0.0
        self._high_activity_start_time: float = 0.0
        # Timestamp when input_rate dropped to low (used for Curious/Confused distinction)
        self._input_zero_since: float = 0.0
        # Timestamp when the user first appeared (face_present: False → True)
        self._session_start_time: float = 0.0
        self._face_absent_since: float = 0.0
        # Start time of the current state (used for min_duration checks)
        self._state_start_time: float = time.time()

    # ─────────────────────────────────────────
    # 写入
    # ─────────────────────────────────────────

    def update(self, key: str, value):
        """Update a single signal; time tracking is maintained automatically."""
        with self._lock:
            if key not in self._state:
                return
            if self._state[key] == value:
                return  # 无变化，不更新

            self._state[key] = value
            self._state["last_updated"] = time.time()
            now = time.time()

            # ── Maintain time tracking on input_rate change ──
            if key == "input_rate":
                if value in ("high", "medium"):
                    self._last_high_activity_time = now
                    self._input_zero_since = 0.0   # Reset inactivity timer
                    if getattr(self, "_high_activity_start_time", 0.0) == 0.0:
                        self._high_activity_start_time = now
                elif value == "low":
                    self._high_activity_start_time = 0.0
                    if self._input_zero_since == 0.0:
                        self._input_zero_since = now  # Begin inactivity timing

            # ── Reset session timer when face_present transitions False → True ──
            if key == "face_present":
                if value is True:
                    self._session_start_time = now
                    self._face_absent_since = 0.0
                else:
                    self._session_start_time = 0.0
                    if getattr(self, "_face_absent_since", 0.0) == 0.0:
                        self._face_absent_since = now

    # ─────────────────────────────────────────
    # 读取基础状态
    # ─────────────────────────────────────────

    def force_update(self, key: str, value):
        """Force-write a value even if unchanged (used for initialisation broadcast)."""
        with self._lock:
            if key not in self._state:
                return
            self._state[key] = value
            self._state["last_updated"] = time.time()

    def get(self) -> dict:
        """Return a thread-safe copy of the current signal snapshot."""
        with self._lock:
            return self._state.copy()

    def get_prev(self) -> dict:
        """Return the previous-frame snapshot."""
        with self._lock:
            return self._prev_state.copy()

    def count_changes(self) -> int:
        """统计自上次快照以来有多少信号发生了变化。"""
        keys = ["face_present", "face_x", "speech_active",
                "audio_category", "input_rate"]
        with self._lock:
            return sum(
                1 for k in keys
                if self._state[k] != self._prev_state.get(k)
            )

    def save_snapshot(self):
        """把当前状态存为 prev，重置 state_start_time。"""
        with self._lock:
            self._prev_state = {k: v for k, v in self._state.items()}
            self._state_start_time = time.time()

    def get_state_duration(self) -> float:
        """当前状态已持续多少秒。"""
        return time.time() - self._state_start_time

    # ── Time-dimension queries (used by Curious/Confused/Tired logic) ──────

    def get_active_duration(self) -> float:
        """Seconds of continuous high/medium input activity."""
        with self._lock:
            start_time = getattr(self, "_high_activity_start_time", 0.0)
            if start_time == 0.0:
                return 0.0
            return time.time() - start_time

    def get_inactive_duration(self) -> float:
        """
        Seconds since input_rate dropped to low.
        Used to distinguish Curious (<90s) from Confused (>180s).
        Returns 0 if currently active or never been active.
        """
        with self._lock:
            if self._input_zero_since == 0.0:
                return 0.0
            return time.time() - self._input_zero_since

    def was_recently_active(self, window_sec: float = 300.0) -> bool:
        """
        Returns True if there has been any high/medium activity within the past window_sec seconds.
        Used to distinguish Relaxed (never active) from Curious/Confused (was previously active).
        """
        with self._lock:
            if self._last_high_activity_time == 0.0:
                return False
            return (time.time() - self._last_high_activity_time) < window_sec

    def get_absent_duration(self) -> float:
        """Seconds the user has been continuously absent (face not detected)."""
        with self._lock:
            start = getattr(self, "_face_absent_since", 0.0)
            if start == 0.0:
                return 0.0
            return time.time() - start

    def get_session_duration(self) -> float:
        """
        Seconds the user has been continuously present (face_present duration).
        Used to trigger Tired based on accumulated session time (30 minutes in production).
        """
        with self._lock:
            if self._session_start_time == 0.0:
                return 0.0
            return time.time() - self._session_start_time

    def get_face_x_zone(self) -> str:
        """Convert face_x float to a zone label: left / center / right."""
        with self._lock:
            x = self._state["face_x"]
        if x < 0.35:
            return "left"
        elif x > 0.65:
            return "right"
        return "center"


# Global singleton
shared_state = SensorState()

