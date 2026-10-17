/* Phone page: link to a dashboard (QR code), record or upload, send to the laptop, show the result.
   Recordings are captured as raw samples and sent as 16 kHz mono WAV, the format the laptop's models use,
   so it doesn't matter which formats this browser's recorder produces. */
(function () {
  const { api, esc, toast, duration } = window.VD;
  const $ = (id) => document.getElementById(id);
  const RATE = 16000;
  const MAX_S = 180;   // recording stops by itself after 3 minutes
  const BARS = 28;
  const HINT = { reading: "Read the whole text, about 30 seconds", vowel: "Hold the “aaah” for 3 to 5 seconds" };
  const VIEWS = ["loading", "pair", "unlinked", "record", "sent"];

  let info = null;     // /api/phone: the dashboard owner, texts, available modes
  let mode = "reading";
  let rec = null;      // the recording in progress
  let clip = null;     // the recording or file ready to send: { blob, seconds, label, url }
  let poll = null;
  const levels = new Array(BARS).fill(0);

  function show(view) {
    VIEWS.forEach((v) => { $(`v-${v}`).hidden = v !== view; });
    $("unlink").hidden = !(view === "record" || view === "sent");
    window.scrollTo(0, 0);
  }

  function unlinked(text) {
    info = null;
    $("linked-to").textContent = "";
    $("unlinked-text").textContent = text ||
      "Open the VoiceDrift dashboard on your laptop and scan its QR code with this phone's camera.";
    show("unlinked");
  }

  // ---------- Linking ----------

  async function boot() {
    $("meter").innerHTML = "<i></i>".repeat(BARS);
    const pair = location.pathname.match(/^\/pair\/([\w-]+)$/);
    if (pair) return offerPairing(pair[1]);
    try {
      info = await api("/api/phone");
    } catch (e) {
      return unlinked(e.status === 401 ? "" : e.message);
    }
    ready();
  }

  async function offerPairing(token) {
    try {
      $("pair-name").textContent = (await api(`/api/pair/${token}`)).name;
    } catch (e) {
      history.replaceState(null, "", "/phone");
      return unlinked(e.message);
    }
    show("pair");
    $("pair-btn").onclick = async () => {
      $("pair-btn").disabled = true;
      $("pair-error").textContent = "";
      try {
        await api(`/api/pair/${token}`, { method: "POST" });
        history.replaceState(null, "", "/phone");
        info = await api("/api/phone");
        ready();
        toast("Phone linked");
      } catch (e) {
        $("pair-error").textContent = e.message;
        $("pair-btn").disabled = false;
      }
    };
  }

  function ready() {
    $("linked-to").textContent = `Linked to ${info.name}`;
    $("text").innerHTML = info.texts.map((t) => `<option value="${esc(t.id)}">${esc(t.title)}</option>`).join("");
    $("passage").textContent = info.texts[0].text;
    setMode(info.modes.reading || !info.modes.vowel ? "reading" : "vowel");
    show("record");
  }

  // ---------- What to record ----------

  function setMode(m) {
    if (rec) return;
    if (clip && m !== mode) discard();
    mode = m;
    document.querySelectorAll("[data-mode]").forEach((b) => {
      b.classList.toggle("on", b.dataset.mode === m);
      b.setAttribute("aria-selected", b.dataset.mode === m);
    });
    $("reading-part").hidden = m !== "reading";
    $("vowel-part").hidden = m !== "vowel";
    $("mode-off").hidden = info.modes[m];
    paint();
  }

  document.querySelector(".tabs").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]");
    if (b) setMode(b.dataset.mode);
  });
  $("text").addEventListener("change", () => {
    $("passage").textContent = info.texts.find((t) => t.id === $("text").value).text;
  });

  function paint() {
    const live = Boolean(rec && !rec.starting);
    $("recorder").classList.toggle("live", live);
    $("rec-btn").classList.toggle("on", live);
    $("rec-btn").disabled = !info.modes[mode] || Boolean(rec && rec.starting);
    $("rec-btn").setAttribute("aria-label", live ? "Stop recording" : "Start recording");
    $("rec-hint").textContent = rec ? (rec.starting ? "Starting the microphone…" : "Recording · tap to stop") : HINT[mode];
    if (!rec) $("rec-time").textContent = clip && clip.seconds ? duration(clip.seconds) : "0:00";
    $("clip").hidden = !clip || Boolean(rec);
    $("send").disabled = !clip || Boolean(rec) || !info.modes[mode];
  }

  // ---------- Recording ----------

  // Collects raw samples off the audio thread in blocks of 4096
  const WORKLET = `registerProcessor("vd-capture", class extends AudioWorkletProcessor {
    constructor() { super(); this.buf = new Float32Array(4096); this.n = 0; }
    process(inputs) {
      const ch = inputs[0] && inputs[0][0];
      if (ch) for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) { this.port.postMessage(this.buf); this.buf = new Float32Array(4096); this.n = 0; }
      }
      return true;
    }
  });`;

  async function startRecording() {
    $("rec-error").textContent = "";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $("rec-error").textContent = "This browser can't record on this page. Use “upload a recording” instead.";
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    const ctx = new AC(); // created during the tap, so iPhones let it start
    ctx.resume();
    const r = (rec = { ctx, chunks: [], frames: 0, starting: true });
    levels.fill(0);
    paint();
    try {
      // Raw microphone: noise suppression and auto gain would change the voice measures
      r.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      r.source = ctx.createMediaStreamSource(r.stream);
      if (ctx.audioWorklet && window.AudioWorkletNode) {
        const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
        await ctx.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);
        r.node = new AudioWorkletNode(ctx, "vd-capture", { channelCount: 1, channelCountMode: "explicit" });
        r.node.port.onmessage = (e) => capture(r, e.data);
      } else {
        r.node = ctx.createScriptProcessor(4096, 1, 1);
        r.node.onaudioprocess = (e) => capture(r, new Float32Array(e.inputBuffer.getChannelData(0)));
      }
      const mute = ctx.createGain();
      mute.gain.value = 0; // the node must reach the speakers to run, but silently
      r.source.connect(r.node);
      r.node.connect(mute);
      mute.connect(ctx.destination);
      r.starting = false;
      r.t0 = performance.now();
      r.timer = setInterval(tick, 100);
      paint();
    } catch (e) {
      stopDevices(r);
      rec = null;
      paint();
      $("rec-error").textContent = e && e.name === "NotAllowedError"
        ? "The microphone is blocked. Allow it for this page in your browser's settings, or upload a recording."
        : "Couldn't start the microphone. Upload a recording instead.";
    }
  }

  function capture(r, block) {
    if (rec !== r) return;
    r.chunks.push(block);
    r.frames += block.length;
    let sum = 0;
    for (let i = 0; i < block.length; i++) sum += block[i] * block[i];
    levels.push(Math.sqrt(sum / block.length));
    levels.shift();
  }

  function tick() {
    const s = (performance.now() - rec.t0) / 1000;
    $("rec-time").textContent = duration(s);
    const bars = $("meter").children;
    levels.forEach((level, i) => {
      const db = 20 * Math.log10(level + 1e-6); // -60 dB (silence) .. 0 dB (full scale)
      bars[i].style.height = `${Math.max(6, Math.min(100, ((db + 60) / 60) * 100))}%`;
    });
    if (s >= MAX_S) stopRecording();
  }

  function stopDevices(r) {
    clearInterval(r.timer);
    if (r.stream) r.stream.getTracks().forEach((t) => t.stop());
    if (r.source) r.source.disconnect();
    if (r.node) r.node.disconnect();
    r.ctx.close().catch(() => {});
  }

  async function stopRecording() {
    const r = rec;
    if (!r || r.starting) return;
    rec = null;
    stopDevices(r);
    Array.from($("meter").children).forEach((bar) => { bar.style.height = ""; });
    const rate = r.ctx.sampleRate;
    const seconds = r.frames / rate;
    if (seconds < 1) {
      paint();
      $("rec-error").textContent = "That was too short. Tap the button and record again.";
      return;
    }
    const samples = new Float32Array(r.frames);
    let at = 0;
    for (const block of r.chunks) { samples.set(block, at); at += block.length; }
    const out = await resample(samples, rate);
    setClip(wav(out.samples, out.rate), seconds, "Your recording");
  }

  $("rec-btn").addEventListener("click", () => (rec ? stopRecording() : startRecording()));

  // ---------- Audio helpers ----------

  // Resample to 16 kHz with the browser's own resampler; keep the original rate if it can't
  async function resample(samples, rate) {
    if (rate === RATE) return { samples, rate };
    try {
      const off = new OfflineAudioContext(1, Math.ceil((samples.length * RATE) / rate), RATE);
      const buffer = off.createBuffer(1, samples.length, rate);
      buffer.getChannelData(0).set(samples);
      const src = off.createBufferSource();
      src.buffer = buffer;
      src.connect(off.destination);
      src.start();
      return { samples: (await off.startRendering()).getChannelData(0), rate: RATE };
    } catch {
      return { samples, rate };
    }
  }

  function mixdown(buffer) {
    const out = new Float32Array(buffer.length);
    for (let c = 0; c < buffer.numberOfChannels; c++) {
      const ch = buffer.getChannelData(c);
      for (let i = 0; i < out.length; i++) out[i] += ch[i] / buffer.numberOfChannels;
    }
    return out;
  }

  // 16-bit PCM mono WAV
  function wav(samples, rate) {
    const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
    const text = (at, s) => { for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i)); };
    text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVE");
    text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    text(36, "data"); view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([view], { type: "audio/wav" });
  }

  // ---------- Uploading a file ----------

  $("file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file || rec) return;
    $("rec-error").textContent = "";
    $("rec-hint").textContent = "Reading the file…";
    let blob = file, seconds = null;
    try { // decode here (handles iPhone voice memos, M4A, ...); if this browser can't, the laptop tries the file
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC();
      const bytes = await file.arrayBuffer();
      const decoded = await new Promise((ok, fail) => ctx.decodeAudioData(bytes, ok, fail));
      ctx.close().catch(() => {});
      const out = await resample(mixdown(decoded), decoded.sampleRate);
      blob = wav(out.samples, out.rate);
      seconds = decoded.duration;
    } catch { /* send the original file */ }
    if (blob.size > info.max_mb * 1048576) {
      paint();
      $("rec-error").textContent = `This recording is too long (over ${info.max_mb} MB). Please use a shorter one.`;
      return;
    }
    setClip(blob, seconds, file.name);
  });

  function setClip(blob, seconds, label) {
    if (clip) URL.revokeObjectURL(clip.url);
    clip = { blob, seconds, label, url: URL.createObjectURL(blob) };
    $("player").src = clip.url;
    $("clip-info").textContent = seconds ? `${label} · ${duration(seconds)}` : label;
    paint();
  }

  function discard() {
    if (clip) URL.revokeObjectURL(clip.url);
    clip = null;
    $("player").removeAttribute("src");
    paint();
  }
  $("discard").addEventListener("click", discard);

  // ---------- Sending and the result ----------

  $("send").addEventListener("click", async () => {
    if (!clip) return;
    $("send").disabled = true;
    $("send-label").textContent = "Sending…";
    $("rec-error").textContent = "";
    const query = new URLSearchParams({ mode });
    if (mode === "reading") query.set("text", $("text").value);
    try {
      const { id } = await api(`/api/phone/checks?${query}`, {
        method: "POST", body: clip.blob, headers: { "Content-Type": clip.blob.type || "application/octet-stream" },
      });
      follow(id);
    } catch (e) {
      if (e.status === 401) return unlinked(e.message);
      $("rec-error").textContent = e.status ? e.message
        : "Couldn't reach your laptop. Check that it's on, running VoiceDrift, and on the same Wi-Fi.";
    } finally {
      $("send-label").textContent = "Send to my dashboard";
      paint();
    }
  });

  function follow(id) {
    show("sent");
    outcome({ status: "queued" });
    clearTimeout(poll);
    const started = Date.now();
    const step = async () => {
      try {
        const c = await api(`/api/phone/checks/${id}`);
        outcome(c);
        const emailing = c.status === "done" && c.result.flagged && !c.email && Date.now() - started < 60000;
        if (c.status === "queued" || c.status === "checking" || emailing) poll = setTimeout(step, 1200);
      } catch (e) {
        if (e.status === 401) return unlinked(e.message);
        outcome({ status: "lost" });
        poll = setTimeout(step, 3000);
      }
    };
    step();
  }

  function outcome(c) {
    const waiting = (text) => `<p class="waiting"><i class="dot busy"></i>${esc(text)}</p>`;
    let html;
    if (c.status === "queued") html = waiting("Waiting for your laptop…");
    else if (c.status === "checking") html = waiting("Your laptop is checking your voice…");
    else if (c.status === "lost") html = waiting("Lost the connection to your laptop. Retrying…");
    else if (c.status === "done") {
      const r = c.result;
      const email = !r.flagged ? "Saved on your dashboard."
        : { sent: "Your laptop emailed you about it. It's also on your dashboard.",
            outbox: "It's on your dashboard. Email isn't set up on the laptop yet, so the email was saved there instead." }[c.email]
          || (c.email ? "It's on your dashboard, but the email couldn't be sent." : "Emailing you…");
      html = `<p class="label">Result</p>
        <div class="headline"><i class="dot ${r.flagged ? "high" : "low"}"></i><h2>${esc(r.headline)}</h2></div>
        <p>${esc(r.detail)}</p><p class="meta">${esc(email)}</p>`;
    } else {
      html = `<p class="label">${c.status === "rejected" ? "Let's try that again" : "The check didn't finish"}</p>
        <div class="headline"><i class="dot ${c.status === "rejected" ? "mod" : ""}"></i><h2>${esc(
          c.status === "rejected" ? "Your laptop couldn't use this recording" : "Something went wrong")}</h2></div>
        <p>${esc(c.message || "")}</p>`;
    }
    $("sent-title").textContent = c.status === "done" ? "Checked" : "Sent to your laptop";
    $("outcome").innerHTML = html;
  }

  $("again").addEventListener("click", () => {
    clearTimeout(poll);
    $("outcome").innerHTML = "";
    discard();
    show("record");
  });

  $("unlink").addEventListener("click", async () => {
    if (!confirm("Unlink this phone? You'll need a new QR code from the laptop to send recordings again.")) return;
    clearTimeout(poll);
    try { await api("/api/phone/unlink", { method: "POST" }); } catch { /* the cookie is gone either way */ }
    unlinked("This phone is unlinked. Scan the QR code on your laptop's dashboard to link it again.");
  });

  boot();
})();
