# VoiceDrift

Record your voice; VoiceDrift tells you which voice condition it is **most similar to**, by
comparing it with research recordings of people with voice conditions. It never says you have
the condition. The **Track your voice** page also compares each reading with **your own**
baseline for that text and tells you in plain language what changed.

> Research prototype, **not a medical device**. It describes changes; it never diagnoses.
> Audio is processed locally on your laptop CPU and is not stored or uploaded.

## Repository layout

```text
VoiceDrift/
├── frontend/          The web app (Next.js + TypeScript): voice checks, Track your voice, phone linking
├── backend/           Everything that serves people
│   ├── settings.py      ports, folders, database and email, read from .env
│   ├── dashboard/       the API for the web app, plus the phone pages, check worker and email
│   ├── streamlit_app/   developer tools: the Test lab (and the older Streamlit pages)
│   └── data/            certs/, outbox/ (and dashboard.db when using SQLite)
├── voice_checker/     The voice analysis itself: no web code, used by the backend
│   ├── audio/ features/ screening/   quality check, biomarkers, research screening models
│   ├── analyze.py drift.py explain.py texts.py storage.py demo.py experiments.py
│   ├── models/          downloaded model weights and the trained screening models
│   ├── samples/         two sample clips
│   └── data/            reading histories (users/) and test-bench clips (experiments/)
├── docker-compose.yml PostgreSQL for the backend
├── .env               this machine's settings and secrets (not in git; template: .env.example)
└── README.md
```

The research datasets (Saarbrücken, TORGO, LibriSpeech, about 10 GB) stay outside the repository,
in `DATASETS_DIR` from `.env` (`E:/VoiceDrift-data` on the development laptop).
**Run every Python command from the repository root** with the virtual environment active.

## Start the whole app, step by step

From creating an account to linking a phone, recording, seeing the result on the laptop and getting
the email. Commands are for PowerShell in the repository folder. You need three things running: the
database (Docker), the backend (Python) and the web app (Next.js).

### Once

1. **Python packages:**

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```

2. **Web app packages** (Node.js 20 or newer):

   ```powershell
   cd frontend
   npm install
   cd ..
   ```

3. **Settings:** `copy .env.example .env`, then fill in the database password and the SMTP values
   (already done on the development laptop).
4. **Brevo, so emails can go out:** Brevo only accepts SMTP logins from IP addresses you allow. In
   Brevo open **Security → Authorized IPs** and add this laptop's public IP address (or turn the IP
   restriction off). Otherwise every email fails with *525 Unauthorized IP address* and the check shows
   *Email failed*; the results themselves are still saved. Also verify the `EMAIL_FROM` address under
   **Senders, Domains & Dedicated IPs → Senders**.
5. **Screening models:** `voice_checker/models/screening/` must hold `svd.joblib` and
   `svd_phrase.joblib` (see [Voice check](#voice-check-the-home-page) to train them).

### Every time

1. **Start the database.** Open Docker Desktop and wait until it says *Engine running*, then:

   ```powershell
   docker compose up -d db
   docker compose ps          # voicedrift-db should be "healthy"
   ```

2. **Start the backend** (first terminal):

   ```powershell
   .venv\Scripts\activate
   python -m backend.dashboard
   ```

   It prints the addresses it serves: the API on `http://localhost:8700` (this laptop only) and the
   phone pages on `https://<laptop Wi-Fi address>:8443`. The first time, Windows asks whether Python
   may accept connections: allow it on **private networks**.
3. **Start the web app** (second terminal):

   ```powershell
   cd frontend
   npm run dev
   ```

   Then open **<http://localhost:3000>** in the laptop's browser.
4. **Create an account.** On the sign-in page choose **Create an account**, enter your name, the email
   address where results should go and a password (8+ characters), and press **Create account**. You
   land on **Today**.
5. **Link the phone.** Open **Phone** in the top bar. Put the phone on the same Wi-Fi as the laptop (or
   on the laptop's Mobile Hotspot), scan the QR code with the phone's camera and open the link. The
   phone warns once that the connection isn't private (the certificate is made by the laptop): tap
   *Advanced → Proceed* (Android) or *Show Details → visit this website* (iPhone). Then tap
   **Link this phone**; the web app says *Phone linked*. A code works once, for 5 minutes.
6. **Record on the phone.** Choose **Read a text** (pick the text and read it aloud) or **Hold “aaah”**
   (3–5 seconds), allow the microphone, record, stop, and press **Send to my dashboard**. Instead of
   recording you can use **or upload a recording**.
7. **See it on the laptop.** The check appears in **Today** and **Checks** within seconds: *Waiting to
   be checked…*, *Checking your voice…*, then the result, for example *Healthy-sounding voice* or
   *Your voice is similar to people with laryngitis*. Click it for the full result.
8. **Get the email.** Every finished check is emailed to the account's address (*Your voice check
   result is ready*, or *… found something to look at*). The check then says **Emailed you**.
   **Settings → Send a test email** checks the email settings at any time.

