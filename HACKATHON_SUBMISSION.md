# Perceptix Hackathon Submission Packet

## 1) Problem
Modern data platforms fail silently: schema drift, stale pipelines, and broken mappings can damage revenue and reporting before humans notice.

Perceptix is an autonomous reliability agent that detects data anomalies, reasons about root cause, investigates evidence, verifies conclusions, and proposes remediation.

## 2) Gemini Usage (Judge-Proof)
Perceptix uses Google Gemini as a structured decision layer across multiple stages (triage, planning, verification, policy suggestion, remediation risk).

For submission runs, set:

```bash
export GEMINI_API_KEY=...
export GEMINI_MODEL_NAME=models/gemini-3-pro-preview
```

Live runtime proof endpoint:

- `GET /api/v1/hackathon/gemini-proof`

This endpoint returns:

- configured model (`configured_model`)
- whether API key is configured (`api_key_configured`)
- whether runtime path is API or mock (`reasoning_path`)
- last reasoning metadata (provider/model/mode/latency)

Judge-visible traceability:
- Each incident includes a `decision_log` (triage/reason/plan/verify/policy/risk) and the dashboard renders it under **Incident Details -> Reasoning Trace**.

## 3) Judging Criteria Mapping

### Technical Execution (40%)
- Multi-agent pipeline: Observe -> Triage/Reason/Plan (Gemini) -> Investigate -> Verify (Gemini) -> Persist -> Escalate -> (Optional) Remediate (`main.py`).
- Production-style API with auth, remediation flows, rule endpoints, tenant APIs (`api.py`).
- Validation and quality gates:
  - tests via `pytest`
  - frontend lint via `npm run lint`
  - frontend production build via `npx vite build`
  - compile checks via `python3 -m py_compile`
- One-command readiness check: `scripts/hackathon_preflight.sh`.

### Potential Impact (20%)
- Broad applicability: any org with data pipelines, BI dashboards, or SLA-bound reporting.
- Faster detection + triage can reduce incident MTTR and data downtime.
- Designed for real operations: escalation channels, historical tracking, and remediation workflows.

### Innovation / Wow (30%)
- Agentic reliability loop with evidence-based verification instead of single-shot alerts.
- Combines model reasoning with deterministic investigation tools.
- Includes dynamic rules + ML triggers + remediation approvals in one platform.

### Presentation / Demo (10%)
- Architecture doc with diagram: `ARCHITECTURE.md`.
- This submission packet maps each judging criterion to concrete artifacts.
- Live proof endpoint demonstrates Gemini configuration and runtime behavior.

## 4) Demo Runbook (3 minutes or less)
1. Open dashboard (System Status + Live Activity visible).
2. Click **Simulate Failure** once (starts a full cycle and injects a fault).
3. Open `GET /api/v1/hackathon/gemini-proof` and highlight model + reasoning path.
4. When the incident appears, open **Incident Details** and show the **Reasoning Trace** (`decision_log`).
5. Show incident operations (archive/delete/bulk).
6. Mention Slack/email escalation and approval-gated remediation.
7. Close on rubric: production deployment, secure APIs, auditable reasoning, real-time UX.

## 5) Demo Checklist
- `GEMINI_API_KEY` set.
- `GEMINI_MODEL_NAME` set to the intended demo model (currently `models/gemini-3-pro-preview`).
- `scripts/hackathon_preflight.sh` passes.
- `/api/v1/hackathon/gemini-proof` shows `reasoning_path=api`.
- At least one full incident cycle demonstrated end-to-end.

## Judge Notes (Quick Verification)
Key URLs:
- Dashboard: `https://perceptix.duckdns.org/`
- Health: `GET https://perceptix.duckdns.org/health`
- API Docs: `https://perceptix.duckdns.org/docs`
- Gemini proof: `GET https://perceptix.duckdns.org/api/v1/hackathon/gemini-proof`

What to look for in the demo:
- The incident **detail view** includes a **Reasoning Trace** (`decision_log`) showing structured steps across:
  - `triage` (should investigate + priority)
  - `reason` (hypothesis summary)
  - `verify` (status + confidence)
  - `policy_suggest` (draft policy suggestion)
  - `remediation_risk` (risk score + approval recommendation)

Multi-tenant:
- The backend routes by `X-Tenant-ID` (default is `demo`).
- Incidents/metrics are isolated per-tenant (separate SQLite DB under `data/tenants/<tenant_id>/`).

## Testing Instructions / Test Login
Test login (OAuth password flow used by the UI):
- Username: `demo`
- Password: `secret`
- Default tenant: `demo` (header `X-Tenant-ID: demo`)

Fast smoke test (copy/paste):
```bash
# 1) Check health
curl -sS https://perceptix.duckdns.org/health

# 2) Verify Gemini runtime configuration (no secrets)
curl -sS https://perceptix.duckdns.org/api/v1/hackathon/gemini-proof

# 3) Get a token
TOKEN=$(curl -sS -X POST https://perceptix.duckdns.org/api/v1/auth/token \
  -H 'content-type: application/x-www-form-urlencoded' \
  --data 'username=demo&password=secret' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 4) Start a full cycle with an injected failure (returns immediately; follow Live Activity + Recent Incidents)
curl -sS -X POST https://perceptix.duckdns.org/api/v1/cycles/trigger \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: demo" \
  -H 'content-type: application/json' \
  -d '{"simulate_failure": true}'

# 5) List recent incidents
curl -sS "https://perceptix.duckdns.org/api/v1/incidents?limit=5&include_archived=true" \
  -H "X-Tenant-ID: demo"
```
