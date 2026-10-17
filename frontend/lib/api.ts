// Calls to the Python backend. Next.js forwards /api/* to it (next.config.ts), so the sign-in cookie is
// same-origin and nothing here needs a backend address.
import type { Check, Overview, Pairing, TextItem, TrackingState, TrackingText, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiError(0, "Can't reach the VoiceDrift backend. Is `python -m backend.dashboard` running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const unreachable = res.status >= 500 && !data.error; // the dev proxy answers 500 when the backend is down
    throw new ApiError(res.status, unreachable
      ? "Can't reach the VoiceDrift backend. Is `python -m backend.dashboard` running?"
      : data.error || `Request failed (${res.status}).`);
  }
  return data as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});
const audio = (blob: Blob): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": blob.type || "application/octet-stream" },
  body: blob,
});

export const api = {
  me: () => call<User>("/me"),
  signup: (name: string, email: string, password: string) => call<{ ok: true }>("/signup", json("POST", { name, email, password })),
  login: (email: string, password: string) => call<{ ok: true }>("/login", json("POST", { email, password })),
  logout: () => call<{ ok: true }>("/logout", json("POST")),

  overview: () => call<Overview>("/dashboard"),
  texts: () => call<TextItem[]>("/texts"),
  newCheck: (blob: Blob, mode: "reading" | "vowel", textId?: string) =>
    call<{ id: number }>(`/checks?mode=${mode}${mode === "reading" && textId ? `&text=${encodeURIComponent(textId)}` : ""}`, audio(blob)),
  check: (id: number | string) => call<Check>(`/checks/${id}`),

  pairing: (address?: string) => call<Pairing>("/pairing", json("POST", address ? { address } : {})),
  unlinkPhone: (id: number) => call<{ ok: true }>(`/phones/${id}`, json("DELETE")),
  testEmail: () => call<{ outcome: "sent" | "outbox"; to: string }>("/email-test", json("POST")),

  trackingTexts: () => call<TrackingText[]>("/tracking"),
  tracking: (textId: string) => call<TrackingState>(`/tracking/${encodeURIComponent(textId)}`),
  addReading: (textId: string, blob: Blob) => call<TrackingState>(`/tracking/${encodeURIComponent(textId)}`, audio(blob)),
  clearReadings: (textId: string) => call<TrackingState>(`/tracking/${encodeURIComponent(textId)}`, json("DELETE")),
  demoReadings: () => call<TrackingState>("/tracking/demo", json("POST")),
};
