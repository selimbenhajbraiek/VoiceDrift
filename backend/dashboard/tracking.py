"""Track your voice: readings of one text, scored against the person's own baseline.

The voice_checker does the measuring (analyze) and the scoring (drift, explain); this module stores the readings
in the database and turns them into what the web app shows.
"""
import io
import os
from functools import lru_cache

from backend.dashboard import db
from voice_checker import config, demo, drift, explain
from voice_checker.analyze import analyze
from voice_checker.features.transcript import align
from voice_checker.texts import TEXTS

FORMATS = {  # how each biomarker value is shown
    "embedding": "{:.3f}", "wpm": "{:.0f} wpm", "wer": "{:.0%}", "filler_count": "{:.0f}",
    "f0_mean_hz": "{:.0f} Hz", "f0_std_st": "{:.1f} st", "pause_count": "{:.0f}", "pause_ratio": "{:.0%}",
}
TREND_KEYS = ["wpm", "pause_ratio", "f0_std_st"]  # the small charts under the trend


def fmt(key, value):
    return FORMATS[key].format(value)


def texts(user_id):
    """Every reading text with how many times this person has read it."""
    counts = db.reading_counts(user_id)
    return [{"id": k, "title": t["title"], "count": counts.get(k, 0)} for k, t in TEXTS.items()]


def add_reading(user_id, text_id, audio):
    """Analyze a recording of TEXTS[text_id] and store it. Raises QualityError if the recording is unusable."""
    db.add_reading(user_id, text_id, analyze(io.BytesIO(audio), text_id))
    return state(user_id, text_id)


def load_demo(user_id):
    """Replace this person's readings of the demo text with 3 baseline and 4 drifting demo readings."""
    db.delete_readings(user_id, demo.TEXT_ID)
    for session in demo.demo_sessions():
        db.add_reading(user_id, demo.TEXT_ID, session)
    return state(user_id, demo.TEXT_ID)


@lru_cache(maxsize=256)
def _summary(z_items, status, persistent):
    """Claude writes the summary when ANTHROPIC_API_KEY is set (status and top changes only); else templates."""
    return explain.summarize(dict(z_items), status, persistent, use_claude=bool(os.environ.get("ANTHROPIC_API_KEY")))


def transcript_diff(text_id, transcript):
    """What was heard, word by word: op is ok, sub (misread), del (skipped) or ins (extra)."""
    _, diff = align(TEXTS[text_id]["text"], transcript)
    return [{"op": op, "expected": exp, "heard": heard} for op, exp, heard in diff]


def state(user_id, text_id):
    """Everything the Track your voice page shows for one text."""
    sessions = db.readings(user_id, text_id)
    text = TEXTS[text_id]
    out = {
        "text": {"id": text_id, "title": text["title"], "text": text["text"]},
        "count": len(sessions),
        "baseline_n": config.BASELINE_N,
        "bands": {"watch": config.WATCH_INDEX, "changed": config.CHANGED_INDEX},
        "persist_k": config.PERSIST_K,
        "latest": None,
        "result": None,
        "trend": None,
    }
    if not sessions:
        return out
    latest = sessions[-1]
    out["latest"] = {
        "timestamp": latest["timestamp"],
        "quality": latest["quality"],
        "transcript": latest["transcript"],
        "diff": transcript_diff(text_id, latest["transcript"]),
    }
    scored = drift.score_history(sessions)
    if scored is None:
        return out

    baseline, rows = scored
    row = rows[-1]
    if row["is_baseline"]:
        out["result"] = {"status": "Baseline"}
    else:
        persistent = drift.is_persistent(rows)
        summary, source = _summary(tuple(sorted(row["z"].items())), row["status"], persistent)
        changes = []
        for key, z in drift.top_changes(row["z"]):
            if key == "embedding":
                now = drift.cosine_distance(latest["embedding"], baseline["embedding"]["centroid"])
                usual = baseline["embedding"]["mean"]
            else:
                now, usual = latest["biomarkers"][key], baseline[key]["mean"]
            changes.append({"key": key, "label": config.LABELS[key][0], "meaning": explain.MEANING[key],
                            "now": fmt(key, now), "usual": fmt(key, usual), "z": round(z, 2),
                            "phrase": explain.describe(key, z)})
        out["result"] = {"status": row["status"], "index": round(row["index"], 2), "persistent": persistent,
                         "summary": summary, "summary_source": source, "changes": changes}

    out["trend"] = {
        "readings": [{"timestamp": s["timestamp"], "index": round(r["index"], 2), "status": r["status"],
                      "is_baseline": r["is_baseline"],
                      "values": {k: s["biomarkers"][k] for k in TREND_KEYS},
                      "shown": {k: fmt(k, s["biomarkers"][k]) for k in TREND_KEYS}}
                     for s, r in zip(sessions, rows)],
        "series": [{"key": k, "label": config.LABELS[k][0], "unit": config.LABELS[k][1],
                    "usual": {"mean": baseline[k]["mean"], "std": baseline[k]["std"]}} for k in TREND_KEYS],
    }
    return out
