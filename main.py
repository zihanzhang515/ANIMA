"""
main.py
-------
ANIMA main entry point.

Starts all threads and wires the callbacks together:
  sense → understand → express

Usage:
  python main.py

Press Ctrl+C to stop.

Development mode: Set DEV_MODE = True to speed up timings
and print all state changes to console.
"""

import time
import threading
from sense.sensor_state import shared_state
from sense.face_tracker import run_face_tracker
from sense.audio_detector import run_audio_detector
from sense.input_monitor import run_input_monitor
from understand.context_pipeline import ContextPipeline
from understand.realtime_pipeline import RealtimePipeline
from express.serial_bridge import bridge
from config.emotions import get_emotion

# ─── Development Mode ──────────────────────────────────────
DEV_MODE = True   # Set False for production (slower, realistic timings)

if DEV_MODE:
    print("=" * 50)
    print("  ANIMA - Development Mode")
    print("  Context check: every 30s (production: 600s)")
    print("  All state changes printed to console")
    print("=" * 50)


# ─── Express Callbacks ─────────────────────────────────────

def on_emotion_change(emotion_name: str, scenario: str, params: dict):
    """Called by ContextPipeline when emotion should change."""
    print(f"\n[MAIN] ✨ Emotion → {emotion_name} ({scenario})")
    bridge.send_emotion(params)


def on_face_track(yaw: int):
    """Called by RealtimePipeline ~20x per second when face detected."""
    bridge.send_track(yaw)
    # Don't print this - too frequent


def on_reflex(reflex_name: str, params: dict):
    """Called by RealtimePipeline when a reflex triggers."""
    print(f"\n[MAIN] ⚡ Reflex → {reflex_name}")
    bridge.send_reflex(reflex_name, params)


# ─── Main ──────────────────────────────────────────────────

def main():
    # Connect to Arduino (runs in simulation if not connected)
    bridge.connect()

    # Set initial relaxed state
    bridge.send_emotion(get_emotion("relaxed"))

    # Stop event shared by all sense threads
    stop_event = threading.Event()

    # ── Start Sense Threads ────────────────────────────────
    threads = [
        threading.Thread(
            target=run_face_tracker,
            args=(stop_event,),
            daemon=True,
            name="FaceTracker"
        ),
        threading.Thread(
            target=run_audio_detector,
            args=(stop_event,),
            daemon=True,
            name="AudioDetector"
        ),
        threading.Thread(
            target=run_input_monitor,
            args=(stop_event,),
            daemon=True,
            name="InputMonitor"
        ),
    ]

    for t in threads:
        t.start()

    # ── Start Understand Pipelines ─────────────────────────
    context_pipeline = ContextPipeline(on_emotion_change=on_emotion_change)
    realtime_pipeline = RealtimePipeline(
        on_face_track=on_face_track,
        on_reflex=on_reflex
    )

    context_pipeline.start()
    realtime_pipeline.start()

    # ── State Monitor (dev mode only) ──────────────────────
    def print_state():
        while not stop_event.is_set():
            time.sleep(5)
            s = shared_state.get()
            print(f"[STATE] face={s['face_present']} x={s['face_x']:.2f} | "
                  f"speech={s['speech_active']} audio={s['audio_category']} | "
                  f"input={s['input_rate']}")

    if DEV_MODE:
        monitor = threading.Thread(target=print_state, daemon=True, name="StateMonitor")
        monitor.start()

    # ── Keep Running ───────────────────────────────────────
    print("\n[MAIN] ANIMA running. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")
        stop_event.set()
        context_pipeline.stop()
        realtime_pipeline.stop()
        bridge.disconnect()
        time.sleep(1)
        print("[MAIN] Goodbye.")


if __name__ == "__main__":
    main()
