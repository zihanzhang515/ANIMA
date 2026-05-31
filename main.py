"""
main.py
Entry point for ANIMA. Starts all sensor threads, pipelines, and the web dashboard.
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

DEV_MODE = True

if DEV_MODE:
    print("=" * 50)
    print("  ANIMA v3 — Sustained Emotions + Emotion-Specific Idle")
    print("=" * 50)


def main():
    bridge.connect()

    # Initialise to relaxed on startup
    bridge.send_emotion({"name": "relaxed", "r": 255, "g": 245, "b": 224})

    stop_event = threading.Event()

    # Realtime pipeline — face tracking, reflexes, idle triggers
    realtime_pipeline = RealtimePipeline(
        on_face_track=lambda yaw: bridge.send_track(yaw),
        on_reflex=lambda name, params: bridge.send_reflex(name, params),
        on_idle=lambda: bridge.send_idle(0, 60, 25),
    )

    def on_emotion_change(emotion_name: str, scenario: str, params: dict):
        print(f"\n[MAIN] Emotion → {emotion_name} ({scenario})")
        from express.study_manager import study_manager
        study_manager.record_emotion(emotion_name)
        bridge.send_emotion(params)

    context_pipeline = ContextPipeline(on_emotion_change=on_emotion_change)

    # Sensor threads
    face_tracker_thread = threading.Thread(
        target=run_face_tracker, args=(stop_event,),
        daemon=False,  # Non-daemon: ensures cap.release() is called on exit
        name="FaceTracker"
    )
    threads = [
        face_tracker_thread,
        threading.Thread(target=run_audio_detector, args=(stop_event,), daemon=True, name="AudioDetector"),
        threading.Thread(target=run_input_monitor,  args=(stop_event,), daemon=True, name="InputMonitor"),
    ]
    for t in threads:
        t.start()

    context_pipeline.start()
    realtime_pipeline.start()

    # Web dashboard
    from web.server import start_dashboard
    start_dashboard(pipeline=context_pipeline, realtime_pipeline=realtime_pipeline)

    print("\n[MAIN] ANIMA running.")
    print("  Type 'phase1' to start 20-min recording")
    print("  Type 'phase2' to start manual replay")
    print("  Press Ctrl+C to stop.\n")

    def command_listener():
        from express.study_manager import study_manager
        while not stop_event.is_set():
            try:
                cmd = input().strip().lower()
                if cmd == "phase1":
                    study_manager.start_phase1()
                elif cmd == "phase2":
                    study_manager.start_phase2(bridge, context_pipeline)
                elif cmd == "stop1":
                    study_manager.stop_phase1()
                elif cmd == "p":
                    study_manager.toggle_pause()
            except EOFError:
                break

    threading.Thread(target=command_listener, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")
        from express.study_manager import study_manager
        if study_manager.phase1_active:
            study_manager.print_analysis("Phase 1 (Interrupted)")
        elif study_manager.phase2_active:
            study_manager.print_analysis("Phase 2 (Interrupted)")

        stop_event.set()
        context_pipeline.stop()
        realtime_pipeline.stop()
        bridge.disconnect()
        face_tracker_thread.join(timeout=3)  # Wait for camera release
        print("[MAIN] Goodbye.")


if __name__ == "__main__":
    main()
