# VoiceDrift

Read a short English text aloud; VoiceDrift measures your voice and compares it with
**your own** baseline for that text, then tells you in plain language what changed.

> Research prototype, **not a medical device**. It describes changes; it never diagnoses.
> Audio is processed locally on your laptop CPU and is not stored or uploaded.

## How it works
```text
recording ─► quality check ─► 4 biomarker modules ─► session JSON ─► drift vs. baseline ─► summary + charts
             (16 kHz mono,      embedding  (ECAPA voice signature)        (per user,       (templates, or
              ≥ 8 s, not         transcript (WPM, WER, fillers)            per text)        Claude if a key
              clipped/noisy)     pitch      (mean F0, F0 SD)                                is set)
                                 pauses     (count, pause ratio)
```

- **Baseline**: the first 3 readings of a text (per user). Until then: *Building your baseline (x/3)*.
- **Scores**: every biomarker becomes a z-score against the baseline, with a minimum std
  (`STD_FLOORS` in `config.py`) so three near-identical readings can't blow up the z.
  The voice signature uses the cosine distance to the baseline centroid, z-scored against
  the baseline readings' own leave-one-out distances.
- **Overall index** = RMS of all z-scores: **Stable** < 2 ≤ **Watch** < 3.5 ≤ **Changed**.
- **Persistent alert** when the last 3 compared readings are all Watch or worse.

## Setup

Python 3.10+ (tested on 3.13, Windows 11, CPU only).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

The first analysis downloads the models (~250 MB) into `models/`: SpeechBrain ECAPA and
Whisper `base.en`. Silero VAD ships inside its pip package.

Optional, for the friendlier Claude-written summary:

```bash
set ANTHROPIC_API_KEY=sk-ant-...   # Windows cmd   (PowerShell: $env:ANTHROPIC_API_KEY="..."; macOS/Linux: export ...)
```

Without a key the app uses its template summaries. With a key, only the status and the
direction of the biggest changes are sent to the API: no audio, transcript or name.

## Run

```bash
streamlit run app.py
```

Then open <http://localhost:8501>. Enter a name, pick a text, record (or upload a WAV/FLAC/OGG/MP3)
and press **Analyze and save**. Or press **Load demo data** in the sidebar to see a full history
without recording.

**🧪 Test lab** (sidebar): runs every module on one recording (a built-in sample, your mic or a
file) and shows each result with its timing: quality, pause timeline, pitch, transcript with
misreads, voice signature, and similarity to a second clip. It also checks that the models are
downloaded and can warm them up. Nothing is saved.

### Test each module on a WAV file

```bash
python -m audio.quality   clip.wav             # accept/reject + duration, SNR, clipping
python -m features.pauses clip.wav             # pause count and pause ratio
python -m features.embedding clip.wav [b.wav]  # 192-dim voice signature (+ similarity to b.wav)
python -m features.transcript clip.wav market  # transcript, WPM, WER, fillers, misread words
python -m features.pitch  clip.wav             # mean F0 (Hz) and F0 SD (semitones)
python analyze.py clip.wav market              # the whole pipeline on one clip
python demo.py                                 # (re)create the demo user and print its scores
```

## Project layout

| File | What it does |
| --- | --- |
| `app.py` | Streamlit UI: recording, results, transcript diff, Plotly charts |
| `test_lab.py` | Test lab page: every module on one clip, plus a system check |
| `widgets.py` | Transcript highlighting and styles shared by both pages |
| `samples/` | Two synthetic sample clips for the Test lab |
| `config.py` | All models, thresholds and z-score floors |
| `texts.py` | The reading texts (ids are stable keys for baselines) |
| `audio/quality.py` | Load → 16 kHz mono, reject short / clipped / noisy clips |
| `features/` | `embedding.py`, `transcript.py`, `pitch.py`, `pauses.py`: one biomarker each |
| `analyze.py` | Runs quality check + all features → one session dict |
| `drift.py` | Baselines, z-scores, overall index, status, persistent alert |
| `explain.py` | Template summary, optional Claude summary with fallback |
| `storage.py` | One JSON file per user in `data/users/` |
| `demo.py` | Demo user: 3 baseline + 4 drifting sessions |

## Tuning

Everything lives in `config.py`. The knobs that matter most:

- `STD_FLOORS` and `EMBEDDING_STD_FLOOR`: raise a floor if a biomarker flags normal
  day-to-day variation as change; lower it to make it more sensitive.
- `WATCH_INDEX` / `CHANGED_INDEX`: the status thresholds.
- `MIN_SNR_DB`, `MAX_CLIP_FRACTION`, `MIN_DURATION_S`: how strict the quality check is.

The voice signature is computed on speech frames only (VAD), because background noise in
the silences moved the full-clip embedding a lot. It is still sensitive to a **different
microphone or room**, so keep the setup the same across readings.

## 3-minute demo script

**Before you go on stage:** run one analysis so the models are downloaded and warm
(`python analyze.py some_clip.wav`), allow microphone access in the browser, and click
**Load demo data** once. On flaky Wi-Fi, set `HF_HUB_OFFLINE=1` after the first download.

| Time | Say | Do |
| --- | --- | --- |
| 0:00 | "Your voice changes when you're tired or run down, and you're often the last to notice. Population norms don't help: everyone's voice is different. VoiceDrift compares **you with you**." | App open on the start screen. Point at the sidebar: *not a medical device, audio stays on this laptop*. |
| 0:25 | "You just read a 30-second text aloud." | Type your name, pick a text, press record and read it. |
| 1:00 | "Before anything is measured, we check quality: too short, clipped or noisy recordings are rejected with a fix-it message." | Press **Analyze and save** (≈ 10 s). Show *Building your baseline (1/3)* and the transcript with misread words highlighted. |
| 1:25 | "Here's what happens after a few weeks. This is a demo user: three baseline readings, then four that slowly drift." | Click **Load demo data**. |
| 1:40 | "The latest reading is **Changed**, and because the last three were all Watch or worse, we raise a persistent alert. In plain language: more pausing, slower reading, a flatter voice. No diagnosis, just what changed and a nudge to rest or check in with a professional." | Show the banner, alert, summary and the *What moved most* table. |
| 2:15 | "Every reading gives eight biomarkers: a 192-dim voice signature, speaking rate, reading errors, filler words, pitch and pitch variability, and pauses. Each is a z-score against your own baseline; the index is their RMS." | Scroll to the trend chart with its Stable / Watch / Changed bands, then the three small charts with the usual-range band. |
| 2:45 | "Everything runs on a laptop CPU, in Python, with open models: SpeechBrain, Whisper, Praat and Silero. Next: more texts, longer baselines and a study with clinicians." | Optional: open *All readings as a table*. |

Backup moment if time allows: record 3 seconds and show the quality check rejecting it.

## Limitations

- Three readings is a small baseline; the std floors keep it from over-reacting, but
  more baseline readings would make the scores more reliable.
- Whisper can mishear words, which shows up as reading errors. Keep this consistent by
  reading in the same quiet setup.
- The thresholds are hand-picked for a demo and not clinically validated.
