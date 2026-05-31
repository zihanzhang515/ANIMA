"""
understand/context_pipeline.py
--------------------------------
Slow understanding layer: evaluates the scene every CHECK_INTERVAL seconds.

Changes in v2:
  - Integrated three time-query methods from sensor_state
  - Added Curious/Confused time-dimension distinction logic
  - Added Tired session-duration check
  - match_context() now receives session_duration_sec
  - Dual parameter sets for test mode and production mode
"""

import time
import threading
import datetime
from sense.sensor_state import shared_state
from config.context_rules_study import CONTEXT_RULES, match_context
from config.emotions import get_emotion

# ── Mode switch (change this one line to toggle all timing parameters) ──
MODE = "test"   # "test" = fast validation  |  "real" = production

if MODE == "test":
    CHECK_INTERVAL   = 7      # Evaluate every 7s (with CONFIRM_THRESHOLD=2, confirmation takes 14s)
    CURIOUS_WINDOW   = 10     # Inactive < 10s → Curious
    CONFUSED_WINDOW  = 30     # Inactive > 30s → Confused
    ACTIVE_LOOKBACK  = 60     # Check for high activity within the past 1 minute
    TIRED_SESSION    = 600    # Present for 10 minutes → Tired (test value)
    TIRED_HOUR       = 20     # 8 PM (test value)
else:
    CHECK_INTERVAL   = 30     # Evaluate every 30s
    CURIOUS_WINDOW   = 90     # Inactive < 90s → Curious
    CONFUSED_WINDOW  = 180    # Inactive > 180s → Confused
    ACTIVE_LOOKBACK  = 300    # Check for high activity within the past 5 minutes
    TIRED_SESSION    = 1800   # Present for 30 minutes → Tired
    TIRED_HOUR       = 23     # 11 PM (production)


