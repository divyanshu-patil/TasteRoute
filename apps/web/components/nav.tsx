"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signIn, signOut, useAccount } from "../lib/account";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/sample", label: "Sample run" },
  { href: "/runs", label: "My runs" },
  { href: "/settings/suppression", label: "Do-not-contact" },
];

function Account() {
  const { enabled, email, error } = useAccount();
  if (!enabled) return null;
  return email ? (
    <div className="account">
      <span className="small muted" title={email}>{email}</span>
      <button className="btn btn-light" onClick={() => void signOut()}>Log out</button>
    </div>
  ) : (
    <button className="btn btn-light" onClick={() => void signIn()} title={error ?? "Log in with Google to keep your runs on any device and send emails from your Gmail"}>
      <span>Log in<span className="hide-s"> to save progress</span></span>
    </button>
  );
}

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
        <div>
          <Account />
        </div>
      </div>
    </header>
  );
}
