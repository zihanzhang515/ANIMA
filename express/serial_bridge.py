"""
express/serial_bridge.py
"""

import json
import time
import threading

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("[EXPRESS] WARNING: pyserial not installed.")


class SerialBridge:
    def __init__(self, port: str = None, baud: int = 9600):
        self.port = port
        self.baud = baud
        self._serial = None
        self._lock = threading.Lock()
        self._connected = False
        self._simulation_mode = not SERIAL_AVAILABLE
        self.current_emotion = "relaxed"

    def connect(self) -> bool:
        if self._simulation_mode:
            print("[EXPRESS] Simulation mode - no hardware connected")
            self._connected = True
            return True

        if self.port is None:
            self.port = self._auto_detect_port()
            if self.port is None:
                print("[EXPRESS] No Arduino found. Running in simulation mode.")
                self._simulation_mode = True
                self._connected = True
                return True

        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            self._connected = True
            print(f"[EXPRESS] Connected to Arduino on {self.port}")
            return True
        except Exception as e:
            print(f"[EXPRESS] Failed to connect: {e}. Running in simulation mode.")
            self._simulation_mode = True
            self._connected = True
            return True

    # ─── 情绪发送（供 context_pipeline 和 dashboard inject 调用）──
    def send_emotion(self, params: dict):
        self.current_emotion = params.get("name", "relaxed")
        cmd = {
            "type":  "emotion",
            "name":  params.get("name",  "relaxed"),
            "ear":   params.get("ear",   0),
            "yaw":   params.get("yaw",   60),
            "pitch": params.get("pitch", 20),
            "r":     params.get("r",     255),
            "g":     params.get("g",     245),
            "b":     params.get("b",     224),
        }
        self._send(cmd)

    # ─── 面部追踪 ──────────────────────────────────────────────
    def send_track(self, yaw: int):
        face_x = (yaw - 20) / 80.0
        self._send({"type": "track", "face_x": face_x, "yaw": yaw})

    # ─── 反射动作 ──────────────────────────────────────────────
    def send_reflex(self, reflex_name: str, params: dict):
        cmd = {
            "type": "reflex",
            "name": reflex_name,
            "ear":  params.get("ear", 0),
            "r":    params.get("r", 0),
            "g":    params.get("g", 255),
            "b":    params.get("b", 255),
        }
        self._send(cmd)

    # ─── Idle 动作 ─────────────────────────────────────────────
    def send_idle(self, *args):
        self._send({"type": "idle"})

    # ─── 底层串口发送 ──────────────────────────────────────────
    def _send(self, cmd: dict):
        json_str = json.dumps(cmd) + "\n"
        if self._simulation_mode:
            print(f"[EXPRESS] SIM → {json_str.strip()}")
            return
        if self._serial is None:
            print(f"[EXPRESS] ERROR: serial not connected, dropping: {json_str.strip()}")
            return
        with self._lock:
            try:
                self._serial.write(json_str.encode("utf-8"))
                print(f"[EXPRESS] TX → {json_str.strip()}")
            except Exception as e:
                print(f"[EXPRESS] Send error: {e} → switching to simulation mode")
                # 串口中途断开（如 Arduino USB 拔掉），切换到模拟模式，避免抛异常
                self._simulation_mode = True
                self._serial = None
                print(f"[EXPRESS] SIM → {json_str.strip()}")

    def _auto_detect_port(self):
        if not SERIAL_AVAILABLE:
            return None
        for p in serial.tools.list_ports.comports():
            search_string = f"{p.description} {p.device}".lower()
            if any(x in search_string for x in ["arduino", "usbmodem", "usbserial", "ch340"]):
                return p.device
        ports = list(serial.tools.list_ports.comports())
        if ports:
            return ports[0].device
        return None

    def disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("[EXPRESS] Disconnected.")


bridge = SerialBridge()
