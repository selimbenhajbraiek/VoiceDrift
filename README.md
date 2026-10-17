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

### Test bench: many voices, controlled changes

```bash
python experiments.py            # all English Windows voices (or: python experiments.py Zira)
```

For each installed English text-to-speech voice it records a 3-reading baseline with small
day-to-day variation, then one reading per condition (another normal day, background noise,
phone mic, slower, long pauses, lower pitch, flat melody, hesitant, tired, someone else) and
checks each against what should happen. Results: a scorecard in `data/experiments/report.md`,
an app user per voice (e.g. **Zira (test voice)**, browse with *Reading to show*), and the clips
in the Test lab's sample list. It uses every English voice that Windows desktop text-to-speech
(System.Speech) can see; on the development laptop that's Zira and Hazel.

This tests **change detection**, not disease detection: VoiceDrift only compares a person
with their own baseline and never diagnoses.

## Research screening (optional)

The **🩺 Voice screening (research)** page compares one recording with research datasets:

| Check | You record | Compared with | Looks for |
| --- | --- | --- | --- |
| Speech check | the reading | TORGO (dysarthria from cerebral palsy or ALS, plus controls) | dysarthria-like speech: slow, slurred, effortful |
| Voice check | a steady “aaah”, 3–5 s | Saarbrücken Voice Database (voice disorders, plus healthy) | voice-disorder-like voice: hoarse, breathy, unstable |

It reports how similar a recording is to each dataset's condition group and how accurate the
model was on speakers it never heard. It **never names a disease**: TORGO has about 15 speakers
and no Parkinson's, MS, stroke or brain-injury speakers, and audio alone can't tell nodules from
polyps. Every result points to a doctor or speech-language therapist for a real assessment.

**1 · Get the data.** On the development laptop the data lives on drive `E:` in `E:\VoiceDrift-data\`.

- **Saarbrücken Voice Database** (official full copy on Zenodo, CC BY 4.0, credit required):
  `python -m screening.download_svd E:/VoiceDrift-data/svd` fetches only the vowel /a/ at normal
  pitch from the healthy, nodules, polyp, vocal-fold-paralysis, laryngitis and reflux zips (via HTTP
  range requests, so ~150 KB per recording instead of ~10 GB of zips), converts `.nsp` to WAV and
  keeps each zip's `overview.csv` (speaker ids). It is paced for Zenodo's rate limit and resumable.
- **TORGO** (<http://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html>, free for academic
  non-profit use, cite the TORGO paper): download `F`, `FC`, `M`, `MC` `.tar.bz2` (9.6 GB in total),
  then extract only the array-microphone WAVs:

  ```bash
  cd E:/VoiceDrift-data
  for f in F FC M MC; do tar -xjf torgo_archives/$f.tar.bz2 -C torgo --wildcards "*/wav_arrayMic/*"; done
  ```

**2 · Train.** Features are cached in `models/screening/`, so a rerun is quick.

```bash
python -m screening.train svd   E:/VoiceDrift-data/svd
python -m screening.train torgo E:/VoiceDrift-data/torgo
```

Each run prints and saves a report (`models/screening/<task>_report.md`) with speaker-independent
results (no speaker in both training and test) and a **recording-setup check**: the same model
trained on the silent parts of each clip only. If silence alone separates the groups, the model
is partly learning the microphone and room, and the page warns about it.

**Results on 2026-10-17** (speaker-independent, controls matched for age and sex; full reports in
`models/screening/*_report.md`):

| Model | Records | Matched AUC | Closest group right (chance 25%) | Status |
| --- | --- | --- | --- | --- |
| Voice check from reading (`svd_phrase`) | reading | 0.81 | 42% | on; normal test readings all scored Low |
| Voice check (`svd`) | “aaah” | 0.70 | 30% | on |
| Speech check (`torgo`) | reading | 0.76 (women 0.44) | – | **off**: failed the recording-setup check and scored every normal reading ~1.0 |

**Test files to upload:** `python -m screening.make_test_set E:/VoiceDrift-data` builds
`E:\VoiceDrift-data\test_uploads\` with conditions the models never saw (Parkinson's, ALS, Reinke's
edema, spasmodic dysphonia, vocal fold cancer, functional dysphonia, dysarthrophonia), healthy
English readers (LibriSpeech dev-clean, CC BY 4.0) and dysarthric TORGO speakers, plus a few
training examples, and writes `RESULTS.md` with what the app says for each file.

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
| `experiments.py` | Test bench: TTS voices × controlled changes → scorecard |
| `screening/` | Research screening: dataset loaders, features, training, prediction |
| `screening_page.py` | Voice screening (research) page: speech check and “aaah” voice check |

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

## Data credits

- **TORGO**: Rudzicz, F., Namasivayam, A. K., & Wolff, T. (2012). The TORGO database of acoustic
  and articulatory speech from speakers with dysarthria. *Language Resources and Evaluation*, 46(4).
  Free for academic (non-profit) use.
- **Saarbrücken Voice Database**: Pützer, M., & Barry, W. J., former Institute of Phonetics, Saarland
  University. Zenodo, doi:10.5281/zenodo.16874898, CC BY 4.0.

## Limitations

- Three readings is a small baseline; the std floors keep it from over-reacting, but
  more baseline readings would make the scores more reliable.
- Whisper can mishear words, which shows up as reading errors. Keep this consistent by
  reading in the same quiet setup.
- The thresholds are hand-picked for a demo and not clinically validated.
