"""
understand/realtime_pipeline.py
--------------------------------
The real-time reaction layer (<100ms).

Handles:
1. Face tracking → head follows user's face position
2. Reflex triggers → Alert (sudden noise), Shy (face too close)

These are Tier 2 behaviors - they execute immediately and
do NOT change the state machine's current emotion.

Runs continuously in its own thread.
"""

import time
import threading
from sense.sensor_state import shared_state
from config.emotions import EMOTION_PARAMS

# Realtime check frequency
REALTIME_INTERVAL = 0.05  # 50ms = 20Hz

# Thresholds for reflex triggers
FACE_CLOSE_THRESHOLD = 0.15   # face_x very near center AND large detected area
# TODO: Add face size detection for proximity
AUDIO_SPIKE_THRESHOLD = 0.12  # RMS threshold for Alert (calibrate after testing)

# Cooldown tracking
_last_reflex_time = {
    "alert": 0,
    "shy": 0,
}
COOLDOWNS = {
    "alert": 10,   # seconds
    "shy": 30,     # seconds
}


class RealtimePipeline:
    def __init__(self, on_face_track=None, on_reflex=None):
        """
        on_face_track: callback(yaw_angle) - called every frame when face detected
        on_reflex: callback(reflex_name, params) - called when reflex triggers
        """
        self.on_face_track = on_face_track
        self.on_reflex = on_reflex
        self._stop_event = threading.Event()

    def start(self):
        """Start realtime pipeline in a background thread."""
        thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="RealtimePipeline"
        )
        thread.start()
        print("[REALTIME] Pipeline started.")
        return thread

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            state = shared_state.get()

            # 1. Face tracking
            if state["face_present"] and self.on_face_track:
                # Map face_x (0.0-1.0) to servo yaw angle (70°-110°)
                # face_x=0.0 (far left) → head turns left (70°)
                # face_x=0.5 (center) → head center (90°)
                # face_x=1.0 (far right) → head turns right (110°)
                yaw = int(70 + state["face_x"] * 40)
                yaw = max(70, min(110, yaw))
                self.on_face_track(yaw)

            # 2. Check for reflex triggers
            self._check_reflexes(state)

            time.sleep(REALTIME_INTERVAL)

    def _check_reflexes(self, state: dict):
        """Check if any reflex behavior should trigger."""
        now = time.time()

        # Alert: Sudden loud noise
        # TODO: Need audio spike detection from audio_detector
        # For now, checking audio_category change as proxy
        # Will improve when raw RMS is exposed from audio_detector

        # Shy: Face suddenly very close
        # Simple heuristic: face_x very near 0.5 (directly in front)
        # Better detection needs face bbox size - TODO
        if state["face_present"]:
            face_centered = abs(state["face_x"] - 0.5) < 0.1  # Very centered
            if face_centered:
                self._trigger_reflex("shy", now)

    def _trigger_reflex(self, name: str, now: float):
        """Trigger a reflex if cooldown has passed."""
        cooldown = COOLDOWNS.get(name, 15)
        if now - _last_reflex_time.get(name, 0) > cooldown:
            _last_reflex_time[name] = now
            params = EMOTION_PARAMS.get(f"reflex_{name}", {})
            print(f"[REALTIME] Reflex triggered: {name}")
            if self.on_reflex:
                self.on_reflex(name, params)
