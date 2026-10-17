"use client";
// Track your voice: read the same text on different days. After 3 readings (the baseline), each new reading is
// compared with the person's own baseline: Stable / Watch / Changed, what moved most, and the trend.
import { useEffect, useState } from "react";
import { LineChart } from "@/components/LineChart";
import { Orb, STATUS_DOT, TranscriptDiff } from "@/components/marks";
import { Recorder, type Clip } from "@/components/Recorder";
import { api } from "@/lib/api";
import { dateTime, shortDate } from "@/lib/format";
import { usePolling, useSession } from "@/lib/session";
import type { TrackingState } from "@/lib/types";

const MIN_SECONDS = 8;
const AXIS_FORMAT: Record<string, (v: number) => string> = {
  wpm: (v) => v.toFixed(0),
  pause_ratio: (v) => `${Math.round(v * 100)}%`,
  f0_std_st: (v) => v.toFixed(1),
};

export default function TrackPage() {
  const { toast } = useSession();
  const texts = usePolling(api.trackingTexts, 0);
  const [textId, setTextId] = useState<string | null>(null);
  const [state, setState] = useState<TrackingState | null>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  const [busy, setBusy] = useState<null | "saving" | "demo" | "clear">(null);
  const [error, setError] = useState("");

  // Start on the text read most often
  const current = textId ?? (texts.data ? [...texts.data].sort((a, b) => b.count - a.count)[0].id : null);
  useEffect(() => {
    if (!current) return;
    setState(null);
    setClip(null);
    setError("");
    api.tracking(current).then(setState).catch((e) => setError(e.message));
  }, [current]);

  async function run(kind: "saving" | "demo" | "clear", call: () => Promise<TrackingState>, done: string) {
    setBusy(kind);
    setError("");
    try {
      const next = await call();
      setTextId(next.text.id);
      setState(next);
      setClip(null);
      texts.reload();
      toast(done);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const s = state;
  const scored = s?.result && s.result.status !== "Baseline" ? s.result : null;
  return (
    <>
      <title>Track your voice · VoiceDrift</title>
      <header className="page-head">
        <div>
          <h1 className="title">Track your <em>voice</em></h1>
          <p className="lede" style={{ marginTop: 16 }}>Read the same text on different days. Your first {s?.baseline_n ?? 3} readings
            are your baseline; every reading after that is compared with how <em>you</em> usually sound.</p>
        </div>
      </header>
      <div className="tabs text-tabs" role="tablist" aria-label="Text">
        {texts.data?.map((t) => (
          <button key={t.id} role="tab" className={t.id === current ? "on" : ""} aria-selected={t.id === current}
            onClick={() => setTextId(t.id)} disabled={!!busy}>{t.title}<span className="n">{t.count}</span></button>
        ))}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}

      {s && (
        <>
          {/* Where this text stands */}
          <section className="section">
            {s.count < s.baseline_n ? (
              <>
                <h2 className="label">Building your baseline <span className="aside">{s.count} of {s.baseline_n}</span></h2>
                <div className="dashes left">{Array.from({ length: s.baseline_n }, (_, i) => <i key={i} className={i < s.count ? "on" : ""} />)}</div>
                <p className="lede">{s.count === 0 ? "No readings of this text yet. " : ""}Read this text {s.baseline_n - s.count} more
                  time{s.baseline_n - s.count === 1 ? "" : "s"}, ideally on different days, in a quiet room with the same microphone.</p>
              </>
            ) : !scored ? (
              <>
                <h2 className="label">Baseline complete <span className="aside">{s.count} readings</span></h2>
                <p className="lede">Your next reading of this text will be compared with your baseline.</p>
              </>
            ) : (
              <>
                <h2 className="label">Latest reading <span className="aside">{s.latest && dateTime(s.latest.timestamp)}</span></h2>
                <div className="drift-status">
                  <h3 className="title"><i className={`dot big ${STATUS_DOT[scored.status]}`} aria-hidden="true" />{scored.status}</h3>
                  <p className="meta">Drift index {scored.index.toFixed(1)} · Stable below {s.bands.watch}, Watch below {s.bands.changed}, Changed above</p>
                </div>
                {scored.persistent && (
                  <p className="alert-line" role="alert"><strong>Persistent change.</strong> Your last {s.persist_k} readings were all
                    Watch or Changed. Consider resting, and if it continues, checking in with a healthcare professional.</p>
                )}
                <p className="lede">{scored.summary}</p>
                <p className="note">{scored.summary_source === "claude" ? "Summary written by Claude from your numbers." : "Summary built from your numbers."}</p>
              </>
            )}
          </section>

          {/* Add a reading */}
          <section className="section">
            <h2 className="label">Add a reading <span className="aside">{s.text.title}</span></h2>
            {busy === "saving" ? (
              <Orb title="Analyzing your reading…" line="Measuring pace, pauses, pitch and your voice signature. About ten seconds." />
            ) : (
              <div className="voice-body" style={{ marginTop: 32 }}>
                <p className="passage">{s.text.text}</p>
                <Recorder clip={clip} onClip={setClip} minSeconds={MIN_SECONDS} disabled={!!busy}
                  idleHint="Press to start, then read the whole text at a natural pace." />
              </div>
            )}
            <div className="flow-end">
              <p className="tips">Same room and microphone each time · read at your natural pace</p>
              <button className="pill" disabled={!clip || (clip.seconds != null && clip.seconds < MIN_SECONDS) || !!busy}
                onClick={() => clip && run("saving", () => api.addReading(s.text.id, clip.blob), "Reading saved")}>
                Analyze and save <span aria-hidden="true">→</span>
              </button>
            </div>
          </section>

          {scored && scored.changes.length > 0 && (
            <section className="section">
              <h2 className="label">What moved most <span className="aside">This reading · your usual</span></h2>
              <div className="rows">
                {scored.changes.map((c) => (
                  <div className="row change-row" key={c.key}>
                    <span><strong>{c.label}</strong><span className="sub">{c.meaning}</span></span>
                    <span className="change-values"><b>{c.now}</b><span className="grey"> · usual {c.usual}</span></span>
                    <span className="change-phrase">{c.z > 0 ? "↑" : "↓"} {c.phrase} <span className="grey">(z {c.z > 0 ? "+" : ""}{c.z.toFixed(1)})</span></span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {s.latest && (
            <section className="section">
              <h2 className="label">What we heard <span className="aside">Latest reading</span></h2>
              <TranscriptDiff diff={s.latest.diff} />
            </section>
          )}

          {s.trend && <Trend state={s} />}

          <div className="track-actions">
            <button className="link quiet" disabled={!!busy}
              onClick={() => run("demo", api.demoReadings, "Demo readings loaded for “The river market”")}>
              {busy === "demo" ? "Loading…" : "See an example with demo readings"}
            </button>
            {s.count > 0 && (
              <button className="link quiet" disabled={!!busy} onClick={() => {
                if (window.confirm(`Delete all ${s.count} readings of “${s.text.title}” and start a new baseline?`)) {
                  run("clear", () => api.clearReadings(s.text.id), "Readings deleted");
                }
              }}>Start over with this text</button>
            )}
          </div>
        </>
      )}
    </>
  );
}

function Trend({ state: s }: { state: TrackingState }) {
  const t = s.trend!;
  const maxIndex = Math.max(...t.readings.map((r) => r.index));
  const top = Math.max(s.bands.changed * 1.4, Math.ceil(maxIndex * 1.15));
  return (
    <section className="section">
      <h2 className="label">Trend <span className="aside">Hollow points: baseline readings</span></h2>
      <h3 className="chart-title">Drift index, each reading</h3>
      <LineChart
        ariaLabel="Drift index for each reading, over the Stable, Watch and Changed bands"
        domain={[0, top]}
        ticks={[0, s.bands.watch, s.bands.changed]}
        format={(v) => v.toFixed(v % 1 ? 1 : 0)}
        bands={[
          { from: 0, to: s.bands.watch, fill: "var(--sage-tint)", label: "Stable" },
          { from: s.bands.watch, to: s.bands.changed, fill: "var(--ochre-tint)", label: "Watch" },
          { from: s.bands.changed, to: top, fill: "var(--terracotta-tint)", label: "Changed" },
        ]}
        endLabel={`${t.readings[t.readings.length - 1].index.toFixed(1)} · ${t.readings[t.readings.length - 1].status}`}
        points={t.readings.map((r) => ({
          label: shortDate(r.timestamp), y: r.index, hollow: r.is_baseline,
          tip: [dateTime(r.timestamp), r.is_baseline ? `Baseline reading · index ${r.index.toFixed(1)}` : `Index ${r.index.toFixed(1)} · ${r.status}`],
        }))}
      />
      <div className="small-multiples">
        {t.series.map((ser) => {
          const values = t.readings.map((r) => r.values[ser.key]);
          const lo = Math.min(...values, ser.usual.mean - ser.usual.std);
          const hi = Math.max(...values, ser.usual.mean + ser.usual.std);
          const padY = (hi - lo) * 0.15 || 1;
          const fmt = AXIS_FORMAT[ser.key] ?? ((v: number) => v.toFixed(1));
          return (
            <div key={ser.key}>
              <h3 className="chart-title">{ser.label} <span className="grey">({ser.unit})</span></h3>
              <LineChart
                ariaLabel={`${ser.label} for each reading, with your usual range shaded`}
                height={170}
                domain={[lo - padY, hi + padY]}
                ticks={[ser.usual.mean]}
                format={fmt}
                bands={[{ from: ser.usual.mean - ser.usual.std, to: ser.usual.mean + ser.usual.std, fill: "var(--sage-tint)", label: "usual" }]}
                points={t.readings.map((r) => ({
                  label: shortDate(r.timestamp), y: r.values[ser.key], hollow: r.is_baseline,
                  tip: [dateTime(r.timestamp), `${ser.label}: ${r.shown[ser.key]}`],
                }))}
              />
            </div>
          );
        })}
      </div>
      <p className="note">Shaded in the small charts: your usual range (baseline average ± 1 standard deviation).</p>
      <details className="table-view">
        <summary>All readings as a table</summary>
        <table>
          <thead><tr><th>When</th><th>Status</th><th>Index</th>{t.series.map((ser) => <th key={ser.key}>{ser.label}</th>)}</tr></thead>
          <tbody>
            {t.readings.map((r) => (
              <tr key={r.timestamp}>
                <td>{dateTime(r.timestamp)}</td><td>{r.status}</td><td>{r.index.toFixed(2)}</td>
                {t.series.map((ser) => <td key={ser.key}>{r.shown[ser.key]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
