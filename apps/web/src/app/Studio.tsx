import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApprovalPanel } from "../components/ApprovalPanel";
import { LetterWithClaims, type ClaimRow } from "../components/EvidenceHover";
import { Badge, Card, Empty, ErrorBox, Loading, money, Page } from "../components/ui";
import { api, must, type Schemas } from "../lib/client";

type BidPayload = {
  job_id: string;
  draft: { cover_letter: string; screening_answers: string[]; revision: number };
  claims: ClaimRow[];
  price: { amount: number; billing: string };
  preview: { submit_proposal: { connects_cost: number; balance_before: number | null; balance_after: number | null } };
  notes: {
    critic: { verdict: string; reasons: string[] }[];
    compliance: { verdict: string; violations: string[] } | null;
    verifier: { removed: string[] } | null;
    other: string[];
  };
};

export function Approvals() {
  const pending = useQuery({ queryKey: ["approvals"], queryFn: () => must(api.GET("/approvals")) });
  return (
    <Page title="Waiting for your approval">
      {pending.isLoading && <Loading />}
      {pending.error && <ErrorBox error={pending.error} />}
      {pending.data?.items.length === 0 && <Empty>Nothing is waiting. Start a bid run from a job.</Empty>}
      <ul className="space-y-2">
        {pending.data?.items.map((item) => (
          <li key={item.thread_id} className="rounded-lg border border-slate-200 bg-white p-3">
            <Badge tone={item.kind === "bid" ? "indigo" : "amber"}>{item.kind === "bid" ? "proposal" : "message"}</Badge>{" "}
            <Link className="font-medium text-indigo-700 hover:underline"
              to={item.kind === "bid" ? `/approvals/${encodeURIComponent(item.thread_id)}` : "/messages"}>
              {item.thread_id}
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function Studio() {
  const { threadId = "" } = useParams();
  const [result, setResult] = useState<Schemas["ApprovalResult"] | null>(null);
  // read from the checkpointer
  const pending = useQuery({ queryKey: ["approvals"], queryFn: () => must(api.GET("/approvals")) });
  if (pending.isLoading) return <Loading what="Loading draft" />;
  if (pending.error) return <ErrorBox error={pending.error} />;
  const item = pending.data?.items.find((i) => i.thread_id === threadId);

  if (!item) {
    return (
      <Page title="Proposal studio">
        {result ? (
          <Card title="Result">
            <p>Status <Badge tone="indigo">{result.status}</Badge></p>
            {result.submission && <pre className="mt-2 overflow-x-auto text-xs">{JSON.stringify(result.submission, null, 2)}</pre>}
            {result.errors?.map((e) => <p key={e} className="text-sm text-red-700">{e}</p>)}
          </Card>
        ) : <Empty>No draft is waiting on this thread.</Empty>}
        <Link to="/approvals" className="mt-4 inline-block text-indigo-700 underline">Back to approvals</Link>
      </Page>
    );
  }

  const p = item.payload as unknown as BidPayload;
  const sub = p.preview.submit_proposal;
  const critic = p.notes.critic.at(-1);
  return (
    <Page title="Proposal studio">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title={`Draft (revision ${p.draft.revision})`}>
            <p className="mb-2 text-xs text-slate-500">Underlined sentences are claims: hover or focus to see their evidence.</p>
            <LetterWithClaims text={p.draft.cover_letter} claims={p.claims} />
            {p.draft.screening_answers.length > 0 && (
              <ol className="mt-3 list-decimal pl-5 text-sm">{p.draft.screening_answers.map((a, i) => <li key={i}>{a}</li>)}</ol>
            )}
          </Card>
          <Card title="Your decision">
            <ApprovalPanel threadId={threadId} text={p.draft.cover_letter} onDone={setResult} />
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="What will be sent">
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between"><dt>Bid</dt><dd>{money(p.price.amount, p.price.billing)}</dd></div>
              <div className="flex justify-between"><dt>Connects cost</dt><dd>{sub.connects_cost}</dd></div>
              <div className="flex justify-between"><dt>Balance before</dt><dd>{sub.balance_before ?? "—"}</dd></div>
              <div className="flex justify-between font-medium"><dt>Balance after</dt><dd data-testid="balance-after">{sub.balance_after ?? "—"}</dd></div>
            </dl>
            <p className="mt-2 text-xs text-slate-500">Dry run only; nothing is sent until you approve.</p>
          </Card>
          <Card title="Critic">
            {critic ? <>
              <Badge tone={critic.verdict === "pass" ? "green" : "amber"}>{critic.verdict}</Badge>
              <ul className="mt-1 list-disc pl-5 text-sm">{critic.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </> : <p className="text-sm text-slate-500">No critique.</p>}
          </Card>
          <Card title="Compliance">
            <Badge tone={p.notes.compliance?.verdict === "allowed" ? "green" : "red"}>{p.notes.compliance?.verdict ?? "—"}</Badge>
            <ul className="mt-1 list-disc pl-5 text-sm">{p.notes.compliance?.violations.map((v) => <li key={v}>{v}</li>)}</ul>
            {(p.notes.verifier?.removed.length ?? 0) > 0 && (
              <p className="mt-2 text-xs text-slate-600">Removed as unsupported: {p.notes.verifier!.removed.join(" · ")}</p>
            )}
            {p.notes.other.map((n) => <p key={n} className="mt-1 text-xs text-amber-700">{n}</p>)}
          </Card>
        </div>
      </div>
    </Page>
  );
}
