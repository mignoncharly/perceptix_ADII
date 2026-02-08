# reasoner.py

"""
Reasoner Module: Root Cause Analysis Brain
Uses Gemini AI to perform intelligent hypothesis generation with full validation.
"""
import os
import json
import time
import logging
import uuid
from typing import Dict, Any, Optional, Tuple, List

from pydantic import ValidationError as PydanticValidationError

# Migrated from deprecated `google.generativeai` to `google-genai` (google.genai).
# See Google's migration guide. [web:107]
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-genai not installed. Running in mock mode.")

from models import (
    ObservationPackage, SystemState, ReasoningOutput,
    ReasoningResult
)
from exceptions import (
    ReasonerError, APICallError, ResponseParsingError,
    InvalidResponseFormatError, TokenLimitExceededError
)
from config import PerceptixConfig, SystemMode
from resilience import exponential_backoff, CircuitBreaker, rate_limit
from gemini_runtime import GeminiRuntime, GeminiSession, GeminiBudget

logger = logging.getLogger("PerceptixReasoner")


class CausalReasoner:
    """
    The Brain of Project Perceptix.
    Uses Gemini AI to perform Root Cause Analysis (RCA) on observed system states.
    """

    def __init__(self, config: PerceptixConfig):
        """
        Initialize CausalReasoner with configuration.

        Args:
            config: System configuration

        Raises:
            ReasonerError: If initialization fails
        """
        self.config = config
        self.component_id = "REASONER_GEMINI_V3"
        self.version = config.system.version

        # Initialize circuit breaker for API calls
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60.0,
            expected_exceptions=(APICallError, TimeoutError),
        )

        # Initialize Gemini client based on mode
        self.client = None
        self.api_available = False
        self.runtime = GeminiRuntime(
            api_key=self.config.api.gemini_api_key,
            model_name=self.config.api.model_name,
            enable_cache=True,
            cache_max_entries=2048,
        )

        if config.system.mode == SystemMode.PRODUCTION:
            if not config.api.gemini_api_key:
                raise ReasonerError(
                    "API key required in PRODUCTION mode",
                    component=self.component_id,
                )
            self._initialize_api_client()

        elif config.system.mode == SystemMode.DEMO:
            # In DEMO mode, try to initialize API if key is available
            if config.api.gemini_api_key:
                self._initialize_api_client()
            else:
                logger.warning("Running in DEMO mode without API key - using mock inference")

        else:  # MOCK mode
            logger.info("Running in MOCK mode - using deterministic mock inference")

        logger.info(
            f"Reasoner initialized: mode={config.system.mode.value}, api_available={self.api_available}"
        )

    def new_session(self, trace_id: str) -> GeminiSession:
        return GeminiSession(
            trace_id=trace_id,
            model_name=self.config.api.model_name,
            provider="google-genai",
            budget=GeminiBudget(max_calls=8, max_prompt_chars=140_000),
        )

    def triage(self, triggers: list[str], observation: ObservationPackage, session: GeminiSession) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Ask Gemini whether to run full reasoning/investigation, and what to prioritize.
        """
        state = observation.payload

        def _mock() -> Dict[str, Any]:
            # Simple deterministic triage: if any trigger exists, investigate.
            priority = "P2"
            if any("Critical" in t or "P0" in t for t in triggers):
                priority = "P0"
            elif any("High" in t or "Major" in t for t in triggers):
                priority = "P1"
            return {
                "should_investigate": True,
                "priority": priority,
                "suspected_incident_types": ["DATA_INTEGRITY_FAILURE"],
                "rationale": "Triggers indicate anomalous behavior requiring investigation.",
                "suggested_focus": triggers[:5],
            }

        # Keep prompt concise: triggers + a small state summary.
        table_summaries = []
        for tname, m in (state.table_metrics or {}).items():
            table_summaries.append(
                {
                    "table": tname,
                    "row_count": getattr(m, "row_count", None),
                    "freshness_minutes": getattr(m, "freshness_minutes", None),
                    "top_null_rates": sorted((m.null_rates or {}).items(), key=lambda kv: kv[1], reverse=True)[:3],
                }
            )

        prompt = f"""You are Perceptix Triage Agent.
Decide if we should run a full investigation cycle based on triggers and a brief state summary.

Triggers:
{json.dumps(triggers, indent=2)}

State summary:
{json.dumps({
  "tables": table_summaries,
  "pipeline_events_count": len(getattr(state, "pipeline_events", []) or []),
  "recent_code_commits_count": len(getattr(state, "recent_code_commits", []) or []),
}, indent=2)}

