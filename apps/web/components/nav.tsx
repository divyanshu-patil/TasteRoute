"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { deleteAccount, signIn, signOut, useAccount } from "../lib/account";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/sample", label: "Sample run" },
  { href: "/runs", label: "All runs" },
  { href: "/settings/suppression", label: "Do-not-contact" },
];

function Account() {
  const { enabled, user, error } = useAccount();
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState<"ask" | "busy" | null>(null);
  const [broken, setBroken] = useState(false); // the picture didn't load: show the initial
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return setDeleting(null);
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  if (!enabled) return null;
  if (user) {
    const label = user.name ?? user.email;
    return (
      <div className="account" ref={box}>
        <button ref={button} className="avatar" aria-haspopup="menu" aria-expanded={open} aria-label={`Account: ${label}`} onClick={() => setOpen((o) => !o)}>
          {user.avatar && !broken
            ? <img src={user.avatar} alt="" referrerPolicy="no-referrer" onError={() => setBroken(true)} /> // eslint-disable-line @next/next/no-img-element
            : label.charAt(0).toUpperCase()}
        </button>
        {open && (
          <div className="account-menu" role="menu" aria-label="Account">
            <div className="stack-s" style={{ gap: 4 }}>
              {user.name && <strong>{user.name}</strong>}
              <span className="small">{user.email}</span>
            </div>
            <button role="menuitem" className="btn btn-light" onClick={() => void signOut()}>Log out</button>
            {deleting ? (
              <div className="stack-s" role="alert">
                <span className="small">This deletes your account, runs, contacts, drafts and do-not-contact list for good.</span>
                <div className="row" style={{ gap: 8 }}>
                  <button className="btn btn-danger btn-sm" disabled={deleting === "busy"}
                    onClick={() => { setDeleting("busy"); deleteAccount().catch(() => setDeleting("ask")); }}>
                    {deleting === "busy" ? "Deleting…" : "Delete everything"}
                  </button>
                  <button className="btn-ghost btn-sm" onClick={() => setDeleting(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <button role="menuitem" className="link small" onClick={() => setDeleting("ask")}>Delete account and data</button>
            )}
          </div>
        )}
      </div>
    );
  }
  return (
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
