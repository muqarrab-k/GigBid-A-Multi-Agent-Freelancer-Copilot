# Shared LangSmith traces

Real runs on the live deployment (https://gigbid-3g0a.onrender.com, `MODEL_PROFILE=open_hosted`:
open-weight models on Groq with Nemotron 3 Ultra on OpenRouter as fallback), project `gigbid`.
Emails, phone numbers, card numbers and payment links are masked before upload
(`apps/api/tracing.py`). The trace id below is also in the run's LangSmith metadata and in the MCP
audit logs for the same run.

| # | case | job | trace id | what happened | link |
|---|---|---|---|---|---|
| 1 | Skipped scam / injection | `62ef812d6c54e6b3` "Website Chatbot" | `07ed96f61848437ba9a5a0a8816c0f00` | Risk flags `off_platform` and `injection`; the injected instruction was flagged, not followed, and the job was skipped before any drafting. | https://smith.langchain.com/public/4df09fc0-cc0c-4fd8-bc4b-52bc9899e616/r |
| 2 | Bid reaching approval | `1c0b990bb7dbe947` "AI Chatbot Developer" | `5f0332c209864bd997b4a4bf2289026a` | Analysis, fit (every requirement strong), pricing, writer, verifier, critic, compliance (allowed), dry-run preview, then the run stops at the approval interrupt. Not approved yet: the approval is done by hand in the demo, which records its own trace. | https://smith.langchain.com/public/655ef2ad-20d9-46b0-a53e-65c241e2a0e2/r |
| 3 | Critic loop | same run as #2 | `5f0332c209864bd997b4a4bf2289026a` | Inside trace #2: three writer passes with the critic asking for revisions after each (unsupported claims removed, too short, screening answers missing), then `critic_unresolved` after the 2-revision budget and the best draft goes to approval. | https://smith.langchain.com/public/655ef2ad-20d9-46b0-a53e-65c241e2a0e2/r |

Missing: a separate trace whose only purpose is the critic loop (#3 is part of #2), and a trace of
an approved, submitted proposal; the approval will be made by hand on the live site.