class ContextPipeline:
    def __init__(self, on_emotion_change=None):
        """
        on_emotion_change: callback(emotion_name, scenario_name, params)
        """
        self.on_emotion_change  = on_emotion_change
        self.current_emotion    = "relaxed"
        self.current_scenario   = "Default"
        self.emotion_entered_at = time.time()

        # Minimum hold time per emotion (seconds).
        # Prevents switching away too quickly even if signals change.
        self.EMOTION_MIN_HOLD = {
            "focus":    45,   # Focus: hold at least 45s; don't drop just because typing paused
            "happy":    30,
            "curious":  20,
            "tired":    30,
            "confused": 30,
            "listen":   15,
            "relaxed":  0,
        }

        # Maximum hold time per emotion → force return to relaxed on expiry ("one-shot notification" semantics).
        # None means unlimited (emotion persists until overridden by a new signal).
        self.EMOTION_MAX_HOLD = {
            "tired":    120,  # Tired: max 2 minutes, then "already notified" → relaxed
            "curious":  60,   # Curious: max 1 minute without new activity → relaxed
            "confused": 120,  # Confused: max 2 minutes → relaxed
        }

        # Candidate confirmation: the same emotion must appear N consecutive times before switching (debounce).
        self._pending_emotion   = None
        self._pending_scenario  = None
        self._pending_count     = 0
        self.CONFIRM_THRESHOLD  = 2   # 2 consecutive evaluations required; at CHECK_INTERVAL=7s, that is 14s

        self._stop_event = threading.Event()

    # ── Thread management ──────────────────────────────────────────────────

    def start(self):
        thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ContextPipeline"
        )
        thread.start()
        print(f"[UNDERSTAND] Context pipeline started. MODE={MODE}, interval={CHECK_INTERVAL}s")
        return thread

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(CHECK_INTERVAL)
            self._evaluate()

    # ── Core evaluation logic ──────────────────────────────────────────────

    def _evaluate(self):
        from express.study_manager import study_manager
        if study_manager.is_paused:
            return

        current          = shared_state.get()
        previous         = shared_state.get_prev()
        session_duration = shared_state.get_session_duration()
        inactive_secs    = shared_state.get_inactive_duration()
        active_secs      = shared_state.get_active_duration()
        absent_secs      = shared_state.get_absent_duration()
        was_active       = shared_state.was_recently_active(ACTIVE_LOOKBACK)

        changes = shared_state.count_changes()
        print(f"\n[UNDERSTAND] ── Evaluate ── {changes} signal change(s)")
        print(f"  face={current['face_present']} | speech={current['speech_active']} | "
              f"audio={current['audio_category']} | input={current['input_rate']}")
        print(f"  inactive={inactive_secs:.0f}s | session={session_duration:.0f}s | "
              f"was_active={was_active}")

        # Step 1: Base rule matching
        new_emotion, new_scenario = match_context(current, previous, inactive_secs)

        # Step 2: Time-dimension overrides
        new_emotion, new_scenario = self._apply_time_overrides(
            new_emotion, new_scenario,
            current, inactive_secs, was_active, session_duration, active_secs, absent_secs
        )

        # Step 2.5: Memory anticipation (disabled for Study 3 to isolate individual triggers)
        """
        if new_emotion == "relaxed" and current["face_present"]:
            try:
                from memory.memory_store import get_preemptive_emotion
                now_dt = datetime.datetime.now()
                preemptive = get_preemptive_emotion(now_dt.hour, now_dt.weekday())
                if preemptive and preemptive != self.current_emotion:
                    print(f"[UNDERSTAND] Memory anticipation: {preemptive} ({now_dt.hour:02d}:xx habit)")
                    new_emotion = preemptive
                    new_scenario = "Memory Anticipated"
            except Exception as mem_err:
                print(f"[UNDERSTAND] Memory anticipation query failed: {mem_err}")
        """

        # Step 3: Generate token (raw sensor data is discarded here)
        token = self._generate_token(current, new_emotion, new_scenario)
        print(f"[UNDERSTAND] Token: {token}")

        # Append token to log file
        try:
            import os
            log_dir  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "token_log.txt")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"[{ts}] {token}\n")
        except Exception as log_err:
            print(f"[UNDERSTAND] Token log write failed: {log_err}")

        # Step 4: Write to memory (only non-relaxed emotions)
        # Study 3: restricted to explicit emotions to avoid noise records
        if new_emotion != "relaxed":
            try:
                from memory.memory_store import save_event
                save_event(token, new_emotion, new_scenario, current)
            except Exception as e:
                print(f"[UNDERSTAND] Memory write failed: {e}")

        # Step 5: Candidate confirmation + emotion switch
        # Check max hold: force return to relaxed if current emotion has expired
        time_in_current = time.time() - self.emotion_entered_at
        max_hold = self.EMOTION_MAX_HOLD.get(self.current_emotion)
        if max_hold and time_in_current >= max_hold:
            print(f"[UNDERSTAND] {self.current_emotion} exceeded max hold {max_hold}s → relaxed")
            self.current_emotion    = "relaxed"
            self.current_scenario   = "Idle Ambient"
            self.emotion_entered_at = time.time()
            self._pending_emotion   = None
            self._pending_count     = 0
            shared_state.update("current_emotion", "relaxed")
            if self.on_emotion_change:
                params = get_emotion("relaxed")
                self.on_emotion_change("relaxed", "Idle Ambient", params)
            shared_state.save_snapshot()
            return

        if new_emotion != self.current_emotion:
            if new_emotion == self._pending_emotion:
                self._pending_count += 1
            else:
                # New candidate; reset count
                self._pending_emotion  = new_emotion
                self._pending_scenario = new_scenario
                self._pending_count    = 1

            if self._pending_count >= self.CONFIRM_THRESHOLD:
                # Candidate confirmed: check min hold
                time_in_current = time.time() - self.emotion_entered_at
                min_hold = self.EMOTION_MIN_HOLD.get(self.current_emotion, 0)

                if time_in_current < min_hold:
                    print(f"[UNDERSTAND] Switch blocked: {self.current_emotion} only held "
                          f"{int(time_in_current)}s (min {min_hold}s required)")
                else:
                    print(f"[UNDERSTAND] Emotion switch ({self._pending_count} confirmations): "
                          f"{self.current_emotion} → {new_emotion} ({new_scenario})")
                    self.current_emotion    = new_emotion
                    self.current_scenario   = new_scenario
                    self.emotion_entered_at = time.time()
                    shared_state.update("current_emotion", new_emotion)
                    self._pending_emotion = None
                    self._pending_count   = 0

                    if self.on_emotion_change:
                        params = get_emotion(new_emotion)
                        self.on_emotion_change(new_emotion, new_scenario, params)
            else:
                print(f"[UNDERSTAND] Candidate ({self._pending_count}/{self.CONFIRM_THRESHOLD}): "
                      f"{self.current_emotion} → {new_emotion}, awaiting confirmation")
        else:
            # Current emotion confirmed; reset candidate
            self._pending_emotion = None
            self._pending_count   = 0
            print(f"[UNDERSTAND] Emotion unchanged: {self.current_emotion}")

        shared_state.update("current_emotion", self.current_emotion)
        shared_state.save_snapshot()

    # ── Time-dimension overrides ───────────────────────────────────────────

    def _apply_time_overrides(
        self,
        emotion: str,
        scenario: str,
        current: dict,
        inactive_secs: float,
        was_active: bool,
        session_duration: float,
        active_secs: float,
        absent_secs: float
    ) -> tuple:
        """
        Apply time-dimension logic on top of the rule-table match result.

        Handles four cases:
        1. Curious vs Confused: distinguished by inactive_secs
        2. Tired: triggered when session_duration exceeds threshold
        3. Relaxed vs Curious: no prior active period → not Curious
        4. Focus / Happy: require minimum active_secs
        5. Long Absence: validated by absent_secs
        """

        # Override 1: Long Absence guard (prevent flicker)
        if scenario == "Long Absence":
            absent_target = 60 if MODE == "test" else 1800
            if absent_secs < absent_target:
                print(f"[UNDERSTAND] Time intercept: absent {absent_secs:.0f}s < {absent_target}s → relaxed")
                return "relaxed", "Idle Ambient"

        # Override 0.5: Proactive curious/confused detection
        # Regardless of rule-table result, if was_active + input=low, evaluate directly
        if (current["face_present"]
                and was_active
                and not current["speech_active"]
                and current["input_rate"] == "low"):
            if inactive_secs >= CONFUSED_WINDOW:
                print(f"[UNDERSTAND] Proactive: inactive {inactive_secs:.0f}s >= {CONFUSED_WINDOW}s → confused")
                return "confused", "Stuck"
            elif inactive_secs >= CURIOUS_WINDOW:
                print(f"[UNDERSTAND] Proactive: inactive {inactive_secs:.0f}s >= {CURIOUS_WINDOW}s → curious")
                return "curious", "Daydreaming"
            # inactive_secs < CURIOUS_WINDOW: no intervention, continue to next checks

        # Override 0: Focus and Happy require minimum active duration
        if emotion == "focus":
            focus_target = 30 if MODE == "test" else 600
            if active_secs < focus_target:
                print(f"[UNDERSTAND] Time intercept: active {active_secs:.0f}s < {focus_target}s, focus not valid → relaxed")
                return "relaxed", "Idle Ambient"

        if emotion == "happy":
            if previous.get("current_emotion") == "tired":
                print("[UNDERSTAND] Transition blocked: cannot jump directly from tired to happy → hold tired")
                return "tired", "Fatigue"

            happy_target = 15 if MODE == "test" else 60
            if active_secs < happy_target:
                print(f"[UNDERSTAND] Time intercept: active {active_secs:.0f}s < {happy_target}s, happy not valid → relaxed")
                return "relaxed", "Idle Ambient"

        if emotion == "tired" and scenario == "Fatigue":
            tired_target = 45 if MODE == "test" else 480
            if session_duration < tired_target:
                print(f"[UNDERSTAND] Time intercept: session {session_duration:.0f}s < {tired_target}s, tired not valid → relaxed")
                return "relaxed", "Idle Ambient"

        # Override 1: Curious vs Confused — time-based distinction
        if emotion in ("curious", "confused"):
            if not was_active:
                # No high activity in the past ACTIVE_LOOKBACK seconds:
                # user was already low-activity, not "stopped" — should be Relaxed, not Curious
                print(f"[UNDERSTAND] Override: {emotion} → relaxed (no prior active period)")
                return "relaxed", "Idle Ambient"

            if inactive_secs == 0.0:
                # Currently still active; neither state applies
                pass

            elif inactive_secs < CURIOUS_WINDOW:
                print(f"[UNDERSTAND] Time override: inactive {inactive_secs:.0f}s < {CURIOUS_WINDOW}s → curious")
                return "curious", "Active Break"

            elif inactive_secs >= CONFUSED_WINDOW:
                print(f"[UNDERSTAND] Time override: inactive {inactive_secs:.0f}s >= {CONFUSED_WINDOW}s → confused")
                return "confused", "Stuck"

            else:
                # Grey zone (CURIOUS_WINDOW ~ CONFUSED_WINDOW): hold as curious
                print(f"[UNDERSTAND] Time override: inactive {inactive_secs:.0f}s in grey zone → hold curious")
                return "curious", "Active Break"

        # Override 2: Session duration → Tired (production mode only)
        # In test mode, tired is triggered only via the Late Night rule
        if MODE != "test":
            if (current["face_present"]
                    and session_duration >= TIRED_SESSION
                    and current["input_rate"] in ("low", "medium")
                    and not current["speech_active"]
                    and emotion not in ("happy", "listen", "focus", "tired")):
                print(f"[UNDERSTAND] Time override: session {session_duration:.0f}s → tired")
                return "tired", "Extended Session"

        return emotion, scenario

    # ── Token generation (raw data is discarded here) ─────────────────────

    def _generate_token(self, state: dict, emotion: str, scenario: str) -> str:
        """
        Generate an abstract memory token.
        Format: <scenario, HH:00, Weekday/Weekend, emotion>

        Raw sensor data is not stored — only this abstract label.
        This is the key privacy-preserving step.
        # RAW SENSOR DATA DISCARDED HERE
        """
        now      = datetime.datetime.now()
        hour_str = f"{now.hour:02d}:00"
        day_type = "Weekend" if now.weekday() >= 5 else "Weekday"
        return f"<{scenario}, {hour_str}, {day_type}, {emotion}>"
