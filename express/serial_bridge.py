"""
express/serial_bridge.py — 加入 WoZ 模式
─────────────────────────────────────────
WoZ 模式下：
  - context_pipeline 的情绪输出被屏蔽
  - 情绪由 dashboard 或 woz_controller 手动发送
  - idle 照常运行（Arduino 端自动执行）
  - 下次切换情绪或手动解锁才退出 WoZ 模式
"""

import serial
import serial.tools.list_ports
import json
import time
import threading


class SerialBridge:
    def __init__(self):
        self._serial = None
        self._lock   = threading.Lock()
        self.woz_mode       = False   # WoZ 锁定标志
        self.current_emotion = "relaxed"

    # ─── 连接 ─────────────────────────────────────────────────
    def connect(self, port: str = None, baud: int = 9600):
        if port is None:
            port = self._find_port()
        self._serial = serial.Serial(port, baud, timeout=2)
        time.sleep(2)
        print(f"[BRIDGE] Connected: {port}")

    def disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
            print("[BRIDGE] Disconnected.")

    def _find_port(self) -> str:
        for p in serial.tools.list_ports.comports():
            if any(x in p.description for x in ["Arduino", "usbmodem", "usbserial", "CH340"]):
                return p.device
        ports = list(serial.tools.list_ports.comports())
        if ports:
            return ports[0].device
        raise RuntimeError("[BRIDGE] No serial port found.")

    # ─── 基础发送 ─────────────────────────────────────────────
    def _send(self, cmd: dict):
        if self._serial and self._serial.is_open:
            with self._lock:
                msg = json.dumps(cmd) + "\n"
                self._serial.write(msg.encode())

    # ─── 情绪发送 ─────────────────────────────────────────────
    def send_emotion(self, params: dict):
        """从 context_pipeline 调用 — WoZ 模式下被屏蔽"""
        if self.woz_mode:
            return  # ← WoZ 锁定，忽略 pipeline 的情绪输出
        self.current_emotion = params.get("name", "relaxed")
        self._send({"type": "emotion", **params})

    def send_emotion_woz(self, params: dict):
        """从 WoZ dashboard 调用 — 绕过锁定直接发送"""
        self.woz_mode = True
        self.current_emotion = params.get("name", "relaxed")
        self._send({"type": "emotion", **params})
        print(f"[BRIDGE][WoZ] Emotion → {self.current_emotion}")

    # ─── WoZ 控制 ─────────────────────────────────────────────
    def set_woz_mode(self, active: bool):
        self.woz_mode = active
        state = "ON" if active else "OFF"
        print(f"[BRIDGE] WoZ mode {state}")
        if not active:
            # 解锁时回到 Relaxed
            self._send({"type": "emotion", "name": "relaxed",
                        "r": 255, "g": 245, "b": 224})
            self.current_emotion = "relaxed"

    # ─── 其他命令 ─────────────────────────────────────────────
    def send_track(self, yaw: int):
        self._send({"type": "track", "yaw": yaw})

    def send_reflex(self, name: str, params: dict):
        if self.woz_mode:
            return  # WoZ 模式下同样屏蔽 reflex
        self._send({"type": "reflex", "name": name, **params})

    def send_idle(self, *args):
        self._send({"type": "idle"})

    def send_calibrate(self, base_pitch: int, min_pitch: int, max_pitch: int):
        self._send({
            "type": "calibrate",
            "base_pitch": base_pitch,
            "min_pitch": min_pitch,
            "max_pitch": max_pitch
        })


bridge = SerialBridge()
