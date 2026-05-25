"""
main.py — 更新版
把 realtime_pipeline 和 context_pipeline 的情绪状态同步起来
"""

import time
import threading
import json
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
    print("  ANIMA v3 — 情绪持续 + 情绪专属 Idle")
    print("=" * 50)


def main():
    bridge.connect()

    # 初始 Relaxed
    bridge.send_emotion({"name": "relaxed", "r": 255, "g": 245, "b": 224})

    stop_event = threading.Event()

    # ── 实时管线（需要在 on_emotion_change 里同步情绪）──────
    realtime_pipeline = RealtimePipeline(
        on_face_track=lambda yaw: bridge.send_track(yaw),
        on_reflex=lambda name, params: bridge.send_reflex(name, params),
        on_idle=lambda: bridge.send_idle(0, 60, 25),  # idle 触发，Arduino 根据当前情绪处理
    )

    def on_emotion_change(emotion_name: str, scenario: str, params: dict):
        print(f"\n[MAIN] ✨ Emotion → {emotion_name} ({scenario})")
        
        from express.study_manager import study_manager
        study_manager.record_emotion(emotion_name)
        
        # 发送情绪命令
        bridge.send_emotion(params)

    context_pipeline = ContextPipeline(on_emotion_change=on_emotion_change)

    # ── Sense 线程 ──────────────────────────────────────────
    face_tracker_thread = threading.Thread(
        target=run_face_tracker, args=(stop_event,),
        daemon=False,  # non-daemon: ensures cap.release() is called on exit
        name="FaceTracker"
    )
    threads = [
        face_tracker_thread,
        threading.Thread(target=run_audio_detector, args=(stop_event,), daemon=True, name="AudioDetector"),
        threading.Thread(target=run_input_monitor,  args=(stop_event,), daemon=True, name="InputMonitor"),
    ]
    for t in threads: t.start()

    context_pipeline.start()
    realtime_pipeline.start()

    # ── Start Web Dashboard ────────────────────────────────
    from web.server import start_dashboard
    start_dashboard(pipeline=context_pipeline, realtime_pipeline=realtime_pipeline)

    print("\n[MAIN] ANIMA running.")
    print("  👉 Type 'phase1' to start 20-min recording")
    print("  👉 Type 'phase2' to start replay from recording")
    print("  👉 Press Ctrl+C to stop.\n")

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
                
    cmd_thread = threading.Thread(target=command_listener, daemon=True)
    cmd_thread.start()

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
        face_tracker_thread.join(timeout=3)  # 等摄像头释放
        print("[MAIN] Goodbye.")



if __name__ == "__main__":
    main()