You can also check without the phone: **New check** in the top bar → **Read a text** or
**Hold “aaah”** → record (or upload) → **Analyze**. **Track your voice** compares readings of the same
text with your own baseline over time.

To stop: `Ctrl+C` in both terminals, then `docker compose stop db`. Accounts, linked phones, results
and readings stay in the database until `docker compose down -v`.

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
  (`STD_FLOORS` in `voice_checker/config.py`) so three near-identical readings can't blow up the z.
  The voice signature uses the cosine distance to the baseline centroid, z-scored against
  the baseline readings' own leave-one-out distances.
- **Overall index** = RMS of all z-scores: **Stable** < 2 ≤ **Watch** < 3.5 ≤ **Changed**.
- **Persistent alert** when the last 3 compared readings are all Watch or worse.

## Setup

Python 3.10+ (tested on 3.13, Windows 11, CPU only).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r backend/requirements.txt     # also installs voice_checker/requirements.txt
copy .env.example .env             # then fill it in (macOS/Linux: cp)
```

The first analysis downloads the models (~250 MB) into `voice_checker/models/`: SpeechBrain ECAPA and
Whisper `base.en`. Silero VAD ships inside its pip package.

Optional, for the friendlier Claude-written summary: add `ANTHROPIC_API_KEY=sk-ant-...` to `.env`.

Without a key the app uses its template summaries. With a key, only the status and the
direction of the biggest changes are sent to the API: no audio, transcript or name.

## Run

The app is the Next.js web app with the Python backend behind it; see
[Start the whole app, step by step](#start-the-whole-app-step-by-step):

```bash
docker compose up -d db          # database
python -m backend.dashboard      # backend: API for the web app + phone pages
cd frontend && npm run dev       # web app: http://localhost:3000
```

**Voice check** (*New check*): read a text (or hold “aaah”), record or upload, and see which voice
condition group your voice is most similar to (see [Voice check](#voice-check-the-home-page); the models
must be trained first). **Track your voice**: read the same text on different days; after 3 baseline
readings each new one is scored Stable / Watch / Changed with what moved most and the trend.
**See an example with demo readings** fills in a full history without recording.

**Developer tools (Streamlit, optional):** `streamlit run backend/streamlit_app/app.py` opens the
**🧪 Test lab** (sidebar), which runs every module on one recording (a built-in sample, your mic or a
file) and shows each result with its timing: quality, pause timeline, pitch, transcript with
misreads, voice signature, and similarity to a second clip. It also checks that the models are
downloaded and can warm them up. Nothing is saved. The older Streamlit versions of Voice check and
Track your voice are still there too; the web app replaces them.

### Test each module on a WAV file

```bash
python -m voice_checker.audio.quality   clip.wav             # accept/reject + duration, SNR, clipping
python -m voice_checker.features.pauses clip.wav             # pause count and pause ratio
python -m voice_checker.features.embedding clip.wav [b.wav]  # 192-dim voice signature (+ similarity to b.wav)
python -m voice_checker.features.transcript clip.wav market  # transcript, WPM, WER, fillers, misread words
python -m voice_checker.features.pitch  clip.wav             # mean F0 (Hz) and F0 SD (semitones)
python -m voice_checker.analyze clip.wav market              # the whole pipeline on one clip
python -m voice_checker.demo                     # (re)create the demo user and print its scores
```

### Test bench: many voices, controlled changes

```bash
python -m voice_checker.experiments     # all English Windows voices (or: ... experiments Zira)
```

For each installed English text-to-speech voice it records a 3-reading baseline with small
day-to-day variation, then one reading per condition (another normal day, background noise,
phone mic, slower, long pauses, lower pitch, flat melody, hesitant, tired, someone else) and
checks each against what should happen. Results: a scorecard in `voice_checker/data/experiments/report.md`,
an app user per voice (e.g. **Zira (test voice)**, browse with *Reading to show*), and the clips
in the Test lab's sample list. It uses every English voice that Windows desktop text-to-speech
(System.Speech) can see; on the development laptop that's Zira and Hazel.

This tests **change detection**, not disease detection: VoiceDrift only compares a person
with their own baseline and never diagnoses.

## Voice check (the home page)

The **🩺 Voice check** page, the first page of the app, compares one recording with research datasets:

| Check | You record | Compared with | Looks for |
| --- | --- | --- | --- |
| Speech check | the reading | TORGO (dysarthria from cerebral palsy or ALS, plus controls) | dysarthria-like speech: slow, slurred, effortful |
| Voice check | a steady “aaah”, 3–5 s | Saarbrücken Voice Database (voice disorders, plus healthy) | voice-disorder-like voice: hoarse, breathy, unstable |

If a recording is unusual, it says *“Your voice is similar to people with …”* with the closest
condition group, and how often that guess was right on speakers the model never heard. It
**never says you have it**, and every result points to an ENT doctor for a real assessment. It can
only name the Saarbrücken groups (nodules or polyps, vocal fold paralysis, laryngitis, and for the
“aaah” also Reinke's edema and functional dysphonia): TORGO has about 15 speakers and no
Parkinson's, MS, stroke or brain-injury speakers, and audio alone can't tell nodules from polyps.

**1 · Get the data** into `DATASETS_DIR` (`.env`). On the development laptop that's `E:\VoiceDrift-data\`.

- **Saarbrücken Voice Database** (official full copy on Zenodo, CC BY 4.0, credit required):
  `python -m voice_checker.screening.download_svd E:/VoiceDrift-data/svd` fetches only the vowel /a/ at normal
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

**2 · Train.** Features are cached in `voice_checker/models/screening/`, so a rerun is quick.

```bash
python -m voice_checker.screening.train svd   E:/VoiceDrift-data/svd
python -m voice_checker.screening.train torgo E:/VoiceDrift-data/torgo
```

Each run prints and saves a report (`voice_checker/models/screening/<task>_report.md`) with speaker-independent
results (no speaker in both training and test) and a **recording-setup check**: the same model
trained on the silent parts of each clip only. If silence alone separates the groups, the model
is partly learning the microphone and room, and the page warns about it.

**Results on 2026-10-17** (speaker-independent, controls matched for age and sex; full reports in
`voice_checker/models/screening/*_report.md`):

| Model | Records | Matched AUC | Closest group right (chance 25%) | Status |
| --- | --- | --- | --- | --- |
| Voice check from reading (`svd_phrase`) | reading | 0.81 | 42% | on; normal test readings all scored Low |
| Voice check (`svd`) | “aaah” | 0.70 | 30% | on |
| Speech check (`torgo`) | reading | 0.76 (women 0.44) | – | **off**: failed the recording-setup check and scored every normal reading ~1.0 |

**Test files to upload:** `python -m voice_checker.screening.make_test_set` builds
`E:\VoiceDrift-data\test_uploads\` with conditions the models never saw (Parkinson's, ALS, Reinke's
edema, spasmodic dysphonia, vocal fold cancer, functional dysphonia, dysarthrophonia), healthy
English readers (LibriSpeech dev-clean, CC BY 4.0) and dysarthric TORGO speakers, plus a few
training examples, and writes `RESULTS.md` with what the app says for each file.

## Phone link: record on your phone, check on your laptop

```bash
docker compose up -d db        # the database (see "Start the whole app, step by step")
python -m backend.dashboard    # the API for the web app and the phone pages
cd frontend && npm run dev     # the web app: http://localhost:3000
```

Create an account in the web app (name, email, password), open **Phone** and scan the QR code with your phone.
The phone opens a page where you read a text or hold “aaah”, record it (or upload a file) and press
**Send to my dashboard**. The laptop runs the same check as **New check** in the web app; the result appears
in the web app and on the phone, and VoiceDrift emails every result to the account's address.

How the two devices connect (same Wi-Fi):

- One backend process, two servers. The **API** the web app uses is on `http://localhost:8700` and only this
  laptop can reach it, so nobody else on the Wi-Fi can reach the accounts (the web app forwards `/api/*` to it). The **phone pages** are on
  `https://<laptop Wi-Fi address>:8443`, because phone browsers only allow the microphone over HTTPS.
- The QR code holds a one-time token that works for 5 minutes. Tapping **Link this phone** gives the phone its
  own session: 30 days, or until you press **Unlink** on the web app's Phone page.
- The HTTPS certificate is self-signed (`backend/data/certs/`, made for the laptop's addresses), so the phone warns once
  that the connection isn't private: tap *Advanced → Proceed* (Android) or *Show Details → visit this website*
  (iPhone). A new Wi-Fi address means a new certificate and one more warning.
- The code uses the detected Wi-Fi address. You can pick another under the code, for example `192.168.137.1`
  when the phone is on the laptop's Mobile Hotspot, or start with `python -m backend.dashboard --ip 192.168.1.23`.

If the phone can't open the page:

- **Windows Firewall:** the first start asks whether Python may accept connections. Allow it on private
  networks, and make sure the Wi-Fi's network profile is *Private* (Settings → Network → Wi-Fi).
- **Client isolation:** guest networks and many office or campus networks stop devices from reaching each
  other. Use a home network, or turn on the laptop's Mobile Hotspot and connect the phone to it.

**Email** settings live in `.env`, so the password is never in the code or in git:
`EMAIL_BACKEND=smtp` plus `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_SSL`, `SMTP_USERNAME` and
`SMTP_PASSWORD` (see `.env.example`; its comments say where each Brevo value is). With `EMAIL_BACKEND=outbox`,
emails are saved as `.eml` files in `backend/data/outbox/` instead (they open in any mail app), so the whole flow
can be tested without an SMTP account. **Settings → Send a test email** in the web app checks the settings.

**Database:** `DATABASE_URL` in `.env`. The default setup is PostgreSQL in Docker (`docker compose up -d db`,
listening on `127.0.0.1:5433` only). For a quick start without Docker, set
`DATABASE_URL=sqlite:///backend/data/dashboard.db`.

**Privacy:** the audio travels encrypted over your Wi-Fi, is checked in memory and then discarded.
The database keeps the accounts (scrypt password hashes), the linked phones (token hashes only) and the
results. The notification email contains the result, never the audio, and goes through your email provider.

## Web app (Next.js)

`frontend/` is the app people use: a Next.js and TypeScript app in the editorial *Echo* design. It talks
only to the backend's API (`/api/*` is forwarded to `http://127.0.0.1:8700`; set `BACKEND_URL` to change
it), so the sign-in cookie stays on one origin. Pages: sign in / create account, **Today**, **New check**,
a check's result, **Checks**, **Track your voice**, **Phone** (QR linking) and **Settings** (email test,
sign out). Recordings are captured in the browser and sent as 16 kHz mono WAV, like the phone page.
Details are in [frontend/README.md](frontend/README.md).

## Project layout

`frontend/` is the Next.js web app ([frontend/README.md](frontend/README.md)). The Python code is in two packages:

| Path | What it does |
| --- | --- |
| `voice_checker/config.py` | All models, thresholds, z-score floors and voice-checker paths (`DATASETS_DIR`) |
| `voice_checker/texts.py` | The reading texts (ids are stable keys for baselines) |
| `voice_checker/audio/quality.py` | Load → 16 kHz mono, reject short / clipped / noisy clips |
| `voice_checker/features/` | `embedding.py`, `transcript.py`, `pitch.py`, `pauses.py`: one biomarker each |
| `voice_checker/analyze.py` | Runs quality check + all features → one session dict |
| `voice_checker/drift.py` | Baselines, z-scores, overall index, status, persistent alert |
| `voice_checker/explain.py` | Template summary, optional Claude summary with fallback |
| `voice_checker/storage.py` | Reading history: one JSON file per user in `voice_checker/data/users/` |
| `voice_checker/demo.py` | Demo user: 3 baseline + 4 drifting sessions |
| `voice_checker/experiments.py` | Test bench: TTS voices × controlled changes → scorecard |
| `voice_checker/screening/` | Research screening: dataset loaders and downloads, features, training, prediction |
| `voice_checker/samples/`, `models/`, `data/` | Sample clips, model weights, reading histories and test-bench clips |
| `backend/settings.py` | Ports, data folders, database URL and email settings, loaded from `.env` |
| `backend/dashboard/` | The backend (`python -m backend.dashboard`): the web app's API and the phone pages (`server.py`), database (`db.py`), accounts (`auth.py`), check worker (`checks.py`), Track your voice (`tracking.py`), email (`notify.py`), Wi-Fi certificate (`network.py`), phone pages (`static/`) |
| `backend/streamlit_app/` | Developer tools in Streamlit (`streamlit run backend/streamlit_app/app.py`): `test_lab.py`, plus the older `app.py` (Track your voice) and `screening_page.py` (Voice check) |
| `backend/data/` | `certs/` (phone HTTPS certificate), `outbox/` (emails when `EMAIL_BACKEND=outbox`) |
| `docker-compose.yml` | PostgreSQL for the backend |

## Tuning

Voice analysis settings live in `voice_checker/config.py`; server settings in `backend/settings.py` and `.env`.
The knobs that matter most:

- `STD_FLOORS` and `EMBEDDING_STD_FLOOR`: raise a floor if a biomarker flags normal
  day-to-day variation as change; lower it to make it more sensitive.
- `WATCH_INDEX` / `CHANGED_INDEX`: the status thresholds.
- `MIN_SNR_DB`, `MAX_CLIP_FRACTION`, `MIN_DURATION_S`: how strict the quality check is.

The voice signature is computed on speech frames only (VAD), because background noise in
the silences moved the full-clip embedding a lot. It is still sensitive to a **different
microphone or room**, so keep the setup the same across readings.

## 3-minute demo script

**Before you go on stage:** run one analysis so the models are downloaded and warm
(`python -m voice_checker.analyze some_clip.wav`), allow microphone access in the browser, and click
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
