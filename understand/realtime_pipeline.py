"""
understand/realtime_pipeline.py — v5

Shy 触发逻辑完全重写：
- 不再检测 face_x 位置（正常坐着就居中，没意义）
- 改为检测脸部大小突然增大（人往前靠近摄像头）
- 触发条件：face_size 在 1 秒内增大超过 SHY_SIZE_DELTA
  且增大后的 face_size 超过 SHY_SIZE_MIN（确认真的很近了）

正常坐着使用电脑：face_size ≈ 0.10~0.20
明显靠近摄像头：face_size > 0.30~0.35
"""

import time
import random
import threading
from sense.sensor_state import shared_state
from config.emotions import EMOTION_PARAMS

REALTIME_INTERVAL = 0.05

IDLE_MIN_SEC = 8
IDLE_MAX_SEC = 20

COOLDOWNS = {
    "alert": 8,
    "shy":   45,
}
_last_reflex_time = {"alert": 0, "shy": 0}

TRACKING_EMOTIONS  = {"listen", "curious"}
NO_REFLEX_EMOTIONS = {"focus", "tired"}

# ─── Shy 检测参数 ─────────────────────────────────────────────
# 脸部大小基线（用滑动平均记录"正常"距离）
_face_size_baseline  = 0.15    # 初始估计，运行时会自动校准
_BASELINE_ALPHA      = 0.02    # 基线更新速度（慢速适应，不被瞬时值影响）

SHY_SIZE_DELTA       = 0.10    # 比基线大这么多才算"突然靠近"
SHY_SIZE_MIN         = 0.35    # 靠近后脸部至少要这么大才触发
SHY_SUSTAIN_SEC      = 1.5     # 需要持续靠近 1.5 秒才触发

_shy_approach_start  = 0.0     # 开始靠近的时间


class RealtimePipeline:
    def __init__(self, on_face_track=None, on_reflex=None, on_idle=None):
        self.on_face_track = on_face_track
        self.on_reflex     = on_reflex
        self.on_idle       = on_idle
        self._stop_event   = threading.Event()
        self._next_idle_time = time.time() + random.uniform(IDLE_MIN_SEC, IDLE_MAX_SEC)
        self.current_emotion = "relaxed"

    def set_emotion(self, emotion_name: str):
        self.current_emotion = emotion_name
        self._next_idle_time = time.time() + random.uniform(IDLE_MIN_SEC, IDLE_MAX_SEC)

    def start(self):
        thread = threading.Thread(
            target=self._run, daemon=True, name="RealtimePipeline"
        )
        thread.start()
        # ← 加这个 idle 线程
        idle_thread = threading.Thread(
            target=self._idle_loop, daemon=True, name="IdleScheduler"
        )
        idle_thread.start()
    
        print("[REALTIME] Pipeline started.")
        print(f"[REALTIME] Shy: 脸部需比基线大 {SHY_SIZE_DELTA:.0%}，"
              f"且大于 {SHY_SIZE_MIN:.0%}，持续 {SHY_SUSTAIN_SEC}s")
        return thread
    
    def _idle_loop(self):
        """每 8-20 秒向 Arduino 发送 idle 命令"""
        while not self._stop_event.is_set():
            wait_time = random.uniform(8, 20)
            self._stop_event.wait(timeout=wait_time)
            if not self._stop_event.is_set() and self.on_idle:
                self.on_idle()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        global _face_size_baseline, _shy_approach_start

        while not self._stop_event.is_set():
            state = shared_state.get()
            now   = time.time()

            # ── Face tracking（仅 listen/curious）────────────
            if state["face_present"] and self.on_face_track:
                if self.current_emotion in TRACKING_EMOTIONS:
                    yaw = int(40 + state["face_x"] * 40)
                    yaw = max(20, min(100, yaw))
                    self.on_face_track(yaw)

            # ── 更新脸部大小基线（慢速移动平均）──────────────
            if state["face_present"] and state["face_size"] > 0:
                _face_size_baseline = (
                    _BASELINE_ALPHA * state["face_size"]
                    + (1 - _BASELINE_ALPHA) * _face_size_baseline
                )

            # ── Idle 定时触发 ─────────────────────────────────
            if now >= self._next_idle_time:
                if self.on_idle:
                    self.on_idle()
                self._next_idle_time = now + random.uniform(IDLE_MIN_SEC, IDLE_MAX_SEC)

            # ── 反射检测 ─────────────────────────────────────
            if self.current_emotion not in NO_REFLEX_EMOTIONS:
                self._check_alert(state, now)
                self._check_shy(state, now)

            time.sleep(REALTIME_INTERVAL)

    def _check_alert(self, state: dict, now: float):
        if state.get("audio_spike") and \
           now - _last_reflex_time["alert"] > COOLDOWNS["alert"]:
            _last_reflex_time["alert"] = now
            params = EMOTION_PARAMS.get("reflex_alert", {})
            print("[REALTIME] ⚡ Alert triggered")
            if self.on_reflex:
                self.on_reflex("alert", params)

    def _check_shy(self, state: dict, now: float):
        global _shy_approach_start

        if not state["face_present"]:
            _shy_approach_start = 0.0
            return

        face_size = state.get("face_size", 0.0)

        # 判断是否"突然靠近"：
        # 1. 脸部大小明显超过当前基线
        # 2. 脸部大小超过绝对阈值（确认真的很近）
        is_approaching = (
            face_size > _face_size_baseline + SHY_SIZE_DELTA and
            face_size > SHY_SIZE_MIN
        )

        if is_approaching:
            if _shy_approach_start == 0.0:
                _shy_approach_start = now
                print(f"[REALTIME] 😳 Shy: 检测到靠近 "
                      f"size={face_size:.2f} baseline={_face_size_baseline:.2f}")
            elif now - _shy_approach_start >= SHY_SUSTAIN_SEC:
                if now - _last_reflex_time["shy"] > COOLDOWNS["shy"]:
                    _last_reflex_time["shy"] = now
                    _shy_approach_start = 0.0
                    params = EMOTION_PARAMS.get("reflex_shy", {})
                    print("[REALTIME] 😳 Shy triggered!")
                    if self.on_reflex:
                        self.on_reflex("shy", params)
        else:
            # 脸部没有持续靠近，重置计时
            if _shy_approach_start != 0.0:
                _shy_approach_start = 0.0

