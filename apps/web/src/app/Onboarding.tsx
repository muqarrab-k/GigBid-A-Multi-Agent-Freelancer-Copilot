import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Accounts } from "../components/Accounts";
import { Badge, Button, Card, ErrorBox, Field, inputClass, Loading, Page } from "../components/ui";
import { api, must } from "../lib/client";

export function Onboarding() {
  const navigate = useNavigate();
  const me = useQuery({ queryKey: ["me"], queryFn: () => must(api.GET("/auth/me")) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => must(api.GET("/settings")) });
  const [connects, setConnects] = useState<string>("");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const save = useMutation({
    mutationFn: () => must(api.PUT("/settings", { body: {
      weekly_connects_budget: connects ? Number(connects) : undefined,
      saved_searches: query ? [{ q: query, skills: [], limit: 20 }, ...(settings.data?.saved_searches ?? [])] : undefined,
    } })),
  });
  const upload = useMutation({
    mutationFn: async () => {
      const text = await file!.text();
      return must(api.POST("/portfolio/upload", { body: { filename: file!.name, text, type: "case_study" } }));
    },
  });

  if (me.isLoading || settings.isLoading) return <Loading />;
  if (me.error) return <ErrorBox error={me.error} />;

  return (
    <Page title="Set up GigBid">
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="1. Persona and rates">
          <p>Signed in as <strong>{me.data?.username}</strong>, persona <Badge tone="indigo">{me.data?.persona}</Badge></p>
          <p className="mt-2 text-sm text-slate-600">
            Rate floors from your fact sheet: hourly ${me.data?.hourly_floor ?? "—"}, fixed minimum ${me.data?.fixed_min ?? "—"}.
            GigBid never bids below these.
          </p>
        </Card>
        <Card title="2. Marketplace">
          <Accounts />
        </Card>
        <Card title="3. Filters and Connects budget">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <Field id="connects" label="Weekly Connects budget">
              <input id="connects" type="number" min={0} max={500} placeholder={String(settings.data?.weekly_connects_budget ?? "")}
                value={connects} onChange={(e) => setConnects(e.target.value)} className={inputClass} />
            </Field>
            <Field id="search" label="Add a saved search (keywords)">
              <input id="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. rag chatbot"
                className={inputClass} />
            </Field>
            <Button type="submit" disabled={save.isPending}>Save preferences</Button>
            {save.isSuccess && <p role="status" className="text-sm text-green-700">Saved.</p>}
            {save.error && <ErrorBox error={save.error} />}
          </form>
        </Card>
        <Card title="4. Portfolio">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (file) upload.mutate(); }}>
            <Field id="portfolio" label="Upload a case study (.md or .txt)">
              <input id="portfolio" type="file" accept=".md,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block text-sm" />
            </Field>
            <Button type="submit" disabled={!file || upload.isPending}>Upload and index</Button>
            {upload.data && (
              <p role="status" className="text-sm text-green-700">
                Indexed <code>{upload.data.evidence_id}</code> ({upload.data.chunks} chunks).
              </p>
            )}
            {upload.error && <ErrorBox error={upload.error} />}
          </form>
        </Card>
      </div>
      <div className="mt-6">
        <Button onClick={() => navigate("/jobs")}>Go to my inbox</Button>
      </div>
    </Page>
  );
}
