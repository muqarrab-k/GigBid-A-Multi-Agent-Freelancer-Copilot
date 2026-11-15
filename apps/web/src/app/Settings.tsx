import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Accounts } from "../components/Accounts";
import { Badge, Button, Card, Empty, ErrorBox, Field, inputClass, Loading, Page } from "../components/ui";
import { api, must, type Schemas } from "../lib/client";

type Search = Schemas["SavedSearch"];

function Memory() {
  const queries = useQueryClient();
  const memory = useQuery({ queryKey: ["memory"], queryFn: () => must(api.GET("/settings/memory")) });
  const forget = useMutation({
    mutationFn: (item: { kind: string; key: string }) =>
      must(api.DELETE("/settings/memory/{kind}/{key}", { params: { path: item } }).then((r) => ({ ...r, data: r.data ?? {} }))),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["memory"] }),
  });
  if (memory.isLoading) return <Loading />;
  if (memory.error) return <ErrorBox error={memory.error} />;
  if (!memory.data?.items.length) return <Empty>Nothing learned yet. Style rules appear after 3 consistent edits.</Empty>;
  return (
    <ul className="space-y-2">
      {memory.data.items.map((m) => (
        <li key={`${m.kind}:${m.key}`} className="rounded-md border border-slate-200 p-2 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span><Badge tone="indigo">{m.kind}</Badge> {m.rule}</span>
            <Button kind="secondary" onClick={() => forget.mutate({ kind: m.kind, key: m.key })} aria-label={`Forget ${m.rule}`}>
              Forget
            </Button>
          </div>
          <p className="mt-1 text-xs text-slate-600">Why: {m.why}</p>
          {m.source_edits?.length ? <p className="text-xs text-slate-500">From {m.source_edits.length} edits</p> : null}
        </li>
      ))}
    </ul>
  );
}

export function Settings() {
  const queries = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => must(api.GET("/settings")) });
  const [form, setForm] = useState<Schemas["SettingsOut"] | null>(null);
  useEffect(() => { if (settings.data) setForm(settings.data); }, [settings.data]);
  const save = useMutation({
    mutationFn: (body: Schemas["SettingsIn"]) => must(api.PUT("/settings", { body })),
    onSuccess: (data) => queries.setQueryData(["settings"], data),
  });

  if (settings.error) return <ErrorBox error={settings.error} />;
  if (settings.isLoading || !form) return <Loading />;
  const setSearch = (i: number, s: Search) => setForm({ ...form, saved_searches: form.saved_searches.map((x, j) => (j === i ? s : x)) });

  return (
    <Page title="Settings">
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Autonomy and budgets">
          <form className="space-y-3" onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ auto_skip_low_fit: form.auto_skip_low_fit, max_tokens_per_job: form.max_tokens_per_job,
              max_revisions: form.max_revisions, weekly_connects_budget: form.weekly_connects_budget, saved_searches: form.saved_searches });
          }}>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.auto_skip_low_fit}
                onChange={(e) => setForm({ ...form, auto_skip_low_fit: e.target.checked })} />
              Skip low-fit jobs automatically
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-500">
              <input type="checkbox" checked={false} disabled /> Send without my approval (never allowed)
            </label>
            <Field id="tokens" label="Token budget per job">
              <input id="tokens" type="number" min={1000} max={200000} value={form.max_tokens_per_job}
                onChange={(e) => setForm({ ...form, max_tokens_per_job: Number(e.target.value) })} className={inputClass} />
            </Field>
            <Field id="revisions" label="Critic revisions (0 to 3)">
              <input id="revisions" type="number" min={0} max={3} value={form.max_revisions}
                onChange={(e) => setForm({ ...form, max_revisions: Number(e.target.value) })} className={inputClass} />
            </Field>
            <Field id="weekly" label="Weekly Connects budget">
              <input id="weekly" type="number" min={0} max={500} value={form.weekly_connects_budget}
                onChange={(e) => setForm({ ...form, weekly_connects_budget: Number(e.target.value) })} className={inputClass} />
            </Field>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Saved searches</legend>
              {form.saved_searches.map((s, i) => (
                <div key={i} className="flex gap-2">
                  <label className="sr-only" htmlFor={`q-${i}`}>Keywords {i + 1}</label>
                  <input id={`q-${i}`} placeholder="keywords" value={s.q ?? ""} className={inputClass}
                    onChange={(e) => setSearch(i, { ...s, q: e.target.value || null })} />
                  <label className="sr-only" htmlFor={`skills-${i}`}>Skills {i + 1}</label>
                  <input id={`skills-${i}`} placeholder="skills, comma separated" value={(s.skills ?? []).join(", ")} className={inputClass}
                    onChange={(e) => setSearch(i, { ...s, skills: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
                  <Button kind="secondary" type="button" aria-label={`Remove search ${i + 1}`}
                    onClick={() => setForm({ ...form, saved_searches: form.saved_searches.filter((_, j) => j !== i) })}>×</Button>
                </div>
              ))}
              <Button kind="secondary" type="button"
                onClick={() => setForm({ ...form, saved_searches: [...form.saved_searches, { q: "", skills: [], limit: 20 }] })}>
                Add search
              </Button>
            </fieldset>
            <Button type="submit" disabled={save.isPending}>Save settings</Button>
            {save.isSuccess && <p role="status" className="text-sm text-green-700">Saved.</p>}
            {save.error && <ErrorBox error={save.error} />}
          </form>
        </Card>
        <div className="space-y-4">
          <Card title="Connected accounts"><Accounts /></Card>
          <Card title="What GigBid learned"><Memory /></Card>
        </div>
      </div>
    </Page>
  );
}