Return STRICT JSON:
{{
  "should_investigate": true|false,
  "priority": "P0"|"P1"|"P2"|"P3",
  "suspected_incident_types": ["SCHEMA_CHANGE", "FRESHNESS_VIOLATION", ...],
  "suggested_focus": ["short bullet", ...],
  "rationale": "short justification"
}}
"""
        payload, meta = self.runtime.generate_json(session=session, stage="triage", prompt=prompt, mock_fn=_mock)
        return payload, meta

    def generate_plan_only(self, observation: ObservationPackage, hypotheses: list[Dict[str, Any]], session: GeminiSession) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        """
        Ask Gemini for a tool plan only (structured InvestigationStep list).
        """
        state = observation.payload

        def _mock() -> Dict[str, Any]:
            return {
                "investigation_plan": [
                    {"step_id": 1, "action": "check_git_diff", "target": "checkout-service-api", "args": {"commit_hash": "latest", "file": "events/tracker.py"}},
                    {"step_id": 2, "action": "verify_etl_mapping", "target": "warehouse_loader_config", "args": {"column": "attribution_source"}},
                ]
            }

        prompt = f"""You are Perceptix Planning Agent.
Create a concrete investigation plan using ONLY allowed tools.

Allowed tools:
- check_git_diff (args: commit_hash, file)
- verify_etl_mapping (args: column)
- monitor_baseline (args: metric)

Triggers/hypotheses:
{json.dumps(hypotheses[:3], indent=2)}

State signals:
{json.dumps({
  "tables": list((state.table_metrics or {}).keys())[:10],
  "pipeline_events": (getattr(state, "pipeline_events", []) or [])[:5],
  "recent_code_commits": [c.model_dump(mode="json") for c in (state.recent_code_commits or [])[:2]],
}, indent=2)}

Return STRICT JSON:
{{
  "investigation_plan": [
    {{"step_id": 1, "action": "check_git_diff", "target": "repo", "args": {{"commit_hash":"latest","file":"path"}}}}
  ]
}}
"""
        payload, meta = self.runtime.generate_json(session=session, stage="plan", prompt=prompt, mock_fn=_mock)
        plan = payload.get("investigation_plan") if isinstance(payload, dict) else None
        if not isinstance(plan, list) or not plan:
            plan = _mock()["investigation_plan"]
        return plan, meta

    def _initialize_api_client(self) -> None:
        """
        Initialize Google Gemini API client via google-genai.

        Raises:
            ReasonerError: If API initialization fails
        """
        if not GEMINI_AVAILABLE:
            raise ReasonerError(
                "google-genai package not installed",
                component=self.component_id,
            )

        try:
            # Prefer explicit key. If you want env-based auth, you can omit api_key and set
            # GEMINI_API_KEY / GOOGLE_API_KEY externally per Google docs. [web:107]
            self.client = genai.Client(api_key=self.config.api.gemini_api_key)
            self.api_available = True
            logger.info(f"Gemini API initialized (google-genai): model={self.config.api.model_name}")
        except Exception as e:
            raise ReasonerError(
                f"Failed to initialize Gemini API: {e}",
                component=self.component_id,
            )

    def _generate_system_prompt(self, system_state: SystemState) -> str:
        """
        Constructs the high-fidelity prompt for the AI.
        Forces the model to look at 'Code Commits' vs 'Data Drift'.

        Args:
            system_state: Validated system state

        Returns:
            str: Formatted prompt for the AI
        """
        context = system_state.model_dump(mode="json")

        return f"""SYSTEM ROLE: You are a Senior Principal Site Reliability Engineer (SRE).
OBJECTIVE: Perform a Root Cause Analysis (RCA) on the provided SYSTEM STATE JSON.

INPUT CONTEXT:
{json.dumps(context, indent=2)}

ANALYSIS INSTRUCTIONS:
1. Compare 'table_metrics' against 'historical_baseline_7d'. Identify significant drifts (>50% deviation).
2. Correlate anomalies with 'recent_code_commits'. Look for semantic matches (e.g., variable renames, logic changes).
3. Assess business impact using 'dependency_map' and 'sla_definitions'.
4. Generate 1-3 ranked hypotheses ordered by likelihood.
5. Create a specific investigation plan with concrete actions.

