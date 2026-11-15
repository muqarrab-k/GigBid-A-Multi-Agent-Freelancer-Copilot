import { useQuery } from "@tanstack/react-query";
import { Card, Empty, ErrorBox, Loading, Page } from "../components/ui";
import { api, must } from "../lib/client";

function Bar({ value, max, label }: { value: number; max: number; label: string }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-28 shrink-0 truncate">{label}</span>
      <div className="h-3 flex-1 rounded bg-slate-100" role="img" aria-label={`${label}: ${value}`}>
        <div className="h-3 rounded bg-indigo-500" style={{ width: `${width}%` }} />
      </div>
      <span className="w-12 text-right tabular-nums">{value}</span>
    </div>
  );
}

const pct = (v?: number | null) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export function Analytics() {
  const data = useQuery({ queryKey: ["analytics"], queryFn: () => must(api.GET("/analytics")) });
  if (data.isLoading) return <Loading what="Loading analytics" />;
  if (data.error) return <ErrorBox error={data.error} />;
  const a = data.data!;
  const connects = Object.entries(a.connects_by_outcome);
  const maxConnects = Math.max(0, ...connects.map(([, v]) => v));
  const maxReason = Math.max(0, ...a.rejection_reasons.map(([, n]) => n));

  return (
    <Page title="Analytics">
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Reply and hire rate by category">
          {a.by_category.length ? (
            <table className="w-full text-left text-sm">
              <thead><tr className="border-b"><th className="py-1">Category</th><th>Sent</th><th>Reply</th><th>Hire</th></tr></thead>
              <tbody>{a.by_category.map((c) => (
                <tr key={c.category} className="border-b"><td className="py-1">{c.category}</td><td>{c.submitted}</td>
                  <td>{pct(c.reply_rate)}</td><td>{pct(c.hire_rate)}</td></tr>
              ))}</tbody>
            </table>
          ) : <Empty>No submitted proposals yet.</Empty>}
        </Card>
        <Card title="Connects spent by outcome">
          {connects.length ? <div className="space-y-1">{connects.map(([k, v]) => <Bar key={k} label={k} value={v} max={maxConnects} />)}</div>
            : <Empty>No Connects spent yet.</Empty>}
        </Card>
        <Card title="Cost and latency per proposal">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt>Proposals drafted</dt><dd>{a.per_proposal.proposals ?? 0}</dd></div>
            <div className="flex justify-between"><dt>Mean model cost</dt><dd>{a.per_proposal.usd_mean != null ? `$${a.per_proposal.usd_mean}` : "—"}</dd></div>
            <div className="flex justify-between"><dt>Mean model time</dt><dd>{a.per_proposal.llm_latency_s_mean != null ? `${a.per_proposal.llm_latency_s_mean} s` : "—"}</dd></div>
          </dl>
        </Card>
        <Card title="Top rejection reasons">
          {a.rejection_reasons.length ? <div className="space-y-1">{a.rejection_reasons.map(([r, n]) => <Bar key={r} label={r} value={n} max={maxReason} />)}</div>
            : <Empty>Nothing rejected or blocked yet.</Empty>}
        </Card>
      </div>
      <Card title="Evaluation results files" className="mt-4">
        <ul className="space-y-1 text-sm">
          {a.eval_files.map((f) => (
            <li key={String(f.file)}><code>{String(f.file)}</code>: {String(f.proposals)} proposals, statuses {JSON.stringify(f.statuses)}</li>
          ))}
        </ul>
      </Card>
    </Page>
  );
}
