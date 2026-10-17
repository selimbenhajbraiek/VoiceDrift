"use client";
// Everything behind sign-in. The backend's session cookie decides; nothing renders until it has answered.
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Shell } from "@/components/Shell";
import { useSession } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { me } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (me === null) router.replace("/login");
  }, [me, router]);
  if (!me) return null;
  return <Shell>{children}</Shell>;
}
