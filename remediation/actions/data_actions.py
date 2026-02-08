"""
Data Actions - File operations and data fixes
Handles backup, restore, and configuration file updates.
"""
import os
import shutil
import yaml
import glob
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from remediation.actions.base import Action, ActionResult, ActionStatus


class BackupFileAction(Action):
    """
    Backup a file to a specified destination.
    """

    def __init__(self):
        super().__init__(
            name="backup_file",
            description="Backup a file to destination directory",
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        required = ["file", "destination"]
        return all(key in params for key in required)

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Params:
            file: Path to file to backup
            destination: Destination directory
        """
        try:
            source_file = str(params["file"])
            dest_dir = str(params["destination"])

            source_path = Path(source_file).expanduser()
            dest_path = Path(dest_dir).expanduser()

            # Keep behavior predictable: resolve relative to current working directory
            cwd = Path(os.getcwd())
            source_abs = (cwd / source_path).resolve() if not source_path.is_absolute() else source_path.resolve()
            dest_abs = (cwd / dest_path).resolve() if not dest_path.is_absolute() else dest_path.resolve()

            if not source_abs.exists():
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Source file not found: {source_abs}",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details={
                        "params": params,
                        "source_resolved": str(source_abs),
                        "destination_resolved": str(dest_abs),
                        "cwd": str(cwd),
                    },
                    error="FileNotFoundError",
                )

            os.makedirs(dest_abs, exist_ok=True)

            filename = source_abs.name
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{filename}.backup_{timestamp_str}"
            backup_abs = (dest_abs / backup_name).resolve()

            shutil.copy2(str(source_abs), str(backup_abs))  # copy2 preserves metadata where possible [web:124]

            self.logger.info(f"Backed up {source_abs} to {backup_abs}")

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Successfully backed up file to {backup_abs}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={
                    "source": str(source_abs),
                    "backup": str(backup_abs),
                    "destination_dir": str(dest_abs),
                },
                rollback_data={"backup_path": str(backup_abs)},
            )

        except Exception as e:
            self.logger.exception("Backup failed with exception")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Backup failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"params": params, "cwd": os.getcwd()},
                error=f"{type(e).__name__}: {str(e)}",
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback backup (delete backup file).
        """
        try:
            backup_path = rollback_data.get("backup_path")
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    message=f"Removed backup: {backup_path}",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details=rollback_data,
                )

            return ActionResult(
                status=ActionStatus.SKIPPED,
                message="Backup file not found, nothing to rollback",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
            )

        except Exception as e:
            self.logger.exception("Rollback failed with exception")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Rollback failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
                error=f"{type(e).__name__}: {str(e)}",
            )


