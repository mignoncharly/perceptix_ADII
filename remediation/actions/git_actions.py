"""
Git Actions - Version control operations
Handles Git operations like creating PRs, committing changes, etc.
"""
import logging
import subprocess
from typing import Dict, Any
from datetime import datetime

from remediation.actions.base import Action, ActionResult, ActionStatus


class CreatePullRequestAction(Action):
    """
    Create a pull request with automated fix.
    """

    def __init__(self):
        super().__init__(
            name="create_pull_request",
            description="Create pull request for automated fix"
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters."""
        required = ['branch', 'title', 'body']
        return all(key in params for key in required)

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Create pull request.

        Params:
            branch: Branch name for the PR
            title: PR title
            body: PR description
            base: Base branch (default: main)
            labels: Optional list of labels
        """
        try:
            branch = params['branch']
            title = params['title']
            body = params['body']
            base = params.get('base', 'main')
            labels = params.get('labels', [])

            # Actual Git operations
            self.logger.info(f"Creating PR: {title} (branch: {branch})")

            # 1. Create and checkout new branch
            subprocess.run(['git', 'checkout', '-b', branch], check=True)
            
            # 2. Add changes
            subprocess.run(['git', 'add', '.'], check=True)
            
            # 3. Commit
            subprocess.run(['git', 'commit', '-m', title], check=True)
            
            # 4. Push (requires remote configuration)
            # subprocess.run(['git', 'push', '-u', 'origin', branch], check=True)

            pr_data = {
                'branch': branch,
                'title': title,
                'body': body,
                'base': base,
                'labels': labels,
                'pr_number': 0,  # PR number would come from API
                'pr_url': "Local branch created. Remote push/PR requires API configuration."
            }

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Local branch {branch} created and changes committed.",
                action_name=self.name,
                timestamp=datetime.now(),
                details=pr_data,
                rollback_data={"branch": branch}
            )

        except Exception as e:
            self.logger.error(f"PR creation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"PR creation failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=params,
                error=str(e)
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback PR creation (close PR, delete branch).
        """
        try:
            branch = rollback_data.get('branch')
            pr_number = rollback_data.get('pr_number')

            # Delete local branch
            self.logger.info(f"Rolling back PR changes, deleting branch {branch}")
            
            # Switch back to main first
            subprocess.run(['git', 'checkout', 'main'], check=True)
            subprocess.run(['git', 'branch', '-D', branch], check=True)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Rolled back PR #{pr_number}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data
            )

        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"PR rollback failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
                error=str(e)
            )


class CommitChangesAction(Action):
    """
    Commit changes to Git repository.
    """

    def __init__(self):
        super().__init__(
            name="commit_changes",
            description="Commit changes to Git"
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters."""
        required = ['message', 'files']
        return all(key in params for key in required)

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Commit changes.

        Params:
            message: Commit message
            files: List of files to commit
            author: Optional author override
        """
        try:
            message = params['message']
            files = params['files']
            author = params.get('author')

            # Actual Git commands
            self.logger.info(f"Committing changes: {message}")
            for f in files:
                subprocess.run(['git', 'add', f], check=True)
            
            subprocess.run(['git', 'commit', '-m', message], check=True)
            
            # Get commit hash
            result = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True)
            commit_hash = result.stdout.strip()

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Changes committed: {commit_hash}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"commit": commit_hash, "files": files},
                rollback_data={"commit": commit_hash}
            )

        except Exception as e:
            self.logger.error(f"Commit failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Commit failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=params,
                error=str(e)
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback commit (git reset).
        """
        try:
            commit_hash = rollback_data.get('commit')

            # Reset commit
            self.logger.info(f"Reverting commit: {commit_hash}")
            subprocess.run(['git', 'reset', '--hard', 'HEAD~1'], check=True)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Reverted commit {commit_hash}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data
            )

        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Commit rollback failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
                error=str(e)
            )


# Register actions
from remediation.actions.base import get_global_registry

registry = get_global_registry()
registry.register('create_pull_request', CreatePullRequestAction)
registry.register('commit_changes', CommitChangesAction)


class GitTagAction(Action):
    """
    Create a Git tag for release/incident.
    """

    def __init__(self):
        super().__init__(
            name="git_tag",
            description="Create a Git tag"
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        return 'tag_name' in params

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        try:
            tag_name = params['tag_name']
            message = params.get('message', f"Incident response: {tag_name}")
            
            subprocess.run(['git', 'tag', '-a', tag_name, '-m', message], check=True)
            
            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Git tag created: {tag_name}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"tag": tag_name},
                rollback_data={"tag": tag_name}
            )
        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Tag creation failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=params,
                error=str(e)
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        try:
            tag_name = rollback_data['tag']
            subprocess.run(['git', 'tag', '-d', tag_name], check=True)
            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Deleted Git tag: {tag_name}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data
            )
        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Tag delete failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
                error=str(e)
            )


registry.register('git_tag', GitTagAction)
