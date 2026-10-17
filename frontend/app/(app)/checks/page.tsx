"use client";
// Every check, from the phone and from this laptop, newest first.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { CheckRow } from "@/components/marks";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/session";
import type { Check } from "@/lib/types";

type Filter = "all" | "flagged" | "healthy" | "unusable";
const FILTERS: [Filter, string, (c: Check) => boolean][] = [
  ["all", "All", () => true],
  ["flagged", "Something found", (c) => c.status === "done" && !!c.result?.flagged],
  ["healthy", "Healthy-sounding", (c) => c.status === "done" && !c.result?.flagged],
  ["unusable", "Couldn't use", (c) => c.status === "rejected" || c.status === "error"],
];

export default function ChecksPage() {
  return <Suspense><Checks /></Suspense>;
}

function Checks() {
  const params = useSearchParams();
  const router = useRouter();
  const raw = params.get("filter");
  const f: Filter = FILTERS.some(([k]) => k === raw) ? (raw as Filter) : "all";
  const { data, error } = usePolling(api.overview, 4000);
  const all = data?.checks ?? [];
  const list = all.filter(FILTERS.find(([k]) => k === f)![2]);

  return (
    <>
      <title>Checks · VoiceDrift</title>
      <header className="page-head">
        <h1 className="title">Checks</h1>
        <div className="tabs" role="tablist">
          {FILTERS.map(([k, label, test]) => (
            <button key={k} role="tab" className={f === k ? "on" : ""} aria-selected={f === k}
              onClick={() => router.replace(k === "all" ? "/checks" : `/checks?filter=${k}`)}>
              {label}<span className="n">{all.filter(test).length}</span>
            </button>
          ))}
        </div>
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <h2 className="label">{list.length} check{list.length === 1 ? "" : "s"} <span className="aside">From your phone and this laptop</span></h2>
      <div className="rows">
        {list.map((c) => <CheckRow key={c.id} check={c} />)}
        {data && list.length === 0 && <p className="empty">Nothing here yet.</p>}
      </div>
    </>
  );
}