class RestoreFileAction(Action):
    """
    Restore a file from backup.

    Supports literal paths AND glob patterns (e.g. backups/foo.backup_*).
    """

    def __init__(self):
        super().__init__(
            name="restore_file",
            description="Restore a file from backup",
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        return "backup" in params and "destination" in params

    def _resolve_backup(self, backup_spec: str) -> Dict[str, Any]:
        """
        Returns dict with keys:
        - resolved_backup (or None)
        - matches (list)
        """
        matches = glob.glob(backup_spec)
        if matches:
            # Choose newest by modification time [web:123]
            newest = max(matches, key=os.path.getmtime)
            return {"resolved_backup": newest, "matches": matches}

        if os.path.exists(backup_spec):
            return {"resolved_backup": backup_spec, "matches": []}

        return {"resolved_backup": None, "matches": []}

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Params:
            backup: Path (or glob) to backup file
            destination: Destination file path
        """
        try:
            backup_spec = str(params["backup"])
            dest_path = str(params["destination"])

            resolved = self._resolve_backup(backup_spec)
            backup_path = resolved["resolved_backup"]

            if not backup_path:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Backup file not found (literal or glob): {backup_spec}",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details={
                        "params": params,
                        "backup_spec": backup_spec,
                        "glob_matches": resolved["matches"],
                        "cwd": os.getcwd(),
                    },
                    error="BackupNotFound",
                )

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(backup_path, dest_path)

            self.logger.info(f"Restored {backup_path} to {dest_path}")

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Successfully restored file to {dest_path}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"backup": backup_path, "destination": dest_path},
                rollback_data={"restored_path": dest_path},
            )

        except Exception as e:
            self.logger.exception("Restore failed with exception")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Restore failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"params": params, "cwd": os.getcwd()},
                error=f"{type(e).__name__}: {str(e)}",
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        return ActionResult(
            status=ActionStatus.SKIPPED,
            message="Rollback not supported for restore action",
            action_name=self.name,
            timestamp=datetime.now(),
            details=rollback_data,
        )


class UpdateYAMLAction(Action):
    """
    Update a value in a YAML file.
    """

    def __init__(self):
        super().__init__(
            name="update_yaml",
            description="Update value in YAML configuration file",
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        required = ["file", "path", "changes"]
        return all(key in params for key in required)

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Params:
            file: Path to YAML file
            path: Dot-separated path to value (e.g., "tables.orders.columns")
            changes: List of dicts with 'old' and 'new' values
        """
        try:
            yaml_file = str(params["file"])
            path_parts = str(params["path"]).split(".")
            changes = params["changes"]

            if not os.path.exists(yaml_file):
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"YAML file not found: {yaml_file}",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details=params,
                    error="FileNotFoundError",
                )

            # Read YAML file
            with open(yaml_file, 'r') as f:
                data = yaml.safe_load(f)
                if data is None:
                    data = {}

            current = data
            for part in path_parts[:-1]:
                if not isinstance(current, dict) or part not in current:
                    return ActionResult(
                        status=ActionStatus.FAILED,
                        message=f"Path not found in YAML: {params['path']}",
                        action_name=self.name,
                        timestamp=datetime.now(),
                        details=params,
                        error="InvalidPath",
                    )
                current = current[part]

            last_key = path_parts[-1]
            if not isinstance(current, dict) or last_key not in current:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Key not found: {last_key}",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details=params,
                    error="KeyNotFound",
                )

            original_value = current[last_key]

            # Apply changes
            if isinstance(current[last_key], list):
                updated_list = []
                for item in current[last_key]:
                    replaced = False
                    for change in changes:
                        if item == change["old"]:
                            updated_list.append(change["new"])
                            replaced = True
                            break
                    if not replaced:
                        updated_list.append(item)
                current[last_key] = updated_list

            elif isinstance(current[last_key], str):
                updated = current[last_key]
                for change in changes:
                    updated = updated.replace(change["old"], change["new"])
                current[last_key] = updated

            else:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Unsupported YAML value type at {params['path']}: {type(current[last_key]).__name__}",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details={"params": params, "value_type": type(current[last_key]).__name__},
                    error="UnsupportedType",
                )

            with open(yaml_file, "w") as f:
                yaml.dump(data, f, default_flow_style=False)

            self.logger.info(f"Updated YAML file: {yaml_file}")

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Successfully updated {yaml_file}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"file": yaml_file, "changes": changes},
                rollback_data={
                    "file": yaml_file,
                    "path": params["path"],
                    "original_value": original_value,
                },
            )

        except Exception as e:
            self.logger.exception("YAML update failed with exception")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"YAML update failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"params": params, "cwd": os.getcwd()},
                error=f"{type(e).__name__}: {str(e)}",
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        try:
            yaml_file = rollback_data["file"]
            path_parts = rollback_data["path"].split(".")
            original_value = rollback_data["original_value"]

            with open(yaml_file, "r") as f:
                data = yaml.safe_load(f)

            current = data
            for part in path_parts[:-1]:
                current = current[part]

            current[path_parts[-1]] = original_value

            with open(yaml_file, "w") as f:
                yaml.dump(data, f, default_flow_style=False)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Successfully rolled back YAML changes in {yaml_file}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
            )

        except Exception as e:
            self.logger.exception("YAML rollback failed with exception")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"YAML rollback failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=rollback_data,
                error=f"{type(e).__name__}: {str(e)}",
            )


# Register actions
from remediation.actions.base import get_global_registry

registry = get_global_registry()
registry.register("backup_file", BackupFileAction)
registry.register("restore_file", RestoreFileAction)
registry.register("update_yaml", UpdateYAMLAction)
