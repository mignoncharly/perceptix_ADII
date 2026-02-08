"""
Approval Gate - Safety mechanism for high-risk actions
Requires human approval before executing destructive actions.
"""
import logging
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


logger = logging.getLogger("ApprovalGate")


class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalToken:
    """Token representing an approval request."""
    token_id: str
    action: str
    details: Dict[str, Any]
    requested_at: datetime
    expires_at: datetime
    status: ApprovalStatus
    approved_by: Optional[str] = None
    approval_comment: Optional[str] = None


class ApprovalGate:
    """
    Manages approval workflow for high-risk remediation actions.
    """

    def __init__(self, timeout_minutes: int = 30):
        """
        Initialize approval gate.

        Args:
            timeout_minutes: Timeout for approval requests (default: 30 minutes)
        """
        self.timeout_minutes = timeout_minutes
        self.pending_approvals: Dict[str, ApprovalToken] = {}
        self.logger = logging.getLogger("ApprovalGate")

    def requires_approval(self, action: str, params: Dict[str, Any]) -> bool:
        """
        Check if action requires approval.

        Args:
            action: Action name
            params: Action parameters

        Returns:
            True if requires approval, False otherwise
        """
        # High-risk keywords
        high_risk_keywords = [
            'delete', 'drop', 'truncate', 'remove', 'destroy',
            'scale_down', 'terminate', 'kill'
        ]

        # Check action name
        action_lower = action.lower()
        if any(keyword in action_lower for keyword in high_risk_keywords):
            return True

        # Check for production environment
        if params.get('environment', '').lower() == 'production':
            return True

        # Check for large-scale operations
        if params.get('count', 0) > 10:  # More than 10 resources
            return True

        return False

    def request_approval(
        self,
        action: str,
        details: Dict[str, Any],
        requester: str = "system"
    ) -> ApprovalToken:
        """
        Create an approval request.

        Args:
            action: Action requiring approval
            details: Action details
            requester: Who is requesting the approval

        Returns:
            ApprovalToken for tracking
        """
        token_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=self.timeout_minutes)

        token = ApprovalToken(
            token_id=token_id,
            action=action,
            details=details,
            requested_at=now,
            expires_at=expires_at,
            status=ApprovalStatus.PENDING
        )

        self.pending_approvals[token_id] = token

        self.logger.info(f"Approval requested for {action} (token: {token_id})")

        # Send actual approval request through configured channels (Slack/email if configured).
        self._send_notification(
            f"⚠️ *APPROVAL REQUIRED*: Remediation action '{action}' requires manual approval.",
            token
        )

        return token

    def check_approval(self, token_id: str) -> ApprovalStatus:
        """
        Check status of an approval request.

        Args:
            token_id: Approval token ID

        Returns:
            Current approval status
        """
        token = self.pending_approvals.get(token_id)

        if not token:
            return ApprovalStatus.EXPIRED

        # Check if expired
        if datetime.now() > token.expires_at:
            token.status = ApprovalStatus.EXPIRED
            return ApprovalStatus.EXPIRED

        return token.status

    def approve(
        self,
        token_id: str,
        approver: str,
        comment: Optional[str] = None
    ) -> bool:
        """
        Approve a pending request.

        Args:
            token_id: Approval token ID
            approver: Who is approving
            comment: Optional approval comment

        Returns:
            True if approved successfully, False otherwise
        """
        token = self.pending_approvals.get(token_id)

        if not token:
            self.logger.error(f"Approval token not found: {token_id}")
            return False

        if token.status != ApprovalStatus.PENDING:
            self.logger.error(f"Token not pending: {token_id} (status: {token.status})")
            return False

        if datetime.now() > token.expires_at:
            token.status = ApprovalStatus.EXPIRED
            self.logger.error(f"Token expired: {token_id}")
            return False

        # Approve
        token.status = ApprovalStatus.APPROVED
        token.approved_by = approver
        token.approval_comment = comment

        self.logger.info(f"Action approved: {token.action} by {approver}")

        # Send confirmation notification
        self._send_notification(
            f"✅ *ACTION APPROVED*: '{token.action}' approved by {approver}.",
            token
        )

        return True

    def reject(
        self,
        token_id: str,
        rejector: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Reject a pending request.

        Args:
            token_id: Approval token ID
            rejector: Who is rejecting
            reason: Rejection reason

        Returns:
            True if rejected successfully, False otherwise
        """
        token = self.pending_approvals.get(token_id)

        if not token:
            self.logger.error(f"Approval token not found: {token_id}")
            return False

        if token.status != ApprovalStatus.PENDING:
            self.logger.error(f"Token not pending: {token_id}")
            return False

        # Reject
        token.status = ApprovalStatus.REJECTED
        token.approved_by = rejector
        token.approval_comment = reason

        self.logger.info(f"Action rejected: {token.action} by {rejector}")

        # Send rejection notification
        self._send_notification(
            f"❌ *ACTION REJECTED*: '{token.action}' rejected by {rejector}. Reason: {reason}",
            token
        )

        return True

    def _send_notification(self, message: str, token: ApprovalToken):
        """Send notification via configured channels."""
        try:
            from config import load_config
            import requests

            config = load_config()
            
            # 1. Slack notification
            webhook_url = config.notification.slack_webhook_url
            if webhook_url:
                payload = {
                    "text": message,
                    "attachments": [{
                        "color": "#ffc107" if token.status == ApprovalStatus.PENDING else "#28a745" if token.status == ApprovalStatus.APPROVED else "#dc3545",
                        "fields": [
                            {"title": "Token", "value": token.token_id, "short": True},
                            {"title": "Expires", "value": token.expires_at.isoformat(), "short": True}
                        ]
                    }]
                }
                requests.post(webhook_url, json=payload, timeout=5)

            # 2. Email notification
            if (
                config.notification.email_smtp_host
                and config.notification.email_from
                and config.notification.email_to
            ):
                import smtplib
                from email.mime.text import MIMEText
                
                msg = MIMEText(f"{message}\n\nToken ID: {token.token_id}\nDetails: {token.details}")
                msg['Subject'] = f"Perceptix Approval Gate: {token.action}"
                msg['From'] = config.notification.email_from
                msg['To'] = config.notification.email_to

                with smtplib.SMTP(config.notification.email_smtp_host, config.notification.email_smtp_port, timeout=5) as server:
                    server.ehlo()
                    if config.notification.email_use_tls and server.has_extn('STARTTLS'):
                        server.starttls()
                        server.ehlo()
                    if config.notification.email_password:
                        server.login(config.notification.email_from, config.notification.email_password)
                    server.send_message(msg)

        except Exception as e:
            self.logger.error(f"Failed to send approval notification: {e}")

    def wait_for_approval(
        self,
        token_id: str,
        timeout_seconds: Optional[int] = None
    ) -> ApprovalStatus:
        """
        Wait for approval (blocking).

        Args:
            token_id: Approval token ID
            timeout_seconds: Max seconds to wait (default: use token expiration)

        Returns:
            Final approval status
        """
        import time

        token = self.pending_approvals.get(token_id)
        if not token:
            return ApprovalStatus.EXPIRED

        # Determine timeout
        if timeout_seconds:
            deadline = datetime.now() + timedelta(seconds=timeout_seconds)
        else:
            deadline = token.expires_at

        # Poll for approval
        while datetime.now() < deadline:
            status = self.check_approval(token_id)

            if status != ApprovalStatus.PENDING:
                return status

            # Wait a bit before checking again
            time.sleep(1)

        # Timeout
        token.status = ApprovalStatus.EXPIRED
        return ApprovalStatus.EXPIRED

    def cleanup_expired(self) -> int:
        """
        Remove expired approval tokens.

        Returns:
            Number of tokens cleaned up
        """
        now = datetime.now()
        expired_tokens = [
            token_id
            for token_id, token in self.pending_approvals.items()
            if now > token.expires_at
        ]

        for token_id in expired_tokens:
            token = self.pending_approvals[token_id]
            token.status = ApprovalStatus.EXPIRED
            del self.pending_approvals[token_id]

        if expired_tokens:
            self.logger.info(f"Cleaned up {len(expired_tokens)} expired approval tokens")

        return len(expired_tokens)

    def get_pending_approvals(self) -> list[ApprovalToken]:
        """
        Get all pending approval requests.

        Returns:
            List of pending approval tokens
        """
        return [
            token
            for token in self.pending_approvals.values()
            if token.status == ApprovalStatus.PENDING
        ]
