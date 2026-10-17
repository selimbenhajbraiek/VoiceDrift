"use client";
// Account and email notifications.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { usePolling, useSession } from "@/lib/session";

export default function SettingsPage() {
  const { me, signOut, toast } = useSession();
  const router = useRouter();
  const { data } = usePolling(api.overview, 0);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function testEmail() {
    setTesting(true);
    setResult(null);
    try {
      const r = await api.testEmail();
      setResult({ ok: true, text: r.outcome === "sent" ? `Test email sent to ${r.to}.` : `Email isn't set up, so the test was saved to ${data?.email.outbox}.` });
    } catch (e) {
      setResult({ ok: false, text: e instanceof Error ? e.message : "The test email couldn't be sent." });
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <title>Settings · VoiceDrift</title>
      <header style={{ marginBottom: 64 }}>
        <p className="meta" style={{ marginBottom: 14 }}>Settings</p>
        <h1 className="display">{me?.name}</h1>
        <p className="lede" style={{ marginTop: 16 }}>{me?.email}</p>
      </header>
      <div className="settings">
        <section>
          <h2 className="label">Email notifications</h2>
          <p className="lede" style={{ marginTop: 24 }}>
            The result of every voice check is emailed to <strong>{me?.email}</strong>
            {data?.email.configured ? <> through {data.email.server}.</> : <>. Email isn&apos;t set up on the laptop yet, so
              for now the messages are saved in <code>{data?.email.outbox}</code>.</>}
            {" "}The email holds the result only, never the recording.
          </p>
          <div className="form-end" style={{ marginTop: 28 }}>
            <button className="pill ghost" onClick={testEmail} disabled={testing}>{testing ? "Sending…" : "Send a test email"}</button>
          </div>
          {result && <p className={result.ok ? "note" : "form-error"} role="status">{result.text}</p>}
          {!data?.email.configured && <p className="note">To send real emails, set <code>EMAIL_BACKEND=smtp</code> and the
            <code> SMTP_*</code> values in <code>.env</code>, then restart the backend.</p>}
        </section>
        <section>
          <h2 className="label">Account</h2>
          <div className="rows">
            <div className="row pref-row"><span><strong>Name</strong><span className="sub">{me?.name}</span></span></div>
            <div className="row pref-row"><span><strong>Email</strong><span className="sub">{me?.email}</span></span></div>
            <div className="row pref-row"><span><strong>Privacy</strong><span className="sub">Recordings are checked on this
              laptop and then deleted. Only results are kept.</span></span></div>
          </div>
          <div className="form-end">
            <button className="link quiet" onClick={async () => { await signOut(); toast("Signed out"); router.replace("/login"); }}>Sign out</button>
          </div>
        </section>
      </div>
    </>
  );
}
