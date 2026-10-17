// Dates from the backend are Unix seconds (checks, phones) or ISO strings (Track your voice readings).
type When = number | string;
const toDate = (w: When) => (typeof w === "number" ? new Date(w * 1000) : new Date(w));

export const date = (w: When) => toDate(w).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
export const shortDate = (w: When) => toDate(w).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
export const dateTime = (w: When) =>
  toDate(w).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export const duration = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

export function ago(w: When) {
  const mins = Math.round((Date.now() - toDate(w).getTime()) / 60000);
  if (mins < 2) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 20) return `${hours}h ago`;
  const days = Math.max(1, Math.round(hours / 24));
  return days < 14 ? `${days}d ago` : date(w);
}

export const initials = (name: string) =>
  name.replace(/^Dr\.?\s+/, "").split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

export const firstName = (name: string) => name.replace(/^Dr\.?\s+/, "").split(/\s+/)[0] || name;
