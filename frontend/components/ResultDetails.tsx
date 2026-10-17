"use client";
// The parts of a voice-check result below the headline: the similarity score on its scale, the closest groups
// (only when something was flagged, like the verdict itself), the voice measures and how reliable the model is.
import type { CheckResult } from "@/lib/types";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function SimilarityScale({ score, bands }: { score: number; bands: { some: number; high: number } }) {
  const zone = score >= bands.high ? "High similarity" : score >= bands.some ? "Some similarity" : "Healthy-sounding";
  return (
    <div className="scale">
      <p className="scale-value"><b>{pct(score)}</b> <span className="grey">· {zone}</span></p>
      <div className="scale-track" role="img"
        aria-label={`Similarity ${pct(score)}: below ${pct(bands.some)} healthy-sounding, from ${pct(bands.some)} some similarity, from ${pct(bands.high)} high similarity`}>
        <i className="zone low" style={{ width: `${bands.some * 100}%` }} />
        <i className="zone mod" style={{ width: `${(bands.high - bands.some) * 100}%` }} />
        <i className="zone high" style={{ width: `${(1 - bands.high) * 100}%` }} />
        <span className="scale-marker" style={{ left: `${Math.min(99, Math.max(1, score * 100))}%` }} />
      </div>
      <p className="note">Below {pct(bands.some)}: healthy-sounding · {pct(bands.some)} to {pct(bands.high)}: some similarity ·
        from {pct(bands.high)}: high similarity. The flag line is set so that about 1 healthy person in 5 is above it.</p>
    </div>
  );
}

export function ClosestGroups({ groups }: { groups: NonNullable<CheckResult["groups"]> }) {
  const named = groups.filter((g) => g.name !== "Healthy").slice(0, 3);
  return (
    <div className="rows">
      {named.map((g) => {
        const n = Math.max(1, Math.round(g.right * 10));
        return (
          <div className="row group-row" key={g.name}>
            <span><strong>{g.name}</strong><span className="sub">When this was the first guess, it was right about {n} time{n === 1 ? "" : "s"} in 10</span></span>
            <span className="bar-track" aria-hidden="true"><i style={{ width: `${Math.max(2, g.probability * 100)}%` }} /></span>
            <span className="bar-value">{pct(g.probability)}</span>
          </div>
        );
      })}
    </div>
  );
}

// Common references for a healthy sustained vowel (Praat / MDVP); [test, wording]
const REFERENCES: Record<string, [((v: number) => boolean) | null, string]> = {
  "Average pitch": [null, "Typical: men about 85–155 Hz, women about 165–255 Hz"],
  "Pitch variability": [null, "Small on a steady “aaah”; larger when reading"],
  "Jitter": [(v) => v < 1.04, "Healthy “aaah”: usually below 1.04%"],
  "Shimmer": [(v) => v < 3.81, "Healthy “aaah”: usually below 3.81%"],
  "Harmonics-to-noise": [(v) => v >= 20, "Healthy “aaah”: usually about 20 dB or more"],
};

export function VoiceMeasures({ measures, vowel }: { measures: NonNullable<CheckResult["measures"]>; vowel: boolean }) {
  return (
    <>
      <div className="rows">
        {measures.map((m) => {
          const [, name, unit] = m.name.match(/^(.*?) \((.*)\)$/) ?? [null, m.name, ""];
          const [test, reference] = REFERENCES[name] ?? [null, ""];
          const outside = vowel && test && m.value != null && !test(m.value);
          return (
            <div className="row measure-row" key={m.name}>
              <span><strong>{name}</strong><span className="sub">{reference}</span></span>
              <span className="measure-value">
                {m.value == null ? <span className="grey">not measured</span> : <><b>{m.value.toFixed(name === "Average pitch" ? 0 : 2)}</b> {unit}</>}
                {outside && <span className="measure-flag">outside the usual range</span>}
              </span>
            </div>
          );
        })}
      </div>
      <p className="note">{vowel
        ? "One measure outside its usual range means little on its own: the check above weighs many measures together."
        : "Jitter, shimmer and harmonics-to-noise are made for a held “aaah”; on a reading they vary more, so the references don't apply."}</p>
    </>
  );
}

export function Reliability({ r, model }: { r: NonNullable<CheckResult["reliability"]>; model: string }) {
  return (
    <p className="lede small-lede">
      Tested on {r.people.toLocaleString("en-GB")} people it had never heard, the {model.toLowerCase()} flagged{" "}
      {pct(r.sensitivity)} of the people with a voice condition and {pct(r.false_alarms)} of healthy people of the same
      ages and sexes. It can only name: {r.names.join(", ")}. It can&apos;t detect other conditions, and it makes mistakes.
    </p>
  );
}
