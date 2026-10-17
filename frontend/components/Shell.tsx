"use client";
// Top bar (desktop), bottom tab bar (mobile), page container and the quiet footer line.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { initials } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Icon, type IconName } from "./Icon";

type NavKey = "today" | "checks" | "track" | "phone" | "settings" | "new" | null;

function navKey(path: string): NavKey {
  if (path === "/") return "today";
  if (path === "/check") return "new";
  if (path.startsWith("/checks")) return "checks";
  if (path.startsWith("/track")) return "track";
  if (path.startsWith("/phone")) return "phone";
  if (path.startsWith("/settings")) return "settings";
  return null;
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { me } = useSession();
  const active = navKey(path);

  const link = (key: NavKey, href: string, label: string) => (
    <Link href={href} className={active === key ? "active" : ""} aria-current={active === key ? "page" : undefined}>{label}</Link>
  );
  const tab = (key: NavKey, href: string, icon: IconName, label: string) => (
    <Link href={href} className={active === key ? "active" : ""} aria-current={active === key ? "page" : undefined}>
      <Icon name={icon} />
      <span>{label}</span>
    </Link>
  );

  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <Link className="logo" href="/" aria-label="VoiceDrift, Today">voicedrift</Link>
          <nav className="nav" aria-label="Main">
            {link("today", "/", "Today")}
            {link("checks", "/checks", "Checks")}
            {link("track", "/track", "Track your voice")}
            {link("phone", "/phone", "Phone")}
          </nav>
          <div className="end">
            {active !== "new" && <Link className="pill sm" href="/check">New check</Link>}
            <Link className={`avatar ${active === "settings" ? "active" : ""}`} href="/settings" aria-label="Settings and account">
              {me ? initials(me.name) : ""}
            </Link>
          </div>
        </div>
      </header>
      <main className="page">
        {children}
        <p className="foot-note">Research prototype · screening support only, not a diagnosis.</p>
      </main>
      <nav className="tabbar" aria-label="Main">
        {tab("today", "/", "home", "Home")}
        {tab("checks", "/checks", "history", "Checks")}
        <Link href="/check" aria-label="New check"><span className="begin"><i /></span></Link>
        {tab("track", "/track", "trend", "Track")}
        {tab("phone", "/phone", "phone", "Phone")}
      </nav>
    </>
  );
}