AVAILABLE TOOLS:
You may ONLY use the following tools in your investigation plan:
1. "check_git_diff": Checks for code changes. Args: {{"target": "repo", "file": "path", "commit_hash": "latest"}}
2. "verify_etl_mapping": Checks ETL schema config. Args: {{"target": "config_name", "column": "col_name"}}
3. "monitor_baseline": Checks metric deviations. Args: {{"target": "table_name", "metric": "metric_name"}}

DO NOT invent new tools. If you need to check a configuration, use 'verify_etl_mapping' or 'check_git_diff'.

OUTPUT FORMAT REQUIREMENTS (STRICT JSON ONLY):
Return a JSON object with this exact schema:
{{
    "analysis_summary": "One sentence summary of the incident.",
    "detected_anomalies": ["List specific metric drifts"],
    "hypotheses": [
        {{
            "id": "H1",
            "description": "The specific technical theory (minimum 10 characters).",
            "supporting_evidence": "Why you think this (e.g., 'Commit X changed field Y').",
            "confidence_score": 0-100
        }}
    ],
    "investigation_plan": [
        {{
            "step_id": 1,
            "action": "check_git_diff",
            "target": "service-name",
            "args": {{"commit_hash": "latest", "file": "path/to/file.py"}}
        }}
    ],
    "severity_assessment": "P0" or "P1" or "P2" or "P3"
}}

