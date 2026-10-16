"""Run the full pipeline on one recording: quality check, then every biomarker.

Test:  python analyze.py path/to/clip.wav [text_id]
"""
from datetime import datetime

from audio.quality import check_quality
from features.embedding import embed
from features.pauses import pause_features
from features.pitch import pitch_features
from features.transcript import transcript_features
from texts import TEXTS


def analyze(source, text_id):
    """Turn a recording of TEXTS[text_id] into a session dict ready to store.

    `source` is a path or file-like object. Raises QualityError if the clip is unusable.
    """
    wav, quality = check_quality(source)
    words = transcript_features(wav, TEXTS[text_id]["text"])
    transcript = words.pop("transcript")
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "text_id": text_id,
        "transcript": transcript,
        "biomarkers": {**words, **pitch_features(wav), **pause_features(wav)},
        "quality": quality,
        "embedding": [round(float(x), 6) for x in embed(wav)],
    }


if __name__ == "__main__":
    import sys

    session = analyze(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else next(iter(TEXTS)))
    print("transcript:", session["transcript"])
    print("quality:   ", session["quality"])
    for key, value in session["biomarkers"].items():
        print(f"  {key:13s} {value:.3f}")
