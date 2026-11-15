# GigBid web

React + Vite + TypeScript, react-router, TanStack Query, Tailwind. Route screens live in
`src/app/`, shared components in `src/components/`, and `src/lib/api/schema.d.ts` is generated
from `apps/api/openapi.json` (`make web-client`; never edit it by hand).

```bash
make api-fake      # api on :8000 with the fake model, no keys (or make api for the real one)
make web           # vite dev server on :5173, proxies the api
make web-build     # dist/, served by the api at /
make e2e           # playwright against the api in fake mode; report in playwright-report/
```

Screens: sign-in and onboarding (persona, GigSim connected and Upwork not connected, rate floors,
saved search and Connects budget, portfolio upload), job inbox, job detail, agent run viewer (live
SSE timeline with trace id), proposal studio (EvidenceHover on every claim, Critic and Compliance
notes, dry-run preview, ApprovalPanel), approvals list, pipeline board, messages, analytics, and
settings (autonomy, budgets, saved searches, accounts, memory viewer). A banner driven by
`GET /status` shows when the marketplace is down.
