import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Card, ErrorBox, Page } from "../components/ui";
import { api, getToken, must } from "../lib/client";

type RunEvent = { event: string; node?: string; status?: string; keys?: string[]; errors?: string[]; trace_id?: string; detail?: string };

// read sse with auth
async function follow(threadId: string, onEvent: (e: RunEvent) => void, signal: AbortSignal): Promise<void> {
  const res = await fetch(`/runs/${encodeURIComponent(threadId)}/events`, {
    headers: { Authorization: `Bearer ${getToken()}`, Accept: "text/event-stream" }, signal,
  });
  if (!res.ok || !res.body) throw new Error(`stream failed (${res.status})`);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

export function RunViewer() {
  const { threadId = "" } = useParams();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState<unknown>(null);
  const run = useQuery({
    queryKey: ["run", threadId, events.length],
    queryFn: () => must(api.GET("/runs/{thread_id}", { params: { path: { thread_id: threadId } } })),
  });

  useEffect(() => {
    const stop = new AbortController();
    setEvents([]);
    follow(threadId, (e) => setEvents((all) => [...all, e]), stop.signal).catch((err) => {
      if (!stop.signal.aborted) setError(err);
    });
    return () => stop.abort();
  }, [threadId]);

  const done = events.find((e) => e.event === "done");
  const waiting = events.some((e) => e.event === "approval_required") || run.data?.status === "awaiting_approval";

  return (
    <Page title="Agent run">
      <p className="mb-4 text-sm text-slate-600">
        Thread <code>{threadId}</code> · trace id <code data-testid="trace-id">{run.data?.trace_id ?? done?.trace_id ?? "…"}</code>
      </p>
      {error !== null && <ErrorBox error={error} />}
      <Card title="Timeline">
        <ol aria-live="polite" className="space-y-2">
          {events.map((e, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 border-l-2 border-indigo-300 pl-3 text-sm">
              <span className="font-medium">{e.node ?? e.event}</span>
              {e.status && <Badge>{e.status}</Badge>}
              {e.event === "approval_required" && <Badge tone="amber">waiting for you</Badge>}
              {e.keys && <span className="text-xs text-slate-500">{e.keys.join(", ")}</span>}
              {e.errors?.map((x) => <span key={x} className="text-xs text-red-700">{x}</span>)}
              {e.detail && <span className="text-xs text-red-700">{e.detail}</span>}
            </li>
          ))}
          {!done && <li role="status" className="pl-3 text-sm text-slate-500">Running…</li>}
        </ol>
      </Card>
      {done && (
        <p className="mt-4 text-sm">Finished with status <Badge tone="indigo">{done.status ?? run.data?.status}</Badge></p>
      )}
      {waiting && (
        <Link to={`/approvals/${encodeURIComponent(threadId)}`}
          className="mt-4 inline-block rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white">
          Review the proposal
        </Link>
      )}
    </Page>
  );
}
