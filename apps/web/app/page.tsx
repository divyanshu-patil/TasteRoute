import Link from "next/link";
import { HeroArt } from "../components/hero-art";
import { NOTHING_SENT } from "../components/ui";

const STEPS = [
  {
    n: "01",
    title: "Tell us what you make",
    body: "Paste your website or describe your products. We match them to brands Qloo knows, or to similar brands when you're too new to be known.",
  },
  {
    n: "02",
    title: "Qloo ranks the venues",
    body: "For every café and bar in your city, Qloo scores how much its guests share your customers' taste, then we subtract plain popularity so you see real fit, not foot traffic.",
  },
  {
    n: "03",
    title: "You approve every pitch",
    body: "We find public business emails and draft short pitches that only use the evidence on screen. You edit, approve and send them yourself.",
  },
];

export default function Home() {
  return (
    <>
      <section className="wrap hero">
        <div className="stack" style={{ gap: 32 }}>
          <div className="kicker">
            <span className="tag">Qloo taste AI</span>
            <span className="tag tag-mist">For food &amp; drink makers</span>
          </div>
          <h1 className="display d-xl">Find venues that share your taste</h1>
          <p className="lead">
            TasteRoute ranks the cafés and bars in your city by taste fit with your brand, shows the Qloo evidence behind
            every pick, and drafts the first email.
          </p>
          <div className="row">
            <Link href="/start" className="btn">
              Start a run
            </Link>
            <Link href="/sample?tour=1" className="btn-ghost">
              Take the 2-minute tour
            </Link>
          </div>
        </div>
        <HeroArt />
      </section>

      <section className="wrap section stack">
        <div className="row between">
          <h2 className="display d-l">How it works</h2>
          <p className="mono muted">3 STEPS · ABOUT 90 SECONDS</p>
        </div>
        <div className="grid-3">
          {STEPS.map((s) => (
            <article key={s.n} className="card stack" style={{ minHeight: 280, justifyContent: "space-between" }}>
              <span className="num-big">{s.n}</span>
              <div className="stack-s">
                <h3 className="h2" style={{ fontSize: 28 }}>
                  {s.title}
                </h3>
                <p className="muted">{s.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="wrap section">
        <div className="inverted arc stack" style={{ padding: "64px 40px", gap: 40 }}>
          <h2 className="display d-l" style={{ maxWidth: "14ch" }}>
            Taste fit, not foot traffic
          </h2>
          <div className="grid-3">
            <div className="stack-s">
              <p className="mono hl" style={{ color: "#fff100" }}>
                TARGET
              </p>
              <p>Qloo scores every venue for people who like the brands you resemble.</p>
            </div>
            <div className="stack-s">
              <p className="mono" style={{ color: "#d1ffca" }}>
                LIFT
              </p>
              <p>We compare that with a popularity-only baseline. A busy tourist spot doesn&apos;t win just for being busy.</p>
            </div>
            <div className="stack-s">
              <p className="mono" style={{ color: "#fff" }}>
                NO QLOO, NO RANKING
              </p>
              <p>If Qloo is unavailable the run stops. We never fall back to guesses dressed up as data.</p>
            </div>
          </div>
        </div>
        <div className="card row between" style={{ borderRadius: "0 0 32px 32px" }}>
          <p className="small muted" style={{ maxWidth: "70ch" }}>
            Honest limits: taste fit is a starting list, not a sales forecast. Coverage depends on Qloo&apos;s
            place data in your city. {NOTHING_SENT}
          </p>
          <Link href="/sample" className="link-mint">
            Explore the sample →
          </Link>
        </div>
      </section>
    </>
  );
}
