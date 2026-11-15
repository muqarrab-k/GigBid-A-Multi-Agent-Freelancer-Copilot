import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading, money, Page } from "../components/ui";
import { api, must } from "../lib/client";

const COLUMNS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"] as const;

// gigsim status to column
function column(status: string): string {
  if (status === "draft") return "drafted";
  if (status === "ignored") return "lost";
  return status;
}

export function Pipeline() {
  const pipeline = useQuery({ queryKey: ["pipeline"], queryFn: () => must(api.GET("/pipeline")) });
  const pending = useQuery({ queryKey: ["approvals"], queryFn: () => must(api.GET("/approvals")) });
  if (pipeline.isLoading) return <Loading what="Loading pipeline" />;
  if (pipeline.error) return <ErrorBox error={pipeline.error} />;
  const proposals = pipeline.data?.proposals ?? [];
  const drafts = (pending.data?.items ?? []).filter((i) => i.kind === "bid");

  return (
    <Page title="Pipeline">
      {proposals.length === 0 && drafts.length === 0 && <Empty>No proposals yet.</Empty>}
      <div className="grid grid-flow-col auto-cols-[minmax(11rem,1fr)] gap-3 overflow-x-auto pb-2">
        {COLUMNS.map((col) => {
          const cards = proposals.filter((p) => column(p.status) === col);
          const extra = col === "drafted" ? drafts : [];
          return (
            <section key={col} aria-label={col} className="rounded-lg bg-slate-100 p-2">
              <h2 className="mb-2 text-sm font-semibold capitalize">{col} ({cards.length + extra.length})</h2>
              <ul className="space-y-2">
                {extra.map((d) => (
                  <li key={d.thread_id} className="rounded-md bg-white p-2 text-xs shadow-sm">
                    <Link className="text-indigo-700 underline" to={`/approvals/${encodeURIComponent(d.thread_id)}`}>{d.thread_id}</Link>
                    <p className="text-slate-500">waiting for approval</p>
                  </li>
                ))}
                {cards.map((p) => (
                  <li key={p.proposal_id} className="rounded-md bg-white p-2 text-xs shadow-sm">
                    <Link className="font-medium text-indigo-700 underline" to={`/jobs/${p.job_id}`}>{p.job_id}</Link>
                    <p className="text-slate-500">{money(p.bid_amount)} · {p.connects_cost ?? "—"} Connects · {p.status}</p>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </Page>
  );
}
