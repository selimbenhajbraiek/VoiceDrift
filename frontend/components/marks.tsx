"use client";
// Small pieces shared by the pages: how a check is summarized, its dot, its email state, the transcript diff.
import Link from "next/link";
import { ago } from "@/lib/format";
import type { Check, DiffWord, DriftStatus } from "@/lib/types";

/** sage = healthy-sounding, terracotta = similar to a condition group, ochre = couldn't use, none = in progress */
export function checkDot(c: Check) {
  if (c.status === "done") return c.result?.flagged ? "high" : "low";
  if (c.status === "rejected") return "mod";
  return "";
}

export function checkHeadline(c: Check) {
  switch (c.status) {
    case "queued": return "Waiting to be checked…";
    case "checking": return "Checking your voice…";
    case "done": return c.result?.headline ?? "Done";
    case "rejected": return "Couldn't use this recording";
    default: return "The check didn't finish";
  }
}

export function whatWasRecorded(c: Check) {
  if (c.mode === "vowel") return "“aaah”";
  return c.text_title ? `Reading · ${c.text_title}` : "Reading";
}

/** "Emailed you", "Saved to the outbox", "Email failed" or null while not sent yet */
export function emailState(c: Check): { text: string; warn: boolean; detail?: string } | null {
  if (c.status !== "done") return null;
  if (!c.email) return { text: "Emailing…", warn: false };
  if (c.email === "sent") return { text: "Emailed you", warn: false };
  if (c.email === "outbox") return { text: "Saved to the outbox", warn: false };
  return { text: "Email failed", warn: true, detail: c.email.replace(/^failed:\s*/, "") };
}

export function CheckRow({ check }: { check: Check }) {
  const mail = emailState(check);
  return (
    <Link className="row check-row" href={`/checks/${check.id}`}>
      <i className={`dot ${checkDot(check)}`} aria-hidden="true" />
      <span>
        <span className="name">{checkHeadline(check)}</span>
        <span className="sub">{ago(check.created)} · {check.device || "Phone"} · {whatWasRecorded(check)}</span>
      </span>
      <span className={`status ${mail?.warn ? "warn" : ""}`} title={mail?.detail}>{mail?.text ?? ""}</span>
    </Link>
  );
}

export const STATUS_DOT: Record<DriftStatus, string> = { Baseline: "", Stable: "low", Watch: "mod", Changed: "high" };

export function TranscriptDiff({ diff }: { diff: DiffWord[] }) {
  return (
    <>
      <p className="diff-legend">
        <span className="w-sub">misread</span> <span className="w-del">skipped</span> <span className="w-ins">extra</span>
      </p>
      <p className="diff">
        {diff.map((w, i) => {
          const sep = i ? " " : "";
          if (w.op === "ok") return sep + w.expected;
          if (w.op === "sub") return <span key={i}>{sep}<span className="w-sub" title={`expected “${w.expected}”`}><s>{w.expected}</s> {w.heard}</span></span>;
          if (w.op === "del") return <span key={i}>{sep}<span className="w-del" title="skipped">{w.expected}</span></span>;
          return <span key={i}>{sep}<span className="w-ins" title="extra word">{w.heard}</span></span>;
        })}
      </p>
    </>
  );
}

export function Orb({ title, line }: { title: string; line: string }) {
  return (
    <div className="processing">
      <div className="orb" aria-hidden="true"><i className="ring" /><i className="ring b" /><i className="ring c" /><i className="core" /></div>
      <h1>{title}</h1>
      <p className="now" aria-live="polite">{line}</p>
    </div>
  );
}
