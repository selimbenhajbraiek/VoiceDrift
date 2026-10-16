"""Personal drift: how far a reading is from the same user's baseline for the same text."""
import numpy as np

import config

SCALARS = list(config.STD_FLOORS)  # scalar biomarkers that get a z-score


def cosine_distance(a, b):
    """1 - cosine similarity between two vectors."""
    return 1.0 - float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def build_baseline(sessions):
    """Summarize the baseline sessions.

    Embedding: centroid, plus mean/std of each baseline reading's distance to the
    centroid of the *other* baseline readings (leave-one-out). A reading compared
    with a centroid that includes itself looks too close, which would make every
    new reading look like drift. Scalars: mean and floored std.
    """
    embs = np.array([s["embedding"] for s in sessions])
    loo = [cosine_distance(e, np.delete(embs, i, axis=0).mean(axis=0)) for i, e in enumerate(embs)]
    baseline = {
        "embedding": {
            "centroid": embs.mean(axis=0),
            "mean": float(np.mean(loo)),
            "std": max(float(np.std(loo, ddof=1)), config.EMBEDDING_STD_FLOOR),
        }
    }
    for key in SCALARS:
        values = [s["biomarkers"][key] for s in sessions]
        baseline[key] = {
            "mean": float(np.mean(values)),
            "std": max(float(np.std(values, ddof=1)), config.STD_FLOORS[key]),
        }
    return baseline


def z_scores(session, baseline):
    """z-score of every biomarker vs. the baseline.

    The embedding z is clipped at 0: sounding *more* like your usual self is not drift.
    """
    emb = baseline["embedding"]
    dist = cosine_distance(session["embedding"], emb["centroid"])
    zs = {"embedding": max(0.0, (dist - emb["mean"]) / emb["std"])}
    for key in SCALARS:
        zs[key] = (session["biomarkers"][key] - baseline[key]["mean"]) / baseline[key]["std"]
    return zs


def drift_index(zs):
    """Overall index: root mean square of all z-scores."""
    return float(np.sqrt(np.mean(np.square(list(zs.values())))))


def status(index):
    """Map the overall index to Stable / Watch / Changed."""
    if index >= config.CHANGED_INDEX:
        return "Changed"
    if index >= config.WATCH_INDEX:
        return "Watch"
    return "Stable"


def score_history(sessions):
    """Score one user's sessions for one text (oldest first).

    Returns None while the baseline is incomplete, else (baseline, rows) with one
    row per session: {"timestamp", "is_baseline", "z", "index", "status"}.
    Baseline rows get the status "Baseline".
    """
    if len(sessions) < config.BASELINE_N:
        return None
    baseline = build_baseline(sessions[: config.BASELINE_N])
    rows = []
    for i, session in enumerate(sessions):
        zs = z_scores(session, baseline)
        index = drift_index(zs)
        is_baseline = i < config.BASELINE_N
        rows.append({
            "timestamp": session["timestamp"],
            "is_baseline": is_baseline,
            "z": zs,
            "index": index,
            "status": "Baseline" if is_baseline else status(index),
        })
    return baseline, rows


def is_persistent(rows, k=config.PERSIST_K):
    """True when the last k non-baseline readings are all Watch or Changed."""
    recent = [r["status"] for r in rows if not r["is_baseline"]][-k:]
    return len(recent) == k and all(s in ("Watch", "Changed") for s in recent)


def top_changes(zs, n=3):
    """The n biomarkers with the largest |z|, biggest first, as [(key, z), ...]."""
    return sorted(zs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:n]
