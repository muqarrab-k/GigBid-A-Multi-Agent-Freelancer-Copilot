# ADR 0002: One marketplace port, adapters behind it, our own MCP layer on top

- Status: accepted (2026-11-14)
- Agents only see MCP tools from our Marketplace server. The server talks to `MarketplacePort`, and adapters (GigSim now, live Upwork later) sit behind it, so switching `marketplace.mode` changes no agent or tool code.
- The port owns the vocabulary: marketplace-neutral Pydantic models and typed errors (`MarketplaceUnavailable`, `RateLimited`, `PolicyViolation`, `InsufficientConnects`, `NotFound`). Adapters translate their API into it, and `capabilities` says what the marketplace allows (live Upwork: drafts only, confirmed on the platform).
- Our own MCP layer is where the safety rules live once for every marketplace: schemas with bounds, required idempotency keys, `dry_run` previews for the approval screen, untrusted-text marking, per-user rate limits, PII-masked audit logs and structured degraded-mode errors.
- Retries live in the adapter and always reuse the same idempotency key, so a retried write can never submit twice or spend Connects twice.
- Trade-off: one more hop and some duplicated checks (the policy pre-check runs here and again in the marketplace). We accept it because the pre-check is what makes `dry_run` honest without side effects.
