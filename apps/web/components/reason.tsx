import { SourceChip } from "./ui";

/** Reasons are template text with "(Qloo)" and "(our inference)" markers; render the markers as source chips. */
export function ReasonText({ text, traceHref }: { text: string; traceHref?: string }) {
  const parts = text.split(/\s*\((Qloo|our inference)\)(\.?)/);
  const out = [];
  for (let i = 0; i < parts.length; i += 3) {
    const sentence = parts[i]?.trim();
    const source = parts[i + 1];
    if (!sentence) continue;
    out.push(
      <span key={i}>
        {sentence}
        {parts[i + 2]}
        {source && <> <SourceChip kind={source === "Qloo" ? "qloo" : "inference"} href={traceHref} /></>}{" "}
      </span>,
    );
  }
  return <>{out}</>;
}
