"""Voice test bench: synthetic voices with controlled changes, scored by the real pipeline.

For every English text-to-speech voice installed on Windows, it records a 3-reading
baseline with small day-to-day variation, then one reading per condition below, and
checks each result against what should happen. It does NOT test disease detection:
VoiceDrift only detects change from a person's own baseline.

Results:
  - a scorecard in the terminal and in data/experiments/report.md
  - one app user per voice, e.g. "Zira (test voice)", to browse in the app
  - the audio in data/experiments/<voice>/, selectable in the Test lab

Run:  python -m voice_checker.experiments [Zira Hazel ...]   (Windows only; about 1 minute per voice)
"""
import html
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import parselmouth
import soundfile as sf
import torch
import torchaudio
from parselmouth.praat import call

from voice_checker import config
from voice_checker import drift
from voice_checker import storage
from voice_checker.analyze import analyze
from voice_checker.audio.quality import QualityError, load_audio
from voice_checker.texts import TEXTS

TEXT_ID = "market"
OUT_DIR = config.ROOT / "data" / "experiments"
SR = config.SAMPLE_RATE

# Three baseline readings with small day-to-day variation in rate and pitch (percent).
BASELINE = [{"rate": -4, "pitch": -2}, {"rate": 0, "pitch": 0}, {"rate": 4, "pitch": 2}]

# key: (label, statuses that pass, biomarkers of which one should be among the top 3
#       changes (None = any), recipe for the reading)
CONDITIONS = {
    "normal": ("Another normal day", {"Stable"}, None, {"rate": 2, "pitch": -1}),
    "noise": ("Background noise, 25 dB below the voice", {"Stable"}, None, {"noise_db": 25}),
    "phone": ("Phone-quality microphone", {"Stable"}, None, {"phone": True}),
    "slower": ("Reading 25% slower", {"Watch", "Changed"}, {"wpm"}, {"rate": -25}),
    "pauses": ("Long pauses between phrases", {"Watch", "Changed"}, {"pause_ratio", "pause_count"}, {"breaks": True}),
    "lower": ("Voice 12% lower", {"Watch", "Changed"}, {"f0_mean_hz"}, {"pitch": -12}),
    "flat": ("Flatter, monotone melody", {"Watch", "Changed"}, {"f0_std_st"}, {"flatten": 0.4}),
    "hesitant": ("Hesitant: fillers and skipped words", {"Watch", "Changed"}, {"filler_count", "wer"}, {"hesitant": True}),
    "tired": ("Tired: slower, long pauses, flatter", {"Changed"}, None, {"rate": -20, "breaks": True, "flatten": 0.5}),
    "other": ("Someone else reads under this name", {"Changed"}, {"embedding"}, {"other_voice": True}),
}

TTS_PS1 = """param([string]$SsmlFile, [string]$OutFile)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile($OutFile)
$s.SpeakSsml([IO.File]::ReadAllText($SsmlFile))
$s.Dispose()
"""
VOICES_PS1 = """Add-Type -AssemblyName System.Speech
(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() |
  ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture }
"""


# --- Text-to-speech ---------------------------------------------------------
def powershell(script, *args):
    """Run a PowerShell script (given as text) with arguments; return its output."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "script.ps1"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path), *args],
            capture_output=True, text=True, check=True,
        )
    return result.stdout


def english_voices():
    """{short name: full name} of the installed English text-to-speech voices."""
    voices = {}
    for line in powershell(VOICES_PS1).splitlines():
        name, _, culture = line.strip().partition("|")
        if culture.startswith("en"):
            voices[name.replace("Microsoft ", "").replace(" Desktop", "")] = name
    return voices


def synthesize(voice, text, rate=0, pitch=0, breaks=False):
    """Speak `text` with a Windows voice (rate and pitch in percent); return 16 kHz mono audio."""
    body = html.escape(text, quote=False)
    if breaks:
        body = body.replace(". ", '. <break time="900ms"/> ').replace(", ", ', <break time="500ms"/> ')
    ssml = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            f'<voice name="{voice}"><prosody rate="{rate:+d}%" pitch="{pitch:+d}%">{body}</prosody></voice></speak>')
    with tempfile.TemporaryDirectory() as tmp:
        ssml_path, wav_path = Path(tmp) / "in.xml", Path(tmp) / "out.wav"
        ssml_path.write_text(ssml, encoding="utf-8")
        powershell(TTS_PS1, str(ssml_path), str(wav_path))
        return load_audio(str(wav_path))


# --- Audio effects ----------------------------------------------------------
def flatten_pitch(wav, keep):
    """Shrink the pitch movement to `keep` (0-1) of the original, with Praat's PSOLA resynthesis."""
    sound = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=SR)
    manipulation = call(sound, "To Manipulation", 0.01, config.PITCH_FLOOR_HZ, config.PITCH_CEILING_HZ)
    tier = call(manipulation, "Extract pitch tier")
    mean = call(tier, "Get mean (curve)", 0, 0)
    call(tier, "Formula", f"{mean} * (self / {mean}) ^ {keep}")
    call([tier, manipulation], "Replace pitch tier")
    return call(manipulation, "Get resynthesis (overlap-add)").values[0].astype(np.float32)


def phone_filter(wav):
    """Band-limit to 300-3400 Hz, like a phone or a cheap headset microphone."""
    w = torch.from_numpy(wav)
    for _ in range(2):  # twice for a steeper slope
        w = torchaudio.functional.highpass_biquad(w, SR, 300.0)
        w = torchaudio.functional.lowpass_biquad(w, SR, 3400.0)
    return w.numpy()


