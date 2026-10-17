"use client";
import { useRef } from "react";
import { useSession } from "@/lib/session";

export function Toast() {
  const { toastMsg } = useSession();
  const last = useRef("");
  if (toastMsg) last.current = toastMsg; // keep the text while it fades out
  return (
    <div className={`toast ${toastMsg ? "show" : ""}`} role="status" aria-live="polite">
      {last.current}
    </div>
  );
}
