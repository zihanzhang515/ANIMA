"""
run_woz.py
----------
Study 2 & 3 Wizard-of-Oz 控制脚本

功能：
  - 数字键 0-6 触发情绪，立刻发给 Arduino
  - 触发后 idle scheduler 自动跟上（8-20s 随机间隔）
  - 按 r 手动回 Relaxed
  - 按 q 退出
  - 所有触发带时间戳，session结束打印完整log

用法：
  python run_woz.py          # Study 2 独立WoZ
  python run_woz.py --log    # 额外输出CSV log文件（Study 3 Phase 1用）

按键映射：
  0 → relaxed    1 → focus
  2 → tired      3 → curious
  4 → happy      5 → listen
  6 → confused   r → relaxed (同0)
  q → 退出
"""

import sys
import time
import threading
import random
import csv
import os
from datetime import datetime

# ─── 情绪参数表 ────────────────────────────────────────────────
EMOTIONS = {
    '0': ("relaxed",  {"ear":0,   "yaw":60, "pitch":25, "r":255,"g":245,"b":224}),
    'r': ("relaxed",  {"ear":0,   "yaw":60, "pitch":25, "r":255,"g":245,"b":224}),
    '1': ("focus",    {"ear":90,  "yaw":60, "pitch":25, "r":0,  "g":0,  "b":200}),
    '2': ("tired",    {"ear":110, "yaw":60, "pitch":40, "r":160,"g":90, "b":0  }),
    '3': ("curious",  {"ear":0,   "yaw":45, "pitch":20, "r":0,  "g":200,"b":200}),
    '4': ("happy",    {"ear":0,   "yaw":60, "pitch":25, "r":255,"g":165,"b":0  }),
    '5': ("listen",   {"ear":0,   "yaw":60, "pitch":25, "r":0,  "g":180,"b":80 }),
    '6': ("confused", {"ear":40,  "yaw":60, "pitch":20, "r":120,"g":0,  "b":180}),
}

KEY_DISPLAY = """
╔══════════════════════════════╗
║   PEARL WoZ Controller       ║
╠══════════════════════════════╣
║  1 → Focus    2 → Tired      ║
║  3 → Curious  4 → Happy      ║
║  5 → Listen   6 → Confused   ║
║  0 / r → Relaxed             ║
║  q → Quit & print log        ║
╚══════════════════════════════╝
"""

# ─── Idle Scheduler ────────────────────────────────────────────
class IdleScheduler:
    """
    随机间隔发送 idle 命令给 Arduino。
    Arduino 端根据 currentEmotion 选择对应的 idle 动画。
    """
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

    def _loop(self):
        while not self._stop.is_set():
            wait = random.uniform(self.min_sec, self.max_sec)
            self._stop.wait(wait)
            if not self._stop.is_set():
                self.bridge.send_idle()


# ─── WoZ Session ───────────────────────────────────────────────
class WoZSession:
    def __init__(self, bridge, save_log=False, participant_id="P00"):
        self.bridge = bridge
        self.save_log = save_log
        self.participant_id = participant_id
        self.session_start = time.time()
        self.current_emotion = "relaxed"
        self.trigger_log = []  # [(timestamp, offset_sec, emotion)]
        self.idle = IdleScheduler(bridge)

    def trigger(self, emotion_name, params):
        """触发情绪：发命令给Arduino + 记录log"""
        now = time.time()
        offset = now - self.session_start

        # 发给 Arduino
        p = params.copy()
        p["name"] = emotion_name
        self.bridge.send_emotion(p)

        # 记录
        self.current_emotion = emotion_name
        self.trigger_log.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "offset_sec": round(offset, 1),
            "emotion": emotion_name,
        })

        print(f"  [{datetime.now().strftime('%H:%M:%S')}]  T+{offset:5.0f}s  →  {emotion_name.upper()}")

    def start(self):
        self.session_start = time.time()
        self.idle.start()
        print(f"\n[WoZ] Session started — {datetime.now().strftime('%H:%M:%S')}")
        # 初始化为 relaxed
        self.trigger("relaxed", EMOTIONS['0'][1])

    def end(self):
        self.idle.stop()
        self._print_log()
        if self.save_log:
            self._save_csv()

    def _print_log(self):
        print(f"\n{'─'*45}")
        print(f"  WoZ Session Log — {self.participant_id}")
        print(f"{'─'*45}")
        print(f"  {'Time':<10} {'Offset':>8}s  Emotion")
        print(f"{'─'*45}")
        for e in self.trigger_log:
            print(f"  {e['timestamp']:<10} {e['offset_sec']:>8.1f}s  {e['emotion']}")
        print(f"{'─'*45}")
        print(f"  Total triggers: {len(self.trigger_log)}")
        print(f"{'─'*45}\n")

    def _save_csv(self):
        os.makedirs("logs", exist_ok=True)
        fname = f"logs/woz_{self.participant_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(fname, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp","offset_sec","emotion"])
            writer.writeheader()
            writer.writerows(self.trigger_log)
        print(f"  Log saved → {fname}")


# ─── Main ──────────────────────────────────────────────────────
def main():
    save_log = "--log" in sys.argv
    pid_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    participant_id = pid_args[0] if pid_args else "P00"

    # 连接 Arduino
    from express.serial_bridge import bridge
    bridge.connect()
    time.sleep(1.5)

    session = WoZSession(bridge, save_log=save_log, participant_id=participant_id)
    session.start()

    print(KEY_DISPLAY)

    # 监听键盘
    try:
        import keyboard as kb
    except ImportError:
        print("[WoZ] ERROR: pip install keyboard")
        bridge.disconnect()
        return

    def on_key(event):
        key = event.name
        if key == 'q':
            session.end()
            bridge.disconnect()
            os._exit(0)
        if key in EMOTIONS:
            name, params = EMOTIONS[key]
            session.trigger(name, params)

    kb.on_press(on_key)

    print("[WoZ] Ready. Waiting for key press...\n")
    kb.wait('q')  # 阻塞直到按 q


if __name__ == "__main__":
    main()
