"use client";
// Link a phone: a one-time QR code (5 minutes) that opens the phone pages on this laptop's Wi-Fi address.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePolling, useSession } from "@/lib/session";
import type { Pairing } from "@/lib/types";

export default function PhonePage() {
  const { toast } = useSession();
  const { data, error, reload } = usePolling(api.overview, 3000);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [expires, setExpires] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [qrError, setQrError] = useState("");
  const known = useRef<Set<number> | null>(null);

  const newCode = useCallback(async (address?: string) => {
    setQrError("");
    try {
      const p = await api.pairing(address);
      setPairing(p);
      setExpires(Date.now() + p.expires_in * 1000);
    } catch (e) {
      setQrError(e instanceof Error ? e.message : "Couldn't make a QR code.");
    }
  }, []);

  useEffect(() => { newCode(); }, [newCode]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Say so when a phone links while this page is open, and show a fresh code (the old one is used up)
  useEffect(() => {
    if (!data) return;
    const ids = new Set(data.phones.map((p) => p.id));
    if (known.current && data.phones.some((p) => !known.current!.has(p.id))) {
      toast("Phone linked");
      newCode(pairing?.address);
    }
    known.current = ids;
  }, [data, toast, newCode, pairing?.address]);

  const left = Math.max(0, Math.round((expires - now) / 1000));
  const expired = pairing && left === 0;

  async function unlink(id: number) {
    try {
      await api.unlinkPhone(id);
      toast("Phone unlinked");
      known.current?.delete(id);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't unlink the phone.");
    }
  }

  return (
    <>
      <title>Phone · VoiceDrift</title>
      <header className="page-head">
        <div>
          <h1 className="title">Use your <em>phone</em></h1>
          <p className="lede" style={{ marginTop: 16 }}>Record on your phone; this laptop checks the recording, shows the
            result here and emails it to you.</p>
        </div>
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="settings">
        <section>
          <h2 className="label">Scan with your phone <span className="aside">{pairing && !expired ? `Works once · ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left` : ""}</span></h2>
          <div className={`qr ${expired ? "expired" : ""}`}>
            {pairing ? <div className="qr-code" dangerouslySetInnerHTML={{ __html: pairing.svg }} /> : <div className="qr-code" />}
            {expired && <button className="pill" onClick={() => newCode(pairing?.address)}>Show a new code</button>}
          </div>
          {qrError && <p className="form-error" role="alert">{qrError}</p>}
          <div className="qr-meta">
            {data && data.addresses.length > 1 ? (
              <label className="grey">Laptop address in the code{" "}
                <select className="u-select" value={pairing?.address ?? ""} onChange={(e) => newCode(e.target.value)}>
                  {data.addresses.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </label>
            ) : <span className="grey">{pairing?.phone_url}</span>}
            <button className="link quiet" onClick={() => newCode(pairing?.address)}>New code</button>
          </div>
        </section>
        <section>
          <h2 className="label">How to link</h2>
          <ol className="steps">
            <li>Put the phone on the <strong>same Wi-Fi</strong> as this laptop (or on the laptop&apos;s Mobile Hotspot).</li>
            <li><strong>Scan the code</strong> with the phone&apos;s camera and open the link.</li>
            <li>The phone warns once that the connection isn&apos;t private: the certificate is made by this laptop. Tap
              <em> Advanced → Proceed</em> (Android) or <em>Show Details → visit this website</em> (iPhone).</li>
            <li>Tap <strong>Link this phone</strong>. Then record a reading or an “aaah” and tap <strong>Send to my
              dashboard</strong>. The result appears in Checks and arrives by email.</li>
          </ol>
          <p className="note">If the phone can&apos;t open the page: allow Python through Windows Firewall on private networks,
            and avoid guest Wi-Fi, which keeps devices apart.</p>

          <h2 className="label" style={{ marginTop: 48 }}>Linked phones</h2>
          <div className="rows">
            {data?.phones.map((p) => (
              <div className="row pref-row" key={p.id}>
                <span><strong>{p.device || "Phone"}</strong><span className="sub">Linked {ago(p.created)} · last used {ago(p.last_seen)}</span></span>
                <button className="link quiet" onClick={() => unlink(p.id)}>Unlink</button>
              </div>
            ))}
            {data && data.phones.length === 0 && <p className="empty">No phone linked yet.</p>}
          </div>
        </section>
      </div>
    </>
  );
}
