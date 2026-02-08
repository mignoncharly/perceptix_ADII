"""
Policy Engine: Adaptive automation routing for remediation actions.

Policies are stored in the Perceptix database (table: policies) and evaluated
on each confirmed incident. Matching policies can trigger remediation playbooks
with optional approval gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from models import IncidentReport
from historian import Historian


logger = logging.getLogger("PolicyEngine")


@dataclass(frozen=True)
class PolicyAction:
    policy_id: str
    playbook: str
    require_approval: bool


class PolicyEngine:
    """
    Evaluate stored policies against an incident report.

    Policy schema (stored as JSON in DB):
      match:
        incident_types: ["DATA_INTEGRITY_FAILURE", "UPSTREAM_DELAY"]
        min_confidence: 85
        contains_any: ["schema", "null"]
      action:
        playbook: "notify_slack_and_email"
        require_approval: true
    """

    def __init__(self, historian: Historian):
        self.historian = historian

    def evaluate(self, report: IncidentReport) -> List[PolicyAction]:
        actions: List[PolicyAction] = []

        try:
            policies = self.historian.list_policies(enabled_only=True)
        except Exception as e:
            logger.error("Failed to load policies: %s", e)
            return actions

        for policy in policies:
            try:
                if not self._matches(policy.get("match") or {}, report):
                    continue

                action = policy.get("action") or {}
                playbook = str(action.get("playbook") or "").strip()
                if not playbook:
                    continue

                require_approval = bool(action.get("require_approval", False))
                actions.append(
                    PolicyAction(
                        policy_id=str(policy.get("id") or ""),
                        playbook=playbook,
                        require_approval=require_approval,
                    )
                )
            except Exception:
                continue

        return actions

    def _matches(self, match: Dict[str, Any], report: IncidentReport) -> bool:
        incident_type = report.incident_type.value
        confidence = float(report.final_confidence_score or 0.0)

        incident_types = match.get("incident_types")
        if incident_types:
            if isinstance(incident_types, str):
                incident_types = [incident_types]
            allowed = {str(x).strip() for x in (incident_types or []) if str(x).strip()}
            if "*" not in allowed and incident_type not in allowed:
                return False

        min_conf = match.get("min_confidence")
        if min_conf is not None:
            try:
                if confidence < float(min_conf):
                    return False
            except Exception:
                return False

        contains_any = match.get("contains_any")
        if contains_any:
            if isinstance(contains_any, str):
                contains_any = [contains_any]
            haystack = (report.root_cause_analysis or "").lower()
            needles = [str(x).lower() for x in (contains_any or []) if str(x)]
            if needles and not any(n in haystack for n in needles):
                return False

        return True

