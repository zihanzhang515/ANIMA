"""
sense/sensor_state.py
---------------------
Thread-safe shared state container for all 5 sensor signals.
All sense modules write here. understand layer reads from here.
"""

import threading
import time


class SensorState:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            # S1: Is the user's face visible?
            "face_present": False,

            # S2: Where is the face horizontally? (0.0=far left, 0.5=center, 1.0=far right)
            "face_x": 0.5,

            # S3: Is someone speaking right now?
            "speech_active": False,

            # S4: What kind of audio is happening?
            # Values: "silence" / "keyboard" / "speech" / "music"
            "audio_category": "silence",

            # S5: How active is keyboard/mouse?
            # Values: "low" / "medium" / "high"
            "input_rate": "low",

            # When was the state last updated?
            "last_updated": time.time(),
        }

        # Track previous state for transition detection
        self._prev_state = self._state.copy()
        self._state_start_time = time.time()  # When did current state begin?

    def update(self, key: str, value):
        """Update a single signal value."""
        with self._lock:
            if key in self._state and self._state[key] != value:
                self._state[key] = value
                self._state["last_updated"] = time.time()

    def get(self) -> dict:
        """Get a snapshot of current state (thread-safe copy)."""
        with self._lock:
            return self._state.copy()

    def get_prev(self) -> dict:
        """Get a snapshot of previous state."""
        with self._lock:
            return self._prev_state.copy()

    def count_changes(self) -> int:
        """Count how many signals changed since last snapshot."""
        with self._lock:
            changes = 0
            for key in ["face_present", "face_x", "speech_active",
                        "audio_category", "input_rate"]:
                if self._state[key] != self._prev_state.get(key):
                    changes += 1
            return changes

    def save_snapshot(self):
        """Save current state as previous state (call after checking for events)."""
        with self._lock:
            self._prev_state = {k: v for k, v in self._state.items()}
            self._state_start_time = time.time()

    def get_state_duration(self) -> float:
        """How many seconds has current state been active?"""
        return time.time() - self._state_start_time


# Global singleton - import this in all modules
shared_state = SensorState()
