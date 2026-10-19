"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/sample", label: "Sample run" },
  { href: "/runs", label: "My runs" },
  { href: "/settings/suppression", label: "Do-not-contact" },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="nav">
      <div className="wrap">
        <Link href="/" className="logo">
          <span>Taste</span>
          <span>Route</span>
        </Link>
        <nav className="pill" aria-label="Main">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <Link href="/start" className="btn">
          Start a run
        </Link>
      </div>
    </header>
  );
}
