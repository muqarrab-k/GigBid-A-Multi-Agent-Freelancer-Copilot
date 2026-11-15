import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { actionTone, Badge, Button, Empty, ErrorBox, inputClass, Loading, money, Page } from "../components/ui";
import { api, must } from "../lib/client";

export function Inbox() {
  const queries = useQueryClient();
  const [text, setText] = useState("");
  const [action, setAction] = useState("all");
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => must(api.GET("/jobs")) });
  const scout = useMutation({
    mutationFn: () => must(api.POST("/jobs/scout", { params: { query: { analyse: false } } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const skip = useMutation({
    mutationFn: (jobId: string) => must(api.POST("/jobs/{job_id}/skip", { params: { path: { job_id: jobId } } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const rows = (jobs.data?.items ?? []).filter((j) =>
    j.title.toLowerCase().includes(text.toLowerCase()) &&
    (action === "all" || (action === "new" ? !j.recommended_action : j.recommended_action === action)));

  return (
    <Page title="Job inbox" actions={
      <Button onClick={() => scout.mutate()} disabled={scout.isPending}>{scout.isPending ? "Scouting…" : "Run scout"}</Button>
    }>
      {scout.data && <p role="status" className="mb-3 text-sm text-slate-600">{scout.data.found} new jobs found.</p>}
      {scout.error && <ErrorBox error={scout.error} />}
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="sr-only" htmlFor="filter">Filter by title</label>
        <input id="filter" placeholder="Filter by title" value={text} onChange={(e) => setText(e.target.value)}
          className={`${inputClass} max-w-xs`} />
        <label className="sr-only" htmlFor="action">Recommended action</label>
        <select id="action" value={action} onChange={(e) => setAction(e.target.value)} className={`${inputClass} max-w-[12rem]`}>
          <option value="all">All actions</option>
          <option value="bid">Bid</option>
          <option value="watch">Watch</option>
          <option value="skip">Skip</option>
          <option value="new">Not analysed</option>
        </select>
      </div>
      {jobs.isLoading && <Loading what="Loading jobs" />}
      {jobs.error && <ErrorBox error={jobs.error} />}
      {jobs.data && rows.length === 0 && <Empty>No jobs yet. Press "Run scout" to search your saved searches.</Empty>}
      <ul className="space-y-2">
        {rows.map((job) => (
          <li key={job.job_id} className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <Link to={`/jobs/${job.job_id}`} className="font-medium text-indigo-700 hover:underline">{job.title || job.job_id}</Link>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-slate-600">
                <span>fit {job.fit_score !== null && job.fit_score !== undefined ? job.fit_score.toFixed(2) : "—"}</span>
                <span>· {money(job.price, job.billing)}</span>
                <span>· {job.connects_cost ?? "—"} Connects</span>
                {job.recommended_action && <Badge tone={actionTone(job.recommended_action)}>{job.recommended_action}</Badge>}
                {(job.risk_badges ?? []).map((b) => <Badge key={b} tone="red">{b}</Badge>)}
                {job.status && <Badge>{job.status}</Badge>}
              </div>
            </div>
            <div className="flex gap-2">
              <Link to={`/jobs/${job.job_id}`} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">Open</Link>
              <Button kind="secondary" onClick={() => skip.mutate(job.job_id)} aria-label={`Skip ${job.title}`}>Skip</Button>
            </div>
          </li>
        ))}
      </ul>
    </Page>
  );
}
