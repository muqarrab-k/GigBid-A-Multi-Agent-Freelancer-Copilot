import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, Empty, ErrorBox, Loading, money, Page } from "../components/ui";
import { api, must } from "../lib/client";

type Row = { requirement: string; strength: string; evidence_ids: string[]; note?: string };

export function JobDetail() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const detail = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => must(api.GET("/jobs/{job_id}", { params: { path: { job_id: jobId } } })),
  });
  const start = useMutation({
    mutationFn: () => must(api.POST("/runs", { body: { job_id: jobId } })),
    onSuccess: (run) => navigate(`/runs/${encodeURIComponent(run.thread_id)}`),
  });

  if (detail.isLoading) return <Loading what="Loading job" />;
  if (detail.error) return <ErrorBox error={detail.error} />;
  const d = detail.data!;
  const job = d.job as Record<string, unknown>;
  const spec = d.job_spec as Record<string, unknown> | null;
  const risk = d.risk_report as { score: number; flags: string[]; explanation: string; signals?: string[] } | null;
  const price = d.price as { amount: number; billing: string; connects_cost: number } | null;
  const matrix = d.evidence_matrix as Row[];

  return (
    <Page title={String(job.title ?? jobId)} actions={
      d.thread_id
        ? <Link className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white" to={`/runs/${encodeURIComponent(d.thread_id)}`}>View run</Link>
        : <Button onClick={() => start.mutate()} disabled={start.isPending}>Start bid run</Button>
    }>
      {start.error && <ErrorBox error={start.error} />}
      <p className="mb-4 text-sm text-slate-600">Status: {d.status ?? "not analysed yet"}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Job post (untrusted text)">
          <p className="whitespace-pre-wrap text-sm">{String(job.description ?? "")}</p>
        </Card>
        <Card title="JobSpec">
          {spec ? (
            <dl className="space-y-1 text-sm">
              {(["deliverables", "requirements", "required_skills", "screening_questions", "hidden_needs"] as const).map((k) => (
                <div key={k}><dt className="font-medium">{k.replace("_", " ")}</dt>
                  <dd className="text-slate-600">{((spec[k] as string[]) ?? []).join("; ") || "—"}</dd></div>
              ))}
            </dl>
          ) : <Empty>Start a bid run to analyse this job.</Empty>}
        </Card>
        <Card title="Risk report">
          {risk ? <>
            <p className="text-sm">Score {risk.score.toFixed(2)} {risk.flags.map((f) => <Badge key={f} tone="red">{f}</Badge>)}</p>
            <p className="mt-1 text-sm text-slate-600">{risk.explanation}</p>
          </> : <Empty>No risk report yet.</Empty>}
        </Card>
        <Card title="Price and decision">
          <p className="text-sm">{price ? `${money(price.amount, price.billing)} · ${price.connects_cost} Connects` : "No price yet."}</p>
          {d.price_rationale && <p className="mt-1 text-sm text-slate-600">{d.price_rationale}</p>}
          <ul className="mt-2 list-disc pl-5 text-sm">{d.decision_reasons?.map((r) => <li key={r}>{r}</li>)}</ul>
        </Card>
      </div>
      <Card title="Requirement to evidence" className="mt-4">
        {matrix?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr className="border-b"><th className="py-1 pr-2">Requirement</th><th className="pr-2">Match</th><th>Evidence</th></tr></thead>
              <tbody>
                {matrix.map((r) => (
                  <tr key={r.requirement} className="border-b align-top">
                    <td className="py-1 pr-2">{r.requirement}</td>
                    <td className="pr-2"><Badge tone={r.strength === "strong" ? "green" : r.strength === "partial" ? "amber" : "red"}>{r.strength}</Badge></td>
                    <td>{r.evidence_ids.length ? r.evidence_ids.map((e) => <code key={e} className="mr-2 block text-xs">{e}</code>) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty>No matrix yet.</Empty>}
      </Card>
    </Page>
  );
}
