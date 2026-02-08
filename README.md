# Project Cognizant (Perceptix) 🧠🚀

**The Autonomous Data Reliability Engine.**

Perceptix is an agentic AI system designed to detect, diagnose, and remediate data quality issues in real-time. By leveraging advanced causal reasoning capabilities from **Google Gemini**, it bridges the gap between raw metrics and actionable business impact.

[![Technical Architecture](https://img.shields.io/badge/Architecture-Mermaid-blue)](./ARCHITECTURE.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🌟 Why Gemini?

In complex data environments, a simple "if-this-then-that" logic isn't enough. We use Google Gemini as the cognitive core of Project Cognizant for:

1.  **Massive Context Window**: We feed Gemini entire table schemas, SLA definitions, and recent Git commit histories. It correlates these diverse data points to find the technical "needle in the haystack."
2.  **Causal Reasoning Stability**: Unlike standard LLMs, Gemini reasoning models excel at structured step-by-step reasoning, ensuring that investigations are technical and evidence-based, not just probabilistic guesses.
3.  **Tool-Use Native**: The model natively understands how to interact with our internal "Investigator" tools to gather evidence before reaching a conclusion.

## 🔥 Key Features

-   **Autonomous Agent Loop**: Observe → Reason → Investigate → Verify → Act.
-   **Smart ML Triggers**: Hybrid approach using Isolation Forests and Autoencoders to trigger investigations.
-   **Self-Healing Remediation**: Proactively suggests and executes fixes (e.g., field renaming rollbacks).
-   **Meta-Learning**: Periodic analysis of incident patterns to identify systemic weaknesses.
-   **Enterprise Ready**: Multi-tenancy, RBAC, and production-hardened deployment.

## 🏗️ Getting Started

### Prerequisites
- Python 3.9+
- Gemini API Key
- Optional: `GEMINI_MODEL_NAME` (defaults to `models/gemini-3-pro-preview`; set explicitly if you want a different Gemini model)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/user/project-cognizant.git
   cd project-cognizant
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Setup environment:
   ```bash
   cp .env.example .env
   # Add your GEMINI_API_KEY
   # Optionally set GEMINI_MODEL_NAME (defaults to models/gemini-3-pro-preview)
   # Optionally customize DEMO_USERNAME / DEMO_PASSWORD
   ```

4. Run the API:
   ```bash
   python api.py
   ```

## 📊 Dashboard

Access the React-based dashboard at `http://localhost:3000` to monitor system health and approve remediation actions.

## 📜 Documentation

-   [Technical Architecture](./ARCHITECTURE.md)
-   [Hackathon Submission Packet](./HACKATHON_SUBMISSION.md)
-   [Deployment Guide](./deploy/README.md)
-   [API Reference](http://localhost:8000/docs)

## 🧪 Hackathon Preflight

Run the full readiness check:

```bash
./scripts/hackathon_preflight.sh
```

Gemini runtime proof endpoint:

- `GET /api/v1/hackathon/gemini-proof`

---
*Created for the Gemini API Hackathon.*
