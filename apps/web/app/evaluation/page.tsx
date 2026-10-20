import type { Metadata } from "next";
import Link from "next/link";
import ev from "../../public/evaluation.json";

export const metadata: Metadata = { title: "Does it find real accounts?" };

type Brand = {
  brand: string;
  split: string;
  what: string;
  comparables: string[];
  not_scored?: string;
  accounts?: number;
  pool?: number;
  recall30?: Record<string, number | null>;
};

const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const nth = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"}`;

export default function Evaluation() {
  const brands = ev.brands as Brand[];
  const f = ev.featured;
  const found = ev.found_top30 as Record<string, number>;
  return (
    <div className="wrap stack" style={{ gap: 40, paddingBottom: 80 }}>
      <div className="stack" style={{ gap: 24 }}>
        <div className="kicker">
          <span className="tag">Backtest</span>
          <span className="tag tag-mist">{ev.city}, run {ev.generated}</span>
        </div>
        <h1 className="display d-l">Does it find real accounts?</h1>
        <p className="lead">
          We tested TasteRoute against an answer key: the venues that already carry real brands, taken from each
          brand&apos;s own published list. Every method ranked the same pool of Qloo&apos;s best-known venues, and none
          saw the brand&apos;s name.
        </p>
      </div>

      <div className="grid-4">
        <div className="stat">
          <p className="mono">TASTEROUTE (QLOO FIT)</p>
          <p className="v">{found["Q-fit"]}</p>
          <p className="small muted">of {ev.accounts} accounts in its top 30</p>
        </div>
        <div className="stat">
          <p className="mono">AN LLM READING NAMES</p>
          <p className="v">{found["LLM"]}</p>
          <p className="small muted">same pool, same brief</p>
        </div>
        <div className="stat">
          <p className="mono">QLOO TASTE ONLY</p>
          <p className="v">{found["Q-raw"]}</p>
          <p className="small muted">affinity without the mass-market check</p>
        </div>
        <div className="stat">
          <p className="mono">CHANCE</p>
          <p className="v">{found["RANDOM"]}</p>
          <p className="small muted">expected from a random order</p>
        </div>
      </div>

      <div className="inverted stack-s" style={{ padding: 32 }}>
        <p className="mono" style={{ color: "#fff100" }}>
          VERDICT
        </p>
        <h2 className="h2">A tie, not a win</h2>
        <p className="muted" style={{ maxWidth: "70ch" }}>
          We wrote down the target before running the test brands: {ev.target}. TasteRoute won{" "}
          {ev.wins.q_fit}, tied {ev.wins.ties} and lost {ev.wins.llm} of the {ev.test_brands_scored} brands we could
          score. The fourth could not be scored because Qloo knows none of its comparable brands; the app refuses to
          rank in that case too. Qloo and the LLM found different accounts, so the results page shows both.
        </p>
      </div>

      <section className="stack-s">
        <h2 className="h2">By brand</h2>
        <p className="small muted">Share of the brand&apos;s accounts in each method&apos;s top 30. Dev brands were used to fix the method before the test run.</p>
        <div className="table-wrap" style={{ overflowX: "auto" }}>
          <table className="t">
            <thead>
              <tr>
                <th>Brand</th>
                <th>Accounts</th>
                <th className="num">TasteRoute</th>
                <th className="num">Qloo taste only</th>
                <th className="num">LLM</th>
                <th className="num">Chance</th>
              </tr>
            </thead>
            <tbody>
              {brands.map((b) => (
                <tr key={b.brand}>
                  <td>
                    <span style={{ fontWeight: 500 }}>{b.brand}</span>{" "}
                    <span className={b.split === "test" ? "tag" : "tag tag-mist"}>{b.split}</span>
                    <p className="small muted">{b.what}</p>
                  </td>
                  {b.not_scored ? (
                    <td colSpan={5} className="small muted">
                      Not scored: {b.not_scored}.
                    </td>
                  ) : (
                    <>
                      <td className="num">{b.accounts}</td>
                      <td className="num">{pct(b.recall30?.["Q-fit"])}</td>
                      <td className="num">{pct(b.recall30?.["Q-raw"])}</td>
                      <td className="num">{pct(b.recall30?.["LLM"])}</td>
                      <td className="num">{pct(b.recall30?.["RANDOM"])}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card stack-s">
        <p className="mono">AN ACCOUNT QLOO FOUND AND THE LLM MISSED</p>
        <h2 className="h2">{f.venue}</h2>
        <p style={{ maxWidth: "70ch" }}>
          A real {f.brand} account ({f.what.toLowerCase()}). TasteRoute ranked this {f.type} {nth(f.q_fit_rank)} of{" "}
          {f.pool}; the LLM ranked it {nth(f.llm_rank)}. Fans of {f.drivers.join(" and ")} over-index there (Qloo).
        </p>
      </section>

      <section className="stack-s">
        <h2 className="h2">What we learned</h2>
        <ul className="stack-s" style={{ maxWidth: "75ch" }}>
          <li>Qloo is strongest at the top of the list for taste-led brands: for the non-alcoholic aperitivo brand, Qloo&apos;s taste score put 7 of 36 accounts in its top 15, the LLM 4.</li>
          <li>The LLM reads names (&ldquo;Whiskey&rdquo;, &ldquo;Wine House&rdquo;, &ldquo;Coffee&rdquo;) and knows famous venues, and ranks accounts higher on average.</li>
          <li>Our mass-market check counts Starbucks and Dunkin&apos;, which pushed real coffee accounts down for a coffee roaster. Qloo&apos;s taste score alone did better on this test.</li>
          <li>If Qloo doesn&apos;t know the brands you resemble (small natural-wine producers here), there is no taste signal to rank with.</li>
        </ul>
      </section>

      <section className="card-mist stack-s">
        <h3 className="h3">Method and limits</h3>
        <p className="small muted" style={{ maxWidth: "80ch" }}>
          Six real brands with public account lists, two used to fix the method and four run once. The method,
          comparables and target were committed before the test run, and the one change made after the dev run is
          recorded. Pools are Qloo&apos;s 500 best-known Brooklyn venues per venue type; accounts outside them are left
          out for every method. Samples are small: one account moves a brand&apos;s number by several points.
        </p>
        <a className="link-mint" href={ev.doc} style={{ alignSelf: "flex-start" }}>
          Full tables, every account and the code →
        </a>
      </section>

      <Link href="/sample" className="btn-ghost" style={{ alignSelf: "flex-start" }}>
        See a sample run
      </Link>
    </div>
  );
}
