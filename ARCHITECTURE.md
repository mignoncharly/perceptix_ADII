# System Architecture: Project Cognizant (Perceptix)

This document details the multi-agent architecture of Perceptix and how it leverages Google Gemini for structured decision-making across the incident lifecycle.

Current deployed demo model: `models/gemini-3-pro-preview` (configurable via `GEMINI_MODEL_NAME`).

## High-Level Architecture

Perceptix follows a **Sense -> Decide -> Act** loop, reinforced by verification, persistence, and feedback learning.

```mermaid
flowchart TD
    User[Dashboard (React)] -->|HTTPS| Nginx[Nginx TLS Reverse Proxy]
    Nginx -->|/api/*| API[FastAPI]
    Nginx -->|/ws/incidents| WS[WebSocket: /ws/incidents]
    API -->|tenant header X-Tenant-ID| TenantResolver[Tenant Resolver]
    TenantResolver -->|per-tenant instance| Main[PerceptixSystem (Orchestrator)]
    WS -->|live events| User

    subgraph "Sense"
        Main --> Obs[Observer]
        Obs -->|ObservationPackage| Main
    end

    subgraph "Decide (Gemini-Backed Controls)"
        Main -->|triage prompt| GeminiRuntime[GeminiRuntime (budget + cache)]
        GeminiRuntime --> Reasoner[Causal Reasoner]
        Reasoner -->|hypotheses| Main
        Reasoner -->|investigation plan| Main
        Main -->|verification prompt| GeminiRuntime
        GeminiRuntime --> Verifier[Verifier]
        Verifier -->|verification + confidence| Main
        Main -->|policy suggestion| GeminiRuntime
        Main -->|remediation risk| GeminiRuntime
    end

    subgraph "Act"
        Main --> Inv[Investigator]
        Inv -->|Evidence Chain| Main
        Main --> Esc[Escalator (Slack/Email)]
        Main --> Policy[Policy Engine]
        Policy -->|match + approval gate| Rem[Remediation Engine]
    end

    subgraph "Persist & Learn"
        Main --> Hist[Historian]
        Hist --> DB[(SQLite per-tenant DB)]
        DB --> Meta[Meta-Learner]
        Meta -->|insights| Main
    end
```

## Agentic Components

### 1. Observer (The Sensor)
Collects metrics from SQLite (demo) or warehouse sources (BigQuery/Snowflake) and composes a validated `ObservationPackage`. It also ingests orchestration/observability events via webhook ingestion and can run ML/rules triggers.

### 2. Gemini Controls (Triage/Plan/Verify/Policy/Risk)
Gemini is used as a structured decision layer (JSON outputs) across multiple stages:
- **Triage:** decide whether to investigate and what to prioritize.
- **Plan:** produce/refine an investigation plan.
- **Verify:** evidence-based confirmation and confidence scoring.
- **Policy suggestion:** propose automation policies for human review.
- **Remediation risk:** assess playbook risk and force approval when needed.

**Runtime proof:** `GET /api/v1/hackathon/gemini-proof` exposes model/provider and whether the runtime path is API or mock.

### 3. Investigator (The Hands)
Executes a step-by-step investigation plan. It can "look" into specific services, verify ETL mappings, and check logs.

### 4. Verifier (The Critic)
Provides a final "check and balance". It reviews the evidence collected by the Investigator against the Reasoner's hypothesis. This ensures high-fidelity alerts (minimal false positives).

### 5. Meta-Learner (The Memory)
Analyzes historical incident data over long periods. It identifies "culprit services" that repeatedly fail and suggests permanent structural fixes.

### 6. Remediation Engine (The Healer)
Autonomous self-healing. Executes playbooks under policy control and approval gates (with additional Gemini risk assessment).

### 7. Decision Log (Traceability)
Each incident stores a `decision_log` that records the structured trace across stages (triage, reason, plan, verify, policy suggestion, remediation risk). This is surfaced in the incident detail UI to make the system auditable and demo-friendly.

## Decision Flow

1. **Anomaly Detected**: Column `user_id` null rate jumps from 0.05 to 0.5.
2. **Gemini Triage/Reason**: Prioritizes the signal and generates root-cause hypotheses.
3. **Investigation**: Investigator collects evidence based on the plan.
4. **Gemini Verification**: Verifier scores the evidence and outputs confidence.
5. **Persistence**: Historian stores the incident, evidence summary, and decision log.
6. **Escalation**: Slack/email alerts trigger when confidence exceeds threshold.
7. **Remediation**: Policy-driven playbooks may require approval; Gemini risk can force approval even when policies don't.