def add_noise(wav, snr_db, rng):
    """Add white noise `snr_db` below the clip's average power."""
    noise_power = np.mean(wav**2) / 10 ** (snr_db / 10)
    return np.clip(wav + rng.normal(0, np.sqrt(noise_power), wav.shape), -0.97, 0.97).astype(np.float32)


def hesitant_text(text):
    """The text with three fillers added and two words skipped."""
    words = text.split()
    del words[60], words[15]  # skipped words (the later index first)
    for i, filler in ((48, "um,"), (22, "uh,"), (6, "um,")):
        words.insert(i, filler)
    return " ".join(words)


def make_reading(voice, other_voice, recipe, rng):
    """Synthesize one reading of the text following a condition's recipe."""
    text = TEXTS[TEXT_ID]["text"]
    if recipe.get("hesitant"):
        text = hesitant_text(text)
    speaker = other_voice if recipe.get("other_voice") else voice
    wav = synthesize(speaker, text, recipe.get("rate", 0), recipe.get("pitch", 0), recipe.get("breaks", False))
    if "flatten" in recipe:
        wav = flatten_pitch(wav, recipe["flatten"])
    if recipe.get("phone"):
        wav = phone_filter(wav)
    if "noise_db" in recipe:
        wav = add_noise(wav, recipe["noise_db"], rng)
    return add_noise(wav, 45, rng)  # faint room tone, as in any real recording


# --- Running and scoring ----------------------------------------------------
def run_voice(short, voice, other_voice, rng):
    """Record one voice's baseline and conditions, save them as an app user; return its scorecard rows."""
    folder = OUT_DIR / short
    folder.mkdir(parents=True, exist_ok=True)
    plan = [(f"baseline{i + 1}", f"Baseline reading {i + 1}", r) for i, r in enumerate(BASELINE)]
    plan += [(key, label, recipe) for key, (label, _, _, recipe) in CONDITIONS.items()
             if other_voice or not recipe.get("other_voice")]
    start = datetime.now().replace(microsecond=0) - timedelta(days=len(plan))
    user, rejected = {"name": f"{short} (test voice)", "sessions": []}, []
    for day, (key, label, recipe) in enumerate(plan):
        print(f"  {short}: {label}", flush=True)
        path = folder / f"{key}.wav"
        sf.write(path, make_reading(voice, other_voice, recipe, rng), SR, subtype="PCM_16")
        try:
            session = analyze(str(path), TEXT_ID)
        except QualityError as e:
            rejected.append({"voice": short, "key": key, "label": label, "status": "Rejected", "detail": str(e)})
            continue
        session.update(timestamp=(start + timedelta(days=day)).isoformat(), label=label, condition=key)
        user["sessions"].append(session)
    storage.save_user(user)
    return score(short, user) + [dict(r, passed=False, index=None, top=[]) for r in rejected]


def score(short, user):
    """Compare each condition's result with what should happen."""
    scored = drift.score_history(user["sessions"])
    if scored is None:
        return []
    results = []
    for session, row in zip(user["sessions"], scored[1]):
        if row["is_baseline"]:
            continue
        label, statuses, keys, _ = CONDITIONS[session["condition"]]
        top = drift.top_changes(row["z"])
        passed = row["status"] in statuses and (keys is None or bool(keys & {k for k, _ in top}))
        results.append({"voice": short, "key": session["condition"], "label": label, "status": row["status"],
                        "index": row["index"], "top": top, "passed": passed})
    return results


def expectation(key):
    """Plain-language expected outcome of a condition."""
    _, statuses, keys, _ = CONDITIONS[key]
    text = " or ".join(sorted(statuses))
    if keys:
        text += ", led by " + " / ".join(config.LABELS[k][0].lower() for k in sorted(keys))
    return text


def report(results):
    """Print the scorecard and save it as data/experiments/report.md."""
    lines = ["| Voice | Condition | Should be | Got | Index | Biggest changes | Pass |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        top = ", ".join(f"{config.LABELS[k][0]} {z:+.1f}" for k, z in r["top"]) or r.get("detail", "")
        index = f"{r['index']:.1f}" if r["index"] is not None else "-"
        lines.append(f"| {r['voice']} | {r['label']} | {expectation(r['key'])} | {r['status']} | {index} | {top} | "
                     f"{'✅' if r['passed'] else '❌'} |")
    passed = sum(r["passed"] for r in results)
    lines.append(f"\n**{passed} of {len(results)} conditions behaved as expected.**")
    text = "# VoiceDrift test bench\n\n" + "\n".join(lines) + "\n"
    (OUT_DIR / "report.md").write_text(text, encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nSaved {OUT_DIR / 'report.md'}")


def main(names):
    """Run the bench for the chosen (default: all) English voices."""
    if sys.platform != "win32":
        sys.exit("The test bench uses the Windows text-to-speech voices, so it runs on Windows only.")
    voices = english_voices()
    chosen = {n: voices[n] for n in names} if names else voices
    print(f"Voices: {', '.join(chosen)}")
    rng = np.random.default_rng(0)
    results = []
    for short, voice in chosen.items():
        other = next((v for n, v in voices.items() if n != short), None)
        results += run_voice(short, voice, other, rng)
    report(results)
    print("Browse the results in the app: type a test voice's name, e.g. "
          f"“{next(iter(chosen))} (test voice)”, and pick a reading.")


if __name__ == "__main__":
    main(sys.argv[1:])
