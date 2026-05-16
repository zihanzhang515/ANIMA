"""
express/emotion_manager.py
---------------------------
情绪状态管理器

负责：
  1. 防止同一情绪重复触发（冷却时间）
  2. 条件消失后定时回 Relaxed
  3. 与 IdleScheduler 配合：情绪触发后自动启动 idle

用法（在 context_pipeline 里）：
  manager = EmotionManager(bridge)
  manager.start_idle()

  # 检测到新情绪时：
  manager.set_emotion("focus", params)

  # 检测条件消失时：
  manager.on_condition_lost("focus")

  # 条件重新满足时：
  manager.on_condition_restored()
"""

import threading
import random
import time


# ── 冷却 & 归位时间（从 context_rules_study 导入）────────────
EMOTION_COOLDOWN_SEC = {
    "focus":    30,
    "tired":    30,
    "curious":  20,
    "happy":    20,
    "listen":   10,
    "confused": 30,
    "relaxed":  0,
}

RETURN_TO_RELAXED_DELAY_SEC = {
    "focus":    20,
    "tired":    15,
    "curious":  15,
    "happy":    20,
    "listen":   10,
    "confused": 20,
}

RELAXED_PARAMS = {
    "name": "relaxed", "ear": 0, "yaw": 60, "pitch": 25,
    "r": 255, "g": 245, "b": 224
}


class IdleScheduler:
    """随机间隔触发 idle 动画（Arduino 按 currentEmotion 决定动作）"""

    def __init__(self, bridge, min_sec=8, max_sec=20):
        self.bridge = bridge
        self.min_sec = min_sec
        self.max_sec = max_sec
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def restart(self):
        """情绪切换时重置 idle 计时器（不重新start线程，只reset等待）"""
        self._stop.set()
        time.sleep(0.05)
        self.start()

    def _loop(self):
        while not self._stop.is_set():
            wait = random.uniform(self.min_sec, self.max_sec)
            self._stop.wait(wait)
            if not self._stop.is_set():
                self.bridge.send_idle()


class EmotionManager:
    def __init__(self, bridge):
        self.bridge = bridge
        self.current_emotion = "relaxed"
        self.idle = IdleScheduler(bridge)

        # 冷却和归位
        self._cooldown_until: float = 0.0
        self._return_timer: threading.Timer = None
        self._lock = threading.Lock()

    def start_idle(self):
        self.idle.start()

    def stop_idle(self):
        self.idle.stop()

    def set_emotion(self, emotion: str, params: dict) -> bool:
        """
        触发新情绪。
        返回 True = 成功触发；False = 在冷却期内被忽略。
        """
        with self._lock:
            # 相同情绪不重复
            if emotion == self.current_emotion:
                return False

            # 检查冷却
            if time.time() < self._cooldown_until:
                remaining = self._cooldown_until - time.time()
                print(f"[EMOTION] Cooldown: {emotion} blocked ({remaining:.0f}s remaining)")
                return False

            # 取消正在等待的归位计时器
            self._cancel_return_timer()

            # 触发
            self.current_emotion = emotion
            cooldown = EMOTION_COOLDOWN_SEC.get(emotion, 20)
            self._cooldown_until = time.time() + cooldown

        p = params.copy()
        p["name"] = emotion
        self.bridge.send_emotion(p)

        # 情绪切换后重置 idle 计时（让 idle 在新情绪下重新计时）
        self.idle.restart()

        print(f"[EMOTION] → {emotion.upper()} (cooldown {cooldown}s)")
        return True

    def go_relaxed(self):
        """立刻回到 Relaxed"""
        with self._lock:
            self._cancel_return_timer()
            if self.current_emotion == "relaxed":
                return
            self.current_emotion = "relaxed"
            self._cooldown_until = 0.0

        self.bridge.send_emotion(RELAXED_PARAMS)
        self.idle.restart()
        print("[EMOTION] → RELAXED")

    def on_condition_lost(self, emotion: str):
        """
        当触发条件消失时调用。
        N 秒后如果没有新情绪触发，自动回 Relaxed。
        """
        with self._lock:
            if self.current_emotion != emotion:
                return  # 已经切换到别的情绪了，不管
            self._cancel_return_timer()
            delay = RETURN_TO_RELAXED_DELAY_SEC.get(emotion, 15)

        print(f"[EMOTION] Condition lost for {emotion}, returning to Relaxed in {delay}s")
        self._return_timer = threading.Timer(delay, self.go_relaxed)
        self._return_timer.daemon = True
        self._return_timer.start()

    def on_condition_restored(self):
        """条件重新满足时取消归位计时器"""
        with self._lock:
            self._cancel_return_timer()

    def _cancel_return_timer(self):
        if self._return_timer is not None:
            self._return_timer.cancel()
            self._return_timer = None
