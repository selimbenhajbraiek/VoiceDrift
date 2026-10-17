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


def ready(tasks):
    """The tasks among `tasks` that are trained and not switched off, in order."""
    return [t for t in tasks if load(t) and not TASKS[t].get("disabled")]


def prepare(source, vowel=False):
    """Quality-check a reading or an "aaah" and return the cleaned 16 kHz audio; raises QualityError."""
    # The models were trained on 1-2 s vowels and ~2 s sentences, so short clips are fine here.
    if vowel:
        return check_vowel(source)[0]
    return check_quality(source, min_duration_s=1.5, hint="Please read at least one full sentence.")[0]


def is_unusual(task, prob):
    """True from the "some similarity" threshold up (chosen in training: 20% of healthy people are above it)."""
    return prob >= load(task).get("thresholds", {"some": 0.5})["some"]


def report(task, wav):
    """Everything about one cleaned clip from a single feature pass, with the same decision as verdict():

    {"score": 0-1 similarity to the condition group, "condition", "right" (as verdict returns them),
     "groups": [(group, probability, how often that first guess was right in testing)], most likely first}.
    """
    bundle = load(task)
    x = features(task, wav)
    prob = float(bundle["model"].predict_proba(x)[:, 1].mean())
    rows = []
    if groups := bundle.get("condition_groups"):
        proba = groups["model"].predict_proba(x).mean(axis=0)
        rows = sorted(((str(c), float(p), float(groups["right"][c])) for c, p in zip(groups["classes"], proba)),
                      key=lambda r: -r[1])
    condition = right = None
    if is_unusual(task, prob):
        named = [r for r in rows if r[0] != "Healthy"]
        condition, right = (named[0][0], named[0][2]) if named else ("A voice disorder", None)
    return {"score": prob, "condition": condition, "right": right, "groups": rows}


def verdict(task, wav):
    """(condition, how often that guess was right in testing) for a cleaned clip; (None, None) if healthy-sounding."""
    if not is_unusual(task, score(task, wav)):
        return None, None
    rows = [r for r in condition_breakdown(task, wav) if r[0] != "Healthy"]
    return (str(rows[0][0]), float(rows[0][2])) if rows else ("A voice disorder", None)
