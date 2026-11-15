import { useId, useState } from "react";

export type ClaimRow = { claim: string; evidence_ids: string[]; label: string; evidence: Record<string, string> };

// claim with evidence popover
export function EvidenceHover({ claim }: { claim: ClaimRow }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const tone = claim.label === "supported" ? "decoration-green-500" : "decoration-amber-500";
  return (
    <span className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-describedby={id} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
        className={`text-left underline decoration-2 underline-offset-4 ${tone}`}>
        {claim.claim}
      </button>
      <span id={id} role="tooltip" hidden={!open}
        className="pointer-events-none absolute left-0 top-full z-20 mt-1 w-80 max-w-[80vw] rounded-md border border-slate-200 bg-white p-3 text-xs shadow-lg">
        <span className="mb-1 block font-semibold">{claim.label}</span>
        {claim.evidence_ids.map((eid) => (
          <span key={eid} className="mb-2 block">
            <code className="text-indigo-700">{eid}</code>
            <span className="block text-slate-600">{claim.evidence[eid] || "(no text)"}</span>
          </span>
        ))}
      </span>
    </span>
  );
}

// letter with claims linked
export function LetterWithClaims({ text, claims }: { text: string; claims: ClaimRow[] }) {
  const parts: (string | ClaimRow)[] = [];
  let rest = text;
  for (const claim of claims) {
    const at = rest.indexOf(claim.claim);
    if (at < 0) continue;
    parts.push(rest.slice(0, at), claim);
    rest = rest.slice(at + claim.claim.length);
  }
  parts.push(rest);
  return (
    <div className="whitespace-pre-wrap leading-relaxed" data-testid="letter">
      {parts.map((p, i) => (typeof p === "string" ? <span key={i}>{p}</span> : <EvidenceHover key={i} claim={p} />))}
    </div>
  );
}
