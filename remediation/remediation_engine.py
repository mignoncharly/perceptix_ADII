"""
Remediation Engine - Main orchestrator for automated remediation
Coordinates playbook execution, approval workflows, and rollback.
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

from config import PerceptixConfig
from database import DatabaseManager
from historian import Historian
from remediation.executor import PlaybookExecutor, Playbook, PlaybookExecution
from remediation.approval_gate import ApprovalGate, ApprovalStatus
from remediation.actions.base import get_global_registry


logger = logging.getLogger("RemediationEngine")


@dataclass
class RemediationResult:
    """Result of a remediation attempt."""
    success: bool
    incident_id: str
    playbook_name: str
    execution: Optional[PlaybookExecution]
    approval_required: bool
    approval_status: Optional[ApprovalStatus] = None
    message: str = ""
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class RemediationEngine:
    """
    Main engine for automated remediation.

    Orchestrates:
    - Playbook matching and execution
    - Approval workflows for high-risk actions
    - Rollback on failure
    - Audit logging
    """

    def __init__(
        self,
        config: PerceptixConfig,
        db_manager: Optional[DatabaseManager] = None,
        historian: Optional[Historian] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize remediation engine.

        Args:
            config: System configuration
        """
        self.config = config
        self.db_manager = db_manager
        self.historian = historian
        self.tenant_id = tenant_id
        self.action_registry = get_global_registry()
        self.executor = PlaybookExecutor(self.action_registry)
        self.approval_gate = ApprovalGate(timeout_minutes=30)
        self.logger = logging.getLogger("RemediationEngine")

        # Load actions (ensure they're registered)
        self._load_actions()

        # Load playbooks
        playbook_dir = Path("remediation/playbooks")
        if playbook_dir.exists():
            count = self.executor.load_playbooks_from_directory(str(playbook_dir))
            self.logger.info(f"Loaded {count} playbooks")
        else:
            self.logger.warning(f"Playbook directory not found: {playbook_dir}")

    def _load_actions(self):
        """Load all action modules to ensure registration."""
        try:
            # Import action modules to trigger registration
            import remediation.actions.data_actions
            import remediation.actions.notification_actions
            import remediation.actions.git_actions
            self.logger.info("Action modules loaded")
        except Exception as e:
            self.logger.error(f"Failed to load action modules: {e}")

    def can_remediate(
        self,
        incident_type: str,
        confidence: float
    ) -> Optional[Playbook]:
        """
        Check if incident can be remediated automatically.

        Args:
            incident_type: Type of incident
            confidence: Confidence score (0-100)

        Returns:
            Matching playbook or None if no match
        """
        for playbook_name in self.executor.list_playbooks():
            playbook = self.executor.get_playbook(playbook_name)

            if playbook and self.executor.matches_trigger(playbook, incident_type, confidence):
                self.logger.info(f"Found matching playbook: {playbook_name}")
                return playbook

        self.logger.info(f"No playbook matches incident: {incident_type}")
        return None

    def execute_remediation(
        self,
        incident_id: str,
        incident_type: str,
        confidence: float,
        context: Optional[Dict[str, Any]] = None,
        dry_run: bool = False
    ) -> RemediationResult:
        """
        Execute remediation for an incident.

        Args:
            incident_id: Incident identifier
            incident_type: Type of incident
            confidence: Confidence score
            context: Additional context for playbook execution
            dry_run: If True, simulate without making changes

        Returns:
            RemediationResult with execution status
        """
        self.logger.info(f"Attempting remediation for incident {incident_id} ({incident_type})")

        # Find matching playbook
        playbook = self.can_remediate(incident_type, confidence)

        if not playbook:
            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name="",
                execution=None,
                approval_required=False,
                message=f"No playbook found for incident type: {incident_type}"
            )

        # Prepare context
        execution_context = context or {}
        execution_context.update({
            'incident_id': incident_id,
            'incident_type': incident_type,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat()
        })

        # Check conditions
        if not self.executor.check_conditions(playbook, execution_context):
            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook.name,
                execution=None,
                approval_required=False,
                message="Playbook conditions not met"
            )

        # Check if approval required
        requires_approval = self._check_approval_required(playbook)

        if requires_approval and not dry_run:
            # Request approval
            approval_token = self.approval_gate.request_approval(
                action=playbook.name,
                details={
                    'incident_id': incident_id,
                    'incident_type': incident_type,
                    'confidence': confidence,
                    'playbook': playbook.name
                }
            )

            if self.historian:
                self.historian.create_remediation_approval(
                    token_id=approval_token.token_id,
                    tenant_id=self.tenant_id,
                    incident_id=incident_id,
                    playbook_name=playbook.name,
                    status="pending",
                    requested_at=approval_token.requested_at.isoformat(),
                    expires_at=approval_token.expires_at.isoformat(),
                    requested_by="system",
                    context=execution_context,
                    details=approval_token.details,
                )

            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook.name,
                execution=None,
                approval_required=True,
                approval_status=ApprovalStatus.PENDING,
                message=f"Approval required (token: {approval_token.token_id})"
            )

        # Execute playbook
        started_at = datetime.now().isoformat()
        execution = self.executor.execute_playbook(
            playbook=playbook,
            context=execution_context,
            dry_run=dry_run
        )
        finished_at = datetime.now().isoformat()

        if self.historian and not dry_run:
            try:
                self.historian.record_remediation_execution(
                    tenant_id=self.tenant_id,
                    incident_id=incident_id,
                    playbook_name=playbook.name,
                    success=bool(execution.success),
                    started_at=started_at,
                    finished_at=finished_at,
                    execution=execution.model_dump() if hasattr(execution, "model_dump") else getattr(execution, "__dict__", {}),
                )
            except Exception as e:
                self.logger.error("Failed to persist remediation execution: %s", e)

        return RemediationResult(
            success=execution.success,
            incident_id=incident_id,
            playbook_name=playbook.name,
            execution=execution,
            approval_required=False,
            message=f"Remediation {'succeeded' if execution.success else 'failed'}"
        )

    def execute_playbook_for_incident(
        self,
        incident_id: str,
        playbook_name: str,
        incident_type: str,
        confidence: float,
        context: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        force_approval: bool = False,
    ) -> RemediationResult:
        """
        Execute a specific playbook for an incident (policy-driven routing).
        """
        playbook = self.executor.get_playbook(playbook_name)
        if not playbook:
            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook_name,
                execution=None,
                approval_required=False,
                message=f"Playbook not found: {playbook_name}",
            )

        execution_context = context or {}
        execution_context.update(
            {
                "incident_id": incident_id,
                "incident_type": incident_type,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat(),
            }
        )

        if not self.executor.check_conditions(playbook, execution_context):
            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook.name,
                execution=None,
                approval_required=False,
                message="Playbook conditions not met",
            )

        requires_approval = force_approval or self._check_approval_required(playbook)
        if requires_approval and not dry_run:
            approval_token = self.approval_gate.request_approval(
                action=playbook.name,
                details={
                    "incident_id": incident_id,
                    "incident_type": incident_type,
                    "confidence": confidence,
                    "playbook": playbook.name,
                    "forced": bool(force_approval),
                },
            )

            if self.historian:
                self.historian.create_remediation_approval(
                    token_id=approval_token.token_id,
                    tenant_id=self.tenant_id,
                    incident_id=incident_id,
                    playbook_name=playbook.name,
                    status="pending",
                    requested_at=approval_token.requested_at.isoformat(),
                    expires_at=approval_token.expires_at.isoformat(),
                    requested_by="system",
                    context=execution_context,
                    details=approval_token.details,
                )

            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook.name,
                execution=None,
                approval_required=True,
                approval_status=ApprovalStatus.PENDING,
                message=f"Approval required (token: {approval_token.token_id})",
            )

        started_at = datetime.now().isoformat()
        execution = self.executor.execute_playbook(
            playbook=playbook,
            context=execution_context,
            dry_run=dry_run,
        )
        finished_at = datetime.now().isoformat()

        if self.historian and not dry_run:
            try:
                self.historian.record_remediation_execution(
                    tenant_id=self.tenant_id,
                    incident_id=incident_id,
                    playbook_name=playbook.name,
                    success=bool(execution.success),
                    started_at=started_at,
                    finished_at=finished_at,
                    execution=execution.model_dump() if hasattr(execution, "model_dump") else getattr(execution, "__dict__", {}),
                )
            except Exception as e:
                self.logger.error("Failed to persist remediation execution: %s", e)

        return RemediationResult(
            success=execution.success,
            incident_id=incident_id,
            playbook_name=playbook.name,
            execution=execution,
            approval_required=False,
            message=f"Remediation {'succeeded' if execution.success else 'failed'}",
        )

    def _check_approval_required(self, playbook: Playbook) -> bool:
        """
        Check if playbook requires approval.

        Args:
            playbook: Playbook to check

        Returns:
            True if approval required, False otherwise
        """
        # Check if any step requires approval
        for step in playbook.steps:
            if self.approval_gate.requires_approval(step.action, step.params):
                return True

        return False

    def rollback_remediation(
        self,
        incident_id: str,
        playbook_name: str
    ) -> RemediationResult:
        """
        Rollback a previous remediation.

        Args:
            incident_id: Incident that was remediated
            playbook_name: Playbook that was executed

        Returns:
            RemediationResult with rollback status
        """
        self.logger.info(f"Rolling back remediation for incident {incident_id}")

        playbook = self.executor.get_playbook(playbook_name)

        if not playbook:
            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook_name,
                execution=None,
                approval_required=False,
                message=f"Playbook not found: {playbook_name}"
            )

        # Execute rollback steps
        if not playbook.rollback:
            return RemediationResult(
                success=False,
                incident_id=incident_id,
                playbook_name=playbook_name,
                execution=None,
                approval_required=False,
                message="Playbook has no rollback steps defined"
            )

        # Create a temporary playbook with just rollback steps
        rollback_playbook = Playbook(
            name=f"{playbook.name}_rollback",
            description=f"Rollback for {playbook.name}",
            triggers=[],
            conditions=[],
            steps=playbook.rollback,
            rollback=[]
        )

        # Execute rollback
        execution = self.executor.execute_playbook(
            playbook=rollback_playbook,
            context={'incident_id': incident_id},
            dry_run=False
        )

        return RemediationResult(
            success=execution.success,
            incident_id=incident_id,
            playbook_name=playbook_name,
            execution=execution,
            approval_required=False,
            message=f"Rollback {'succeeded' if execution.success else 'failed'}"
        )

    def list_playbooks(self) -> List[Dict[str, Any]]:
        """
        List all available playbooks.

        Returns:
            List of playbook information
        """
        playbooks = []

        for name in self.executor.list_playbooks():
            playbook = self.executor.get_playbook(name)
            if playbook:
                playbooks.append({
                    'name': playbook.name,
                    'description': playbook.description,
                    'steps': len(playbook.steps),
                    'triggers': playbook.triggers,
                    'has_rollback': len(playbook.rollback) > 0
                })

        return playbooks

    def get_pending_approvals(self) -> list:
        """
        Get all pending approval requests.

        Returns:
            List of pending approvals
        """
        if self.historian:
            approvals = self.historian.get_pending_remediation_approvals()
            return [
                {
                    "token_id": a["token_id"],
                    "action": a["playbook_name"],
                    "details": a.get("details") or {},
                    "requested_at": a["requested_at"],
                    "expires_at": a["expires_at"],
                }
                for a in approvals
            ]

        approvals = self.approval_gate.get_pending_approvals()

        return [
            {
                'token_id': approval.token_id,
                'action': approval.action,
                'details': approval.details,
                'requested_at': approval.requested_at.isoformat(),
                'expires_at': approval.expires_at.isoformat()
            }
            for approval in approvals
        ]

    def approve_remediation(
        self,
        token_id: str,
        approver: str,
        comment: Optional[str] = None
    ) -> bool:
        """
        Approve a pending remediation.

        Args:
            token_id: Approval token ID
            approver: Who is approving
            comment: Optional approval comment

        Returns:
            True if approved successfully
        """
        if not self.historian:
            return self.approval_gate.approve(token_id, approver, comment)

        approval = self.historian.get_remediation_approval(token_id)
        if not approval:
            return False
        if str(approval.get("status")) != "pending":
            return False

        # Mark approved, then execute.
        self.historian.update_remediation_approval_status(token_id, "approved", approved_by=approver, comment=comment)

        incident_id = str(approval["incident_id"])
        playbook_name = str(approval["playbook_name"])
        context = approval.get("context") or {}

        playbook = self.executor.get_playbook(playbook_name)
        if not playbook:
            self.historian.update_remediation_approval_status(token_id, "failed", approved_by=approver, comment="playbook_not_found")
            return False

        started_at = datetime.now().isoformat()
        execution = self.executor.execute_playbook(playbook=playbook, context=context, dry_run=False)
        finished_at = datetime.now().isoformat()

        self.historian.record_remediation_execution(
            tenant_id=self.tenant_id,
            incident_id=incident_id,
            playbook_name=playbook_name,
            success=bool(execution.success),
            started_at=started_at,
            finished_at=finished_at,
            execution=execution.model_dump() if hasattr(execution, "model_dump") else getattr(execution, "__dict__", {}),
        )

        self.historian.update_remediation_approval_status(
            token_id,
            "executed" if execution.success else "failed",
            approved_by=approver,
            comment=comment,
        )
        return bool(execution.success)

    def reject_remediation(
        self,
        token_id: str,
        rejector: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Reject a pending remediation.

        Args:
            token_id: Approval token ID
            rejector: Who is rejecting
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        if not self.historian:
            return self.approval_gate.reject(token_id, rejector, reason)

        approval = self.historian.get_remediation_approval(token_id)
        if not approval:
            return False
        if str(approval.get("status")) != "pending":
            return False

        return self.historian.update_remediation_approval_status(
            token_id,
            "rejected",
            approved_by=rejector,
            comment=reason,
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Get remediation engine status.

        Returns:
            Status information
        """
        return {
            'playbooks_loaded': len(self.executor.list_playbooks()),
            'actions_registered': len(self.action_registry.list_actions()),
            'pending_approvals': len(self.approval_gate.get_pending_approvals()),
            'status': 'operational'
        }
