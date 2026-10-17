"""Build a folder of recordings to upload in the app's 🩺 page, and score them all.

  1_unseen_conditions/   SVD conditions the models never saw (Parkinson's, ALS, ...), speakers not in training
  2_english_readings/    healthy English readers (LibriSpeech dev-clean, CC BY 4.0) and dysarthric
                         TORGO speakers; neither was used by the voice models
  3_seen_in_training/    SVD examples the models WERE trained on: fine for a demo, not a fair test

Each folder gets *_aaah.wav files (for the "Hold aaah" tab) and/or *_reading.wav files (for
"Read a text"). Files the app would reject are removed; RESULTS.md lists what the app says
for every remaining file.

Needs E:/VoiceDrift-data/librispeech/LibriSpeech/dev-clean (https://www.openslr.org/12).
Run:  python -m voice_checker.screening.make_test_set E:/VoiceDrift-data
"""
import csv
import io
import shutil
import sys
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

from voice_checker import config
from voice_checker.audio.quality import QualityError, check_quality, check_vowel, load_audio
from voice_checker.screening import predict
from voice_checker.screening.download_svd import open_zip, read_nsp

UNSEEN = {  # Zenodo zip -> file label (conditions not used in training)
    "Morbus Parkinson.zip": "parkinsons",
    "Amyotrophe Lateralsklerose.zip": "als",
    "Reinke O\u0308dem.zip": "reinke_edema",
    "Spasmodische Dysphonie.zip": "spasmodic_dysphonia",
    "Stimmlippenkarzinom.zip": "vocal_fold_cancer",
    "Funktionelle Dysphonie.zip": "functional_dysphonia",
    "Dysarthrophonie.zip": "dysarthrophonia",
}
PER_CONDITION = 3
TORGO_DYSARTHRIA = ["F03", "M01", "M03"]  # TORGO's control recordings are too noisy for the quality check
LIBRI_PER_SEX = 3
READING_S = 12.0  # utterances are short, so several are joined into one reading
GAP = np.zeros(6400, dtype=np.float32)  # 0.4 s pause between joined utterances


def trained_speakers(svd_root):
    """Speaker ids of every SVD recording used in training (from the overview.csv files)."""
    speakers = set()
    for path in Path(svd_root).glob("*/overview.csv"):
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            speakers |= {row["SprecherID"] for row in csv.DictReader(f)}
    return speakers


def save_nsp(z, member, target):
    """Convert one .nsp member of an open zip to a WAV file."""
    samples, rate = read_nsp(z.read(member))
    sf.write(target, samples, rate, subtype="PCM_16")


def unseen_conditions(svd_root, out):
    """A few vowel + sentence pairs per unseen condition, from speakers not in training."""
    out.mkdir(parents=True, exist_ok=True)
    skip, used = trained_speakers(svd_root), set()
    for name, label in UNSEEN.items():
        with open_zip(name, requests.Session()) as z:
            names = set(z.namelist())
            rows = csv.DictReader(io.TextIOWrapper(io.BytesIO(z.read("overview.csv")), encoding="utf-8", errors="replace"))
            picked = 0
            for row in rows:
                sid = row["AufnahmeID"]
                vowel, sentence = f"{sid}/vowels/{sid}-a_n.nsp", f"{sid}/sentences/{sid}-phrase.nsp"
                if row["SprecherID"] in skip or sid in used or vowel not in names or sentence not in names:
                    continue
                used.add(sid)  # a session listed under two conditions is used once
                save_nsp(z, vowel, out / f"{label}_{sid}_aaah.wav")
                save_nsp(z, sentence, out / f"{label}_{sid}_reading.wav")
                picked += 1
                if picked == PER_CONDITION:
                    break
        print(f"  {label}: {picked} speakers", flush=True)


def join_reading(paths, target, min_len_s=0.0):
    """Join utterances (each at least `min_len_s`) with short pauses until about READING_S; returns seconds."""
    parts, total = [], 0.0
    for path in paths:
        wav = load_audio(str(path))
        if len(wav) >= min_len_s * 16000:
            parts += [wav, GAP]
            total += len(wav) / 16000
        if total >= READING_S:
            break
    if parts:
        sf.write(target, np.concatenate(parts), 16000, subtype="PCM_16")
    return total


