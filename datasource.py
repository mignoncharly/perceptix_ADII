"""
Data Source layer for Perceptix.
Abstracts the data fetching logic to support multiple backends (SQLite, Warehouse, etc.)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import json

try:
    import aiosqlite
except ModuleNotFoundError:  # pragma: no cover - depends on environment packaging
    aiosqlite = None

logger = logging.getLogger("PerceptixDataSource")

class DataSource(ABC):
    """Abstract base class for data sources."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to data source."""
        pass
        
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass
        
    @abstractmethod
    async def get_table_metrics(self, table_name: str) -> Dict[str, Any]:
        """
        Calculate metrics for a given table.
        Returns:
            Dict containing row_count, freshness_minutes, null_rates
        """
        pass
    
    @abstractmethod
    async def get_recent_commits(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent code commits (simulated or from VCS)."""
        pass

class SQLiteDataSource(DataSource):
    """SQLite implementation of DataSource."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    async def connect(self) -> None:
        # No-op for transient connections
        pass

    async def disconnect(self) -> None:
        # No-op for transient connections
        pass

    async def get_table_metrics(self, table_name: str) -> Dict[str, Any]:
        try:
            # 1. Row count
            if aiosqlite is not None:
                async with aiosqlite.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                    async with conn.execute(f"SELECT COUNT(*) FROM {table_name}") as cursor:
                        row_count_res = await cursor.fetchone()
                        row_count = row_count_res[0] if row_count_res else 0

                    # 2. Freshness (minutes since last max timestamp)
                    ts_column_map = {
                        'orders': 'timestamp',
                        'users': 'signup_date',
                        'inventory': 'last_updated',
                        'products': None
                    }
                    ts_column = ts_column_map.get(table_name)

                    freshness_minutes = 0
                    if ts_column:
                        async with conn.execute(f"SELECT MAX({ts_column}) FROM {table_name}") as cursor:
                            max_ts_res = await cursor.fetchone()
                            max_ts_str = max_ts_res[0] if max_ts_res else None

                        if max_ts_str:
                            max_ts = datetime.fromisoformat(max_ts_str.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            if max_ts.tzinfo is None:
                                max_ts = max_ts.replace(tzinfo=timezone.utc)

                            diff = now - max_ts
                            freshness_minutes = int(diff.total_seconds() / 60)

                    # 3. Null Rates - OPTIMIZED (Single Query)
                    async with conn.execute(f"PRAGMA table_info({table_name})") as cursor:
                        columns_info = await cursor.fetchall()
                        columns = [row[1] for row in columns_info]

                    null_rates = {}
                    if columns and row_count > 0:
                        select_parts = [f"COUNT({col})" for col in columns]
                        query = f"SELECT {', '.join(select_parts)} FROM {table_name}"

                        async with conn.execute(query) as cursor:
                            non_null_counts = await cursor.fetchone()

                        if non_null_counts:
                            for idx, col in enumerate(columns):
                                non_null = non_null_counts[idx]
                                null_count = row_count - non_null
                                rate = null_count / row_count
                                null_rates[col] = round(rate, 4)
                    else:
                        for col in columns:
                            null_rates[col] = 0.0
            else:
                # Offline fallback for environments where aiosqlite is unavailable.
                import sqlite3

                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                try:
                    row_count_res = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                    row_count = row_count_res[0] if row_count_res else 0

                    ts_column_map = {
                        'orders': 'timestamp',
                        'users': 'signup_date',
                        'inventory': 'last_updated',
                        'products': None
                    }
                    ts_column = ts_column_map.get(table_name)

                    freshness_minutes = 0
                    if ts_column:
                        max_ts_res = conn.execute(f"SELECT MAX({ts_column}) FROM {table_name}").fetchone()
                        max_ts_str = max_ts_res[0] if max_ts_res else None

                        if max_ts_str:
                            max_ts = datetime.fromisoformat(max_ts_str.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            if max_ts.tzinfo is None:
                                max_ts = max_ts.replace(tzinfo=timezone.utc)

                            diff = now - max_ts
                            freshness_minutes = int(diff.total_seconds() / 60)

                    columns_info = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                    columns = [row[1] for row in columns_info]

                    null_rates = {}
                    if columns and row_count > 0:
                        select_parts = [f"COUNT({col})" for col in columns]
                        query = f"SELECT {', '.join(select_parts)} FROM {table_name}"
                        non_null_counts = conn.execute(query).fetchone()

                        if non_null_counts:
                            for idx, col in enumerate(columns):
                                non_null = non_null_counts[idx]
                                null_count = row_count - non_null
                                rate = null_count / row_count
                                null_rates[col] = round(rate, 4)
                    else:
                        for col in columns:
                            null_rates[col] = 0.0
                finally:
                    conn.close()

            return {
                "row_count": row_count,
                "freshness_minutes": freshness_minutes,
                "null_rates": null_rates,
                "table_name": table_name,
                "timestamp": datetime.now(timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"Error fetching metrics for {table_name}: {e}")
            raise
            
    async def get_recent_commits(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch recent commits from all monitored repositories.
        Currently monitors repositories in data/repos.
        This is CPU bound (git operations), so for true async we should run in executor,
        but for this prototype keeping it sync blocking within async method is 
        acceptable or we can wrap it.
        """
        try:
            import git
        except ModuleNotFoundError:
            logger.warning("GitPython not installed; returning empty commit history")
            return []
        import os
        import asyncio
        from datetime import datetime
        
        # Helper to run blocking git ops
        def _get_commits_sync():
            commits = []
            repo_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/repos"))
            
            if not os.path.exists(repo_base_dir):
                return []

            for repo_name in os.listdir(repo_base_dir):
                repo_path = os.path.join(repo_base_dir, repo_name)
                if not os.path.isdir(os.path.join(repo_path, ".git")):
                    continue
                    
                try:
                    repo = git.Repo(repo_path)
                    # Get last 'limit' commits
                    for commit in repo.iter_commits(max_count=limit):
                        # Get changed files
                        files_changed = list(commit.stats.files.keys())
                        
                        commits.append({
                            "repo": repo_name,
                            "author": commit.author.name,
                            "message": commit.message.strip(),
                            "timestamp": datetime.fromtimestamp(commit.committed_date).isoformat(),
                            "files_changed": files_changed
                        })
                except Exception as e:
                    # Log error but continue with other repos
                    print(f"Error reading repo {repo_name}: {e}")
                    continue
            return commits

        # Run CPU-bound git operations in a thread pool
        loop = asyncio.get_running_loop()
        commits = await loop.run_in_executor(None, _get_commits_sync)
                
        # Sort by timestamp desc and take top N
        commits.sort(key=lambda x: x['timestamp'], reverse=True)
        return commits[:limit]


class WarehouseDataSource(DataSource):
    """
    Warehouse-backed data source using a configured connector (BigQuery/Snowflake).

    Table naming:
      - BigQuery: use `dataset.table` in monitored_tables.
      - Snowflake: use `schema.table` or just `table` (schema from connector config).
    """

    def __init__(
        self,
        connector_type: str,
        connector_config: Dict[str, Any],
        monitored_tables: List[str],
        table_timestamp_columns: Optional[Dict[str, str]] = None,
        table_null_columns: Optional[Dict[str, List[str]]] = None,
    ):
        from connectors import ConnectorFactory

        self.connector_type = connector_type
        self.connector_config = connector_config
        self.monitored_tables = monitored_tables
        self.table_timestamp_columns = table_timestamp_columns or {}
        self.table_null_columns = table_null_columns or {}

        self._connector = ConnectorFactory.create_connector(connector_type, connector_config)
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connector.connect)
        self._connected = True

    async def disconnect(self) -> None:
        if not self._connected:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connector.disconnect)
        self._connected = False

    def _split_table(self, table_name: str) -> tuple[str, str]:
        if "." in table_name:
            a, b = table_name.split(".", 1)
            return a, b
        # Default schema/dataset is connector-specific.
        default_schema = str(self.connector_config.get("schema") or self.connector_config.get("dataset") or "").strip()
        return default_schema, table_name

    async def get_table_metrics(self, table_name: str) -> Dict[str, Any]:
        await self.connect()

        schema, table = self._split_table(table_name)
        loop = asyncio.get_running_loop()

        # Row count
        row_count = await loop.run_in_executor(None, lambda: int(self._connector.get_table_row_count(schema, table)))

        # Freshness (optional)
        freshness_minutes = 0
        ts_col = self.table_timestamp_columns.get(table_name) or self.table_timestamp_columns.get(table)
        if ts_col:
            if self.connector_type.lower() == "bigquery":
                fq = f"`{schema}.{table}`" if schema else f"`{table}`"
                query = f"SELECT MAX({ts_col}) AS max_ts FROM {fq}"
            else:
                fq = f"{schema}.{table}" if schema else table
                query = f"SELECT MAX({ts_col}) AS MAX_TS FROM {fq}"

            rows = await loop.run_in_executor(None, lambda: self._connector.execute_query(query))
            max_ts = rows[0].get("max_ts") or rows[0].get("MAX_TS") if rows else None
            if max_ts:
                # Snowflake can return datetime objects; BigQuery returns datetime-like types.
                if hasattr(max_ts, "isoformat"):
                    max_dt = max_ts
                else:
                    max_dt = datetime.fromisoformat(str(max_ts).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if getattr(max_dt, "tzinfo", None) is None:
                    max_dt = max_dt.replace(tzinfo=timezone.utc)
                freshness_minutes = int((now - max_dt).total_seconds() / 60)

        # Null rates (optional columns)
        null_rates: Dict[str, float] = {}
        cols = self.table_null_columns.get(table_name) or self.table_null_columns.get(table) or []
        if cols:
            if self.connector_type.lower() == "bigquery":
                fq = f"`{schema}.{table}`" if schema else f"`{table}`"
                parts = [f"COUNTIF({c} IS NULL) AS {c}_nulls" for c in cols]
                query = f"SELECT COUNT(*) AS total_rows, {', '.join(parts)} FROM {fq}"
                rows = await loop.run_in_executor(None, lambda: self._connector.execute_query(query))
                row = rows[0] if rows else {}
                total_rows = int(row.get("total_rows") or 0)
                for c in cols:
                    nulls = int(row.get(f"{c}_nulls") or 0)
                    null_rates[c] = (nulls / total_rows) if total_rows > 0 else 0.0
            else:
                fq = f"{schema}.{table}" if schema else table
                parts = [f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS {c}_NULLS" for c in cols]
                query = f"SELECT COUNT(*) AS TOTAL_ROWS, {', '.join(parts)} FROM {fq}"
                rows = await loop.run_in_executor(None, lambda: self._connector.execute_query(query))
                row = rows[0] if rows else {}
                total_rows = int(row.get("TOTAL_ROWS") or 0)
                for c in cols:
                    nulls = int(row.get(f"{c.upper()}_NULLS") or row.get(f"{c}_NULLS") or 0)
                    null_rates[c] = (nulls / total_rows) if total_rows > 0 else 0.0

        return {
            "row_count": int(row_count),
            "freshness_minutes": int(max(0, freshness_minutes)),
            "null_rates": null_rates,
            "table_name": table_name,
            "timestamp": datetime.now(timezone.utc),
        }

    async def get_recent_commits(self, limit: int = 5) -> List[Dict[str, Any]]:
        # Warehouse connectors do not expose VCS info; keep this empty (API remains stable).
        return []
