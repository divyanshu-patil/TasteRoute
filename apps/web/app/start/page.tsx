"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { LocationPicker } from "../../components/location-picker";
import { Banner, ErrorPanel } from "../../components/ui";
import { ApiError, api, type S } from "../../lib/api";

type Product = { name: string; kind: string };
type Intake = {
  profile: {
    brand_name: string;
    one_liner: string;
    category: string;
    prospects_are_consumer_facing: boolean;
    price_tier: "budget" | "mid" | "premium" | "unknown";
    style_words: string[];
    products: { name: string; kind?: string | null }[];
  };
  source: "llm" | "empty";
  pages: string[];
  notice: string | null;
  unsupported: boolean;
  unsupported_message: string | null;
  source_text: string;
};
type City = S["CityHit"];
type Place = S["Place"];

const STEP_NAMES = ["Your brand", "Profile", "Qloo matches", "City"];

function message(e: unknown): string {
  if (e instanceof ApiError) return e.detail || e.title;
  return "Something went wrong. Please try again.";
}

export default function Start() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // step 1
  const [mode, setMode] = useState<"url" | "describe">("url");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  // step 2
  const [intake, setIntake] = useState<Intake | null>(null);
  const [name, setName] = useState("");
  const [oneLiner, setOneLiner] = useState("");
  const [tier, setTier] = useState<Intake["profile"]["price_tier"]>("unknown");
  const [style, setStyle] = useState("");
  const [sender, setSender] = useState("");
  const [products, setProducts] = useState<Product[]>([{ name: "", kind: "" }]);
  const [override, setOverride] = useState(false);
  // step 3
  const [brand, setBrand] = useState<S["BrandOut"] | null>(null);
  const [resolution, setResolution] = useState<S["ResolutionOut"][]>([]);
  const [entities, setEntities] = useState<Record<string, S["EntityOut"][]>>({});
  const [searchFor, setSearchFor] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<S["QlooSearchItem"][]>([]);
  // step 4
  const [categories, setCategories] = useState<S["CategoryOut"][]>([]);
  const [types, setTypes] = useState<string[]>(["cafe", "bar"]);
  const [city, setCity] = useState<City | null>(null);
  const [base, setBase] = useState<Place | null>(null);
  const placeError = useCallback((e: unknown) => setError(message(e)), []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const unsupported = !!intake?.unsupported;

  const submitIntake = () =>
    run(async () => {
      const body = mode === "url" ? { website_url: url.trim(), description: description.trim() || undefined } : { description: description.trim() };
      const out = await api<Intake>("/v1/brands/intake", { method: "POST", body });
      const p = out.profile;
      setIntake(out);
      setName(p.brand_name || "");
      setOneLiner(p.one_liner || "");
      setTier(p.price_tier || "unknown");
      setStyle((p.style_words || []).join(", "));
      setProducts(p.products.length ? p.products.slice(0, 5).map((x) => ({ name: x.name, kind: x.kind ?? "" })) : [{ name: "", kind: "" }]);
      setStep(2);
    });

  const saveProfile = () =>
    run(async () => {
      const cleaned = products.filter((p) => p.name.trim()).map((p) => ({ name: p.name.trim(), kind: p.kind.trim() || null }));
      if (!name.trim() || !cleaned.length) throw new ApiError(422, "validation_error", "Add your brand name and at least one product", "");
      const profile = {
        one_liner: oneLiner.trim().slice(0, 140),
        category: intake?.profile.category ?? "food_drink",
        prospects_are_consumer_facing: intake?.profile.prospects_are_consumer_facing ?? true,
        price_tier: tier,
        style_words: style.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 6),
        sender_name: sender.trim() || null,
      };
      let b: S["BrandOut"];
      if (brand) {
        b = await api<S["BrandOut"]>(`/v1/brands/${brand.id}`, {
          method: "PATCH",
          body: { name: name.trim(), profile, products: cleaned, unsupported_override: override },
        });
      } else {
        const created = await api<S["BrandCreated"]>("/v1/brands", {
          method: "POST",
          body: {
            name: name.trim(),
            website_url: mode === "url" && url.trim() ? url.trim() : null,
            profile,
            products: cleaned,
            unsupported_override: override,
            source_text: intake?.source_text?.slice(0, 13000) || null,
          },
        });
        b = await api<S["BrandOut"]>(`/v1/brands/${created.brand_id}`);
      }
      setBrand(b);
      const res = await api<S["ResolutionOut"][]>(`/v1/brands/${b.id}/resolve`, { method: "POST" });
      setResolution(res);
      setEntities(Object.fromEntries(res.map((r) => [r.product_id, r.entities])));
      setStep(3);
    });

  const putEntities = (pid: string, list: S["EntityOut"][]) =>
    run(async () => {
      const out = await api<S["EntityOut"][]>(`/v1/products/${pid}/entities`, {
        method: "PUT",
        body: { entities: list.map((e) => ({ entity_id: e.entity_id, source_call_id: e.source_call_id ?? "" })) },
      });
      setEntities((m) => ({ ...m, [pid]: out }));
    });

  const searchQloo = () =>
    run(async () => {
      if (searchQ.trim().length < 2) return;
      setSearchResults(await api<S["QlooSearchItem"][]>(`/v1/qloo/search?q=${encodeURIComponent(searchQ.trim())}`));
    });

  const goCity = () =>
    run(async () => {
      if (!categories.length) setCategories(await api<S["CategoryOut"][]>("/v1/categories"));
      setStep(4);
    });

  const startRun = () =>
    run(async () => {
      if (!brand || !city) return;
      const out = await api<S["RunCreated"]>("/v1/runs", {
        method: "POST",
        body: {
          brand_id: brand.id,
          product_ids: brand.products.map((p) => p.id),
          city: { name: city.name, display_name: city.display_name, country: city.country, lat: city.lat, lon: city.lon, bbox: city.bbox },
          venue_types: types,
          base,
        },
      });
      router.push(`/runs/${out.run_id}`);
    });

  const anyEntities = Object.values(entities).some((l) => l.length > 0);
  const pack = categories.find((c) => c.id === brand?.category) ?? categories[0];

  return (
    <div className="wrap stack" style={{ gap: 40 }}>
      <div className="stack-s">
        <ol className="row mono" aria-label="Steps" style={{ listStyle: "none", padding: 0, margin: 0, gap: 8 }}>
          {STEP_NAMES.map((s, i) => (
            <li key={s} className={`tag ${i + 1 === step ? "tag-ink" : i + 1 < step ? "" : "tag-mist"}`} aria-current={i + 1 === step ? "step" : undefined}>
              {String(i + 1).padStart(2, "0")} {s}
            </li>
          ))}
        </ol>
        <h1 className="display d-l">
          {step === 1 && "What do you make?"}
          {step === 2 && "Check your profile"}
          {step === 3 && "Who Qloo thinks you are"}
          {step === 4 && "Where do you sell?"}
        </h1>
      </div>

      {error && <Banner tone="warn">{error}</Banner>}

      {step === 1 && (
        <section className="card-lg stack" aria-labelledby="s1">
          <h2 id="s1" className="sr-only">Your brand</h2>
          <div className="row" role="radiogroup" aria-label="How to describe your brand">
            <label className="check">
              <input type="radio" name="mode" checked={mode === "url"} onChange={() => setMode("url")} /> Use my website
            </label>
            <label className="check">
              <input type="radio" name="mode" checked={mode === "describe"} onChange={() => setMode("describe")} /> Describe instead
            </label>
          </div>
          {mode === "url" && (
            <label className="field">
              <span>Website</span>
              <input className="input input-xl" type="url" inputMode="url" placeholder="https://yourbrand.com" value={url} onChange={(e) => setUrl(e.target.value)} />
            </label>
          )}
          <label className="field">
            <span>{mode === "url" ? "Short description (optional, used if the site can't be read)" : "Describe your brand and products"}</span>
            <textarea
              className="textarea"
              maxLength={1500}
              placeholder="We're a small Brooklyn maker of nitro cold brew and ginger kombucha for cafés and bars…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <div className="row between">
            <p className="small faint">We read up to 3 pages of your site. Your text is kept for 30 days.</p>
            <button className="btn" disabled={busy || (mode === "url" ? !url.trim() : description.trim().length < 20)} onClick={submitIntake}>
              {busy ? "Reading…" : "Continue"}
            </button>
          </div>
        </section>
      )}

      {step === 2 && intake && (
        <section className="stack" aria-labelledby="s2">
          <h2 id="s2" className="sr-only">Profile</h2>
          {intake.notice && <Banner>{intake.notice}</Banner>}
          {unsupported && (
            <ErrorPanel title="Probably not a fit">
              <p>{intake.unsupported_message}</p>
              <label className="check">
                <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />
                I sell to cafés, bars or shops whose guests are consumers. Continue anyway.
              </label>
            </ErrorPanel>
          )}
          <div className="grid-2">
            <div className="card stack">
              <span className="tag" style={{ alignSelf: "flex-start" }}>
                {intake.source === "llm" ? "Drafted by AI · please check" : "Fill in"}
              </span>
              <label className="field">
                <span>Brand name</span>
                <input className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span>One-liner</span>
                <input className="input" value={oneLiner} maxLength={140} onChange={(e) => setOneLiner(e.target.value)} />
              </label>
              <div className="grid-2">
                <label className="field">
                  <span>Price tier</span>
                  <select className="select" value={tier} onChange={(e) => setTier(e.target.value as typeof tier)}>
                    <option value="budget">Budget</option>
                    <option value="mid">Mid</option>
                    <option value="premium">Premium</option>
                    <option value="unknown">Not sure</option>
                  </select>
                </label>
                <label className="field">
                  <span>Sign emails as</span>
                  <input className="input" value={sender} maxLength={80} placeholder="Sam at Fieldnote" onChange={(e) => setSender(e.target.value)} />
                </label>
              </div>
              <label className="field">
                <span>Style words (comma separated)</span>
                <input className="input" value={style} onChange={(e) => setStyle(e.target.value)} />
              </label>
            </div>
            <div className="card stack">
              <div className="row between">
                <h3 className="h3">Products</h3>
                <span className="mono faint">{products.length}/5</span>
              </div>
              {products.map((p, i) => (
                <div key={i} className="row" style={{ alignItems: "flex-end", flexWrap: "nowrap" }}>
                  <label className="field" style={{ flex: 2 }}>
                    <span>Name</span>
                    <input className="input" value={p.name} maxLength={120} onChange={(e) => setProducts(products.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                  </label>
                  <label className="field" style={{ flex: 1.4 }}>
                    <span>Kind</span>
                    <input className="input" value={p.kind} maxLength={120} placeholder="cold brew" onChange={(e) => setProducts(products.map((x, j) => (j === i ? { ...x, kind: e.target.value } : x)))} />
                  </label>
                  <button className="btn-ghost btn-sm" aria-label={`Remove ${p.name || "product"}`} disabled={products.length === 1} onClick={() => setProducts(products.filter((_, j) => j !== i))}>
                    ×
                  </button>
                </div>
              ))}
              <button className="btn-ghost" disabled={products.length >= 5} onClick={() => setProducts([...products, { name: "", kind: "" }])}>
                + Add product
              </button>
            </div>
          </div>
          <div className="row between">
            <button className="link" onClick={() => setStep(1)}>← Back</button>
            <button className="btn" disabled={busy || (unsupported && !override)} onClick={saveProfile}>
              {busy ? "Asking Qloo…" : "Save and match with Qloo"}
            </button>
          </div>
        </section>
      )}

      {step === 3 && brand && (
        <section className="stack" aria-labelledby="s3">
          <h2 id="s3" className="sr-only">Qloo matches</h2>
          <p className="lead">
            Qloo ranks venues by the tastes of people who like these brands. Small brands use similar, better-known brands. Remove any that
            don&apos;t fit and add your own.
          </p>
          {brand.products.map((p) => {
            const r = resolution.find((x) => x.product_id === p.id);
            const list = entities[p.id] ?? [];
            return (
              <article key={p.id} className="card stack">
                <div className="row between">
                  <h3 className="h2" style={{ fontSize: 28 }}>{p.name}</h3>
                  <span className={`tag ${list.length ? "" : "tag-mist"}`}>
                    {list.length ? (list.some((e) => e.role === "self") ? "Qloo knows this" : "Using similar brands") : "No match yet"}
                  </span>
                </div>
                {r && !list.length && <p className="muted small">{r.message}</p>}
                <ul className="row" style={{ listStyle: "none", padding: 0, margin: 0 }} aria-label={`Qloo brands for ${p.name}`}>
                  {list.map((e) => (
                    <li key={e.entity_id} className="tag tag-mist" style={{ fontSize: 14, padding: "6px 8px 6px 14px" }}>
                      {e.name}
                      <button className="link" aria-label={`Remove ${e.name}`} onClick={() => putEntities(p.id, list.filter((x) => x.entity_id !== e.entity_id))}>
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
                {searchFor === p.id ? (
                  <div className="stack-s">
                    <div className="row" style={{ flexWrap: "nowrap" }}>
                      <label className="sr-only" htmlFor={`q-${p.id}`}>Search Qloo brands</label>
                      <input id={`q-${p.id}`} className="input" placeholder="Search Qloo, e.g. Blue Bottle Coffee" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchQloo()} />
                      <button className="btn" disabled={busy} onClick={searchQloo}>Search</button>
                    </div>
                    <ul className="stack-s" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {searchResults.map((x) => (
                        <li key={x.entity_id} className="row between card-mist" style={{ padding: "10px 16px" }}>
                          <span>{x.name} <span className="mono faint">popularity {Math.round(x.popularity * 100)}</span></span>
                          <button
                            className="btn-ghost btn-sm"
                            disabled={list.some((e) => e.entity_id === x.entity_id) || list.length >= 8}
                            onClick={() => putEntities(p.id, [...list, { entity_id: x.entity_id, name: x.name, type: x.type, role: "comparable", source_call_id: x.source_call_id }])}
                          >
                            Add
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <button className="link" style={{ alignSelf: "flex-start" }} onClick={() => { setSearchFor(p.id); setSearchQ(""); setSearchResults([]); }}>
                    + Add a brand from Qloo
                  </button>
                )}
              </article>
            );
          })}
          {!anyEntities && <Banner tone="warn">At least one product needs a Qloo match before we can rank venues.</Banner>}
          <div className="row between">
            <button className="link" onClick={() => setStep(2)}>← Back</button>
            <button className="btn" disabled={busy || !anyEntities} onClick={goCity}>Continue</button>
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="grid-2" aria-labelledby="s4">
          <h2 id="s4" className="sr-only">City and venue types</h2>
          <div className="card stack">
            <LocationPicker city={city} base={base} onCity={setCity} onBase={setBase} onError={placeError} />
          </div>
          <div className="card stack">
            <fieldset className="stack-s" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="label" style={{ marginBottom: 12 }}>Venue types</legend>
              {pack?.venue_types.map((v) => (
                <label key={v.id} className="choice">
                  <input
                    type="checkbox"
                    checked={types.includes(v.id)}
                    onChange={(e) => setTypes(e.target.checked ? [...types, v.id] : types.filter((t) => t !== v.id))}
                  />
                  <span className="stack-s"><strong>{v.label}</strong></span>
                </label>
              ))}
            </fieldset>
            <p className="small faint">Each type uses 2 Qloo calls plus one per product. Live runs are limited per day; the sample run is always free.</p>
            <div className="row between">
              <button className="link" onClick={() => setStep(3)}>← Back</button>
              <button className="btn" disabled={busy || !city || !types.length} onClick={startRun}>
                {busy ? "Starting…" : "Start run"}
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