def torgo_readings(torgo_root, out):
    """One ~12 s reading per dysarthric TORGO speaker, from their sentence recordings."""
    out.mkdir(parents=True, exist_ok=True)
    for speaker in TORGO_DYSARTHRIA:
        paths = sorted(Path(torgo_root).glob(f"{speaker}/Session*/wav_arrayMic/*.wav"))
        seconds = join_reading(paths, out / f"torgo_{speaker}_dysarthria_reading.wav", min_len_s=2.5)
        print(f"  TORGO {speaker} (dysarthria): {seconds:.0f} s", flush=True)


def librispeech_readings(libri_root, out):
    """One ~12 s reading for a few healthy LibriSpeech readers of each sex."""
    out.mkdir(parents=True, exist_ok=True)
    root = Path(libri_root) / "LibriSpeech"
    picked = {"F": [], "M": []}
    for line in (root / "SPEAKERS.TXT").read_text(encoding="utf-8").splitlines():
        cols = [c.strip() for c in line.split("|")]
        if line.startswith(";") or len(cols) < 3 or cols[2] != "dev-clean" or cols[1] not in picked:
            continue
        if len(picked[cols[1]]) < LIBRI_PER_SEX:
            picked[cols[1]].append(cols[0])
    for sex, speakers in picked.items():
        for speaker in speakers:
            paths = sorted((root / "dev-clean" / speaker).glob("*/*.flac"))
            seconds = join_reading(paths, out / f"healthy_librispeech_{speaker}_{sex.lower()}_reading.wav")
            print(f"  LibriSpeech {speaker} ({sex}, healthy): {seconds:.0f} s", flush=True)


def seen_examples(svd_root, out):
    """One vowel + sentence per trained group (these speakers WERE in training)."""
    out.mkdir(parents=True, exist_ok=True)
    for folder in ("healthy", "laryngitis", "nodules", "polyp", "vocal_fold_paralysis"):
        for vowel in sorted(Path(svd_root, folder).glob("*-a_n.wav")):
            sentence = vowel.with_name(vowel.name.replace("-a_n", "-phrase"))
            if sentence.exists():
                sid = vowel.name.split("-")[0]
                shutil.copy(vowel, out / f"{folder}_{sid}_aaah.wav")
                shutil.copy(sentence, out / f"{folder}_{sid}_reading.wav")
                break


def score_file(path):
    """What the app's 🩺 page says for one file: (check, band, score, closest group or '')."""
    task = "svd" if path.stem.endswith("aaah") else "svd_phrase"
    try:
        wav, _ = check_vowel(str(path)) if task == "svd" else check_quality(str(path), min_duration_s=1.5)
    except QualityError as e:
        return task, "rejected", None, str(e)[:60]
    prob = predict.score(task, wav)
    t = predict.load(task)["thresholds"]
    band = "High" if prob >= t["high"] else "Some" if prob >= t["some"] else "Low"
    conditions = [r[0] for r in predict.condition_breakdown(task, wav) if r[0] != "Healthy"]
    closest = conditions[0] if band != "Low" and conditions else ""  # the one name the app shows
    return task, band, prob, closest


def results(root):
    """Score every test file, remove the ones the app would reject, and write RESULTS.md."""
    lines = ["# What the app says for each test file", "",
             "| Folder | File | Check | Result | Score | Closest group |", "| --- | --- | --- | --- | --- | --- |"]
    removed = []
    for path in sorted(root.glob("*/*.wav")):
        task, band, prob, closest = score_file(path)
        if band == "rejected":
            removed.append(f"- {path.parent.name}/{path.name}: {closest}")
            path.unlink()
            continue
        check = "Hold aaah" if task == "svd" else "Read a text"
        lines.append(f"| {path.parent.name} | {path.name} | {check} | {band} | {prob:.0%} | {closest} |")
    if removed:
        lines += ["", "Removed because the app's quality check rejects them:", *removed]
    (root / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else config.DATASETS_DIR
    root = data / "test_uploads"
    shutil.rmtree(root, ignore_errors=True)  # rebuild from scratch (only this generated folder)
    print("Unseen SVD conditions…")
    unseen_conditions(data / "svd", root / "1_unseen_conditions")
    print("English readings…")
    librispeech_readings(data / "librispeech", root / "2_english_readings")
    torgo_readings(data / "torgo", root / "2_english_readings")
    seen_examples(data / "svd", root / "3_seen_in_training")
    results(root)
