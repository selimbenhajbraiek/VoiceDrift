"""Transcript, speaking rate, reading errors and filler words, from faster-whisper.

Test:  python -m voice_checker.features.transcript path/to/clip.wav [text_id]
"""
import re
from functools import lru_cache

import jiwer
from faster_whisper import WhisperModel

from voice_checker import config


@lru_cache(maxsize=None)
def get_model():
    """Download (first run only) and load Whisper base.en, int8 on CPU."""
    return WhisperModel(
        config.WHISPER_MODEL,
        device="cpu",
        compute_type=config.WHISPER_COMPUTE,
        download_root=str(config.MODELS_DIR / "whisper"),
    )


def normalize(text):
    """Lowercase, drop apostrophes and turn other punctuation into spaces; return the words."""
    text = text.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", text).split()


def transcribe(wav):
    """Return (transcript, words), where words carry .start and .end in seconds."""
    segments, _ = get_model().transcribe(
        wav,
        language="en",
        word_timestamps=True,
        initial_prompt=config.FILLER_PROMPT,  # keeps "um"/"uh" in the transcript
        condition_on_previous_text=False,
    )
    words = [w for seg in segments for w in seg.words]
    return "".join(w.word for w in words).strip(), words


def align(expected_text, transcript):
    """Compare what was heard with the expected text, ignoring filler words.

    Returns (wer, diff) where diff is a list of (op, expected_word, heard_word)
    and op is "ok", "sub" (misread), "del" (skipped) or "ins" (extra word).
    """
    ref = normalize(expected_text)
    hyp = [w for w in normalize(transcript) if w not in config.FILLER_WORDS]
    out = jiwer.process_words(" ".join(ref), " ".join(hyp))
    diff = []
    for c in out.alignments[0]:
        r = ref[c.ref_start_idx : c.ref_end_idx]
        h = hyp[c.hyp_start_idx : c.hyp_end_idx]
        if c.type == "equal":
            diff += [("ok", w, w) for w in r]
        elif c.type == "substitute":
            diff += [("sub", a, b) for a, b in zip(r, h)]
        elif c.type == "delete":
            diff += [("del", w, None) for w in r]
        else:
            diff += [("ins", None, w) for w in h]
    return float(out.wer), diff


def transcript_features(wav, expected_text):
    """Transcript plus words per minute, word error rate and filler-word count.

    Words per minute counts the non-filler words over the time from the first
    to the last spoken word.
    """
    text, words = transcribe(wav)
    heard = normalize(text)
    n_fillers = sum(w in config.FILLER_WORDS for w in heard)
    minutes = float(words[-1].end - words[0].start) / 60 if words else 0.0
    wer, _ = align(expected_text, text)
    return {
        "transcript": text,
        "wpm": (len(heard) - n_fillers) / minutes if minutes > 0 else 0.0,
        "wer": wer,
        "filler_count": n_fillers,
    }


if __name__ == "__main__":
    import sys

    from voice_checker.audio.quality import load_audio
    from voice_checker.texts import TEXTS

    text_id = sys.argv[2] if len(sys.argv) > 2 else next(iter(TEXTS))
    result = transcript_features(load_audio(sys.argv[1]), TEXTS[text_id]["text"])
    print(result)
    _, diff = align(TEXTS[text_id]["text"], result["transcript"])
    print("misreads:", [d for d in diff if d[0] != "ok"])
