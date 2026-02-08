"""
Database Connection Management with Connection Pooling and Transactions
Provides production-ready database access with proper resource management.
"""
import sqlite3
try:
    import psycopg2
    from psycopg2 import pool as psycopg2_pool
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

import logging
import threading
from contextlib import contextmanager
from typing import Optional, List, Tuple, Any, Dict, Protocol
from queue import Queue, Empty
from pathlib import Path

from exceptions import (
    DatabaseError,
    ConnectionPoolExhaustedError,
    TransactionError,
    QueryExecutionError
)


logger = logging.getLogger("PerceptixDatabase")


class DatabaseConnection:
    """
    Wrapper for SQLite connection with transaction support.
    """

    def __init__(self, connection: sqlite3.Connection, pool: 'ConnectionPool'):
        self.connection = connection
        self.pool = pool
        self.in_transaction = False

    def execute(self, query: str, params: Optional[Tuple] = None) -> sqlite3.Cursor:
        """
        Execute a query with parameters.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            sqlite3.Cursor: Result cursor

        Raises:
            QueryExecutionError: If query execution fails
        """
        try:
            cursor = self.connection.cursor()
            if params:
                return cursor.execute(query, params)
            else:
                return cursor.execute(query)
        except sqlite3.Error as e:
            raise QueryExecutionError(
                f"Query execution failed: {e}",
                component="DatabaseConnection",
                context={"query": query[:100]}  # Truncate long queries
            )

    def executemany(self, query: str, params_list: List[Tuple]) -> sqlite3.Cursor:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query to execute
            params_list: List of parameter tuples

        Returns:
            sqlite3.Cursor: Result cursor

        Raises:
            QueryExecutionError: If query execution fails
        """
        try:
            cursor = self.connection.cursor()
            return cursor.executemany(query, params_list)
        except sqlite3.Error as e:
            raise QueryExecutionError(
                f"Batch query execution failed: {e}",
                component="DatabaseConnection",
                context={"query": query[:100], "batch_size": len(params_list)}
            )

    def commit(self) -> None:
        """
        Commit current transaction.

        Raises:
            TransactionError: If commit fails
        """
        try:
            self.connection.commit()
            self.in_transaction = False
        except sqlite3.Error as e:
            raise TransactionError(
                f"Transaction commit failed: {e}",
                component="DatabaseConnection"
            )

    def rollback(self) -> None:
        """
        Rollback current transaction.

        Raises:
            TransactionError: If rollback fails
        """
        try:
            self.connection.rollback()
            self.in_transaction = False
        except sqlite3.Error as e:
            raise TransactionError(
                f"Transaction rollback failed: {e}",
                component="DatabaseConnection"
            )

    def close(self) -> None:
        """Return connection to pool."""
        if self.in_transaction:
            logger.warning("Closing connection with active transaction - rolling back")
            self.rollback()
        self.pool.return_connection(self.connection)


class PostgresConnectionPool:
    """Connection pool for PostgreSQL."""
    def __init__(self, config: Any):
        if not HAS_PSYCOPG2:
            raise DatabaseError("psycopg2-binary is required for PostgreSQL support")
        
        try:
            self._pool = psycopg2_pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=config.max_connections,
                host=config.host,
                port=config.port,
                database=config.name,
                user=config.user,
                password=config.password,
                connect_timeout=config.connection_timeout
            )
            logger.info(f"Initialized PostgreSQL connection pool for {config.name}")
        except Exception as e:
            raise DatabaseError(f"Failed to initialize PostgreSQL pool: {e}")

    def get_connection(self):
        conn = self._pool.getconn()
        return PostgresDatabaseConnection(conn, self)

    def return_connection(self, connection):
        self._pool.putconn(connection)

    def close_all(self):
        self._pool.closeall()

class PostgresDatabaseConnection:
    """Wrapper for PostgreSQL connection."""
    def __init__(self, connection, pool):
        self.connection = connection
        self.pool = pool
        self.in_transaction = False

    def execute(self, query: str, params: Optional[Tuple] = None):
        try:
            # PostgreSQL uses %s instead of ?
            if "?" in query:
                query = query.replace("?", "%s")
            
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            return cursor
        except Exception as e:
            raise QueryExecutionError(f"PostgreSQL Query failed: {e}")

    def executemany(self, query: str, params_list: List[Tuple]):
        try:
            if "?" in query:
                query = query.replace("?", "%s")
            cursor = self.connection.cursor()
            cursor.executemany(query, params_list)
            return cursor
        except Exception as e:
            raise QueryExecutionError(f"PostgreSQL Batch Query failed: {e}")

    def commit(self):
        self.connection.commit()
        self.in_transaction = False

    def rollback(self):
        self.connection.rollback()
        self.in_transaction = False

    def close(self):
        if self.in_transaction:
            self.rollback()
        self.pool.return_connection(self.connection)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class SQLitePool:
    """
    Thread-safe connection pool for SQLite database.
    """

    def __init__(
        self,
        db_path: str,
        max_connections: int = 5,
        timeout: float = 30.0,
        check_same_thread: bool = False
    ):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self.check_same_thread = check_same_thread

        self._pool: Queue = Queue(maxsize=max_connections)
        self._all_connections: List[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        try:
            db_path = Path(self.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            for _ in range(self.max_connections):
                conn = self._create_connection()
                self._all_connections.append(conn)
                self._pool.put(conn)
            logger.info(f"Initialized SQLite connection pool with {self.max_connections} connections")
        except Exception as e:
            raise DatabaseError(f"Failed to initialize SQLite pool: {e}")

    def _create_connection(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=self.check_same_thread
            )
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            return conn
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to create SQLite connection: {e}")

    def get_connection(self):
        if self._closed:
            raise DatabaseError("Connection pool is closed")
        try:
            conn = self._pool.get(timeout=self.timeout)
            return DatabaseConnection(conn, self)
        except Empty:
            raise ConnectionPoolExhaustedError(f"Connection pool exhausted (max: {self.max_connections})")

    def return_connection(self, connection: sqlite3.Connection) -> None:
        if not self._closed:
            self._pool.put(connection)

    def close_all(self) -> None:
        with self._lock:
            if self._closed: return
            self._closed = True
            for conn in self._all_connections:
                try: conn.close()
                except Exception as e: logger.error(f"Error closing connection: {e}")
            self._all_connections.clear()
            logger.info("SQLite connection pool closed")


class DatabaseManager:
    """
    High-level database manager with schema management and migrations.
    """

    def __init__(self, config: Any):
        """
        Initialize database manager.

        Args:
            config: Database configuration object
        """
        self.config = config
        
        if config.type == "postgresql":
            self.pool = PostgresConnectionPool(config)
        else:
            # Fallback to SQLite (original ConnectionPool renamed to SQLitePool)
            self.pool = SQLitePool(config.path, config.max_connections)
            
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """
        Ensure database schema exists.

        Raises:
            DatabaseError: If schema creation fails
        """
        try:
            with self.transaction() as conn:
                # ID type handled properly for both
                id_type = "TEXT PRIMARY KEY" if self.config.type == "sqlite" else "VARCHAR(128) PRIMARY KEY"
                
                # Create incidents table
                conn.execute(f'''
                    CREATE TABLE IF NOT EXISTS incidents (
                        id {id_type},
                        tenant_id TEXT,
                        timestamp TEXT NOT NULL,
                        type TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        summary TEXT NOT NULL,
                        status TEXT DEFAULT 'DETECTED',
                        full_json TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Create indices for common queries
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_incidents_timestamp
                    ON incidents(timestamp)
                ''')

                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_incidents_type
                    ON incidents(type)
                ''')

                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_incidents_confidence
                    ON incidents(confidence)
                ''')

                # Create index for tenant_id for multi-tenant queries
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id
                    ON incidents(tenant_id)
                ''')

                # Create schema version table
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Insert initial version if not exists
                cursor = conn.execute('SELECT version FROM schema_version ORDER BY version DESC LIMIT 1')
                result = cursor.fetchone()
                if result is None:
                    conn.execute('INSERT INTO schema_version (version) VALUES (?)', (1,))
                    current_version = 1
                else:
                    current_version = result[0]

                # Apply migrations for all versions after baseline v1.
                if current_version < 2:
                    self._apply_migration_v2(conn)
                if current_version < 3:
                    self._apply_migration_v3(conn)
                if current_version < 4:
                    self._apply_migration_v4(conn)
                if current_version < 5:
                    self._apply_migration_v5(conn)
                if current_version < 6:
                    self._apply_migration_v6(conn)
                if current_version < 7:
                    self._apply_migration_v7(conn)

                conn.commit()

            logger.info("Database schema initialized successfully")

        except Exception as e:
            raise DatabaseError(
                f"Failed to initialize database schema: {e}",
                component="DatabaseManager"
            )

    def _apply_migration_v2(self, conn: DatabaseConnection) -> None:
        """
        Apply migration version 2: Add tenant_id column for multi-tenancy.

        Args:
            conn: Database connection

        Raises:
            DatabaseError: If migration fails
        """
        try:
            logger.info("Applying migration v2: Adding tenant_id column")

            # Check if tenant_id column already exists
            cursor = conn.execute("PRAGMA table_info(incidents)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'tenant_id' not in columns:
                # Add tenant_id column (default NULL for existing records)
                conn.execute('ALTER TABLE incidents ADD COLUMN tenant_id TEXT')
                logger.info("Added tenant_id column to incidents table")

                # Create index for tenant_id
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id
                    ON incidents(tenant_id)
                ''')
                logger.info("Created index on tenant_id column")

            # Update schema version
            conn.execute('INSERT INTO schema_version (version) VALUES (?)', (2,))
            logger.info("Migration v2 applied successfully")

        except Exception as e:
            raise DatabaseError(
                f"Failed to apply migration v2: {e}",
                component="DatabaseManager"
            )

    def _apply_migration_v3(self, conn: DatabaseConnection) -> None:
        """
        Apply migration version 3: Add metrics tables.
        """
        try:
            logger.info("Applying migration v3: Adding metrics tables")
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS metrics_timeseries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_metrics_name_ts 
                ON metrics_timeseries(metric_name, timestamp)
            ''')
            
            conn.execute('INSERT INTO schema_version (version) VALUES (?)', (3,))
            logger.info("Migration v3 applied successfully")
            
        except Exception as e:
            raise DatabaseError(f"Failed to apply migration v3: {e}", component="DatabaseManager")

    def _apply_migration_v4(self, conn: DatabaseConnection) -> None:
        """
        Apply migration version 4: Add status column to incidents table.
        """
        try:
            logger.info("Applying migration v4: Adding status column")
            
            # Check if status column already exists
            if self.config.type == "sqlite":
                cursor = conn.execute("PRAGMA table_info(incidents)")
                columns = [row[1] for row in cursor.fetchall()]
            else:
                # PostgreSQL
                cursor = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='incidents'")
                columns = [row[0] for row in cursor.fetchall()]

            if 'status' not in columns:
                conn.execute("ALTER TABLE incidents ADD COLUMN status TEXT DEFAULT 'DETECTED'")
                logger.info("Added status column to incidents table")
            
            conn.execute('INSERT INTO schema_version (version) VALUES (?)', (4,))
            logger.info("Migration v4 applied successfully")
            
        except Exception as e:
            raise DatabaseError(f"Failed to apply migration v4: {e}", component="DatabaseManager")

    def _apply_migration_v5(self, conn: DatabaseConnection) -> None:
        """
        Apply migration version 5: Add app_config table for dynamic configuration.
        """
        try:
            logger.info("Applying migration v5: Adding app_config table")
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('INSERT INTO schema_version (version) VALUES (?)', (5,))
            logger.info("Migration v5 applied successfully")
            
        except Exception as e:
            raise DatabaseError(f"Failed to apply migration v5: {e}", component="DatabaseManager")

    def _apply_migration_v6(self, conn: DatabaseConnection) -> None:
        """
        Apply migration version 6:
        - Add archived_at column to incidents for MTTR calculations
        - Add audit_events table for tracking user actions
        """
        try:
            logger.info("Applying migration v6: Adding archived_at + audit_events")

            # Add archived_at column if missing
            if self.config.type == "sqlite":
                cursor = conn.execute("PRAGMA table_info(incidents)")
                columns = [row[1] for row in cursor.fetchall()]
            else:
                cursor = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='incidents'")
                columns = [row[0] for row in cursor.fetchall()]

            if 'archived_at' not in columns:
                conn.execute("ALTER TABLE incidents ADD COLUMN archived_at TEXT")
                logger.info("Added archived_at column to incidents table")

            conn.execute('''
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    details_json TEXT
                )
            ''')

            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
                ON audit_events(timestamp)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_events_actor
                ON audit_events(actor)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_events_entity
                ON audit_events(entity_type, entity_id)
            ''')

            conn.execute('INSERT INTO schema_version (version) VALUES (?)', (6,))
            logger.info("Migration v6 applied successfully")

        except Exception as e:
            raise DatabaseError(f"Failed to apply migration v6: {e}", component="DatabaseManager")

    def _apply_migration_v7(self, conn: DatabaseConnection) -> None:
        """
        Apply migration version 7:
        - Add pipeline_events table for webhook ingestion / orchestration signals
        - Add policies table for approval-gated automation routing
        - Add remediation_approvals / remediation_executions tables for persistent approval gates
        """
        try:
            logger.info("Applying migration v7: pipeline_events + policies + remediation persistence")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    source TEXT NOT NULL,
                    pipeline TEXT NOT NULL,
                    run_id TEXT,
                    status TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT,
                    metrics_json TEXT,
                    event_timestamp TEXT NOT NULL,
                    received_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pipeline_events_ts
                ON pipeline_events(event_timestamp)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pipeline_events_pipeline
                ON pipeline_events(pipeline)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pipeline_events_tenant
                ON pipeline_events(tenant_id)
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS policies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    match_json TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_policies_enabled
                ON policies(enabled)
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS remediation_approvals (
                    token_id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    incident_id TEXT NOT NULL,
                    playbook_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    requested_by TEXT,
                    approved_by TEXT,
                    comment TEXT,
                    context_json TEXT,
                    details_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_remediation_approvals_status
                ON remediation_approvals(status)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_remediation_approvals_incident
                ON remediation_approvals(incident_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_remediation_approvals_tenant
                ON remediation_approvals(tenant_id)
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS remediation_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT,
                    incident_id TEXT NOT NULL,
                    playbook_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    execution_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_remediation_exec_incident
                ON remediation_executions(incident_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_remediation_exec_tenant
                ON remediation_executions(tenant_id)
                """
            )

            conn.execute('INSERT INTO schema_version (version) VALUES (?)', (7,))
            logger.info("Migration v7 applied successfully")
        except Exception as e:
            raise DatabaseError(f"Failed to apply migration v7: {e}", component="DatabaseManager")

    def get_app_config(self) -> Dict[str, str]:
        """Fetch all configuration entries."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT key, value FROM app_config")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def set_app_config(self, key: str, value: str) -> None:
        """Set a configuration entry."""
        with self.transaction() as conn:
            # SQLite upsert
            conn.execute(
                "INSERT INTO app_config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value)
            )

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.
        """
        conn = self.pool.get_connection()
        conn.in_transaction = True

        try:
            yield conn
            # Auto-commit if caller did not explicitly commit/rollback.
            if conn.in_transaction:
                conn.commit()
        except Exception as e:
            try:
                if conn.in_transaction:
                    conn.rollback()
            except Exception:
                pass
            raise TransactionError(
                f"Transaction failed: {e}",
                component="DatabaseManager"
            )
        finally:
            conn.close()

    @contextmanager
    def connection(self):
        """
        Context manager for simple database operations.
        """
        conn = self.pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def close(self) -> None:
        """Close database manager and connection pool."""
        self.pool.close_all()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
