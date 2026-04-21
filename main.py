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

# Ref to context_pipeline so reflexes can read the current sustained emotion
_context_pipeline_ref = None

def on_emotion_change(emotion_name: str, scenario: str, params: dict):
    """Called by ContextPipeline when emotion should change."""
    print(f"\n[MAIN] ✨ Emotion → {emotion_name} ({scenario})")
    bridge.send_emotion(params)  # ENTER 阶段：平滑过渡到目标姿态

    # ── HOLD 阶段：进入动画结束后切换到持续 idle 循环 ──
    hold_params = params.get("hold_params")
    if hold_params:
        enter_ms = params.get("duration_ms", 3000)
        def switch_to_hold(ename=emotion_name, hp=hold_params, delay_s=enter_ms / 1000 + 0.5):
            time.sleep(delay_s)
            bridge.send_hold(ename, hp)
            print(f"[MAIN] 💤 Hold → {ename} ({hp.get('idle_type', 'subtle')})")
        threading.Thread(target=switch_to_hold, daemon=True, name=f"Hold_{emotion_name}").start()


def on_face_track(yaw: int):
    """Called by RealtimePipeline ~20x per second when face detected."""
    bridge.send_track(yaw)
    # Don't print this - too frequent


def on_reflex(reflex_name: str, params: dict):
    """Called by RealtimePipeline when a reflex triggers."""
    print(f"\n[MAIN] ⚡ Reflex → {reflex_name}")
    bridge.send_reflex(reflex_name, params)

    # Reflexes are momentary - they don't change or log the sustained emotion state.
    if reflex_name in ("alert", "shy"):
        # 短暂在 dashboard 显示反射状态，然后恢复 Tier 1 情绪
        shared_state.force_update("current_emotion", reflex_name)
        def revert_to_persistent():
            time.sleep(3)
            persistent = _context_pipeline_ref.current_emotion if _context_pipeline_ref else "relaxed"
            shared_state.force_update("current_emotion", persistent)
            bridge.send_emotion(get_emotion(persistent))  # 硬件回位：物理回到 Tier 1 姿态
        threading.Thread(target=revert_to_persistent, daemon=True).start()

    elif reflex_name == "greeting":
        # 返回识别：纯物理手势，不改变 dashboard 显示的情绪状态
        # 完成后让 Arduino 回到当前 Tier 1 姿态（为将来 Arduino 加动画序列做准备）
        def revert_after_greeting():
            duration_s = params.get("duration_ms", 1500) / 1000 + 0.5
            time.sleep(duration_s)
            persistent = _context_pipeline_ref.current_emotion if _context_pipeline_ref else "relaxed"
            bridge.send_emotion(get_emotion(persistent))  # 硬件回位
        threading.Thread(target=revert_after_greeting, daemon=True).start()


# ─── Main ──────────────────────────────────────────────────

def main():
    # Connect to Arduino (runs in simulation if not connected)
    bridge.connect()

    # Set initial relaxed state
    bridge.send_emotion(get_emotion("relaxed"))

    # Stop event shared by all sense threads
    stop_event = threading.Event()

    face_tracker_thread = threading.Thread(
        target=run_face_tracker,
        args=(stop_event,),
        daemon=True,
        name="FaceTracker"
    )
    threads = [
        face_tracker_thread,
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
    global _context_pipeline_ref
    context_pipeline = ContextPipeline(on_emotion_change=on_emotion_change)
    _context_pipeline_ref = context_pipeline
    realtime_pipeline = RealtimePipeline(
        on_face_track=on_face_track,
        on_reflex=on_reflex
    )

    context_pipeline.start()
    realtime_pipeline.start()

    # Force-broadcast the initial emotion so dashboard shows correct state on load
    # (use force_update to bypass the no-change guard in update())
    shared_state.force_update("current_emotion", "relaxed")

    # ── Start Web Dashboard ────────────────────────────────
    from web.server import start_dashboard
    start_dashboard(pipeline=context_pipeline)

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
        # Shut down HTTP server explicitly so port is released immediately
        from web.server import stop_dashboard
        stop_dashboard()
        # Wait up to 2s for face_tracker to call cap.release() cleanly
        face_tracker_thread.join(timeout=2.0)
        if face_tracker_thread.is_alive():
            print("[MAIN] Warning: face tracker didn't exit cleanly")
        time.sleep(0.2)
        print("[MAIN] Goodbye.")


if __name__ == "__main__":
    main()
