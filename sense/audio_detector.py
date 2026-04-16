"""
sense/audio_detector.py
-----------------------
S3: Is speech happening? (True/False)
S4: What audio category? ("silence" / "keyboard" / "speech" / "music")

Uses sounddevice for audio capture.
Simple RMS-based classification for now.
TODO: Replace with Librosa MFCC classifier for better accuracy.

Runs in its own thread, updates shared_state continuously.
"""

import time
import threading
import numpy as np
from sense.sensor_state import shared_state

# Audio settings
SAMPLE_RATE = 16000
CHUNK_SIZE = 1600       # 0.1 seconds of audio
CHANNELS = 1

# thresholds for classification (tune these after testing)
SILENCE_THRESHOLD = 0.01
VOICE_THRESHOLD = 0.5   # Threshold for mean FFT amplitude in voice band
SPIKE_THRESHOLD = 0.15  # RMS sudden spike threshold


def classify_audio(audio_chunk: np.ndarray) -> tuple:
    """
    FFT and RMS-based audio classification.
    Returns (audio_category, speech_active, rms)
    """
    rms = float(np.sqrt(np.mean(audio_chunk ** 2)))
    
    # S3: Use FFT to analyze frequencies for human voice (300Hz - 3400Hz)
    fft = np.fft.rfft(audio_chunk)
    freqs = np.fft.rfftfreq(len(audio_chunk), 1 / SAMPLE_RATE)
    
    voice_mask = (freqs >= 300) & (freqs <= 3400)
    voice_band = float(np.mean(np.abs(fft[voice_mask])))
    full_band = float(np.mean(np.abs(fft)))
    
    speech_active = voice_band > VOICE_THRESHOLD
    
    # S4: Categorize based on overall features
    if full_band > voice_band * 2.5:
        category = "music"   # Full band energy much greater than voice band = music
    elif voice_band > VOICE_THRESHOLD:
        category = "speech"
    elif rms < SILENCE_THRESHOLD:
        category = "silence"
    else:
        category = "ambient"
        
    return category, speech_active, rms


def run_audio_detector(stop_event: threading.Event):
    """
    Main loop for audio detection.
    Call this in a daemon thread from main.py.
    """
    try:
        import sounddevice as sd
    except ImportError:
        print("[SENSE] ERROR: sounddevice not installed. Run: pip install sounddevice")
        return

    print("[SENSE] Audio detector started.")
    prev_rms = 0.0

    while not stop_event.is_set():
        try:
            # Record one chunk of audio
            audio = sd.rec(
                CHUNK_SIZE,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32"
            )
            sd.wait()

            # Classify the chunk
            category, speech, rms = classify_audio(audio.flatten())

            shared_state.update("audio_category", category)
            shared_state.update("speech_active", speech)

            # Detect sudden loud sounds (spikes) to trigger Alert signals
            if rms > SPIKE_THRESHOLD and prev_rms < SPIKE_THRESHOLD * 0.5:
                shared_state.update("audio_spike", True)
            else:
                shared_state.update("audio_spike", False)
                
            prev_rms = rms

        except Exception as e:
            print(f"[SENSE] Audio error: {e}")
            time.sleep(0.5)

    print("[SENSE] Audio detector stopped.")
