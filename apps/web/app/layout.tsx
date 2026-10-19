import type { Metadata, Viewport } from "next";
import { Anton, Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { Nav } from "../components/nav";
import "./globals.css";

const anton = Anton({ weight: "400", subsets: ["latin"], variable: "--font-anton", display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: { default: "TasteRoute — find venues whose guests share your taste", template: "%s · TasteRoute" },
  description:
    "TasteRoute uses Qloo taste data to rank the cafés and bars whose guests already like what you make, explains why, and drafts grounded pitches you approve and send yourself.",
};

export const viewport: Viewport = { themeColor: "#e5e5e5" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${anton.variable} ${inter.variable} ${mono.variable}`}>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <Nav />
        <main id="main">{children}</main>
        <footer className="footer">
          <div className="wrap row between">
            <p className="mono">TASTEROUTE · TASTE FIT FROM QLOO · AI AGENT WITH A PLAN GUARD</p>
            <p className="small">
              Taste fit is a starting list, not a sales forecast. Nothing is sent without your click.{" "}
              <Link href="/settings/suppression">Do-not-contact list</Link> · <Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
