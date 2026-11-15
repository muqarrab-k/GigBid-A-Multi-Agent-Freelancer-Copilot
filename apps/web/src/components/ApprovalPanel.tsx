import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, must, type Schemas } from "../lib/client";
import { Button, ErrorBox, inputClass } from "./ui";

type Result = Schemas["ApprovalResult"];

// approve, edit or reject
export function ApprovalPanel({ threadId, text, onDone }: { threadId: string; text: string; onDone?: (r: Result) => void }) {
  const queries = useQueryClient();
  const [mode, setMode] = useState<"idle" | "edit" | "reject">("idle");
  const [edited, setEdited] = useState(text);
  const [reason, setReason] = useState("");
  const answer = useMutation({
    mutationFn: (body: Schemas["ApprovalIn"]) =>
      must(api.POST("/approvals/{thread_id}", { params: { path: { thread_id: threadId } }, body })),
    onSuccess: (result) => {
      setMode("idle");
      queries.invalidateQueries();
      onDone?.(result);
    },
  });
  const busy = answer.isPending;
  return (
    <div className="space-y-3">
      {mode === "edit" && (
        <div>
          <label htmlFor="edit-text" className="mb-1 block text-sm font-medium">Edited text</label>
          <textarea id="edit-text" rows={10} value={edited} onChange={(e) => setEdited(e.target.value)} className={inputClass} />
        </div>
      )}
      {mode === "reject" && (
        <div>
          <label htmlFor="reject-reason" className="mb-1 block text-sm font-medium">Reason</label>
          <input id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} className={inputClass} />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {mode === "idle" && <>
          <Button disabled={busy} onClick={() => answer.mutate({ action: "approve" })}>Approve and send</Button>
          <Button kind="secondary" disabled={busy} onClick={() => setMode("edit")}>Edit</Button>
          <Button kind="danger" disabled={busy} onClick={() => setMode("reject")}>Reject</Button>
        </>}
        {mode === "edit" && <>
          <Button disabled={busy || !edited.trim()} onClick={() => answer.mutate({ action: "edit", edited_text: edited })}>
            Save edit and recheck
          </Button>
          <Button kind="secondary" onClick={() => setMode("idle")}>Cancel</Button>
        </>}
        {mode === "reject" && <>
          <Button kind="danger" disabled={busy || !reason.trim()} onClick={() => answer.mutate({ action: "reject", reason })}>
            Confirm reject
          </Button>
          <Button kind="secondary" onClick={() => setMode("idle")}>Cancel</Button>
        </>}
      </div>
      {busy && <p role="status" className="text-sm text-slate-500">Resuming the thread…</p>}
      {answer.error && <ErrorBox error={answer.error} />}
    </div>
  );
}
