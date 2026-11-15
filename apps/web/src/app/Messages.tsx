import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApprovalPanel } from "../components/ApprovalPanel";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Page } from "../components/ui";
import { api, must } from "../lib/client";

type Pending = { reply: string; flags: string[]; intent: { intent: string; summary: string }; slots: { start: string; end: string }[] };

function Thread({ threadId }: { threadId: string }) {
  const queries = useQueryClient();
  const detail = useQuery({
    queryKey: ["thread", threadId],
    queryFn: () => must(api.GET("/messages/{thread_id}", { params: { path: { thread_id: threadId } } })),
  });
  const draft = useMutation({
    mutationFn: () => must(api.POST("/messages/{thread_id}/draft", { params: { path: { thread_id: threadId } } })),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
  if (detail.isLoading) return <Loading what="Loading messages" />;
  if (detail.error) return <ErrorBox error={detail.error} />;
  const d = detail.data!;
  const pending = d.pending as unknown as Pending | null;

  return (
    <div className="space-y-4">
      <Card title="Conversation">
        <ol className="space-y-2">
          {d.messages.map((m) => (
            <li key={m.message_id} className={`rounded-md p-2 text-sm ${m.sender === "client" ? "bg-slate-100" : "bg-indigo-50"}`}>
              <span className="text-xs font-semibold">{m.sender}{m.untrusted && " (untrusted)"}</span>
              <p className="whitespace-pre-wrap">{m.text}</p>
            </li>
          ))}
        </ol>
      </Card>
      {pending ? (
        <Card title="Suggested reply">
          <p className="mb-2 text-sm">
            <Badge tone={pending.intent.intent === "scam_signal" ? "red" : "indigo"}>{pending.intent.intent}</Badge>{" "}
            {pending.flags.map((f) => <Badge key={f} tone="red">{f}</Badge>)}
          </p>
          <p className="mb-3 whitespace-pre-wrap rounded-md border border-slate-200 p-2 text-sm">{pending.reply}</p>
          <ApprovalPanel threadId={d.conversation_id} text={pending.reply}
            onDone={() => queries.invalidateQueries({ queryKey: ["thread", threadId] })} />
        </Card>
      ) : (
        <div className="flex items-center gap-3">
          <Button onClick={() => draft.mutate()} disabled={draft.isPending}>{draft.isPending ? "Drafting…" : "Suggest a reply"}</Button>
          {d.draft_status && <span className="text-sm text-slate-600">Last draft: {d.draft_status}</span>}
        </div>
      )}
      {draft.error && <ErrorBox error={draft.error} />}
      {draft.data?.errors?.map((e) => <p key={e} className="text-sm text-red-700">{e}</p>)}
    </div>
  );
}

export function Messages() {
  const threads = useQuery({ queryKey: ["threads"], queryFn: () => must(api.GET("/messages")) });
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Page title="Messages">
      {threads.isLoading && <Loading />}
      {threads.error && <ErrorBox error={threads.error} />}
      {threads.data?.items.length === 0 && <Empty>No client has written yet. Replies appear after clients view your proposals.</Empty>}
      <div className="grid gap-4 md:grid-cols-3">
        <ul className="space-y-2">
          {threads.data?.items.map((t) => (
            <li key={t.thread_id}>
              <button type="button" onClick={() => setOpen(t.thread_id)} aria-pressed={open === t.thread_id}
                className={`w-full rounded-md border p-2 text-left text-sm ${open === t.thread_id ? "border-indigo-500 bg-indigo-50" : "border-slate-200 bg-white"}`}>
                <span className="font-medium">{t.job_id ?? t.thread_id}</span>
                {t.draft_status && <span className="block text-xs text-slate-500">{t.draft_status}</span>}
              </button>
            </li>
          ))}
        </ul>
        <div className="md:col-span-2">{open ? <Thread threadId={open} /> : threads.data?.items.length ? <Empty>Pick a thread.</Empty> : null}</div>
      </div>
    </Page>
  );
}
