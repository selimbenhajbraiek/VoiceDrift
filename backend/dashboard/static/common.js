/* Helpers shared by the dashboard, account and phone pages */
window.VD = (function () {
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // fetch() for the JSON API: throws an Error with .status and the server's message
  async function api(path, { method = "GET", json, body, headers = {} } = {}) {
    const opts = { method, headers: { ...headers }, credentials: "same-origin" };
    if (json !== undefined) {
      opts.body = JSON.stringify(json);
      opts.headers["Content-Type"] = "application/json";
    } else if (body !== undefined) {
      opts.body = body;
    }
    let res;
    try {
      res = await fetch(path, opts);
    } catch {
      throw Object.assign(new Error("Can't reach VoiceDrift on the laptop. Is it still running?"), { status: 0 });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || `Something went wrong (${res.status}).`), { status: res.status });
    return data;
  }

  let toastTimer;
  function toast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  const duration = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

  // Epoch seconds -> "14:32" today, "12 Oct, 14:32" otherwise
  function when(epoch) {
    const d = new Date(epoch * 1000);
    const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === new Date().toDateString()) return time;
    return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${time}`;
  }

  function ago(epoch) {
    const mins = Math.round((Date.now() / 1000 - epoch) / 60);
    if (mins < 2) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.round(mins / 60);
    return hours < 24 ? `${hours} h ago` : when(epoch);
  }

  return { esc, api, toast, duration, when, ago };
})();
