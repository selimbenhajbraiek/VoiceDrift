"use client";
// Sign in (/login) and create an account (/signup): the editorial statement on the left, the form on the right.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

// Static waveform heights (percent) so server and client render the same bars
const bars = Array.from({ length: 64 }, (_, i) =>
  Math.round(12 + Math.abs(Math.sin(i * 0.42) * Math.sin(i * 0.13 + 1) * 80) + (i % 3) * 3),
);

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const { me, refresh } = useSession();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const signup = mode === "signup";

  useEffect(() => {
    if (me) router.replace("/");
  }, [me, router]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || ""), password = String(form.get("password") || "");
    setBusy(true);
    setError("");
    try {
      if (signup) await api.signup(String(form.get("name") || ""), email, password);
      else await api.login(email, password);
      await refresh(); // the layout effect above then goes to Today
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <title>{signup ? "Create account · VoiceDrift" : "Sign in · VoiceDrift"}</title>
      <span className="logo">voicedrift</span>
      <section className="statement">
        <h1 className="display">The voice <em>remembers</em> what words leave out.</h1>
        <div className="wave" aria-hidden="true">
          {bars.map((h, i) => <i key={i} style={{ height: `${h}%`, animationDelay: `${(i * 0.05).toFixed(2)}s` }} />)}
        </div>
        <p className="lede">Record a short reading or an “aaah”, here or on your phone. VoiceDrift checks your voice and
          tracks how it changes over time, and emails you every result.</p>
      </section>
      <form noValidate onSubmit={submit}>
        <h2>{signup ? "Create your account" : "Sign in"}</h2>
        {signup && (
          <div className="field">
            <label htmlFor="name">Your name</label>
            <input className="u-input" id="name" name="name" autoComplete="name" required />
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input className="u-input" id="email" name="email" type="email" autoComplete="username" required />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input className="u-input" id="password" name="password" type="password" required minLength={8}
            autoComplete={signup ? "new-password" : "current-password"} />
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="pill lg wide" type="submit" disabled={busy}>
          {busy ? "One moment…" : signup ? "Create account" : "Continue"} <span aria-hidden="true">→</span>
        </button>
        <div className="links">
          {signup
            ? <span className="grey">Already have an account? <Link className="link" href="/login">Sign in</Link></span>
            : <span className="grey">New here? <Link className="link" href="/signup">Create an account</Link></span>}
        </div>
        {signup && <p className="grey small">Results are emailed to this address. Your recordings are checked and then
          deleted; only the results are kept.</p>}
      </form>
      <footer>Research prototype · not a diagnostic device</footer>
    </div>
  );
}
