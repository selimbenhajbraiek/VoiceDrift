import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk, Newsreader } from "next/font/google";
import { Toast } from "@/components/Toast";
import { SessionProvider } from "@/lib/session";
import "./styles/base.css";
import "./styles/screens.css";
import "./styles/flow.css";
import "./styles/app.css";

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-newsreader",
  display: "swap",
});
const hanken = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-hanken", display: "swap" });

export const metadata: Metadata = {
  title: { default: "VoiceDrift", template: "%s · VoiceDrift" },
  description: "Check your voice and track how it changes. Research prototype, not a diagnostic device.",
};

export const viewport: Viewport = {
  themeColor: "#faf8f3",
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${newsreader.variable} ${hanken.variable}`}>
      <body>
        <SessionProvider>
          {children}
          <Toast />
        </SessionProvider>
      </body>
    </html>
  );
}
