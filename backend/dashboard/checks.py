"""Check the recordings phones send: one at a time in a background thread, then email the result.

The audio only lives in memory until its check is done; the database keeps the result.
"""
import io
import logging
import math
import queue
import threading

import numpy as np

from voice_checker.config import SAMPLE_RATE
from voice_checker.audio.quality import QualityError
from backend.dashboard import db, notify
from voice_checker.screening import READING_TASKS, TASKS, describe, predict
from voice_checker.screening.features import VOICE_QUALITY, voice_quality

log = logging.getLogger("dashboard")
jobs = queue.Queue()
state = {"engine": "loading"}  # loading -> ready, or missing when no model is trained


def tasks():
    """{"reading": task or None, "vowel": task or None}: the model each recording mode uses."""
    reading = predict.ready(READING_TASKS)
    return {"reading": reading[0] if reading else None, "vowel": "svd" if predict.ready(["svd"]) else None}


def submit(check_id, user, mode, audio):
    """Queue a stored check (see db.add_check) with its audio bytes."""
    jobs.put((check_id, dict(user), mode, audio))


def start():
    """Start the worker thread; it loads the models first so the first check isn't slow."""
    threading.Thread(target=work, name="voice-checks", daemon=True).start()


def work():
    available = [t for t in tasks().values() if t]
    if not available:
        state["engine"] = "missing"
    else:
        try:  # loads the ECAPA embedding model and the classifiers
            predict.score(available[0], np.random.default_rng(0).normal(0, 0.01, 32000).astype(np.float32))
            state["engine"] = "ready"
        except Exception:
            log.exception("Warming up the voice models failed")
            state["engine"] = "missing"
    while True:
        check_id, user, mode, audio = jobs.get()
        try:
            run(check_id, user, mode, audio)
        except Exception:
            log.exception("Check %s failed", check_id)
            db.update_check(check_id, status="error",
                            message="Something went wrong on the laptop while checking this recording. Please try again.")


def run(check_id, user, mode, audio):
    task = tasks()[mode]
    if task is None:
        db.update_check(check_id, status="error", message="This check isn't available: its model isn't trained yet.")
        return
    db.update_check(check_id, status="checking")
    try:
        wav = predict.prepare(io.BytesIO(audio), vowel=mode == "vowel")
    except QualityError as e:
        db.update_check(check_id, status="rejected", message=str(e))
        return
    found = predict.report(task, wav)
    condition, right = found["condition"], found["right"]
    headline, detail = describe(condition, right)
    result = {"flagged": condition is not None, "condition": condition, "right": right, "headline": headline,
              "detail": detail, "model": TASKS[task]["title"], "seconds": round(len(wav) / SAMPLE_RATE, 1),
              **details(task, mode, wav, found)}
    db.update_check(check_id, status="done", result=result)
    email(check_id, user)


def details(task, mode, wav, found):
    """What the result page shows beyond the headline: the similarity score and its bands, the closest groups,
    the voice measures and how the model did on people it never heard."""
    bundle = predict.load(task)
    metrics = bundle["speaker_metrics"]
    clip = predict.middle(wav) if mode == "vowel" else wav  # an "aaah" is measured on its steady middle
    measures = voice_quality(clip)
    return {
        "score": round(found["score"], 3),
        "bands": {k: round(float(v), 3) for k, v in bundle["thresholds"].items()},
        "groups": [{"name": name, "probability": round(p, 3), "right": round(r, 2)} for name, p, r in found["groups"]],
        "measures": [{"name": name, "value": None if math.isnan(v) else round(float(v), 2)}
                     for name, v in zip(VOICE_QUALITY, measures)],
        "reliability": {"people": int(metrics["n"]), "sensitivity": round(metrics["sensitivity"], 2),
                        "false_alarms": round(1 - metrics["specificity"], 2),
                        "names": [str(c) for c in (bundle.get("condition_groups") or {}).get("classes", []) if c != "Healthy"]},
    }


def email(check_id, user):
    """Email the user the result of a finished check and record how it went."""
    subject, body = notify.result_email(user["name"], db.check(check_id, user["id"]))
    try:
        outcome = notify.send(user["email"], subject, body)
    except Exception as e:  # a bad SMTP setting must not lose the result
        log.warning("Email for check %s failed: %s", check_id, e)
        outcome = f"failed: {e}"
    db.update_check(check_id, email=outcome)
