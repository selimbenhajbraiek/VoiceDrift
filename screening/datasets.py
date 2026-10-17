"""Loaders for the research datasets. Each returns [(path, label, group, meta)]: label 1 = condition group.

`group` is the speaker, so testing can keep every speaker entirely in either the training
or the test part. `meta` holds "sex" ("f"/"m") and "age" (years, or None) for the
balancing and the report, and "condition" (the SVD folder, or dysarthria/control).
"""
import csv
import random
import re
from datetime import date
from pathlib import Path


def load_torgo(root, mic="arrayMic", per_speaker=200, seed=0):
    """TORGO utterances: dysarthric speakers (F01, M03, ...) = 1, controls (FC01, MC02, ...) = 0.

    Expects the extracted official archives anywhere under `root`, i.e. folders
    <speaker>/Session*/wav_<mic>/*.wav. Up to `per_speaker` random utterances each, from
    one microphone type only so that the two groups are recorded the same way.
    """
    rng = random.Random(seed)
    speakers = sorted({p for p in Path(root).rglob("*") if p.is_dir() and re.fullmatch(r"[FM]C?\d{2}", p.name)})
    items = []
    for speaker in speakers:
        wavs = sorted(speaker.glob(f"Session*/wav_{mic}/*.wav"))
        rng.shuffle(wavs)
        label = 0 if speaker.name[1] == "C" else 1
        meta = {"sex": speaker.name[0].lower(), "age": None, "condition": "dysarthria" if label else "control"}
        items += [(p, label, speaker.name, meta) for p in wavs[:per_speaker]]
    return items


def years_between(born, recorded):
    """Age in years from two ISO dates, or None if either is missing."""
    try:
        return (date.fromisoformat(recorded) - date.fromisoformat(born)).days / 365.25
    except ValueError:
        return None


def svd_sessions(folder):
    """{session id: {"speaker", "sex", "age"}} from a folder's overview.csv (shipped in the Zenodo zips)."""
    path = folder / "overview.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return {row["AufnahmeID"]: {"speaker": row["SprecherID"],
                                    "sex": "f" if row["Geschlecht"].lower() == "w" else row["Geschlecht"].lower(),
                                    "age": years_between(row["Geburtsdatum"], row["AufnahmeDatum"])}
                for row in csv.DictReader(f)}


def load_svd(root, pattern="*a_n*.wav"):
    """SVD sustained /a/ at normal pitch: root/healthy/ = 0, every other folder (one per pathology) = 1.

    Files are named like 123-a_n.wav (session 123). The group is the speaker id from
    overview.csv, so one person's sessions stay together. A session listed under two
    pathologies is used once.
    """
    items = {}
    for folder in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        label = 0 if folder.name.lower() == "healthy" else 1
        sessions = svd_sessions(folder)
        for p in sorted(folder.rglob(pattern)):
            info = sessions.get(p.stem.split("-")[0], {})
            group = "speaker" + info.get("speaker", "-session" + p.stem.split("-")[0])
            items.setdefault(p.name, (p, label, group, {"sex": info.get("sex", "?"), "age": info.get("age"),
                                                        "condition": folder.name}))
    return list(items.values())


LOADERS = {"torgo": load_torgo, "svd": load_svd, "svd_phrase": lambda root: load_svd(root, pattern="*-phrase.wav")}
