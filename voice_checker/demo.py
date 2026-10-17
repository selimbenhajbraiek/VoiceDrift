"""Demo data: a fake user with 3 baseline readings and 4 readings that drift.

Run:  python -m voice_checker.demo   (or use the "Load demo data" button in the app)
"""
from datetime import datetime, timedelta

import numpy as np

from voice_checker import config
from voice_checker import storage
from voice_checker.features.transcript import align, normalize
from voice_checker.texts import TEXTS

TEXT_ID = "market"

# One row per session: wpm, f0 mean, f0 SD, pauses, pause ratio, misreads,
# fillers and embedding noise. The first 3 are the baseline; then the reader
# gets gradually slower, flatter, more hesitant, and sounds less like themself.
SESSIONS = [
    # wpm   f0     f0sd  pauses ratio  slips fillers emb
    (158, 118.0, 2.95, 9, 0.13, 1, 0, 0.020),
    (164, 121.0, 3.10, 8, 0.12, 0, 1, 0.020),
    (155, 116.5, 2.85, 10, 0.14, 2, 0, 0.020),
    (151, 117.0, 2.75, 10, 0.15, 2, 1, 0.020),  # Stable: small wobble
    (133, 114.0, 2.25, 16, 0.22, 4, 3, 0.022),  # Watch
    (130, 113.5, 2.15, 16, 0.23, 5, 3, 0.024),  # Watch
    (117, 110.5, 1.75, 19, 0.31, 7, 5, 0.026),  # Changed
]


def fake_transcript(text, slips, fillers, rng):
    """The expected text with a few misread/skipped words and filler words."""
    words = normalize(text)
    for i in sorted(rng.choice(len(words), slips, replace=False), reverse=True):
        w = words[i]
        if rng.random() < 0.4:
            del words[i]  # skipped word
        else:
            words[i] = w[:-1] if w.endswith("s") else w + "s"  # misread ending
    for i in sorted(rng.choice(len(words), fillers, replace=False), reverse=True):
        words.insert(int(i), str(rng.choice(["um", "uh"])))
    return " ".join(words).capitalize() + "."


def fake_embedding(base, drift_dir, noise, step, rng):
    """A unit vector near `base`, pushed along `drift_dir` as the sessions go on."""
    v = base + 0.025 * max(0, step - 2) * drift_dir + rng.normal(0, noise, base.shape)
    return v / np.linalg.norm(v)


def demo_sessions():
    """3 baseline and 4 drifting demo readings of TEXT_ID, oldest first (session dicts like analyze() returns)."""
    rng = np.random.default_rng(7)
    base, drift_dir = rng.normal(size=(2, 192))
    base /= np.linalg.norm(base)
    drift_dir /= np.linalg.norm(drift_dir)
    text = TEXTS[TEXT_ID]["text"]
    start = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=len(SESSIONS))
    sessions = []
    for i, (wpm, f0, f0sd, pauses, ratio, slips, fillers, noise) in enumerate(SESSIONS):
        transcript = fake_transcript(text, slips, fillers, rng)
        wer, _ = align(text, transcript)
        when = start + timedelta(days=i, minutes=int(rng.integers(0, 90)))
        sessions.append({
            "timestamp": when.isoformat(timespec="seconds"),
            "text_id": TEXT_ID,
            "transcript": transcript,
            "biomarkers": {
                "wpm": wpm, "wer": wer, "filler_count": fillers,
                "f0_mean_hz": f0, "f0_std_st": f0sd,
                "pause_count": pauses, "pause_ratio": ratio,
            },
            "quality": {"duration_s": round(len(normalize(text)) / wpm * 60, 1), "snr_db": 32.0, "clipped_pct": 0.0},
            "embedding": [round(float(x), 6) for x in fake_embedding(base, drift_dir, noise, i, rng)],
        })
    return sessions


def load_demo():
    """Overwrite the demo user with fresh demo sessions and return it."""
    user = {"name": config.DEMO_USER, "sessions": demo_sessions()}
    storage.save_user(user)
    return user


if __name__ == "__main__":
    from voice_checker import drift

    user = load_demo()
    _, rows = drift.score_history(storage.sessions_for_text(user, TEXT_ID))
    for r in rows:
        top = ", ".join(f"{k} {z:+.1f}" for k, z in drift.top_changes(r["z"]))
        print(f"{r['timestamp']}  {r['status']:8s} index {r['index']:.2f} | {top}")
    print("persistent alert:", drift.is_persistent(rows))
    print("saved to", storage.user_file(config.DEMO_USER))
