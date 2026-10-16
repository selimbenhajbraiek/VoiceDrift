"""Load a recording as 16 kHz mono and reject clips that can't be analyzed reliably.

Test:  python -m audio.quality path/to/clip.wav
"""
import numpy as np
import soundfile as sf
import torch
import torchaudio

import config
from features.pauses import speech_segments

NO_SPEECH = (
    "We couldn't hear any speech. Check that the right microphone is selected and "
    "that your browser is allowed to use it, then record again."
)


class QualityError(ValueError):
    """A recording we can't use; the message tells the user how to fix it."""


def read_audio(source):
    """Decode a path or file-like object into (samples [n, channels], sample_rate)."""
    try:
        return sf.read(source, dtype="float32", always_2d=True)
    except sf.SoundFileError as e:
        raise QualityError(
            "We couldn't read this file. Please upload a WAV, FLAC, OGG or MP3 recording."
        ) from e


def to_16k_mono(samples, sr):
    """Average the channels and resample to 16 kHz with torchaudio."""
    mono = torch.from_numpy(samples).mean(dim=1)
    if sr != config.SAMPLE_RATE:
        mono = torchaudio.functional.resample(mono, sr, config.SAMPLE_RATE)
    return mono.numpy()


def load_audio(source):
    """Decode a clip to 16 kHz mono float32, without any quality checks."""
    return to_16k_mono(*read_audio(source))


def estimate_snr_db(wav, segments):
    """Speech-to-background ratio in dB: energy inside VAD speech vs. outside it.

    Returns None when there is too little non-speech audio to measure the background.
    """
    sr = config.SAMPLE_RATE
    is_speech = np.zeros(len(wav), dtype=bool)
    for start, end in segments:
        is_speech[int(start * sr) : int(end * sr)] = True
    noise = wav[~is_speech]
    if len(noise) < config.MIN_NOISE_S * sr:
        return None
    speech_power = np.mean(wav[is_speech] ** 2)
    noise_power = np.mean(noise**2) + 1e-10
    return float(10 * np.log10(speech_power / noise_power))


def check_quality(source):
    """Load a recording and make sure it is usable.

    Returns (wav, report): the 16 kHz mono clip trimmed to the speech plus a
    small margin, and {"duration_s", "snr_db", "clipped_pct"}.
    Raises QualityError with a fix-it message otherwise.
    """
    samples, sr = read_audio(source)
    if samples.size == 0 or np.abs(samples).max() < 1e-3:
        raise QualityError(NO_SPEECH)

    clipped = float(np.mean(np.abs(samples) >= config.CLIP_LEVEL))
    if clipped > config.MAX_CLIP_FRACTION:
        raise QualityError(
            f"{clipped:.1%} of the recording is clipped (too loud), which distorts the voice. "
            "Sit about an arm's length from the microphone or lower its input volume, then record again."
        )

    wav = to_16k_mono(samples, sr)
    segments = speech_segments(wav)
    if not segments:
        raise QualityError(NO_SPEECH)

    snr = estimate_snr_db(wav, segments)
    if snr is not None and snr < config.MIN_SNR_DB:
        raise QualityError(
            f"There is too much background noise: your voice is only {snr:.0f} dB above it "
            f"(we need {config.MIN_SNR_DB:.0f} dB). Move to a quieter room, switch off fans, "
            "music or TV, and speak closer to the microphone."
        )

    margin = int(config.SPEECH_MARGIN_S * config.SAMPLE_RATE)
    first = max(0, int(segments[0][0] * config.SAMPLE_RATE) - margin)
    last = int(segments[-1][1] * config.SAMPLE_RATE) + margin
    wav = wav[first:last]
    duration = len(wav) / config.SAMPLE_RATE
    if duration < config.MIN_DURATION_S:
        raise QualityError(
            f"We only heard {duration:.1f} s of reading; we need at least "
            f"{config.MIN_DURATION_S:.0f} s. Please read the whole text before stopping."
        )
    return wav, {"duration_s": round(duration, 1), "snr_db": snr, "clipped_pct": 100 * clipped}


if __name__ == "__main__":
    import sys

    try:
        _, report = check_quality(sys.argv[1])
        print("OK", report)
    except QualityError as e:
        print("REJECTED:", e)
