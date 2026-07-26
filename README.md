# Perceptix

Perceptix is a data-reliability project built for the Gemini API Hackathon. It explores a simple idea: when a data-quality alert fires, the useful question is not only **what failed?** but also **what changed, what is affected, and what evidence supports the diagnosis?**

The system combines deterministic rules, anomaly detection and a tool-using investigation loop. Gemini helps connect evidence from schemas, service-level rules, incidents and repository history; it does not replace the underlying checks.

## How it works

The investigation flow follows five steps:

1. **Observe** a rule violation or anomaly.
2. **Reason** about likely causes and business impact.
3. **Investigate** by calling the available evidence tools.
4. **Verify** the explanation against collected facts.
5. **Act** by proposing a remediation for review.

The React dashboard gives operators a place to inspect system health and approve remediation actions. Automatic suggestions are treated as proposals, not as unquestionable truth.

## Main components

- Rule-based quality checks
- Isolation Forest and autoencoder triggers
- Gemini-backed investigation workflow
- Remediation proposals and approval handling
- Multi-tenant access control
- Incident history and recurring-pattern analysis
- REST API, CLI and React dashboard
- Tests, load checks and deployment assets

## Repository guide

| Path | Purpose |
| --- | --- |
| `perceptix` | Core application logic |
| `rules` / `rules_engine` | Deterministic quality rules |
| `ml` | Anomaly-detection components |
| `remediation` | Proposed and approved corrective actions |
| `frontend` | Monitoring and approval interface |
| `tenancy` / `security` | Tenant boundaries and access control |
| `tests` / `load_tests` | Functional and performance checks |
| `deploy` | Deployment configuration |

The deeper design notes are in [`ARCHITECTURE.md`](./ARCHITECTURE.md). Hackathon context and verification steps are documented in [`HACKATHON_SUBMISSION.md`](./HACKATHON_SUBMISSION.md).

## Local setup

Requirements:

- Python 3.9+
- A Gemini API key
- Node.js for the dashboard

```bash
git clone https://github.com/mignoncharly/perceptix_ADII.git
cd perceptix_ADII

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Add `GEMINI_API_KEY` to `.env`. `GEMINI_MODEL_NAME` is optional.

Start the API:

```bash
python api.py
```

The dashboard runs separately from `frontend/`. The API also exposes a runtime-proof endpoint:

```text
GET /api/v1/hackathon/gemini-proof
```

## Preflight

Run the project checks before a demo or deployment:

```bash
./scripts/hackathon_preflight.sh
```

Perceptix is an engineering experiment, not a promise that every data incident can be solved by a language model. Its value is in bringing evidence, repeatable checks and human approval into the same investigation.
