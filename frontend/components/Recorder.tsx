"use client";
// One round button (terracotta dot to start, ink square to stop), a scrolling loudness waveform and a big timer.
// Or upload a file instead. Either way the parent gets a 16 kHz WAV clip (lib/audio.ts) it can send.
import { useEffect, useRef, useState } from "react";
import { fileToWav, startCapture, type Capture } from "@/lib/audio";
import { duration } from "@/lib/format";

export interface Clip {
  blob: Blob;
  seconds: number | null;
  label: string;
}

const BARS = 56;
const MAX_S = 180; // a recording stops by itself after 3 minutes
const silhouette = Array.from({ length: BARS }, (_, i) => Math.round(8 + Math.abs(Math.sin(i * 0.5) * Math.sin(i * 0.17 + 1)) * 80));

export function Recorder({ clip, onClip, minSeconds, idleHint, disabled }: {
  clip: Clip | null;
  onClip: (clip: Clip | null) => void;
  minSeconds: number;
  idleHint: string;
  disabled?: boolean;
}) {
  const [state, setState] = useState<"idle" | "starting" | "live">("idle");
  const [error, setError] = useState("");
  const [url, setUrl] = useState<string | null>(null);
  const capture = useRef<Capture | null>(null);
  const levels = useRef<number[]>([]);
  const bars = useRef<(HTMLElement | null)[]>([]);
  const timer = useRef<HTMLDivElement>(null);
  const started = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  // A playable copy of the clip, released when it changes
  useEffect(() => {
    if (!clip) return setUrl(null);
    const u = URL.createObjectURL(clip.blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [clip]);

  // Stop the microphone if the page is left mid-recording
  useEffect(() => () => capture.current?.cancel(), []);

  // Repaint the timer and the waveform ten times a second while recording (refs: no re-render per frame)
  useEffect(() => {
    if (state !== "live") return;
    const t = setInterval(() => {
      const s = (performance.now() - started.current) / 1000;
      if (timer.current) timer.current.textContent = duration(s);
      const offset = BARS - levels.current.length; // new bars enter from the right
      bars.current.forEach((b, i) => { if (b) b.style.height = `${Math.max(3, (levels.current[i - offset] ?? 0) * 100)}%`; });
      if (s >= MAX_S) stop();
    }, 100);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stop() only uses refs and state setters
  }, [state]);

  async function start() {
    setError("");
    onClip(null);
    levels.current = [];
    setState("starting");
    try {
      capture.current = await startCapture((level) => {
        levels.current.push(level);
        if (levels.current.length > BARS) levels.current.shift();
      });
      started.current = performance.now();
      setState("live");
    } catch (e) {
      capture.current = null;
      setState("idle");
      setError(e instanceof Error ? e.message : "Couldn't start the microphone.");
    }
  }

  async function stop() {
    const c = capture.current;
    if (!c) return;
    capture.current = null;
    setState("idle");
    bars.current.forEach((b) => b && (b.style.height = ""));
    const { blob, seconds } = await c.stop();
    if (seconds === 0) return setError("No sound reached the recorder. Check the microphone, or upload a recording.");
    if (seconds < 1) return setError("That was too short. Press the button and record again.");
    onClip({ blob, seconds, label: "Your recording" });
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    setError("");
    const { blob, seconds } = await fileToWav(file);
    if (blob.size > 25 * 1048576) return setError("This recording is too long (over 25 MB). Please use a shorter one.");
    onClip({ blob, seconds, label: file.name });
  }

  const live = state === "live";
  const tooShort = clip?.seconds != null && clip.seconds < minSeconds;
  return (
    <div className={`recorder ${live ? "live" : clip ? "done" : ""}`}>
      <div className="live-wave" aria-hidden="true">
        {Array.from({ length: BARS }, (_, i) => (
          <i key={i} ref={(el) => { bars.current[i] = el; }} style={clip && !live ? { height: `${silhouette[i]}%` } : undefined} />
        ))}
      </div>
      <div className="rec-wrap">
        <button className="rec-btn" onClick={live ? stop : start} disabled={disabled || state === "starting"}
          aria-label={live ? "Stop recording" : "Start recording"}><i /></button>
      </div>
      <div className="timer" ref={timer}>{duration(clip?.seconds && !live ? clip.seconds : 0)}</div>
      <p className="rec-hint" aria-live="polite">
        {state === "starting" ? "Starting the microphone…"
          : live ? "Recording · press again to stop"
          : clip ? (
            <>
              {tooShort ? `Too short: record at least ${minSeconds} seconds.` : `${clip.label} · ready to send.`}
              <button className="link quiet" onClick={() => onClip(null)}>Discard</button>
            </>
          ) : idleHint}
      </p>
      {error && <p className="rec-error" role="alert">{error}</p>}
      {clip && url && !live && <audio className="player" controls src={url} />}
      {!live && (
        <p className="rec-upload">
          <button className="link quiet" onClick={() => fileInput.current?.click()} disabled={disabled}>or upload a recording</button>
          <input ref={fileInput} type="file" className="sr-only" accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg"
            onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
        </p>
      )}
    </div>
  );
}
