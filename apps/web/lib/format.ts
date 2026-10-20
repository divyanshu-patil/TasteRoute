export const pct = (v: number) => Math.round(v * 100);

/** Lift against mass-market taste at the same venues (runs scored since D-23), else against plain popularity. */
export function liftText(lift: number, massMarket = false): string {
  const n = pct(lift);
  const vs = massMarket ? "vs mass-market taste" : "vs typical";
  return n > 0 ? `+${n} ${vs}` : n === 0 ? (massMarket ? "level with mass-market taste" : "typical") : `${n} ${vs}`;
}

export const LIFT_TIP_MASS = "How much more this venue's guests lean toward brands like yours than toward mass-market brands (Qloo)";

/** Chips for buyability flags (RNK-09); scores are never changed by them. */
export const FLAG_CHIP: Record<string, string> = {
  chain: "Chain",
  signal_brand_venue: "One of the brands you resemble",
  maker_competitor: "Makes what you make",
  check_licence: "Check licence · our inference",
  rising: "Rising (Qloo)",
};

export const CONFIDENCE: Record<string, string> = {
  high: "Top 20% taste fit, clearly above a typical venue, backed by at least two of your reference brands (or by your own brand when Qloo knows it and it is the only one).",
  medium: "Top 40% taste fit and above a typical venue.",
  low: "Weaker or less certain taste fit. Worth a look, not a priority.",
};

export const FIT_LABEL: Record<string, string> = {
  clear: "clear lead",
  close: "close call",
  tie: "tie",
  single_product: "only product",
  unscored: "not scored",
};

export const CONTACT_STATUS: Record<string, string> = {
  found: "Email found",
  none: "No public business email found",
  limit_reached: "Not checked (limit reached)",
  suppressed: "On your do-not-contact list",
  skipped_social: "Only a social page listed",
  not_checked: "Not checked yet",
};

export const STEP_LABEL: Record<string, string> = {
  resolve_entities: "Match your products to Qloo brands",
  rank_venues: "Rank venues by taste fit vs a popularity baseline",
  match_products: "Pick the best product for each venue",
  attach_evidence: "Attach Qloo evidence and reasons",
  find_contacts: "Find public business contacts",
  draft_pitches: "Draft grounded pitches",
  finish_phase: "Wrap up",
};

export const SCOUT_STEPS = ["resolve_entities", "rank_venues", "match_products", "attach_evidence"];
export const OUTREACH_STEPS = ["find_contacts", "draft_pitches"];
export const DRAFT_RESULT: Record<string, string> = {
  llm: "AI draft written",
  template: "Template draft",
  skipped_approved: "Approved draft kept",
  suppressed: "On your do-not-contact list",
};
/** What the live panel says while a step works on one venue. */
export const STEP_DOING: Record<string, string> = { find_contacts: "Checking", draft_pitches: "Drafting for" };

/** Venue types come from the category pack; the API only returns ids on rows. */
export const venueTypeLabel = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);

type LatLon = { lat: number; lon: number };
/** Straight-line kilometres between two points (haversine). */
export function km(a: LatLon, b: LatLon): number {
  const r = Math.PI / 180;
  const h = Math.sin(((b.lat - a.lat) * r) / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}
export const kmText = (d: number) => `${d < 10 ? d.toFixed(1) : Math.round(d)} km`;

export function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
