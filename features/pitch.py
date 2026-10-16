"""Pitch, from Praat (parselmouth): mean F0 and F0 variability over voiced frames.

Test:  python -m features.pitch path/to/clip.wav
"""
import numpy as np
import parselmouth

import config


def pitch_features(wav):
    """Mean F0 in Hz and F0 standard deviation in semitones, over voiced frames only."""
    sound = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=config.SAMPLE_RATE)
    pitch = sound.to_pitch(pitch_floor=config.PITCH_FLOOR_HZ, pitch_ceiling=config.PITCH_CEILING_HZ)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]  # Praat marks unvoiced frames with 0
    if len(f0) == 0:
        raise ValueError("No voiced speech found in the recording.")
    semitones = 12 * np.log2(f0 / 100.0)  # relative to 100 Hz; the SD doesn't depend on the reference
    return {"f0_mean_hz": float(f0.mean()), "f0_std_st": float(semitones.std())}


if __name__ == "__main__":
    import sys

    from audio.quality import load_audio

    print(pitch_features(load_audio(sys.argv[1])))
