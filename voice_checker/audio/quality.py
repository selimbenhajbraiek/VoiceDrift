"""Load a recording as 16 kHz mono and reject clips that can't be analyzed reliably.

Test:  python -m voice_checker.audio.quality path/to/clip.wav
"""
import numpy as np
import parselmouth
import soundfile as sf
import torch
import torchaudio

from voice_checker import config
from voice_checker.features.pauses import speech_segments

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


def check_level(samples):
    """Reject silent or clipped audio; returns the clipped fraction."""
    if samples.size == 0 or np.abs(samples).max() < 1e-3:
        raise QualityError(NO_SPEECH)
    clipped = float(np.mean(np.abs(samples) >= config.CLIP_LEVEL))
    if clipped > config.MAX_CLIP_FRACTION:
        raise QualityError(
            f"{clipped:.1%} of the recording is clipped (too loud), which distorts the voice. "
            "Sit about an arm's length from the microphone or lower its input volume, then record again."
        )
    return clipped


def check_snr(snr):
    """Reject recordings whose voice is less than MIN_SNR_DB above the background."""
    if snr is not None and snr < config.MIN_SNR_DB:
        raise QualityError(
            f"There is too much background noise: your voice is only {snr:.0f} dB above it "
            f"(we need {config.MIN_SNR_DB:.0f} dB). Move to a quieter room, switch off fans, "
            "music or TV, and speak closer to the microphone."
        )


def voiced_span(wav):
    """(start_s, end_s, voiced fraction) from the first to the last voiced frame (Praat pitch tracking).

    The whole span is kept, breaks included: disordered voices break up, and that is
    part of what the model listens to.
    """
    sound = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=config.SAMPLE_RATE)
    pitch = sound.to_pitch(time_step=0.01, pitch_floor=config.PITCH_FLOOR_HZ, pitch_ceiling=config.PITCH_CEILING_HZ)
    voiced = pitch.selected_array["frequency"] > 0
    if not voiced.any():
        return 0.0, 0.0, 0.0
    times = pitch.xs()[voiced]
    first, last = int(np.argmax(voiced)), len(voiced) - 1 - int(np.argmax(voiced[::-1]))
    return float(times[0]), float(times[-1]), float(voiced[first : last + 1].mean())


def check_vowel(source, min_duration_s=1.0):  # the training vowels (SVD) are 1-2 s long
    """Like check_quality, for a sustained “aaah”: finds it by voicing, since speech detectors often miss vowels.

    Returns (wav, report): the 16 kHz mono steady part of the vowel, and its report.
    """
    samples, sr = read_audio(source)
    clipped = check_level(samples)
    wav = to_16k_mono(samples, sr)
    start, end, fraction = voiced_span(wav)
    if end - start < min_duration_s or fraction < 0.5:
        raise QualityError(f"We only heard {end - start:.1f} s of “aaah”; we need at least {min_duration_s:g} s of "
                           "mostly voiced sound. Take a breath and hold the “aaah” for 3 to 5 seconds at a comfortable pitch.")
    i, j = int(start * config.SAMPLE_RATE), int(end * config.SAMPLE_RATE)
    vowel, rest = wav[i:j], np.concatenate([wav[:i], wav[j:]])
    snr = None
    if len(rest) >= config.MIN_NOISE_S * config.SAMPLE_RATE:
        snr = float(10 * np.log10(np.mean(vowel**2) / (np.mean(rest**2) + 1e-10)))
    check_snr(snr)
    return vowel, {"duration_s": round(float(end - start), 1), "snr_db": snr, "clipped_pct": 100 * clipped}


def check_quality(source, min_duration_s=config.MIN_DURATION_S, hint="Please read the whole text before stopping."):
    """Load a recording and make sure it is usable (at least `min_duration_s` of speech).

    Returns (wav, report): the 16 kHz mono clip trimmed to the speech plus a
    small margin, and {"duration_s", "snr_db", "clipped_pct"}.
    Raises QualityError with a fix-it message otherwise.
    """
    samples, sr = read_audio(source)
    clipped = check_level(samples)
    wav = to_16k_mono(samples, sr)
    segments = speech_segments(wav)
    if not segments:
        raise QualityError(NO_SPEECH)
    snr = estimate_snr_db(wav, segments)
    check_snr(snr)

    margin = int(config.SPEECH_MARGIN_S * config.SAMPLE_RATE)
    first = max(0, int(segments[0][0] * config.SAMPLE_RATE) - margin)
    last = int(segments[-1][1] * config.SAMPLE_RATE) + margin
    wav = wav[first:last]
    duration = len(wav) / config.SAMPLE_RATE
    if duration < min_duration_s:
        raise QualityError(
            f"We only heard {duration:.1f} s of voice; we need at least {min_duration_s:g} s. {hint}"
        )
    return wav, {"duration_s": round(duration, 1), "snr_db": snr, "clipped_pct": 100 * clipped}


if __name__ == "__main__":
    import sys

    try:
        _, report = check_quality(sys.argv[1])
        print("OK", report)
    except QualityError as e:
        print("REJECTED:", e)
