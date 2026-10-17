/* Dashboard: link a phone with a one-time QR code, follow the checks it sends, test the email */
(function () {
  const { api, esc, toast, when, ago } = window.VD;
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 2000;
  const ENGINE = { loading: "Loading the voice models…", ready: "Voice models ready", missing: "No voice model is trained yet" };

  let data = null;          // last /api/dashboard
  let pairing = null;       // current QR code, with .expires (ms)
  let requesting = false;
  let another = false;      // showing the QR code although a phone is already linked
  let seen = null;          // check id -> status, to announce changes
  let phoneIds = null;      // linked phone ids, to notice a new link
  let fresh = new Set();    // checks that arrived since the last poll (highlighted once)
  let painted = "";         // the check list as last painted, to skip repaints when nothing changed

  // ---------- Polling ----------

  async function refresh() {
    try {
      data = await api("/api/dashboard");
      $("offline").hidden = true;
    } catch (e) {
      if (e.status === 401) { location.href = "/login"; return; }
      $("offline").hidden = false;
      setTimeout(refresh, POLL_MS * 2);
      return;
    }
    announce();
    paint();
    setTimeout(refresh, POLL_MS);
  }

  function announce() {
    const ids = data.phones.map((p) => p.id);
    if (phoneIds) {
      const linked = data.phones.find((p) => !phoneIds.includes(p.id));
      if (linked) {
        toast(`Phone linked: ${linked.device || "your phone"}`);
        another = false;
        pairing = null;
      }
    }
    phoneIds = ids;

    const now = Object.fromEntries(data.checks.map((c) => [c.id, c.status]));
    fresh = new Set(seen ? data.checks.filter((c) => seen[c.id] === undefined).map((c) => c.id) : []);
    if (seen) {
      for (const c of data.checks) {
        if (seen[c.id] === c.status) continue;
        if (seen[c.id] === undefined) toast("New recording from your phone. Checking it…");
        else if (c.status === "done") toast(c.result.flagged ? "A check found something. You'll get an email." : "Check done: healthy-sounding voice. You'll get an email.");
        else if (c.status === "rejected") toast("A recording couldn't be used. See the details below.");
      }
    }
    seen = now;
  }

  // ---------- Painting ----------

  function paint() {
    const first = data.user.name.split(/\s+/)[0];
    const hour = new Date().getHours();
    $("hello").textContent = `Good ${hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening"}, ${first}.`;
    $("who").textContent = data.user.email;
    paintPhones();
    paintPairing();
    paintChecks();
    paintEmail();
  }

  function paintPhones() {
    $("phones").innerHTML = data.phones.map((p) => `
      <div class="row phone">
        <div><span class="name">${esc(p.device || "Phone")}</span>
          <span class="sub">Linked ${esc(when(p.created))} · last used ${esc(ago(p.last_seen))}</span></div>
        <button class="text-btn" data-unlink="${p.id}">Disconnect</button>
      </div>`).join("");
    $("link-aside").textContent = data.phones.length
      ? `${data.phones.length} linked` : "Same Wi-Fi as this laptop";
  }

  function paintPairing() {
    const show = !data.phones.length || another;
    $("pairing").hidden = !show;
    $("link-another").hidden = show;
    $("hide-code").hidden = !(show && data.phones.length);
    const field = $("addr-field");
    if (data.addresses.length > 1 && !field.dataset.filled) {
      $("addr").innerHTML = data.addresses.map((a, i) =>
        `<option value="${esc(a)}">${esc(a)}${i === 0 ? " (detected Wi-Fi)" : ""}</option>`).join("");
      field.dataset.filled = "1";
      field.hidden = false;
    }
    if (show && (!pairing || pairing.expires <= Date.now())) newPairing();
  }

  async function newPairing() {
    if (requesting) return;
    requesting = true;
    try {
      pairing = await api("/api/pairing", { method: "POST", json: { address: $("addr").value || null } });
      pairing.expires = Date.now() + pairing.expires_in * 1000;
      $("qr").innerHTML = pairing.svg;
      $("qr").classList.remove("expired");
      $("phone-url").textContent = pairing.phone_url;
      tick();
    } catch (e) {
      $("qr-expiry").textContent = e.message;
    } finally {
      requesting = false;
    }
  }

  // The countdown under the QR code; a fresh code is made when it runs out and the tab is visible
  function tick() {
    if (!pairing || $("pairing").hidden) return;
    const left = Math.round((pairing.expires - Date.now()) / 1000);
    if (left > 0) {
      $("qr-expiry").textContent = `Works once, for ${VD.duration(left)} more ·`;
      return;
    }
    $("qr").classList.add("expired");
    $("qr-expiry").textContent = "This code has expired ·";
    if (!document.hidden) newPairing();
  }

  function checkRow(c) {
    const what = c.mode === "vowel" ? "“aaah”" : `Reading${c.text_title ? ` · ${c.text_title}` : ""}`;
    const sub = [what, c.device && `from ${c.device}`, when(c.created)].filter(Boolean).join(" · ");
    let dot, head, more = "", status = "", warn = false;
    if (c.status === "queued" || c.status === "checking") {
      dot = "busy";
      head = c.status === "queued" ? "Waiting to be checked…" : "Checking your voice…";
    } else if (c.status === "done") {
      dot = c.result.flagged ? "high" : "low";
      head = c.result.headline;
      more = c.result.detail;
      status = { sent: "Emailed you", outbox: "Saved to the outbox" }[c.email] || (c.email ? "Email failed" : "Emailing…");
      warn = Boolean(c.email && c.email.startsWith("failed"));
    } else if (c.status === "rejected") {
      dot = "mod";
      head = "Couldn't use this recording";
      more = c.message;
    } else {
      dot = "";
      head = "The check didn't finish";
      more = c.message;
    }
    const title = warn ? ` title="${esc(c.email)}"` : "";
    return `<div class="row check${fresh.has(c.id) ? " fresh" : ""}">
        <i class="dot ${dot}"></i>
        <div><span class="name">${esc(head)}</span><span class="sub">${esc(sub)}</span>
          ${more ? `<p class="more">${esc(more)}</p>` : ""}</div>
        <span class="status${warn ? " warn" : ""}"${title}>${esc(status)}</span>
      </div>`;
  }

  function paintChecks() {
    $("engine").textContent = ENGINE[data.engine] || "";
    const key = JSON.stringify(data.checks);
    if (key === painted && !fresh.size) return;
    painted = key;
    $("checks").innerHTML = data.checks.length
      ? data.checks.map(checkRow).join("")
      : `<p class="empty">No checks yet. Record on your phone and press “Send to my dashboard”.</p>`;
  }

  function paintEmail() {
    const to = `<strong>${esc(data.user.email)}</strong>`;
    $("email-text").innerHTML = data.email.configured
      ? `VoiceDrift emails the result of every check to ${to} through ${esc(data.email.server)}. The email holds the result only, never the recording.`
      : `VoiceDrift emails the result of every check to ${to}. Email isn't set up yet, so for now the messages are
         saved on this laptop in <code>${esc(data.email.outbox)}</code>. To send real emails, set
         <code>EMAIL_BACKEND=smtp</code> and the <code>SMTP_*</code> values in <code>.env</code> and restart.`;
  }

  // ---------- Actions ----------

  $("qr-new").addEventListener("click", newPairing);
  $("addr").addEventListener("change", newPairing);
  $("link-another").addEventListener("click", () => { another = true; pairing = null; paintPairing(); });
  $("hide-code").addEventListener("click", () => { another = false; paintPairing(); });

  $("phones").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-unlink]");
    if (!btn || !confirm("Disconnect this phone? It will need a new QR code to send recordings again.")) return;
    try {
      await api(`/api/phones/${btn.dataset.unlink}`, { method: "DELETE" });
      data.phones = data.phones.filter((p) => String(p.id) !== btn.dataset.unlink);
      phoneIds = data.phones.map((p) => p.id);
      paint();
      toast("Phone disconnected");
    } catch (err) { toast(err.message); }
  });

  $("email-test").addEventListener("click", async () => {
    $("email-test").disabled = true;
    try {
      const r = await api("/api/email-test", { method: "POST" });
      toast(r.outcome === "sent" ? `Test email sent to ${r.to}` : "Email isn't set up: the test was saved to the outbox");
    } catch (err) {
      toast(err.message);
    } finally {
      $("email-test").disabled = false;
    }
  });

  $("signout").addEventListener("click", async () => {
    try { await api("/api/logout", { method: "POST" }); } finally { location.href = "/login"; }
  });

  setInterval(tick, 1000);
  document.addEventListener("visibilitychange", tick);
  refresh();
})();
