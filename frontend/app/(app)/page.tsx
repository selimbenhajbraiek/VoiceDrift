"use client";
import Link from "next/link";
import { CheckRow } from "@/components/marks";
import { api } from "@/lib/api";
import { firstName } from "@/lib/format";
import { usePolling, useSession } from "@/lib/session";

const WEEK_S = 7 * 86400;

export default function TodayPage() {
  const { me } = useSession();
  const { data, error } = usePolling(api.overview, 4000); // checks sent from a phone appear on their own
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });

  const checks = data?.checks ?? [];
  const week = checks.filter((c) => Date.now() / 1000 - c.created < WEEK_S);
  const flagged = week.filter((c) => c.result?.flagged).length;
  const latest = checks.find((c) => c.status === "done");
  const lede = !data ? "" : latest ? `Your latest result: ${latest.result!.headline.toLowerCase()}.`
    : "Record your first voice check, here or on your phone.";

  return (
    <>
      <title>Today · VoiceDrift</title>
      <header className="today-head" style={{ marginBottom: 64 }}>
        <p className="meta">{today}</p>
        <h1 className="display">{greet}, <em>{firstName(me?.name ?? "")}.</em></h1>
        <p className="lede">{lede}</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        {data?.engine === "loading" && <p className="note">The voice models are loading on the laptop; the first check may take a little longer.</p>}
        {data?.engine === "missing" && <p className="form-error">No screening model is trained yet, so checks can&apos;t run. See the README.</p>}
      </header>
      <div className="today">
        <section>
          <h2 className="label">Latest checks <Link className="aside link" href="/checks">All checks</Link></h2>
          <div className="rows">
            {checks.slice(0, 6).map((c) => <CheckRow key={c.id} check={c} />)}
            {data && checks.length === 0 && <p className="empty">No checks yet.</p>}
          </div>
        </section>
        <section>
          <h2 className="label">This week</h2>
          <div className="stats">
            <Link className="stat" href="/checks"><b>{data ? week.length : "–"}</b><span>Checks</span></Link>
            <Link className={`stat ${flagged ? "alert" : ""}`} href="/checks?filter=flagged"><b>{data ? flagged : "–"}</b><span>Something found</span></Link>
            <Link className="stat" href="/phone"><b>{data ? data.phones.length : "–"}</b><span>Phones linked</span></Link>
          </div>
          <div className="begin-block">
            <h2>Begin a <em>check</em></h2>
            <Link className="row" href="/check?mode=reading">
              <span><strong>Read a text</strong><span className="sub">About 30 seconds, read aloud</span></span>
              <span className="arrow" aria-hidden="true">→</span>
            </Link>
            <Link className="row" href="/check?mode=vowel">
              <span><strong>Hold “aaah”</strong><span className="sub">A steady vowel for 3 to 5 seconds</span></span>
              <span className="arrow" aria-hidden="true">→</span>
            </Link>
            <Link className="row" href="/track">
              <span><strong>Track your voice</strong><span className="sub">Compare readings with your own baseline</span></span>
              <span className="arrow" aria-hidden="true">→</span>
            </Link>
            <Link className="row" href="/phone">
              <span><strong>Use your phone</strong><span className="sub">Link it with a QR code, record anywhere</span></span>
              <span className="arrow" aria-hidden="true">→</span>
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
