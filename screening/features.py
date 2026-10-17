"""Features for the screening models: one fixed-length vector per recording.

ECAPA embedding (192) + MFCC means and SDs (26) + Praat voice-quality measures (5).
"""
from functools import lru_cache

import numpy as np
import parselmouth
import torch
import torchaudio
from parselmouth.praat import call

import config
from features.embedding import embed
from features.pauses import speech_segments

VOICE_QUALITY = ["Average pitch (Hz)", "Pitch variability (semitones)", "Jitter (%)", "Shimmer (%)", "Harmonics-to-noise (dB)"]


@lru_cache(maxsize=None)
def mfcc_transform():
    """13 MFCCs on 25 ms frames every 10 ms."""
    return torchaudio.transforms.MFCC(sample_rate=config.SAMPLE_RATE, n_mfcc=13,
                                      melkwargs={"n_fft": 400, "hop_length": 160, "n_mels": 40})


def mfcc_stats(wav):
    """Mean and SD of each MFCC over the clip (26 numbers)."""
    m = mfcc_transform()(torch.from_numpy(wav)).numpy()
    return np.concatenate([m.mean(axis=1), m.std(axis=1)])


def voice_quality(wav):
    """Praat's classic measures: F0 mean and SD, local jitter and shimmer (%), HNR (dB); NaN if unvoiced."""
    sound = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=config.SAMPLE_RATE)
    lo, hi = config.PITCH_FLOOR_HZ, config.PITCH_CEILING_HZ
    f0 = sound.to_pitch(pitch_floor=lo, pitch_ceiling=hi).selected_array["frequency"]
    f0 = f0[f0 > 0]
    if len(f0) < 3:
        return np.full(len(VOICE_QUALITY), np.nan)
    points = call(sound, "To PointProcess (periodic, cc)", lo, hi)
    jitter = call(points, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    shimmer = call([sound, points], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    hnr = call(call(sound, "To Harmonicity (cc)", 0.01, lo, 0.1, 1.0), "Get mean", 0, 0)
    return np.array([f0.mean(), np.std(12 * np.log2(f0 / 100)), 100 * jitter, 100 * shimmer, hnr])


def feature_vector(wav):
    """The full feature vector of one 16 kHz mono clip (223 numbers)."""
    return np.concatenate([embed(wav), mfcc_stats(wav), voice_quality(wav)]).astype(np.float32)


def silence_vector(wav):
    """MFCC stats of the non-speech parts only (for the recording-setup check).

    None if no speech was detected (a sustained vowel often isn't, and then the "silence"
    would be the voice itself) or if there is under 0.2 s of silence.
    """
    sr = config.SAMPLE_RATE
    segments = speech_segments(wav)
    if not segments:
        return None
    mask = np.ones(len(wav), dtype=bool)
    for start, end in segments:
        mask[int(start * sr) : int(end * sr)] = False
    rest = wav[mask]
    return mfcc_stats(rest) if len(rest) >= 0.2 * sr else None
