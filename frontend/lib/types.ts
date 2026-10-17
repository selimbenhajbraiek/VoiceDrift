// Shapes of the backend's JSON (backend/dashboard/server.py and tracking.py).

export type Mode = "reading" | "vowel";

export interface User {
  name: string;
  email: string;
}

export interface CheckResult {
  flagged: boolean;
  condition: string | null;
  right: number | null; // how often the closest-group guess was right in testing (0..1)
  headline: string;
  detail: string;
  model: string;
  seconds: number;
  // Added for the result page; checks made before then don't have them
  score?: number;                                   // 0..1 similarity to the voice-condition recordings
  bands?: { some: number; high: number };           // flagged from "some"; "high" = high similarity
  groups?: { name: string; probability: number; right: number }[];  // closest groups, most likely first
  measures?: { name: string; value: number | null }[];               // pitch, variability, jitter, shimmer, HNR
  reliability?: { people: number; sensitivity: number; false_alarms: number; names: string[] };
}

export interface Check {
  id: number;
  device: string | null;
  created: number; // Unix seconds
  mode: Mode;
  text_id: string | null;
  text_title?: string | null;
  status: "queued" | "checking" | "done" | "rejected" | "error";
  result: CheckResult | null;
  message: string | null;
  email: string | null; // "sent", "outbox" or "failed: ..." once the email went out
}

export interface Phone {
  id: number;
  device: string | null;
  created: number;
  last_seen: number;
}

export interface Overview {
  user: User;
  phones: Phone[];
  checks: Check[];
  engine: "loading" | "ready" | "missing";
  modes: Record<Mode, boolean>;
  email: { configured: boolean; server: string | null; outbox: string };
  addresses: string[];
}

export interface Pairing {
  url: string;
  svg: string;
  address: string;
  phone_url: string;
  expires_in: number;
}

export interface TextItem {
  id: string;
  title: string;
  text: string;
}

export interface TrackingText {
  id: string;
  title: string;
  count: number;
}

export interface DiffWord {
  op: "ok" | "sub" | "del" | "ins";
  expected: string | null;
  heard: string | null;
}

export type DriftStatus = "Baseline" | "Stable" | "Watch" | "Changed";

export interface TrackingState {
  text: TextItem;
  count: number;
  baseline_n: number;
  bands: { watch: number; changed: number };
  persist_k: number;
  latest: {
    timestamp: string;
    quality: { duration_s: number; snr_db: number | null; clipped_pct: number };
    transcript: string;
    diff: DiffWord[];
  } | null;
  result:
    | { status: "Baseline" }
    | {
        status: Exclude<DriftStatus, "Baseline">;
        index: number;
        persistent: boolean;
        summary: string;
        summary_source: "template" | "claude";
        changes: { key: string; label: string; meaning: string; now: string; usual: string; z: number; phrase: string }[];
      }
    | null;
  trend: {
    readings: {
      timestamp: string;
      index: number;
      status: DriftStatus;
      is_baseline: boolean;
      values: Record<string, number>;
      shown: Record<string, string>;
    }[];
    series: { key: string; label: string; unit: string; usual: { mean: number; std: number } }[];
  } | null;
}
