"use client";
// New voice check: read a text or hold "aaah", record (or upload), then the laptop checks it.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Recorder, type Clip } from "@/components/Recorder";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/session";
import type { Mode } from "@/lib/types";

// The voice-check models were trained on ~2 s sentences and 1-2 s vowels, so short clips work (the backend needs
// 1.5 s of speech or 1 s of "aaah"). Only Track your voice needs the whole text.
const MIN_SECONDS: Record<Mode, number> = { reading: 1.5, vowel: 1 };
const TITLES: Record<Mode, React.ReactNode> = {
  reading: <>Read this <em>aloud</em></>,
  vowel: <>Hold a steady <em>“aaah”</em></>,
};

export default function CheckPage() {
  return <Suspense><NewCheck /></Suspense>;
}

function NewCheck() {
  const params = useSearchParams();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(params.get("mode") === "vowel" ? "vowel" : "reading");
  const [textId, setTextId] = useState<string | null>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const texts = usePolling(api.texts, 0).data;
  const overview = usePolling(api.overview, 0).data;
  const text = texts?.find((t) => t.id === textId) ?? texts?.[0];
  const available = overview ? overview.modes[mode] : true;
  const ready = clip && (clip.seconds == null || clip.seconds >= MIN_SECONDS[mode]) && available && !sending;

  const switchMode = (m: Mode) => {
    if (m === mode) return;
    setMode(m);
    setClip(null); // a reading and an "aaah" are checked by different models
    setError("");
  };

  async function analyze() {
    if (!clip) return;
    setSending(true);
    setError("");
    try {
      const { id } = await api.newCheck(clip.blob, mode, text?.id);
      router.push(`/checks/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the recording.");
      setSending(false);
    }
  }

  return (
    <>
      <title>New check · VoiceDrift</title>
      <div className="flow-title">
        <p className="meta">New voice check</p>
        <h1 className="title">{TITLES[mode]}</h1>
      </div>
      <div className="tabs voice-tabs" role="tablist">
        <button role="tab" className={mode === "reading" ? "on" : ""} aria-selected={mode === "reading"} onClick={() => switchMode("reading")}>Read a text</button>
        <button role="tab" className={mode === "vowel" ? "on" : ""} aria-selected={mode === "vowel"} onClick={() => switchMode("vowel")}>Hold “aaah”</button>
      </div>

      <div className="voice-body">
        <div>
          {mode === "reading" ? (
            <>
              {texts && texts.length > 1 && (
                <div className="tabs text-tabs" role="tablist" aria-label="Text to read">
                  {texts.map((t) => (
                    <button key={t.id} role="tab" className={t.id === text?.id ? "on" : ""} aria-selected={t.id === text?.id}
                      onClick={() => setTextId(t.id)}>{t.title}</button>
                  ))}
                </div>
              )}
              <p className="passage">{text?.text ?? "…"}</p>
            </>
          ) : (
            <p className="passage">Take a breath and say <em>“aaah”</em> at a comfortable pitch and loudness, as steadily as
              you can, for <em>3 to 5 seconds</em>.</p>
          )}
        </div>
        <Recorder clip={clip} onClip={setClip} minSeconds={MIN_SECONDS[mode]} disabled={!available || sending}
          idleHint={mode === "reading" ? "Press to start, then read the whole text at a natural pace." : "Press to start, then hold the “aaah” for 3 to 5 seconds."} />
      </div>
      <p className="note">{mode === "reading"
        ? "Short recordings work too: from about 2 seconds of speech (one full sentence). A longer reading gives a steadier result."
        : "Short recordings work too: from about 1 second of steady “aaah”. 3 to 5 seconds gives a steadier result."}</p>

      {!available && <p className="form-error">This check isn&apos;t available: its model isn&apos;t trained on the laptop yet.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="flow-end">
        <p className="tips">Quiet room · microphone 20–30 cm away · {mode === "reading" ? "natural pace" : "steady pitch"}</p>
        <button className="pill" disabled={!ready} onClick={analyze}>{sending ? "Sending…" : "Analyze"} <span aria-hidden="true">→</span></button>
      </div>
    </>
  );
}
