"""
understand/context_pipeline.py
-------------------------------
The 10-15 minute context understanding layer.

Every CHECK_INTERVAL seconds:
1. Check how many signals changed (3+ = meaningful event)
2. Match current state against context rules
3. If emotion changed → trigger new emotion
4. Generate abstract memory token
5. Write to memory store

This is the "slow thinking" part of the system.
"""

import time
import threading
import datetime
from sense.sensor_state import shared_state
from config.context_rules import match_context
from config.emotions import get_emotion

# How often to check for context changes (seconds)
CHECK_INTERVAL = 30   # Check every 30s during development, raise to 600 for production

# Minimum signals that must change to trigger a re-evaluation
MIN_SIGNAL_CHANGES = 3


class ContextPipeline:
    def __init__(self, on_emotion_change=None):
        """
        on_emotion_change: callback(emotion_name, scenario_name, params)
        Called whenever the active emotion should change.
        """
        self.on_emotion_change = on_emotion_change
        self.current_emotion = "relaxed"
        self.current_scenario = "Default"
        self.emotion_entered_at = time.time()  # ← 新增：记录当前情绪开始时间
        
        # 每个情绪的最短持续时间（秒）
        # 在这段时间内，即使状态改变，情绪也不会退出
        self.EMOTION_MIN_HOLD = {
            "focus":    300,   # Focus至少保持5分钟
            "happy":    60,    # Happy至少保持1分钟
            "curious":  120,   # Curious至少保持2分钟
            "tired":    180,   # Tired至少保持3分钟
            "confused": 120,
            "listen":   30,
            "relaxed":  0,     # Relaxed随时可以改变
        }
        self._stop_event = threading.Event()

    def start(self):
        """Start context pipeline in a background thread."""
        thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ContextPipeline"
        )
        thread.start()
        print("[UNDERSTAND] Context pipeline started.")
        return thread

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(CHECK_INTERVAL)
            self._evaluate()

    def _evaluate(self):
        """One evaluation cycle."""
        current = shared_state.get()
        previous = shared_state.get_prev()
        duration = shared_state.get_state_duration()

        # Count how many signals changed
        changes = shared_state.count_changes()

        print(f"[UNDERSTAND] Evaluating... {changes} signal(s) changed")
        print(f"[UNDERSTAND] State: face={current['face_present']} "
              f"speech={current['speech_active']} "
              f"audio={current['audio_category']} "
              f"input={current['input_rate']}")

        # Match current state against rules
        new_emotion, new_scenario = match_context(current, previous, duration)

        # Generate memory token regardless of whether emotion changed
        token = self._generate_token(current, new_emotion, new_scenario)
        print(f"[UNDERSTAND] Token: {token}")

        # Save to memory (import here to avoid circular imports)
        try:
            from memory.memory_store import save_event
            save_event(token, new_emotion, new_scenario, current)
        except Exception as e:
            print(f"[UNDERSTAND] Memory write failed: {e}")

        # Did the emotion change?
        if new_emotion != self.current_emotion:
            # 检查当前情绪是否已经持续足够久了
            time_in_current = time.time() - self.emotion_entered_at
            min_hold = self.EMOTION_MIN_HOLD.get(self.current_emotion, 0)
            
            if time_in_current < min_hold:
                # 还没到最短持续时间，不退出
                print(f"[UNDERSTAND] 忽略情绪变化请求（{self.current_emotion} 只持续了 {int(time_in_current)}s，最少需要 {min_hold}s）")
                shared_state.save_snapshot()
                return
            
            # 可以切换了
            print(f"[UNDERSTAND] Emotion: {self.current_emotion} → {new_emotion} ({new_scenario})")
            self.current_emotion = new_emotion
            self.current_scenario = new_scenario
            self.emotion_entered_at = time.time()  # 重置计时

            # Notify the express layer
            if self.on_emotion_change:
                params = get_emotion(new_emotion)
                self.on_emotion_change(new_emotion, new_scenario, params)
        else:
            print(f"[UNDERSTAND] Emotion unchanged: {self.current_emotion}")

        # Save current state as previous for next cycle
        shared_state.save_snapshot()

    def _generate_token(self, state: dict, emotion: str, scenario: str) -> str:
        """
        Generate an abstract memory token.
        Format: <Scenario, HH:00, Weekday/Weekend>
        
        Raw sensor data is NOT stored - only this abstract label.
        This is the privacy-preserving step.
        """
        now = datetime.datetime.now()
        hour_str = f"{now.hour:02d}:00"
        day_type = "Weekend" if now.weekday() >= 5 else "Weekday"

        return f"<{scenario}, {hour_str}, {day_type}, {emotion}>"
