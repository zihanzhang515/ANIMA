# -*- coding: utf-8 -*-
"""
sense/audio_detector.py
-----------------------
S3: Is speech happening? (True/False)
S4: What audio category? ("silence" / "speech" / "music" / "alert_spike")

Changes in v2:
  1. Added ZCR (zero-crossing rate): speech has high, variable ZCR;
     music has low, stable ZCR.
  2. classify() now requires voice_ratio + ZCR double-verification for speech.
  3. Sliding-window speech lock threshold raised from 0.15 to 0.45
     to prevent vocal songs from being misclassified as speech.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import threading
import numpy as np
from sense.sensor_state import shared_state

# ── 音频基础参数 ──
SAMPLE_RATE = 16000
CHUNK_SIZE  = 1024
CHANNELS    = 1

# ── Classification thresholds (calibrated) ──────────────────────────────
SILENCE_THRESHOLD   = 100
SPEECH_THRESHOLD    = 150
ENERGETIC_THRESHOLD = 300
SPIKE_RATIO         = 6.0
SPIKE_MIN_RMS       = 4000
SPEECH_FREQ_LOW     = 100
SPEECH_FREQ_HIGH    = 2500
VOICE_ENERGY_RATIO  = 0.65
HISTORY_SIZE        = 15

# ── ZCR parameters for speech vs music distinction ───────────────────────
ZCR_SPEECH_MIN  = 0.03   # Minimum ZCR for speech (0.06 was too high; male voices often fell below)
ZCR_VAR_MIN     = 0.01   # Minimum frame-to-frame ZCR variance

# ── Bass (low-frequency) feature: music has far more bass than speech ─────
BASS_FREQ_LOW    = 50     # Bass band lower bound (Hz)
BASS_FREQ_HIGH   = 200    # Bass band upper bound (Hz)
BASS_MUSIC_RATIO = 0.25   # Bass/total ratio above this → likely music (0.12 was too permissive)
BASS_SPEECH_MAX  = 0.15   # Bass/total ratio below this → likely speech

# ── Sliding-window speech lock threshold ─────────────────────────────────
SPEECH_WINDOW_RATIO = 0.45   # 0.15 was too low; vocal songs easily exceeded it


class AudioClassifier:
    def __init__(self):
        import collections
        self.rms_history = collections.deque(maxlen=HISTORY_SIZE)
        self.zcr_history = collections.deque(maxlen=8)

    def compute_rms(self, audio_data: np.ndarray) -> float:
        return float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))

    def get_voice_ratio(self, audio_data: np.ndarray) -> float:
        fft   = np.abs(np.fft.rfft(audio_data))
        freqs = np.fft.rfftfreq(len(audio_data), 1.0 / SAMPLE_RATE)
        voice_mask   = (freqs >= SPEECH_FREQ_LOW) & (freqs <= SPEECH_FREQ_HIGH)
        voice_energy = np.sum(fft[voice_mask])
        total_energy = np.sum(fft) + 1e-10
        return float(voice_energy / total_energy)

    def get_zcr(self, audio_data: np.ndarray) -> float:
        """
        Zero-crossing rate: fraction of samples where the signal changes sign.
        Speech has fast, variable articulation → high, unstable ZCR.
        Music has continuous rhythm → low, stable ZCR.
        """
        audio_f = audio_data.astype(np.float32)
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_f)))) / 2
        return float(zero_crossings / len(audio_f))

    def get_bass_ratio(self, audio_data: np.ndarray) -> float:
        """低频能量占比。音乐有明显低音，说话几乎没有。"""
        fft   = np.abs(np.fft.rfft(audio_data))
        freqs = np.fft.rfftfreq(len(audio_data), 1.0 / SAMPLE_RATE)
        bass_mask   = (freqs >= BASS_FREQ_LOW) & (freqs <= BASS_FREQ_HIGH)
        bass_energy = np.sum(fft[bass_mask])
        total_energy = np.sum(fft) + 1e-10
        return float(bass_energy / total_energy)

    def is_speech_by_zcr(self, audio_data: np.ndarray) -> bool:
        """
        ZCR dual-verification:
        Condition 1 — current frame ZCR exceeds minimum threshold.
        Condition 2 — recent frames show significant ZCR variance (speech is irregular; music is stable).
        Both conditions must be met to classify as genuine speech.
        """
        zcr = self.get_zcr(audio_data)
        self.zcr_history.append(zcr)

        if zcr < ZCR_SPEECH_MIN:
            return False

        if len(self.zcr_history) >= 4:
            zcr_var = float(np.std(list(self.zcr_history)))
            if zcr_var < ZCR_VAR_MIN:
                return False

        return True

    def detect_spike(self, current_rms: float) -> bool:
        if len(self.rms_history) < 8:
            return False
        if current_rms < SPIKE_MIN_RMS:
            return False
        avg_rms = np.mean(list(self.rms_history))
        if avg_rms < 80:
            return False
        return current_rms > avg_rms * SPIKE_RATIO

    def classify(self, audio_data: np.ndarray) -> dict:
        rms         = self.compute_rms(audio_data)
        voice_ratio = self.get_voice_ratio(audio_data)
        bass_ratio  = self.get_bass_ratio(audio_data)
        is_spike    = self.detect_spike(rms)

        self.rms_history.append(rms)

        if rms < SILENCE_THRESHOLD:
            return {"s3_voice": False, "s4_category": "silence",
                    "rms": rms, "voice_ratio": voice_ratio, "bass_ratio": bass_ratio}

        # Speech requires: voice_ratio + ZCR + bass not too high (excludes vocal songs)
        voice_ratio_ok = (voice_ratio >= VOICE_ENERGY_RATIO) and (rms >= SPEECH_THRESHOLD)
        zcr_ok         = self.is_speech_by_zcr(audio_data)
        not_music_bass = bass_ratio < BASS_MUSIC_RATIO  # High bass ratio indicates music
        is_voice       = voice_ratio_ok and zcr_ok and not_music_bass

        # Conversely: strong bass → classify as music regardless of voice_ratio
        is_music_by_bass = (bass_ratio >= BASS_MUSIC_RATIO) and (rms >= ENERGETIC_THRESHOLD * 0.5)

        if is_voice:
            return {"s3_voice": True, "s4_category": "speech",
                    "rms": rms, "voice_ratio": voice_ratio, "bass_ratio": bass_ratio}

        if is_spike:
            return {"s3_voice": False, "s4_category": "alert_spike",
                    "rms": rms, "voice_ratio": voice_ratio, "bass_ratio": bass_ratio}

        if is_music_by_bass or rms >= ENERGETIC_THRESHOLD:
            return {"s3_voice": False, "s4_category": "loud_noise",
                    "rms": rms, "voice_ratio": voice_ratio, "bass_ratio": bass_ratio}

        return {"s3_voice": False, "s4_category": "silence",
                "rms": rms, "voice_ratio": voice_ratio, "bass_ratio": bass_ratio}


def run_audio_detector(stop_event: threading.Event):
    try:
        import sounddevice as sd
    except ImportError:
        print("[SENSE] ERROR: sounddevice not installed. Run: pip install sounddevice")
        return

    print("[SENSE] Audio detector started.")

    classifier    = AudioClassifier()
    last_category = None

    from collections import deque, Counter
    WINDOW_SIZE      = 40
    category_history = deque(maxlen=WINDOW_SIZE)
    rms_history_long = deque(maxlen=WINDOW_SIZE)

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
            while not stop_event.is_set():
                try:
                    audio, overflowed = stream.read(CHUNK_SIZE)
                    audio_np = audio.flatten()

                    result       = classifier.classify(audio_np)
                    raw_category = result["s4_category"]
                    rms          = result["rms"]
                    voice        = result["s3_voice"]
                    is_spike     = (raw_category == "alert_spike")

                    shared_state.update("audio_spike", is_spike)

                    if not is_spike:
                        category_history.append(raw_category)
                        rms_history_long.append(rms)
                    if len(category_history) == WINDOW_SIZE:
                        counts = Counter(category_history)
                        if counts.get("silence", 0) > WINDOW_SIZE * 0.70:
                            final_category = "silence"
                        else:
                            active_sounds = [c for c in category_history if c != "silence"]
                            if not active_sounds:
                                final_category = "silence"
                            else:
                                active_counts = Counter(active_sounds)
                                # Speech threshold raised from 0.15 to SPEECH_WINDOW_RATIO (0.45)
                                loud_frames = sum(1 for r in rms_history_long if r >= ENERGETIC_THRESHOLD)
                                true_loud_ratio = loud_frames / WINDOW_SIZE

                                if true_loud_ratio >= 0.60:
                                    final_category = "music"
                                elif active_counts.get("speech", 0) > len(active_sounds) * SPEECH_WINDOW_RATIO:
                                    final_category = "speech"
                                else:
                                    final_category = active_counts.most_common(1)[0][0]
                                    if final_category == "loud_noise" or final_category == "keyboard":
                                        final_category = "silence"
                    else:
                        final_category = raw_category

                    shared_state.update("audio_rms", float(rms))
                    shared_state.update("audio_category", final_category)
                    shared_state.update("speech_active", voice)

                    if rms > 150:
                        zcr = classifier.get_zcr(audio_np)
                        print(f"   [Tuning] RMS: {rms:5.0f} | Voice: {result['voice_ratio']:.1%} | ZCR: {zcr:.3f} | Bass: {result['bass_ratio']:.1%}")

                    display_cat = "alert_spike" if is_spike else final_category
                    if display_cat != last_category or is_spike:
                        icon = {"silence": "🔇", "speech": "🗣️ ",
                                "music": "🎵", "alert_spike": "⚡"}.get(display_cat, "?")
                        print(f"[AUDIO] {icon} Locked: {final_category.upper():<10} | "
                              f"Raw: {raw_category:<12} | Speech: {voice}"
                              + (" [Spike blocked]" if is_spike else ""))
                        last_category = display_cat

                except Exception as e:
                    print(f"[SENSE] Audio error inside loop: {e}")
                    time.sleep(0.5)

    except Exception as e:
        print(f"[SENSE] Audio stream error: {e}")

    print("[SENSE] Audio detector stopped.")


def run_calibration():
    import sounddevice as sd
    classifier = AudioClassifier()
    print("\n" + "="*50)
    print("ANIMA Audio Threshold Calibration (with ZCR)")
    print("="*50)

    def sample(label, seconds, instruction):
        print(f"\n{'─'*50}")
        print(f"[Scene]: {label}")
        print(f">> {instruction}")
        for i in range(3, 0, -1):
            print(f"  Countdown {i}...", end='\r')
            time.sleep(1)
        print("  Recording...")
        rms_v, ratio_v, zcr_v, bass_v = [], [], [], []
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
            for _ in range(int(SAMPLE_RATE / CHUNK_SIZE * seconds)):
                audio, _ = stream.read(CHUNK_SIZE)
                audio_np = audio.flatten()
                rms_v.append(classifier.compute_rms(audio_np))
                ratio_v.append(classifier.get_voice_ratio(audio_np))
                zcr_v.append(classifier.get_zcr(audio_np))
                bass_v.append(classifier.get_bass_ratio(audio_np))
        print(f"  Done")
        print(f"     RMS:   min={min(rms_v):.0f}  max={max(rms_v):.0f}  avg={np.mean(rms_v):.0f}")
        print(f"     Voice: min={min(ratio_v):.2f}  max={max(ratio_v):.2f}  avg={np.mean(ratio_v):.2f}")
        print(f"     ZCR:   min={min(zcr_v):.3f}  max={max(zcr_v):.3f}  avg={np.mean(zcr_v):.3f}  std={np.std(zcr_v):.3f}")
        print(f"     Bass:  min={min(bass_v):.3f}  max={max(bass_v):.3f}  avg={np.mean(bass_v):.3f}")
        return rms_v, ratio_v, zcr_v, bass_v

    silence_rms, _, _, _                               = sample("Silence",    5, "Stay completely silent")
    speech_rms,  speech_ratio, speech_zcr, speech_bass = sample("Speech",     8, "Speak at normal volume continuously")
    music_rms,   _, music_zcr, music_bass              = sample("Music",      8, "Play a pop song with vocals")
    spike_rms,   _, _, _                               = sample("Table bang", 5, "Bang the table hard twice mid-sample")

    silence_max  = np.percentile(silence_rms, 95)
    speech_min   = np.percentile(speech_rms, 20)
    speech_r_min = np.percentile(speech_ratio, 20)
    speech_z_avg   = np.mean(speech_zcr)
    music_z_avg    = np.mean(music_zcr)
    speech_bass_avg = np.mean(speech_bass)
    music_bass_avg  = np.mean(music_bass)
    music_min      = np.percentile(music_rms, 20)
    spike_max      = np.percentile(spike_rms, 90)
    normal_avg     = np.mean(speech_rms)

    print("\n" + "="*50)
    print("Suggested thresholds — copy to top of file")
    print("="*50)
    print(f"SILENCE_THRESHOLD   = {int(max(50, silence_max * 1.3))}")
    print(f"SPEECH_THRESHOLD    = {int(speech_min * 0.8)}")
    print(f"ENERGETIC_THRESHOLD = {int(music_min * 0.8)}")
    print(f"VOICE_ENERGY_RATIO  = {max(0.2, speech_r_min - 0.1):.2f}")
    print(f"SPIKE_RATIO         = {max(2.5, spike_max / (normal_avg + 1) * 0.5):.1f}")
    print(f"SPIKE_MIN_RMS       = {int(max(200, silence_max * 2))}")
    print(f"\n# ZCR params (speech={speech_z_avg:.3f}, music={music_z_avg:.3f})")
    print(f"ZCR_SPEECH_MIN      = {max(0.03, music_z_avg * 1.1):.3f}")
    print(f"ZCR_VAR_MIN         = 0.02")
    print(f"\n# Bass params (speech={speech_bass_avg:.3f}, music={music_bass_avg:.3f})")
    bass_threshold = (speech_bass_avg + music_bass_avg) / 2
    print(f"BASS_MUSIC_RATIO    = {bass_threshold:.3f}  # Above this -> likely music")
    print(f"BASS_SPEECH_MAX     = {speech_bass_avg + 0.02:.3f}  # Speech bass upper bound")
    print("="*50)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "calibrate":
        run_calibration()
    else:
        stop_event = threading.Event()
        try:
            run_audio_detector(stop_event)
        except KeyboardInterrupt:
            stop_event.set()
        print("停止运行")
