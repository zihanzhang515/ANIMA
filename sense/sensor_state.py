"""
sense/sensor_state.py
---------------------
Thread-safe shared state for all 5 sensor signals.

v2 改动：
  - 新增 audio_spike 字段（Alert reflex 需要）
  - 新增内部时间追踪：last_high_activity_time / input_zero_since / session_start_time
  - 新增查询方法：get_inactive_duration() / was_recently_active() / get_session_duration()
  - update() 自动维护时间追踪，外部模块无需额外操作
"""

import threading
import time


class SensorState:
    def __init__(self):
        self._lock = threading.Lock()

        # ── 五个核心信号 ──
        self._state = {
            "face_present":   False,   # S1
            "face_x":         0.5,     # S2  (0.0=左 / 0.5=中 / 1.0=右)
            "face_size":      0.0,     # S2b 人脸视在大小（bbox.width），代理靠近距离
            "speech_active":  False,   # S3
            "audio_category": "silence",  # S4  silence/speech/music/alert_spike
            "audio_spike":    False,   # S4b  突发声音，Alert reflex 专用
            "audio_rms":      0.0,
            "input_rate":     "low",   # S5   low/medium/high
            "current_emotion":"relaxed",
            "last_updated":   time.time(),
        }

        # ── 前一帧快照（用于 transition 检测）──
        self._prev_state = self._state.copy()

        # ── 时间追踪（内部，不暴露到 _state）──
        # 上次 input_rate 是 high/medium 的时间戳
        self._last_high_activity_time: float = 0.0
        self._high_activity_start_time: float = 0.0
        # input_rate 变成 low 的时间戳（用于 Curious/Confused 区分）
        self._input_zero_since: float = 0.0
        # 用户本次出现的时间戳（face_present 从 False→True）
        self._session_start_time: float = 0.0
        self._face_absent_since: float = 0.0
        # 当前 state 起始时间（用于 min_duration 检查）
        self._state_start_time: float = time.time()

    # ─────────────────────────────────────────
    # 写入
    # ─────────────────────────────────────────

    def update(self, key: str, value):
        """更新单个信号，自动维护时间追踪。"""
        with self._lock:
            if key not in self._state:
                return
            if self._state[key] == value:
                return  # 无变化，不更新

            self._state[key] = value
            self._state["last_updated"] = time.time()
            now = time.time()

            # ── input_rate 变化时维护时间追踪 ──
            if key == "input_rate":
                if value in ("high", "medium"):
                    self._last_high_activity_time = now
                    self._input_zero_since = 0.0   # 重置归零计时
                    if getattr(self, "_high_activity_start_time", 0.0) == 0.0:
                        self._high_activity_start_time = now
                elif value == "low":
                    self._high_activity_start_time = 0.0
                    if self._input_zero_since == 0.0:
                        self._input_zero_since = now  # 开始计归零时长

            # ── face_present 从 False→True 时重置 session 计时 ──
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

    def get(self) -> dict:
        """当前信号快照（线程安全副本）。"""
        with self._lock:
            return self._state.copy()

    def get_prev(self) -> dict:
        """上一帧快照。"""
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

    # ─────────────────────────────────────────
    # 时间维度查询（Curious/Confused/Tired 专用）
    # ─────────────────────────────────────────

    def get_active_duration(self) -> float:
        """连续保持 high/medium 活跃的秒数"""
        with self._lock:
            start_time = getattr(self, "_high_activity_start_time", 0.0)
            if start_time == 0.0:
                return 0.0
            return time.time() - start_time

    def get_inactive_duration(self) -> float:
        """
        input_rate 归零（low）已经多少秒了。
        用于区分 Curious（<90s）和 Confused（>180s）。
        返回 0 表示当前还在活跃或从未活跃过。
        """
        with self._lock:
            if self._input_zero_since == 0.0:
                return 0.0
            return time.time() - self._input_zero_since

    def was_recently_active(self, window_sec: float = 300.0) -> bool:
        """
        过去 window_sec 秒内，有没有出现过 high/medium 活跃状态。
        用于区分 Relaxed（从来没高活跃）和 Curious/Confused（之前高活跃过）。
        """
        with self._lock:
            if self._last_high_activity_time == 0.0:
                return False
            return (time.time() - self._last_high_activity_time) < window_sec

    def get_absent_duration(self) -> float:
        """用户离开（不在场）的连续秒数。"""
        with self._lock:
            start = getattr(self, "_face_absent_since", 0.0)
            if start == 0.0:
                return 0.0
            return time.time() - start

    def get_session_duration(self) -> float:
        """
        用户本次在场的累计秒数（face_present 持续时间）。
        用于 Tired 的累计工时触发（30分钟）。
        """
        with self._lock:
            if self._session_start_time == 0.0:
                return 0.0
            return time.time() - self._session_start_time

    def get_face_x_zone(self) -> str:
        """把 face_x 浮点数转成 left/center/right 区域。"""
        with self._lock:
            x = self._state["face_x"]
        if x < 0.35:
            return "left"
        elif x > 0.65:
            return "right"
        return "center"


# 全局单例
shared_state = SensorState()

