# -*- coding: utf-8 -*-
"""
sense/audio_detector.py
-----------------------
S3: Is speech happening? (True/False)
S4: What audio category? ("silence" / "speech" / "music" / "alert_spike")

修改记录 v2：
  1. 新增 ZCR（零交叉率）特征 — 说话时断断续续，ZCR 高且变化大；
                               音乐持续稳定，ZCR 低且变化小
  2. classify() 改为 voice_ratio + ZCR 双重验证，才认定为 speech
  3. 滑动窗口 speech 锁定门槛从 0.15 → 0.45，防止有人声的歌曲误判
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

# ── 分类阈值（校准后的值）──
SILENCE_THRESHOLD   = 100
SPEECH_THRESHOLD    = 150
ENERGETIC_THRESHOLD = 300
SPIKE_RATIO         = 6.0
SPIKE_MIN_RMS       = 4000
SPEECH_FREQ_LOW     = 100
SPEECH_FREQ_HIGH    = 2500
VOICE_ENERGY_RATIO  = 0.65
HISTORY_SIZE        = 15

# ── ZCR 语音/音乐区分参数 ──
ZCR_SPEECH_MIN  = 0.06   # 说话 ZCR 下限（低于此值即使 voice_ratio 达标也判为音乐）
ZCR_VAR_MIN     = 0.02   # ZCR 帧间变化下限（音乐稳定，说话变化大）

# ── 低频（Bass）特征：音乐低频能量明显高于说话 ──
BASS_FREQ_LOW   = 50     # bass 频段下限 Hz
BASS_FREQ_HIGH  = 200    # bass 频段上限 Hz
BASS_MUSIC_RATIO = 0.12  # bass 占总能量超过此比例 → 倾向于音乐
BASS_SPEECH_MAX  = 0.08  # bass 占总能量低于此比例 → 更可能是说话

# ── 滑动窗口 speech 门槛 ──
SPEECH_WINDOW_RATIO = 0.45   # 原来 0.15 太低，有人声的歌轻松超过


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
        零交叉率：信号每秒从正到负（或负到正）的次数占比。
        说话时口型变化快，ZCR 高且不稳定。
        音乐节奏连续，ZCR 低且稳定。
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
        ZCR 双重验证：
        条件1 — 当前帧 ZCR 高于下限
        条件2 — 最近几帧 ZCR 变化明显（说话不稳定，音乐稳定）
        两个条件都满足才认为是真正的说话
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

        # speech 需要：voice_ratio 达标 + ZCR 达标 + 低频不能太多（排除有人声的歌）
        voice_ratio_ok = (voice_ratio >= VOICE_ENERGY_RATIO) and (rms >= SPEECH_THRESHOLD)
        zcr_ok         = self.is_speech_by_zcr(audio_data)
        not_music_bass = bass_ratio < BASS_MUSIC_RATIO  # 低频占比太高说明是音乐
        is_voice       = voice_ratio_ok and zcr_ok and not_music_bass

        # 反过来：低频明显 → 直接判为音乐（不管 voice_ratio 多高）
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
                                # ── 【改动2】speech 门槛 0.15 → SPEECH_WINDOW_RATIO(0.45) ──
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
                        print(f"   [微调参考] RMS: {rms:5.0f} | 人声占比: {result['voice_ratio']:.1%} | ZCR: {zcr:.3f} | Bass占比: {result['bass_ratio']:.1%}")

                    display_cat = "alert_spike" if is_spike else final_category
                    if display_cat != last_category or is_spike:
                        icon = {"silence": "🔇", "speech": "🗣️ ",
                                "music": "🎵", "alert_spike": "⚡"}.get(display_cat, "?")
                        print(f"👉 [系统听觉] {icon} 锁定大场景: {final_category.upper():<10} | "
                              f"瞬时判定: {raw_category:<12} | 说话中: {voice}"
                              + (" [💥 突刺阻断!]" if is_spike else ""))
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
    print("ANIMA 音频阈值校准（含 ZCR）")
    print("="*50)

    def sample(label, seconds, instruction):
        print(f"\n{'─'*50}")
        print(f"【场景】：{label}")
        print(f"👉 {instruction}")
        for i in range(3, 0, -1):
            print(f"  倒计时 {i}...", end='\r')
            time.sleep(1)
        print("  🟢 开始！")
        rms_v, ratio_v, zcr_v, bass_v = [], [], [], []
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
            for _ in range(int(SAMPLE_RATE / CHUNK_SIZE * seconds)):
                audio, _ = stream.read(CHUNK_SIZE)
                audio_np = audio.flatten()
                rms_v.append(classifier.compute_rms(audio_np))
                ratio_v.append(classifier.get_voice_ratio(audio_np))
                zcr_v.append(classifier.get_zcr(audio_np))
                bass_v.append(classifier.get_bass_ratio(audio_np))
        print(f"  ✅ 完成")
        print(f"     RMS:   min={min(rms_v):.0f}  max={max(rms_v):.0f}  avg={np.mean(rms_v):.0f}")
        print(f"     Voice: min={min(ratio_v):.2f}  max={max(ratio_v):.2f}  avg={np.mean(ratio_v):.2f}")
        print(f"     ZCR:   min={min(zcr_v):.3f}  max={max(zcr_v):.3f}  avg={np.mean(zcr_v):.3f}  std={np.std(zcr_v):.3f}")
        print(f"     Bass:  min={min(bass_v):.3f}  max={max(bass_v):.3f}  avg={np.mean(bass_v):.3f}")
        return rms_v, ratio_v, zcr_v, bass_v

    silence_rms, _, _, _                          = sample("静音",   5, "保持绝对安静")
    speech_rms,  speech_ratio, speech_zcr, speech_bass = sample("说话",   8, "正常音量持续说话")
    music_rms,   _, music_zcr, music_bass          = sample("音乐",   8, "播放一首有人声的流行歌")
    spike_rms,   _, _, _                           = sample("拍桌子", 5, "采样中途用力拍两下桌子")

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
    print("建议阈值 → 复制替换代码顶部")
    print("="*50)
    print(f"SILENCE_THRESHOLD   = {int(max(50, silence_max * 1.3))}")
    print(f"SPEECH_THRESHOLD    = {int(speech_min * 0.8)}")
    print(f"ENERGETIC_THRESHOLD = {int(music_min * 0.8)}")
    print(f"VOICE_ENERGY_RATIO  = {max(0.2, speech_r_min - 0.1):.2f}")
    print(f"SPIKE_RATIO         = {max(2.5, spike_max / (normal_avg + 1) * 0.5):.1f}")
    print(f"SPIKE_MIN_RMS       = {int(max(200, silence_max * 2))}")
    print(f"\n# ZCR 参数（说话={speech_z_avg:.3f}，音乐={music_z_avg:.3f}）")
    print(f"ZCR_SPEECH_MIN      = {max(0.03, music_z_avg * 1.1):.3f}")
    print(f"ZCR_VAR_MIN         = 0.02")
    print(f"\n# Bass 参数（说话={speech_bass_avg:.3f}，音乐={music_bass_avg:.3f}）")
    bass_threshold = (speech_bass_avg + music_bass_avg) / 2
    print(f"BASS_MUSIC_RATIO    = {bass_threshold:.3f}  # 超过此值倾向音乐")
    print(f"BASS_SPEECH_MAX     = {speech_bass_avg + 0.02:.3f}  # 说话低频上限")
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
