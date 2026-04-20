"""
understand/realtime_pipeline.py
--------------------------------
实时反射层（<100ms）。

处理：
  1. Face tracking — 头部跟随用户脸部位置
  2. Alert reflex — 突发声音触发（接入 audio_spike）
  3. Shy reflex   — 用户靠近触发（修复触发逻辑）

v2 改动：
  - Alert 接入 shared_state["audio_spike"]（原来是 TODO）
  - Shy 修复触发条件（原来是 face_centered，现在加面部尺寸代理判断）
  - 冷却逻辑改为实例变量，避免全局状态
"""

import time
import threading
from sense.sensor_state import shared_state
from config.emotions import EMOTION_PARAMS

# 检查频率
REALTIME_INTERVAL = 0.05   # 50ms = 20Hz

# Shy 触发：人脸视在大小迅速增大（代理局部快速靠近）
# face_size = bbox.width，正常工作距离大约 0.15~0.30
# 超过 SHY_SIZE_THRESHOLD 认为靠近
SHY_SIZE_THRESHOLD    = 0.40   # bbox.width > 0.40 认为用户明显靠近
SHY_MIN_DELTA         = 0.12   # 当前帧比历史均值大 0.12（即迅速靠近）也触发
SHY_TRIGGER_FRAMES    = 6      # 需要连续 6 帧超阈值（约 0.3s）

# 冷却时间
COOLDOWNS = {
    "alert": 10,   # 秒
    "shy":   60,   # 秒
}


class RealtimePipeline:
    def __init__(self, on_face_track=None, on_reflex=None):
        """
        on_face_track: callback(yaw_angle) — 每帧检测到人脸时调用
        on_reflex:     callback(reflex_name, params) — 反射触发时调用
        """
        self.on_face_track = on_face_track
        self.on_reflex     = on_reflex
        self._stop_event   = threading.Event()

        # 冷却计时（实例变量，非全局）
        self._last_reflex_time = {"alert": 0.0, "shy": 0.0}

        # Shy 连续帧计数
        self._shy_frame_count  = 0
        # 记录近期 face_size 历史（用于计算基平线）
        import collections
        self._face_size_history = collections.deque(maxlen=30)  # 记忆最近 30 帧（1.5s）

    # ─────────────────────────────────────────
    # 线程管理
    # ─────────────────────────────────────────

    def start(self):
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
            self._handle_face_track(state)

            # 2. Reflex checks
            self._check_reflexes(state)

            time.sleep(REALTIME_INTERVAL)

    # ─────────────────────────────────────────
    # Face tracking
    # ─────────────────────────────────────────

    def _handle_face_track(self, state: dict):
        """头部跟随人脸 X 位置。"""
        if not state["face_present"] or not self.on_face_track:
            return
        # face_x: 0.0（最左）→ 0.5（中）→ 1.0（最右）
        # 映射到 yaw: 70°（左）→ 90°（中）→ 110°（右）
        yaw = int(70 + state["face_x"] * 40)
        yaw = max(70, min(110, yaw))
        self.on_face_track(yaw)

    # ─────────────────────────────────────────
    # 反射检测
    # ─────────────────────────────────────────

    def _check_reflexes(self, state: dict):
        now = time.time()

        # ── Alert：突发声音 ────────────────────────────────
        # audio_spike 由 audio_detector 写入，检测到拍桌子/突然巨响时为 True
        if state.get("audio_spike", False):
            self._trigger_reflex("alert", now)

        # ── Shy：人脸视在大小迅速增大（人快速靠近）────────────────────
        # 用 face_size (bbox.width) 作为距离代理
        # 正常工作거离: face_size 大约 0.15~0.30
        # 靠近: face_size > 0.40 或者比基平线大出很多
        face_size = state.get("face_size", 0.0)
        if state.get("face_present", False) and face_size > 0:
            self._face_size_history.append(face_size)

            # 基平线 = 最近历史帧的均值（不包括最新帧）
            if len(self._face_size_history) >= 10:
                baseline = sum(list(self._face_size_history)[:-3]) / max(1, len(self._face_size_history) - 3)
                delta    = face_size - baseline

                # 大小超过绝对阈值 或 快速增大了很多
                is_close = (face_size > SHY_SIZE_THRESHOLD) or (delta > SHY_MIN_DELTA)

                if is_close:
                    self._shy_frame_count += 1
                    if self._shy_frame_count >= SHY_TRIGGER_FRAMES:
                        self._trigger_reflex("shy", now)
                        self._shy_frame_count = 0
                else:
                    self._shy_frame_count = 0
        else:
            self._shy_frame_count = 0
            # 没有人脸时不记录 size

    def _trigger_reflex(self, name: str, now: float):
        """触发反射，如果冷却时间还没到则忽略。"""
        cooldown = COOLDOWNS.get(name, 15)
        last     = self._last_reflex_time.get(name, 0.0)

        if now - last < cooldown:
            return  # 还在冷却中

        self._last_reflex_time[name] = now
        params = EMOTION_PARAMS.get(f"reflex_{name}", {})
        print(f"[REALTIME] 反射触发：{name}")

        if self.on_reflex:
            self.on_reflex(name, params)
