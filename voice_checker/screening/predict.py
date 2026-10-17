"""Score a new recording with a trained screening model."""
from functools import lru_cache

import joblib
import numpy as np

from voice_checker import config
from voice_checker.audio.quality import check_quality, check_vowel
from voice_checker.screening import MODEL_DIR, TASKS
from voice_checker.screening.features import feature_vector

WINDOW_S = 3.0  # TORGO clips are short utterances, so a long reading is scored in pieces
VOWEL_S = 2.0   # SVD vowels are short, so only the steady middle of an "aaah" is used


@lru_cache(maxsize=None)
def load(task):
    """The saved bundle {"model", metrics…} for a task, or None if it hasn't been trained."""
    path = MODEL_DIR / f"{task}.joblib"
    return joblib.load(path) if path.exists() else None


def windows(wav, seconds=WINDOW_S):
    """Split a clip into pieces of `seconds`, keeping a last piece of at least half that."""
    n = int(seconds * config.SAMPLE_RATE)
    return [wav[i : i + n] for i in range(0, max(1, len(wav) - n // 2), n)] or [wav]


def middle(wav, seconds=VOWEL_S):
    """The central `seconds` of a clip."""
    n = int(seconds * config.SAMPLE_RATE)
    start = max(0, (len(wav) - n) // 2)
    return wav[start : start + n]


def features(task, wav):
    """The model's feature rows for a clip: 3 s windows of a reading, or the middle of an "aaah"."""
    start, stop = load(task).get("columns", (0, None))
    clips = windows(wav) if TASKS[task]["recording"] == "reading" else [middle(wav)]
    return np.stack([feature_vector(c) for c in clips])[:, start:stop]


def score(task, wav):
    """Probability (0-1) that the recording resembles the dataset's condition group."""
    return float(load(task)["model"].predict_proba(features(task, wav))[:, 1].mean())


def condition_breakdown(task, wav):
    """[(group, probability, how often that first guess was right in testing)], most likely first; [] if none."""
    groups = load(task).get("condition_groups")
    if not groups:
        return []
    proba = groups["model"].predict_proba(features(task, wav)).mean(axis=0)
    rows = [(c, float(p), groups["right"][c]) for c, p in zip(groups["classes"], proba)]
    return sorted(rows, key=lambda r: -r[1])
