import type { ReactNode } from "react";

// ponytail: the markdown an LLM answer uses (headings, lists, bold, italic, code, links); add a library if tables are needed
const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

function inline(text: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((t, i) => {
    if (t.startsWith("**") && t.endsWith("**") && t.length > 4) return <strong key={i}>{t.slice(2, -2)}</strong>;
    if (t.startsWith("`") && t.endsWith("`") && t.length > 2) return <code key={i}>{t.slice(1, -1)}</code>;
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(t);
    if (link) {
      const href = link[2]!;
      // Only site paths and web links; never javascript: or data:
      return /^(\/|https?:\/\/)/.test(href) ? <a key={i} className="link" href={href}>{link[1]}</a> : link[1];
    }
    if (/^(\*[^*].*\*|_[^_].*_)$/.test(t)) return <em key={i}>{t.slice(1, -1)}</em>;
    return t;
  });
}

/** Renders a short markdown answer as React elements (no HTML injection). */
export function Markdown({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let para: string[] = [];
  const flush = () => {
    if (para.length) out.push(<p key={out.length}>{inline(para.join(" "))}</p>);
    para = [];
    if (list) {
      const items = list.items.map((x, i) => <li key={i}>{inline(x)}</li>);
      out.push(list.ordered ? <ol key={out.length}>{items}</ol> : <ul key={out.length}>{items}</ul>);
    }
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    const num = /^\d+[.)]\s+(.*)$/.exec(line);
    const head = /^#{1,6}\s+(.*)$/.exec(line);
    if (!line) flush();
    else if (head) { flush(); out.push(<p key={out.length}><strong>{inline(head[1]!)}</strong></p>); }
    else if (bullet || num) {
      const ordered = !!num;
      if (para.length || (list && list.ordered !== ordered)) flush();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? num)![1]!);
    } else if (list) list.items[list.items.length - 1] += ` ${line}`;
    else para.push(line);
  }
  flush();
  return <div className="md">{out}</div>;
}
