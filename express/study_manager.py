import time
import json
import os
import threading

STUDY_FILE = "study3_record.json"

class StudyManager:
    def __init__(self):
        self.phase1_active = False
        self.phase2_active = False
        self.start_time = 0
        self.recordings = []
        self.s5_log = []
        self._replay_thread = None
        self._s5_thread = None
        self.is_paused = False
        
        self._start_s5_logging()

    def _start_s5_logging(self):
        def _loop():
            while True:
                if (self.phase1_active or self.phase2_active) and not self.is_paused:
                    try:
                        from sense.sensor_state import shared_state
                        rate = shared_state.get().get("input_rate", "unavailable")
                    except Exception:
                        rate = "unavailable"
                    
                    self.s5_log.append({
                        "offset": round(time.time() - self.start_time, 1),
                        "rate": rate
                    })
                time.sleep(5)
                
        self._s5_thread = threading.Thread(target=_loop, daemon=True)
        self._s5_thread.start()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            print("\n" + "="*40)
            print("  [STUDY] ⏸️ SYSTEM PAUSED")
            print("  (Sensors/Replay ignored. Press 'p' to resume)")
            print("="*40 + "\n")
        else:
            print("\n" + "="*40)
            print("  [STUDY] ▶️ SYSTEM RESUMED")
            print("="*40 + "\n")

    def start_phase1(self):
        print("\n" + "="*50)
        print("  [STUDY] Phase 1: RECORDING STARTED (20 mins)")
        print("="*50 + "\n")
        self.phase1_active = True
        self.phase2_active = False
        self.start_time = time.time()
        self.recordings = []
        self.s5_log = []
        
        # 记录初始状态
        self.record_emotion("relaxed")

    def stop_phase1(self):
        if not self.phase1_active: return
        self.phase1_active = False
        
        # 保存到文件
        filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), STUDY_FILE)
        with open(filepath, "w") as f:
            json.dump(self.recordings, f, indent=2)
            
        print("\n" + "="*50)
        print(f"  [STUDY] Phase 1: RECORDING SAVED TO {STUDY_FILE}")
        print("="*50 + "\n")
        
        self.print_analysis("Phase 1")

    def record_emotion(self, emotion_name):
        if not self.phase1_active and not self.phase2_active:
            return
            
        elapsed = time.time() - self.start_time
        # 只记录 20 分钟内的情绪
        if elapsed > 20 * 60:
            if self.phase1_active: self.stop_phase1()
            if self.phase2_active: self.stop_phase2()
            return
            
        try:
            from sense.sensor_state import shared_state
            current_s5 = shared_state.get().get("input_rate", "unavailable")
        except Exception:
            current_s5 = "unavailable"
            
        self.recordings.append({
            "time_offset": round(elapsed, 2),
            "emotion": emotion_name,
            "s5_at_trigger": current_s5
        })
        print(f"[STUDY] Recorded: {emotion_name} at {elapsed:.1f}s (S5: {current_s5})")

    def start_phase2(self, bridge, context_pipeline):
        filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), STUDY_FILE)
        if not os.path.exists(filepath):
            print(f"[STUDY] ERROR: No recording found at {filepath}")
            return
            
        with open(filepath, "r") as f:
            self.recordings = json.load(f)
            
        print("\n" + "="*50)
        print("  [STUDY] Phase 2: MANUAL RECORDING STARTED")
        print("="*50 + "\n")
        
        self.phase1_active = False
        self.phase2_active = True
        self.s5_log = []
        self.start_time = time.time()
        self.recordings = []
        
        self.record_emotion("relaxed")
        
    def stop_phase2(self):
        if not self.phase2_active: return
        self.phase2_active = False
        
        filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "study3_phase2.json")
        with open(filepath, "w") as f:
            json.dump(self.recordings, f, indent=2)
            
        print("\n" + "="*50)
        print("  [STUDY] Phase 2: RECORDING SAVED")
        print("="*50 + "\n")
        self.print_analysis("Phase 2")

    def print_analysis(self, phase_name):
        print(f"\n[{phase_name} Analysis] ===================")
        print("--- Emotion Trigger Log ---")
        for e in self.recordings:
            s5 = e.get('s5_at_trigger', 'N/A')
            print(f"  T+{e['time_offset']:.1f}s  [{e['emotion'].upper()}]  S5: {s5}")
            
        print("\n--- S5 Snapshot Log (every 5s) ---")
        for s in self.s5_log:
            print(f"  T+{s['offset']:.1f}s  S5: {s['rate']}")
            
        print("\n--- Anticipatory Window Analysis ---")
        # 针对每个情绪触发点，寻找 s5_log 里时间更晚且 rate 发生变化的第一条记录
        for e in self.recordings:
            trigger_t = e['time_offset']
            emo = e['emotion'].upper()
            
            target_snap = None
            for i, snap in enumerate(self.s5_log):
                if snap['offset'] > trigger_t:
                    # 如果找到了之后的第一个状态
                    target_snap = snap
                    break
                    
            if target_snap:
                delta = target_snap['offset'] - trigger_t
                if delta > 0:
                    print(f"  [{emo}] triggered {delta:.1f}s BEFORE S5 confirmed [{target_snap['rate']}]")
                else:
                    print(f"  [{emo}] triggered {abs(delta):.1f}s AFTER S5 confirmed [{target_snap['rate']}]")
            else:
                print(f"  [{emo}] triggered at end of session (no future S5 data)")
        print("==========================================\n")

study_manager = StudyManager()
