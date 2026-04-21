"""
express/serial_bridge.py
------------------------
Sends commands from Python to Arduino via USB Serial.

Protocol: JSON strings terminated by newline
Arduino reads JSON and controls servos + LED.

Command formats:
1. Emotion command:  {"type":"emotion","name":"curious","ear":90,"yaw":110,"pitch":100,"r":0,"g":206,"b":209}
2. Track command:    {"type":"track","yaw":95}         (real-time face tracking)
3. Reflex command:   {"type":"reflex","name":"alert","ear":90,"r":0,"g":255,"b":255}
4. Idle command:     {"type":"idle","ear":47,"yaw":92,"pitch":88}
"""

import json
import time
import threading

# Try to import serial - will fail gracefully if not installed
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("[EXPRESS] WARNING: pyserial not installed. Run: pip install pyserial")
    print("[EXPRESS] Running in simulation mode (printing commands only)")


class SerialBridge:
    def __init__(self, port: str = None, baud: int = 9600):
        """
        port: Serial port (e.g. "/dev/ttyUSB0" on Linux, "COM3" on Windows)
              If None, will auto-detect or run in simulation mode.
        """
        self.port = port
        self.baud = baud
        self._serial = None
        self._lock = threading.Lock()
        self._connected = False
        self._simulation_mode = not SERIAL_AVAILABLE

    def connect(self) -> bool:
        """Connect to Arduino. Returns True if successful."""
        if self._simulation_mode:
            print("[EXPRESS] Simulation mode - no hardware connected")
            self._connected = True
            return True

        # Auto-detect port if not specified
        if self.port is None:
            self.port = self._auto_detect_port()
            if self.port is None:
                print("[EXPRESS] No Arduino found. Running in simulation mode.")
                self._simulation_mode = True
                self._connected = True
                return True

        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset after connection
            self._connected = True
            print(f"[EXPRESS] Connected to Arduino on {self.port}")
            return True
        except Exception as e:
            print(f"[EXPRESS] Failed to connect: {e}. Running in simulation mode.")
            self._simulation_mode = True
            self._connected = True
            return True

    def send_emotion(self, params: dict):
        """Send an emotion command to Arduino."""
        cmd = {
            "type": "emotion",
            "ear":   params.get("ear", 45),
            "yaw":   params.get("yaw", 90),
            "pitch": params.get("pitch", 90),
            "r":     params.get("r", 255),
            "g":     params.get("g", 245),
            "b":     params.get("b", 224),
        }
        self._send(cmd)

    def send_track(self, yaw: int):
        """Send a real-time face tracking command (just yaw update)."""
        cmd = {"type": "track", "yaw": yaw}
        self._send(cmd)

    def send_reflex(self, reflex_name: str, params: dict):
        """Send a reflex behavior command."""
        cmd = {
            "type": "reflex",
            "name": reflex_name,
            "ear":  params.get("ear", 90),
            "r":    params.get("r", 0),
            "g":    params.get("g", 255),
            "b":    params.get("b", 255),
        }
        self._send(cmd)

    def send_idle(self, ear: int, yaw: int, pitch: int):
        """Send an idle micro-motion command."""
        cmd = {"type": "idle", "ear": ear, "yaw": yaw, "pitch": pitch}
        self._send(cmd)

    def send_hold(self, emotion_name: str, hold_params: dict):
        """
        Send a hold/idle command — tells Arduino to enter sustained idle loop
        for the current emotion after the ENTER animation completes.

        Arduino will loop a gentle micro-motion until it receives a new command.
        Protocol: {"type":"hold","name":"happy","idle_type":"ear_twitch","idle_range":20,...}
        """
        cmd = {
            "type":             "hold",
            "name":             emotion_name,
            "idle_type":        hold_params.get("idle_type", "subtle"),
            "idle_range":       hold_params.get("idle_range", 5),
            "idle_interval_ms": hold_params.get("idle_interval_ms", 3000),
            "r":                hold_params.get("r", 255),
            "g":                hold_params.get("g", 245),
            "b":                hold_params.get("b", 224),
        }
        self._send(cmd)

    def _send(self, cmd: dict):
        """Send a JSON command to Arduino."""
        json_str = json.dumps(cmd) + "\n"

        if self._simulation_mode:
            if cmd.get("type") != "track":
                print(f"[EXPRESS] SIM → {json_str.strip()}")
            return

        with self._lock:
            try:
                self._serial.write(json_str.encode("utf-8"))
            except Exception as e:
                print(f"[EXPRESS] Send error: {e}")

    def _auto_detect_port(self):
        """Try to find Arduino's serial port automatically."""
        import glob
        import sys

        if sys.platform == "darwin":  # macOS
            ports = glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/tty.usbserial*")
        elif sys.platform == "linux":
            ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        else:  # Windows
            ports = [f"COM{i}" for i in range(1, 20)]

        for port in ports:
            try:
                s = serial.Serial(port, 9600, timeout=0.5)
                s.close()
                print(f"[EXPRESS] Found port: {port}")
                return port
            except:
                continue

        return None

    def disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("[EXPRESS] Disconnected.")


# Global singleton
bridge = SerialBridge()
