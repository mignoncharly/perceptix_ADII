"""
Main Orchestrator: Complete Perceptix System
Coordinates all components with full error handling and lifecycle management.
"""
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

from perceptix.ui import banner

from config import load_config, PerceptixConfig, apply_dynamic_settings
from database import DatabaseManager
from observer import Observer
from reasoner import CausalReasoner
from agent_loops import Investigator, Verifier
from escalator import Escalator
from metrics import SystemMetrics
from models import IncidentReport
from historian import Historian
from meta_learner import MetaLearner
from remediation.remediation_engine import RemediationEngine
from policy_engine import PolicyEngine
from exceptions import (
    PerceptixError, ObserverError, ReasonerError,
    InvestigatorError, VerifierError, HistorianError,
    SystemError, CycleLimitExceededError
)

# IMPORTANT:
# Do NOT configure logging here. Configure it in cli.py (RichHandler for demos),
# otherwise you'll get duplicated handlers / messy output.
logger = logging.getLogger("PerceptixOrchestrator")


class PerceptixSystem:
    """
    Main orchestrator for the Perceptix system.
    Coordinates all components with proper lifecycle management.
    """

    def __init__(self, config: Optional[PerceptixConfig] = None, tenant_id: str | None = None):
        try:
            # Load configuration
            self.config = config or load_config()
            logger.info(f"Perceptix System initializing: mode={self.config.system.mode.value}")
            self.tenant_id = tenant_id

            # Initialize database
            self.db_manager = DatabaseManager(self.config.database)
            logger.info(f"Database initialized: {self.config.database.type}")

            # Load Dynamic Configuration from DB
            try:
                dynamic_settings = self.db_manager.get_app_config()
                if dynamic_settings:
                    logger.info(f"Loading {len(dynamic_settings)} dynamic configuration settings")
                    apply_dynamic_settings(self.config, dynamic_settings)
            except Exception as e:
                logger.warning(f"Failed to load dynamic configuration: {e}")

            # Core storage first (used by automation subsystems).
            self.historian = Historian(self.db_manager)
            self.meta_learner = MetaLearner(self.db_manager)
            self.policy_engine = PolicyEngine(self.historian)

            # Initialize components
            self.observer = Observer(self.config)
            self.reasoner = CausalReasoner(self.config)
            self.investigator = Investigator(self.config)
            self.verifier = Verifier(self.config)
            self.remediation_engine = RemediationEngine(
                self.config,
                db_manager=self.db_manager,
                historian=self.historian,
                tenant_id=self.tenant_id,
            )
            self.escalator = Escalator(self.config)
            self.metrics = SystemMetrics()

            logger.info("All components initialized successfully")

            # System state
            self.cycle_count = 0
            self.max_cycles = self.config.system.max_cycles
            self.last_cycle_timestamp: Optional[str] = None
            self.last_reasoning_metadata: Optional[Dict[str, Any]] = None

        except Exception as e:
            raise SystemError(
                f"Failed to initialize Perceptix system: {e}",
                component="PerceptixSystem"
            )

    async def run_cycle(self, cycle_id: int, simulate_failure: bool = False) -> Optional[IncidentReport]:
        """
        Execute a single analysis cycle.
        """
        import asyncio
        
        logger.info(f"--- STARTING CYCLE {cycle_id} ---")
        cycle_start_time = time.time()
        had_anomaly = False
        hypothesis_confidence: Optional[float] = None
        verification_status: Optional[str] = None
        decision_log: list[Dict[str, Any]] = []
        cycle_trace_id = str(uuid.uuid4())
        gemini_session = self.reasoner.new_session(cycle_trace_id)

        if cycle_id > self.max_cycles:
            raise CycleLimitExceededError(
                f"Exceeded maximum cycles: {self.max_cycles}",
                component="PerceptixSystem",
                context={"cycle_id": cycle_id}
            )

        try:
            # 1. OBSERVE
            banner(f"Cycle {cycle_id}", "Phase 1: Observation")
            logger.info(f"[CYCLE {cycle_id}] Phase 1: Observation")
            observer_start = time.time()
            try:
                state_package = await self.observer.get_system_state(simulate_failure=simulate_failure)
                self.metrics.record_agent_execution(
                    agent="observer",
                    duration_ms=(time.time() - observer_start) * 1000,
                    success=True,
                )
            except Exception:
                self.metrics.record_agent_execution(
                    agent="observer",
                    duration_ms=(time.time() - observer_start) * 1000,
                    success=False,
                )
                raise

            # Smart Trigger Logic
            triggers = []

            # Check Rules
            if hasattr(state_package, "rules_evaluation") and state_package.rules_evaluation:
                if state_package.rules_evaluation.get("triggered_count", 0) > 0:
                    triggers.append("Custom Rules Triggered")
                    logger.warning(
                        f"[CYCLE {cycle_id}] Rules Triggered: "
                        f"{state_package.rules_evaluation.get('triggered_rules', [])}"
                    )

            # Check ML
            if hasattr(state_package, "ml_predictions") and state_package.ml_predictions:
                for table, pred in state_package.ml_predictions.items():
                    if pred.get("is_anomaly", False) and pred.get("confidence", 0) > 0.8:
                        triggers.append(f"ML Anomaly in {table}")

            # Check for direct baseline drift
            if hasattr(state_package.payload, "historical_baseline_7d") and state_package.payload.historical_baseline_7d:
                for table, metrics in state_package.payload.table_metrics.items():
                    if table in state_package.payload.historical_baseline_7d:
                        baseline = state_package.payload.historical_baseline_7d[table]
                        current_null = metrics.null_rates.get("attribution_source", 0.0)
                        if baseline.avg_attribution_null_rate > 0 and current_null > baseline.avg_attribution_null_rate * 5:
                            triggers.append(f"Major Null Rate Drift in {table}")

            # Baseline-free safety triggers (works for any connector).
            for table, metrics in state_package.payload.table_metrics.items():
                try:
                    if int(metrics.freshness_minutes) > 1440:
                        triggers.append(f"Critical Freshness Violation in {table}")
                except Exception:
                    pass

            # Orchestration/observability triggers (webhook ingested events).
            try:
                for evt in getattr(state_package.payload, "pipeline_events", []) or []:
                    status = str(evt.get("status") or "").upper()
                    severity = str(evt.get("severity") or "").upper()
                    if status in ("FAILED", "FAILURE", "ERROR") or severity in ("HIGH", "CRITICAL", "P0", "P1"):
                        pipeline = evt.get("pipeline") or "pipeline"
                        triggers.append(f"Pipeline Event: {pipeline} {status or severity}".strip())
            except Exception:
                pass

                try:
                    for col, rate in (metrics.null_rates or {}).items():
                        if float(rate) >= 0.95:
                            triggers.append(f"Severe Null Rate in {table}.{col}")
                        elif float(rate) >= 0.50:
                            triggers.append(f"High Null Rate in {table}.{col}")
                except Exception:
                    pass

            # If no triggers, return early
            if not triggers:
                logger.info(f"[CYCLE {cycle_id}] System Healthy. Triggers: None")
                self.last_reasoning_metadata = {
                    "cycle_id": cycle_id,
                    "reasoning_skipped": True,
                    "reason": "no_triggers",
                }
                return None

            # 1.5 TRIAGE (Gemini-assisted, budgeted + cached)
            try:
                triage_payload, triage_meta = self.reasoner.triage(triggers=triggers, observation=state_package, session=gemini_session)
                decision_log.append(
                    {
                        "stage": "triage",
                        "summary": str(triage_payload.get("rationale", ""))[:280],
                        "should_investigate": bool(triage_payload.get("should_investigate", True)),
                        "priority": triage_payload.get("priority"),
                        "suspected_incident_types": triage_payload.get("suspected_incident_types", []),
                        "meta": triage_meta,
                    }
                )
                if not bool(triage_payload.get("should_investigate", True)):
                    logger.info(f"[CYCLE {cycle_id}] Triage decided to skip investigation.")
                    self.last_reasoning_metadata = {
                        "cycle_id": cycle_id,
                        "reasoning_skipped": True,
                        "reason": "triage_skip",
                        "triage": triage_payload,
                    }
                    return None
            except Exception as e:
                logger.warning(f"[CYCLE {cycle_id}] Triage failed, continuing without triage gating. error={e}")

            logger.warning(
                f"[CYCLE {cycle_id}] ANOMALY DETECTED: {', '.join(triggers)}. Engaging reasoning pipeline."
            )
            had_anomaly = True

            # 2. REASON
            banner(f"Cycle {cycle_id}", "Phase 2: Reasoning")
            logger.info(f"[CYCLE {cycle_id}] Phase 2: Reasoning")
            
            # Wrap synchronous Reasoner call in executor to allow event loop to breathe if other concurrent tasks existed
            loop = asyncio.get_running_loop()
            reasoner_start = time.time()
            try:
                analysis = await loop.run_in_executor(
                    None,
                    lambda: self.reasoner.generate_hypotheses(
                        state_package,
                        trace_id=cycle_trace_id,
                        session=gemini_session,
                    ),
                )
                self.metrics.record_agent_execution(
                    agent="reasoner",
                    duration_ms=(time.time() - reasoner_start) * 1000,
                    success=True,
                )
            except Exception:
                self.metrics.record_agent_execution(
                    agent="reasoner",
                    duration_ms=(time.time() - reasoner_start) * 1000,
                    success=False,
                )
                raise
            self.last_reasoning_metadata = analysis.metadata

            decision_log.append(
                {
                    "stage": "reason",
                    "summary": str(analysis.reasoning.analysis_summary)[:280],
                    "severity": getattr(analysis.reasoning.severity_assessment, "value", None),
                    "hypotheses_count": len(analysis.reasoning.hypotheses or []),
                    "meta": analysis.metadata,
                }
            )

            if not analysis.reasoning.hypotheses:
                logger.warning(f"[CYCLE {cycle_id}] No hypotheses generated")
                return None

            primary_hypothesis = analysis.reasoning.hypotheses[0]
            hypothesis_confidence = primary_hypothesis.confidence_score
            logger.info(
                f"[CYCLE {cycle_id}] Primary Hypothesis: {primary_hypothesis.id} "
                f"(confidence: {primary_hypothesis.confidence_score}%)"
            )

            # 3. INVESTIGATE
            banner(f"Cycle {cycle_id}", "Phase 3: Investigation")
            logger.info(f"[CYCLE {cycle_id}] Phase 3: Investigation")
            investigator_start = time.time()
            try:
                evidence_chain = await self.investigator.execute_plan(analysis.reasoning.investigation_plan)
                self.metrics.record_agent_execution(
                    agent="investigator",
                    duration_ms=(time.time() - investigator_start) * 1000,
                    success=True,
                )
            except Exception:
                self.metrics.record_agent_execution(
                    agent="investigator",
                    duration_ms=(time.time() - investigator_start) * 1000,
                    success=False,
                )
                raise
            logger.info(f"[CYCLE {cycle_id}] Evidence collected: {len(evidence_chain)} items")

            # 4. VERIFY
            banner(f"Cycle {cycle_id}", "Phase 4: Verification")
            logger.info(f"[CYCLE {cycle_id}] Phase 4: Verification")
            verifier_start = time.time()
            try:
                final_report = await self.verifier.verify_incident(
                    primary_hypothesis,
                    evidence_chain,
                    analysis.reasoning.detected_anomalies,
                    cycle_id=cycle_id,
                    decision_log=decision_log,
                    session=gemini_session,
                )
                self.metrics.record_agent_execution(
                    agent="verifier",
                    duration_ms=(time.time() - verifier_start) * 1000,
                    success=True,
                )
            except Exception:
                self.metrics.record_agent_execution(
                    agent="verifier",
                    duration_ms=(time.time() - verifier_start) * 1000,
                    success=False,
                )
                raise
            verification_status = final_report.verification_status.value
            hypothesis_confidence = final_report.final_confidence_score
            logger.info(
                f"[CYCLE {cycle_id}] Verification complete: "
                f"status={final_report.verification_status.value}, "
                f"confidence={final_report.final_confidence_score}%"
            )

            # 5. PERSIST
            banner(f"Cycle {cycle_id}", "Phase 5: Persistence")
            logger.info(f"[CYCLE {cycle_id}] Phase 5: Persistence")
            self.historian.save_incident(final_report, tenant_id=self.tenant_id)

            # 5.5 POLICY SUGGESTION (Gemini-assisted)
            try:
                policy_suggestion, policy_meta = self.reasoner.suggest_policy_for_incident(final_report, session=gemini_session)
                decision_log.append(
                    {
                        "stage": "policy_suggest",
                        "summary": str(policy_suggestion.get("rationale", ""))[:280],
                        "suggested_policy": policy_suggestion,
                        "meta": policy_meta,
                    }
                )
                # Store updated report JSON with decision log (already persisted once). For MVP, keep it in-memory;
                # next incident persistence retains trace in full_json.
            except Exception as e:
                logger.warning(f"[CYCLE {cycle_id}] Policy suggestion failed (non-fatal). error={e}")

            # 6. REMEDIATION (Policy-Driven + Approval Gates)
            if final_report.final_confidence_score >= self.config.system.confidence_threshold:
                banner(f"Cycle {cycle_id}", "Phase 6: Remediation")
                logger.info(f"[CYCLE {cycle_id}] Phase 6: Remediation")

                policy_actions = self.policy_engine.evaluate(final_report)
                if policy_actions:
                    for action in policy_actions:
                        self.historian.record_audit_event(
                            actor="system",
                            action="policy.matched",
                            entity_type="policy",
                            entity_id=action.policy_id,
                            details={
                                "incident_id": final_report.report_id,
                                "incident_type": final_report.incident_type.value,
                                "playbook": action.playbook,
                                "require_approval": action.require_approval,
                            },
                        )
                        # Gemini risk assessment can force approvals even if policy didn't.
                        force_approval = bool(action.require_approval)
                        try:
                            pb = self.remediation_engine.executor.get_playbook(action.playbook)
                            steps = []
                            if pb:
                                steps = [s.model_dump() if hasattr(s, "model_dump") else getattr(s, "__dict__", {}) for s in (pb.steps or [])]
                            risk_payload, risk_meta = self.reasoner.assess_playbook_risk(
                                incident=final_report,
                                playbook_name=action.playbook,
                                playbook_steps=steps,
                                session=gemini_session,
                            )
                            decision_log.append(
                                {
                                    "stage": "remediation_risk",
                                    "summary": str(risk_payload.get("rationale", ""))[:280],
                                    "playbook": action.playbook,
                                    "risk": risk_payload,
                                    "meta": risk_meta,
                                }
                            )
                            if bool(risk_payload.get("require_approval")):
                                force_approval = True
                            try:
                                if float(risk_payload.get("risk_score", 0)) >= 70:
                                    force_approval = True
                            except Exception:
                                pass
                        except Exception as e:
                            logger.warning(f"[CYCLE {cycle_id}] Remediation risk assessment failed (non-fatal). error={e}")

                        rem_result = self.remediation_engine.execute_playbook_for_incident(
                            incident_id=final_report.report_id,
                            playbook_name=action.playbook,
                            incident_type=final_report.incident_type.value,
                            confidence=final_report.final_confidence_score,
                            context={"evidence": [e.model_dump() for e in evidence_chain]},
                            force_approval=force_approval,
                        )
                        logger.info(f"[CYCLE {cycle_id}] Policy remediation result: {rem_result.message}")
                else:
                    # Backward-compatible behavior: match playbooks by triggers.
                    force_approval = False
                    try:
                        pb = self.remediation_engine.can_remediate(final_report.incident_type.value, final_report.final_confidence_score)
                        steps = []
                        if pb:
                            steps = [s.model_dump() if hasattr(s, "model_dump") else getattr(s, "__dict__", {}) for s in (pb.steps or [])]
                            risk_payload, risk_meta = self.reasoner.assess_playbook_risk(
                                incident=final_report,
                                playbook_name=pb.name,
                                playbook_steps=steps,
                                session=gemini_session,
                            )
                            decision_log.append(
                                {
                                    "stage": "remediation_risk",
                                    "summary": str(risk_payload.get("rationale", ""))[:280],
                                    "playbook": pb.name,
                                    "risk": risk_payload,
                                    "meta": risk_meta,
                                }
                            )
                            force_approval = bool(risk_payload.get("require_approval"))
                    except Exception as e:
                        logger.warning(f"[CYCLE {cycle_id}] Remediation risk assessment failed (non-fatal). error={e}")

                    rem_result = self.remediation_engine.execute_remediation(
                        incident_id=final_report.report_id,
                        incident_type=final_report.incident_type.value,
                        confidence=final_report.final_confidence_score,
                        context={"evidence": [e.model_dump() for e in evidence_chain]},
                    )
                    logger.info(f"[CYCLE {cycle_id}] Remediation result: {rem_result.message}")

            # 7. ESCALATE
            banner(f"Cycle {cycle_id}", "Phase 7: Escalation")
            logger.info(f"[CYCLE {cycle_id}] Phase 7: Escalation")
            if final_report.final_confidence_score >= self.config.system.confidence_threshold:
                results = self.escalator.broadcast(final_report)
                for channel, success in results.items():
                    alert_level = self.escalator._determine_alert_level(final_report)
                    self.metrics.record_alert(channel, success, alert_level)
                logger.info(f"[CYCLE {cycle_id}] Alert broadcast done")
            else:
                logger.info(f"[CYCLE {cycle_id}] Confidence below threshold. No alert sent.")

            logger.info(f"--- CYCLE {cycle_id} COMPLETE ---")

            # 8. META-LEARNING (Periodic Analysis)
            if cycle_id % 5 == 0:
                banner(f"Cycle {cycle_id}", "Phase 8: Meta-Learning")
                logger.info(f"[CYCLE {cycle_id}] Phase 8: Meta-Learning Periodic Analysis")
                self.meta_learner.analyze_patterns()

            return final_report

        except (ObserverError, ReasonerError, InvestigatorError, VerifierError, HistorianError) as e:
            logger.error(f"[CYCLE {cycle_id}] Component error: {e}")
            raise

        except Exception as e:
            logger.error(f"[CYCLE {cycle_id}] Unexpected error: {e}")
            raise SystemError(
                f"Cycle {cycle_id} failed unexpectedly: {e}",
                component="PerceptixSystem",
                context={"cycle_id": cycle_id}
            )
        finally:
            cycle_duration = (time.time() - cycle_start_time) * 1000
            try:
                self.metrics.record_cycle(cycle_id, cycle_duration, had_anomaly)
                if hypothesis_confidence is not None and verification_status:
                    self.metrics.record_hypothesis(hypothesis_confidence, verification_status)
                self.historian.save_metric("cycle_duration", cycle_duration)
                if hypothesis_confidence is not None:
                    self.historian.save_metric("confidence", hypothesis_confidence)
                if had_anomaly:
                    self.historian.save_metric("anomalies_detected", 1.0)
            except Exception as metrics_error:
                logger.warning(f"[CYCLE {cycle_id}] Failed to persist cycle metrics: {metrics_error}")
            self.last_cycle_timestamp = datetime.now().isoformat()

    def get_metrics_summary(self):
        return self.metrics.get_summary()

    def shutdown(self) -> None:
        logger.info("Shutting down Perceptix system...")
        try:
            self.db_manager.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


if __name__ == "__main__":
    print("Please use the CLI tool or API to run Perceptix.")
