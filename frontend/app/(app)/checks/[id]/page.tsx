"use client";
// One voice check: the breathing orb while the laptop works on it, then the result.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { checkDot, checkHeadline, emailState, Orb, whatWasRecorded } from "@/components/marks";
import { NotFound } from "@/components/NotFound";
import { ClosestGroups, Reliability, SimilarityScale, VoiceMeasures } from "@/components/ResultDetails";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { usePolling } from "@/lib/session";
import type { Check } from "@/lib/types";

/** Still changing: being checked, or done but the email hasn't gone out yet */
const working = (c: Check | null) => !c || c.status === "queued" || c.status === "checking" || (c.status === "done" && !c.email);

export default function CheckResultPage() {
  const { id } = useParams<{ id: string }>();
  const [live, setLive] = useState(true);
  const { data: c, error } = usePolling(() => api.check(id), live ? 1500 : 0, id); // poll while the check is changing
  useEffect(() => { setLive(working(c)); }, [c]);

  if (error && !c) return error.includes("not found") ? <NotFound /> : <p className="form-error" role="alert">{error}</p>;
  if (!c || c.status === "queued" || c.status === "checking") {
    return (
      <>
        <title>Checking · VoiceDrift</title>
        <Orb title="Checking your voice…" line={!c ? "Loading…" : c.status === "queued"
          ? "Waiting for the laptop to start…"
          : "Comparing your recording with the research recordings. This takes a few seconds."} />
      </>
    );
  }

  const r = c.result;
  const mail = emailState(c);
  const reliability = r?.right ? Math.max(1, Math.round(r.right * 10)) : null;
  return (
    <>
      <title>{`${checkHeadline(c)} · VoiceDrift`}</title>
      <Link className="back" href="/checks">← All checks</Link>
      <header className="result-head">
        <div>
          <p className="meta">{dateTime(c.created)} · {c.device || "Phone"} · {whatWasRecorded(c)}{r ? ` · ${r.seconds} s` : ""}</p>
          <h1 className="title result-title"><i className={`dot big ${checkDot(c)}`} aria-hidden="true" />{checkHeadline(c)}</h1>
        </div>
        <div className="actions">
          <Link className="pill" href={`/check?mode=${c.mode}`}>New check</Link>
        </div>
      </header>

      {c.status === "done" && r ? (
        <div className="result-low">
          <section>
            <h2 className="label">What this means</h2>
            <p className="lede result-detail">{r.detail}</p>
            {r.flagged && reliability && !r.groups?.length && (
              <p className="note">The closest group is a guess: in testing on speakers the model never heard, it was right
                about {reliability} time{reliability === 1 ? "" : "s"} in 10.</p>
            )}
          </section>
          <section>
            <h2 className="label">Details</h2>
            <ul className="quality">
              <li><span>Checked with</span><b>{r.model}</b></li>
              <li><span>Recording</span><b>{whatWasRecorded(c)}</b></li>
              <li><span>Length used</span><b>{r.seconds} s</b></li>
              <li><span>Sent from</span><b>{c.device || "Phone"}</b></li>
              <li><span>Email</span><b className={mail?.warn ? "warn" : ""} title={mail?.detail}>{mail?.text}</b></li>
            </ul>
            {mail?.warn && <p className="note">The email couldn&apos;t be sent ({mail.detail}). The result is saved here either way.</p>}
          </section>
        </div>
      ) : (
        <section>
          <p className="lede result-detail">{c.message}</p>
          <p className="note">Nothing was saved from this recording. Try again in a quiet room, close to the microphone.</p>
        </section>
      )}

      {c.status === "done" && r?.score != null && r.bands && (
        <section className="section">
          <h2 className="label">How similar your voice is <span className="aside">to the voice-condition recordings</span></h2>
          <SimilarityScale score={r.score} bands={r.bands} />
        </section>
      )}
      {c.status === "done" && r?.flagged && !!r.groups?.length && (
        <section className="section">
          <h2 className="label">Closest groups <span className="aside">The model&apos;s guess, not a diagnosis</span></h2>
          <ClosestGroups groups={r.groups} />
        </section>
      )}
      {c.status === "done" && !!r?.measures?.length && (
        <section className="section">
          <h2 className="label">Your voice measures <span className="aside">{c.mode === "vowel" ? "The steady middle of your “aaah”" : "Your reading"}</span></h2>
          <VoiceMeasures measures={r.measures} vowel={c.mode === "vowel"} />
        </section>
      )}
      {c.status === "done" && r?.reliability && (
        <section className="section">
          <h2 className="label">How reliable is this?</h2>
          <Reliability r={r.reliability} model={r.model} />
        </section>
      )}

      <p className="disclaimer">VoiceDrift is a research prototype and does not diagnose. It compares your recording with
        research recordings of people with and without voice conditions and says which group it resembles most. Only an
        ENT doctor or a speech-language therapist can assess your voice properly.</p>
    </>
  );
}
