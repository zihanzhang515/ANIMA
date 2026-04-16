"""
sense/input_monitor.py
----------------------
S5: Keyboard/mouse activity rate ("low" / "medium" / "high")

Uses pynput to listen for keyboard and mouse events system-wide.
Counts events per 10-second window, then classifies rate.

Runs in its own thread, updates shared_state continuously.
"""

import time
import threading
from sense.sensor_state import shared_state

# How often to evaluate rate (seconds)
EVALUATION_WINDOW = 10

# Event count thresholds for classification
# Tune these based on your typical typing speed
HIGH_THRESHOLD = 30     # 30+ events per 10s = high activity
MEDIUM_THRESHOLD = 8    # 8-30 events per 10s = medium activity
                        # < 8 events per 10s = low activity

# Thread-safe counter
_event_count = 0
_count_lock = threading.Lock()


def _on_key_press(key):
    global _event_count
    with _count_lock:
        _event_count += 1


def _on_mouse_move(x, y):
    # Only count significant mouse movements (not micro-jitter)
    # TODO: Track displacement instead of every move event
    pass


def _on_mouse_click(x, y, button, pressed):
    if pressed:
        global _event_count
        with _count_lock:
            _event_count += 1


def run_input_monitor(stop_event: threading.Event):
    """
    Main loop for input monitoring.
    Call this in a daemon thread from main.py.
    """
    global _event_count

    try:
        from pynput import keyboard, mouse
    except ImportError:
        print("[SENSE] ERROR: pynput not installed. Run: pip install pynput")
        return

    print("[SENSE] Input monitor started.")

    # Start listeners (they run in their own threads)
    kb_listener = keyboard.Listener(on_press=_on_key_press)
    mouse_listener = mouse.Listener(
        on_move=_on_mouse_move,
        on_click=_on_mouse_click
    )
    kb_listener.start()
    mouse_listener.start()

    while not stop_event.is_set():
        time.sleep(EVALUATION_WINDOW)

        # Read and reset counter
        with _count_lock:
            count = _event_count
            _event_count = 0

        # Classify rate
        if count >= HIGH_THRESHOLD:
            rate = "high"
        elif count >= MEDIUM_THRESHOLD:
            rate = "medium"
        else:
            rate = "low"

        shared_state.update("input_rate", rate)
        print(f"[SENSE] Input: {count} events → {rate}")

    kb_listener.stop()
    mouse_listener.stop()
    print("[SENSE] Input monitor stopped.")
