# VoiceDrift web app

The app people use to check their voice and track how it changes, built with Next.js (App Router) and
TypeScript in the editorial *Echo* design. All data comes from the Python backend in `../backend`.

> Research prototype, not a medical device. Results are screening support, never a diagnosis.

## Run

Node 20+ (tested on Node 22). The backend must be running (`python -m backend.dashboard` from the
repository root, with the database up: see the main README).

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Production build: `npm run build && npm start`. Type-check only: `npm run typecheck`.

The browser only talks to this app. `/api/*` is forwarded to the backend (`next.config.ts`), so the
backend's sign-in cookie is same-origin. The backend address defaults to `http://127.0.0.1:8700`; set
`BACKEND_URL` to change it (for `npm start`, before `npm run build`, because rewrites are fixed at build
time). The microphone works on `localhost` or HTTPS.

## Pages

| Path | What it shows |
| --- | --- |
| `/login`, `/signup` | Sign in, create an account |
| `/` | Today: latest checks (refreshes, so phone checks appear), this week, where to begin |
| `/check` | New voice check: read a text or hold “aaah”, record or upload, Analyze |
| `/checks/[id]` | One check: “Listening…” while the laptop works on it, then the result and its email status |
| `/checks` | Every check, from the phone and this laptop, with filters |
| `/track` | Track your voice: baseline progress, Stable / Watch / Changed, what moved most, what was heard, trend charts |
| `/phone` | Link a phone with a one-time QR code; linked phones |
| `/settings` | Account, email notifications (send a test email), sign out |

## Code

| Path | What it is |
| --- | --- |
| `lib/api.ts` | Every backend call, typed (`lib/types.ts` mirrors the backend's JSON) |
| `lib/audio.ts` | Microphone capture and uploads → 16 kHz mono WAV in the browser (same as the phone page) |
| `lib/session.tsx` | Who is signed in, toasts, and the polling hook |
| `components/Recorder.tsx` | Record button, live waveform, timer, upload, playback |
| `components/LineChart.tsx` | The SVG line chart behind the Track your voice trend (labeled bands, hover, end label) |
| `components/Shell.tsx` | Top bar (desktop) and tab bar (mobile) |
| `app/styles/` | `base.css` (tokens, controls), `screens.css`, `flow.css`, `app.css` (checks, phone, charts) |
