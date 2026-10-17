"""Pauses, from silero-vad: how often the reader stops and for how long.

Test:  python -m voice_checker.features.pauses path/to/clip.wav
"""
import warnings
from functools import lru_cache

import torch
from silero_vad import get_speech_timestamps, load_silero_vad

from voice_checker import config


@lru_cache(maxsize=None)
def get_vad():
    """Load silero-vad once (the weights ship inside the pip package)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)  # torch.jit.load deprecation notice
        return load_silero_vad()


def speech_segments(wav):
    """Return the speech in a 16 kHz mono clip as [(start_s, end_s), ...]."""
    stamps = get_speech_timestamps(
        torch.from_numpy(wav),
        get_vad(),
        threshold=config.VAD_THRESHOLD,
        sampling_rate=config.SAMPLE_RATE,
    )
    return [(s["start"] / config.SAMPLE_RATE, s["end"] / config.SAMPLE_RATE) for s in stamps]


def pause_features(wav):
    """Number of pauses >= MIN_PAUSE_S, and the share of time spent in them.

    The pause ratio is pause time divided by the time from the first to the
    last speech, so silence before and after the reading does not count.
    """
    segs = speech_segments(wav)
    gaps = [nxt[0] - prev[1] for prev, nxt in zip(segs, segs[1:])]
    pauses = [g for g in gaps if g >= config.MIN_PAUSE_S]
    span = segs[-1][1] - segs[0][0] if segs else 0.0
    return {
        "pause_count": len(pauses),
        "pause_ratio": sum(pauses) / span if span > 0 else 0.0,
    }


if __name__ == "__main__":
    import sys

    from voice_checker.audio.quality import load_audio

    print(pause_features(load_audio(sys.argv[1])))