CRITICAL: Ensure all hypotheses have:
- id starting with 'H' followed by number
- description minimum 10 characters
- supporting_evidence minimum 5 characters
- confidence_score between 0 and 100
"""

    def _mock_inference(self, system_state: SystemState) -> str:
        """
        Simulates intelligent Gemini response for demo/mock mode.
        Returns deterministic but realistic reasoning output.

        Args:
            system_state: System state to analyze

        Returns:
            str: JSON string with mock reasoning output
        """
        orders_table = system_state.table_metrics.get("orders_table")
        attribution_null_rate = 0.0

        if orders_table:
            attribution_null_rate = orders_table.null_rates.get("attribution_source", 0.0)

        is_anomalous = attribution_null_rate > 0.50

        if is_anomalous:
            response = {
                "analysis_summary": "Critical data quality degradation in orders_table detected immediately following checkout-service-api deployment.",
                "detected_anomalies": [
                    f"orders_table.attribution_source null_rate is {attribution_null_rate:.2f} (expected ~0.05)",
                    "Anomaly correlates with recent code commit timestamp",
                ],
                "hypotheses": [
                    {
                        "id": "H1",
                        "description": "Schema Mismatch: Upstream checkout-service renamed the tracking field, but the ETL pipeline expects the old name.",
                        "supporting_evidence": "Commit 'refactor: rename tracking_pixel_id to source_id' occurred recently. Null spike is near 100%, indicating complete field mapping failure.",
                        "confidence_score": 95.0,
                    },
                    {
                        "id": "H2",
                        "description": "Traffic Shift: A new marketing campaign is sending traffic without tracking parameters.",
                        "supporting_evidence": "Marketing_ROI_Report is a dependency. However, 98% drop is too steep for just organic traffic mix.",
                        "confidence_score": 20.0,
                    },
                ],
                "investigation_plan": [
                    {
                        "step_id": 1,
                        "action": "check_git_diff",
                        "target": "checkout-service-api",
                        "args": {"commit_hash": "latest", "file": "events/tracker.py"},
                    },
                    {
                        "step_id": 2,
                        "action": "verify_etl_mapping",
                        "target": "warehouse_loader_config",
                        "args": {"column": "attribution_source"},
                    },
                ],
                "severity_assessment": "P0",
            }
        else:
            response = {
                "analysis_summary": "System metrics within normal parameters. No critical anomalies detected.",
                "detected_anomalies": [],
                "hypotheses": [
                    {
                        "id": "H1",
                        "description": "No significant issues detected. All metrics within baseline thresholds.",
                        "supporting_evidence": "Attribution null rate is 0.05, consistent with 7-day average. No recent code changes affecting data pipeline.",
                        "confidence_score": 95.0,
                    }
                ],
                "investigation_plan": [
                    {
                        "step_id": 1,
                        "action": "monitor_baseline",
                        "target": "orders_table",
                        "args": {"metric": "attribution_source_null_rate"},
                    }
                ],
                "severity_assessment": "P3",
            }

        return json.dumps(response, indent=2)

    @rate_limit(max_calls=10, time_window=60.0)
    @exponential_backoff(max_retries=3, base_delay=2.0, max_delay=30.0)
    def _call_llm_api(self, prompt: str) -> str:
        """
        Call Gemini API with retry and rate limiting.

        Args:
            prompt: Prompt to send to API

        Returns:
            str: API response text

        Raises:
            APICallError: If API call fails
            TokenLimitExceededError: If prompt is too long
        """
        if not self.client or not self.api_available:
            raise APICallError("Client not initialized", component=self.component_id)

        try:
            estimated_tokens = len(prompt.split())
            if estimated_tokens > self.config.api.max_tokens * 0.8:
                raise TokenLimitExceededError(
                    f"Prompt too long: ~{estimated_tokens} tokens",
                    component=self.component_id,
                    context={"estimated_tokens": estimated_tokens},
                )

            # google-genai call pattern: client.models.generate_content(...) [web:107]
            response = self.circuit_breaker.call(
                self.client.models.generate_content,
                model=self.config.api.model_name,
                contents=prompt,
            )

            response_text = getattr(response, "text", None)
            if not response_text:
                raise APICallError("Empty response from API", component=self.component_id)

            return response_text

        except TokenLimitExceededError:
            raise
        except APICallError:
            raise
        except Exception as e:
            raise APICallError(
                f"Gemini API call failed: {e}",
                component=self.component_id,
                context={"error_type": type(e).__name__},
            )

    def _parse_and_validate_response(self, response_text: str) -> ReasoningOutput:
        """
        Parse and validate LLM response using Pydantic.

        Args:
            response_text: JSON response from LLM

        Returns:
            ReasoningOutput: Validated reasoning output

        Raises:
            ResponseParsingError: If JSON parsing fails
            InvalidResponseFormatError: If validation fails
        """
        try:
            # Clean markdown code blocks if present
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```"):
                # Remove first line (```json or just ```)
                cleaned_text = "\n".join(cleaned_text.split("\n")[1:])
                # Remove last line (```)
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3].strip()
            
            response_data = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            raise ResponseParsingError(
                f"Failed to parse JSON response: {e}",
                component=self.component_id,
                context={"response_preview": response_text[:200]},
            )

        try:
            return ReasoningOutput(**response_data)
        except PydanticValidationError as e:
            errors = e.errors()
            error_details = [f"{err['loc']}: {err['msg']}" for err in errors]
            raise InvalidResponseFormatError(
                f"Response validation failed: {'; '.join(error_details)}",
                component=self.component_id,
                context={"validation_errors": errors},
            )

    def generate_hypotheses(
        self,
        observation: ObservationPackage,
        *,
        trace_id: str | None = None,
        session: GeminiSession | None = None,
    ) -> ReasoningResult:
        """
        The main reasoning loop with full validation and error handling.

        Args:
            observation: Validated observation package from Observer

        Returns:
            ReasoningResult: Validated reasoning result with metadata
        """
        start_time = time.time()
        effective_trace_id = trace_id or (session.trace_id if session is not None else None) or str(uuid.uuid4())
        effective_session = session or self.new_session(effective_trace_id)

        logger.info(f"[{effective_trace_id}] Starting hypothesis generation")

        try:
            system_state = observation.payload

            prompt = self._generate_system_prompt(system_state)
            logger.debug(f"[{effective_trace_id}] Prompt generated ({len(prompt)} chars)")

            if self.api_available and self.client:
                logger.info(
                    f"[{effective_trace_id}] Calling Gemini API "
                    f"(provider=google-genai, model={self.config.api.model_name})"
                )
                response_text = self._call_llm_api(prompt)
            else:
                logger.info(
                    f"[{effective_trace_id}] Using mock inference "
                    f"(model_config={self.config.api.model_name})"
                )
                time.sleep(1.5)
                response_text = self._mock_inference(system_state)

            logger.debug(f"[{effective_trace_id}] Parsing response")
            reasoning_output = self._parse_and_validate_response(response_text)

            # Optional extra Gemini control: plan refinement (separate call, cached/budgeted).
            try:
                plan, plan_meta = self.generate_plan_only(
                    observation=observation,
                    hypotheses=[h.model_dump(mode="json") for h in reasoning_output.hypotheses],
                    session=effective_session,
                )
                # Validate/normalize plan items via Pydantic model (same schema as ReasoningOutput).
                from models import InvestigationStep

                validated = []
                for item in plan:
                    validated.append(InvestigationStep(**item))
                reasoning_output.investigation_plan = validated
            except Exception as e:
                logger.warning(f"[{effective_trace_id}] Plan refinement failed, keeping original plan. error={e}")
                plan_meta = None

            latency_ms = (time.time() - start_time) * 1000

            result = ReasoningResult(
                metadata={
                    "component": self.component_id,
                    "latency_ms": round(latency_ms, 2),
                    "trace_id": effective_trace_id,
                    "version": self.version,
                    "api_used": self.api_available and self.client is not None,
                    "provider": "google-genai" if GEMINI_AVAILABLE else "mock",
                    "model_name": self.config.api.model_name,
                    "reasoning_mode": "api" if (self.api_available and self.client is not None) else "mock",
                    "hypotheses_count": len(reasoning_output.hypotheses),
                    "gemini_session_calls": effective_session.call_count,
                    "gemini_session_cache_hits": effective_session.cache_hits,
                    "plan_refinement": bool(plan_meta),
                },
                reasoning=reasoning_output,
            )

            logger.info(
                f"[{effective_trace_id}] Hypothesis generation complete: "
                f"{len(reasoning_output.hypotheses)} hypotheses, "
                f"severity={reasoning_output.severity_assessment.value}, "
                f"latency={latency_ms:.0f}ms"
            )

            return result

        except (APICallError, ResponseParsingError, InvalidResponseFormatError):
            raise
        except Exception as e:
            raise ReasonerError(
                f"Unexpected error in generate_hypotheses: {e}",
                component=self.component_id,
                trace_id=effective_trace_id,
            )

    def suggest_policy_for_incident(
        self,
        incident: Any,
        session: GeminiSession,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Ask Gemini to propose a draft automation policy (human review recommended).
        """
        def _mock() -> Dict[str, Any]:
            return {
                "name": f"Auto-route {getattr(incident, 'incident_type', 'INCIDENT')} with approval",
                "enabled": True,
                "match": {
                    "incident_types": [str(getattr(incident, "incident_type", "UNKNOWN"))],
                    "min_confidence": 85,
                },
                "action": {"playbook": "Fix Schema Mismatch", "require_approval": True},
                "rationale": "Recurring incidents benefit from a consistent approval-gated response.",
            }

        prompt = f"""You are Perceptix Policy Advisor.
Propose a single automation policy based on the incident, suitable for human review.

Incident summary:
{json.dumps({
  "incident_type": getattr(getattr(incident, "incident_type", None), "value", None) or str(getattr(incident, "incident_type", "UNKNOWN")),
  "confidence": getattr(incident, "final_confidence_score", None),
  "root_cause_analysis": getattr(incident, "root_cause_analysis", "")[:600],
  "recommended_actions": getattr(incident, "recommended_actions", [])[:5],
}, indent=2)}

Return STRICT JSON:
{{
  "name": "string",
  "enabled": true|false,
  "match": {{"incident_types": ["SCHEMA_CHANGE"], "min_confidence": 0-100}},
  "action": {{"playbook": "Playbook Name", "require_approval": true|false}},
  "rationale": "short justification"
}}
"""
        payload, meta = self.runtime.generate_json(session=session, stage="policy_suggest", prompt=prompt, mock_fn=_mock)
        return payload, meta

    def assess_playbook_risk(
        self,
        *,
        incident: Any,
        playbook_name: str,
        playbook_steps: List[Dict[str, Any]],
        session: GeminiSession,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Ask Gemini to assess remediation risk and whether to require approval.
        """
        def _mock() -> Dict[str, Any]:
            return {
                "risk_score": 30,
                "require_approval": True,
                "rationale": "Automated actions should be approval gated in production environments.",
            }

        prompt = f"""You are Perceptix Remediation Risk Assessor.
Given an incident and a remediation playbook, assess risk.

Incident:
{json.dumps({
  "incident_type": getattr(getattr(incident, "incident_type", None), "value", None) or str(getattr(incident, "incident_type", "UNKNOWN")),
  "confidence": getattr(incident, "final_confidence_score", None),
  "summary": getattr(incident, "root_cause_analysis", "")[:600],
}, indent=2)}

Playbook:
{json.dumps({"name": playbook_name, "steps": playbook_steps}, indent=2)}

Return STRICT JSON:
{{
  "risk_score": 0-100,
  "require_approval": true|false,
  "rationale": "short justification"
}}
"""
        payload, meta = self.runtime.generate_json(session=session, stage="remediation_risk", prompt=prompt, mock_fn=_mock)
        return payload, meta
