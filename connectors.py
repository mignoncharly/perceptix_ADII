"""
Data Source Connectors Module
Provides adapters for connecting to real data warehouses: Snowflake, BigQuery, Redshift.
"""
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from datetime import datetime

from models import TableMetric
from exceptions import PerceptixError
from config import PerceptixConfig


logger = logging.getLogger("PerceptixConnectors")


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class DataSourceError(PerceptixError):
    """Base exception for data source errors."""
    pass


class ConnectionError(DataSourceError):
    """Connection to data source failed."""
    pass


class QueryError(DataSourceError):
    """Query execution failed."""
    pass


# -------------------------------------------------------------------------
# Base Connector Interface
# -------------------------------------------------------------------------

class DataSourceConnector(ABC):
    """
    Abstract base class for data source connectors.
    All connectors must implement these methods.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize connector with configuration.

        Args:
            config: Connector-specific configuration
        """
        self.config = config
        self.connection = None
        self.component_id = self.__class__.__name__

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.

        Args:
            query: SQL query string

        Returns:
            List of result rows as dictionaries
        """
        pass

    @abstractmethod
    def get_table_row_count(self, schema: str, table: str) -> int:
        """
        Get row count for a specific table.

        Args:
            schema: Database schema name
            table: Table name

        Returns:
            Row count
        """
        pass

    @abstractmethod
    def get_table_metrics(self, schema: str, table: str, columns: List[str]) -> TableMetric:
        """
        Get comprehensive metrics for a table.

        Args:
            schema: Database schema name
            table: Table name
            columns: List of column names to analyze

        Returns:
            TableMetric: Metrics for the table
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


# -------------------------------------------------------------------------
# Snowflake Connector
# -------------------------------------------------------------------------

class SnowflakeConnector(DataSourceConnector):
    """
    Snowflake data warehouse connector.
    Uses snowflake-connector-python library.
    """

    def connect(self) -> None:
        """Establish connection to Snowflake."""
        try:
            import snowflake.connector

            self.connection = snowflake.connector.connect(
                account=self.config.get('account'),
                user=self.config.get('user'),
                password=self.config.get('password'),
                warehouse=self.config.get('warehouse'),
                database=self.config.get('database'),
                schema=self.config.get('schema', 'PUBLIC'),
                role=self.config.get('role', 'SYSADMIN')
            )

            logger.info(f"[SNOWFLAKE] Connected to {self.config.get('account')}")

        except ImportError:
            raise ConnectionError(
                "snowflake-connector-python not installed. Install with: pip install snowflake-connector-python",
                component=self.component_id
            )
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to Snowflake: {e}",
                component=self.component_id,
                context={"account": self.config.get('account')}
            )

    def disconnect(self) -> None:
        """Close Snowflake connection."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("[SNOWFLAKE] Connection closed")
            except Exception as e:
                logger.error(f"[SNOWFLAKE] Error closing connection: {e}")

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query on Snowflake."""
        if not self.connection:
            raise ConnectionError("Not connected to Snowflake", component=self.component_id)

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)

            # Fetch column names
            columns = [desc[0] for desc in cursor.description]

            # Fetch results
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            cursor.close()
            return results

        except Exception as e:
            raise QueryError(
                f"Query execution failed: {e}",
                component=self.component_id,
                context={"query": query[:100]}
            )

    def get_table_row_count(self, schema: str, table: str) -> int:
        """Get row count from Snowflake table."""
        query = f"SELECT COUNT(*) as row_count FROM {schema}.{table}"
        results = self.execute_query(query)
        return results[0]['ROW_COUNT'] if results else 0

    def get_table_metrics(self, schema: str, table: str, columns: List[str]) -> TableMetric:
        """Get comprehensive metrics for Snowflake table."""
        # Build query for null counts
        null_checks = ", ".join([
            f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) as {col}_nulls"
            for col in columns
        ])

        query = f"""
        SELECT
            COUNT(*) as total_rows,
            {null_checks}
        FROM {schema}.{table}
        """

        results = self.execute_query(query)
        if not results:
            raise QueryError(
                f"No results returned for table {schema}.{table}",
                component=self.component_id
            )

        row = results[0]
        total_rows = row['TOTAL_ROWS']

        # Calculate null rates
        null_rates = {}
        for col in columns:
            null_count = row.get(f'{col.upper()}_NULLS', 0)
            null_rates[col] = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        return TableMetric(
            table_name=f"{schema}.{table}",
            row_count=total_rows,
            null_rates=null_rates,
            last_updated=datetime.now().isoformat()
        )


# -------------------------------------------------------------------------
# BigQuery Connector
# -------------------------------------------------------------------------

class BigQueryConnector(DataSourceConnector):
    """
    Google BigQuery connector.
    Uses google-cloud-bigquery library.
    """

    def connect(self) -> None:
        """Establish connection to BigQuery."""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            # Load credentials
            if 'credentials_path' in self.config:
                credentials = service_account.Credentials.from_service_account_file(
                    self.config['credentials_path']
                )
                self.connection = bigquery.Client(
                    credentials=credentials,
                    project=self.config.get('project_id')
                )
            else:
                # Use default credentials
                self.connection = bigquery.Client(project=self.config.get('project_id'))

            logger.info(f"[BIGQUERY] Connected to project {self.config.get('project_id')}")

        except ImportError:
            raise ConnectionError(
                "google-cloud-bigquery not installed. Install with: pip install google-cloud-bigquery",
                component=self.component_id
            )
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to BigQuery: {e}",
                component=self.component_id,
                context={"project": self.config.get('project_id')}
            )

    def disconnect(self) -> None:
        """Close BigQuery connection."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("[BIGQUERY] Connection closed")
            except Exception as e:
                logger.error(f"[BIGQUERY] Error closing connection: {e}")

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query on BigQuery."""
        if not self.connection:
            raise ConnectionError("Not connected to BigQuery", component=self.component_id)

        try:
            query_job = self.connection.query(query)
            results = query_job.result()

            return [dict(row.items()) for row in results]

        except Exception as e:
            raise QueryError(
                f"Query execution failed: {e}",
                component=self.component_id,
                context={"query": query[:100]}
            )

    def get_table_row_count(self, schema: str, table: str) -> int:
        """Get row count from BigQuery table."""
        # BigQuery uses dataset instead of schema
        query = f"SELECT COUNT(*) as row_count FROM `{schema}.{table}`"
        results = self.execute_query(query)
        return results[0]['row_count'] if results else 0

    def get_table_metrics(self, schema: str, table: str, columns: List[str]) -> TableMetric:
        """Get comprehensive metrics for BigQuery table."""
        # Build query for null counts
        null_checks = ", ".join([
            f"COUNTIF({col} IS NULL) as {col}_nulls"
            for col in columns
        ])

        query = f"""
        SELECT
            COUNT(*) as total_rows,
            {null_checks}
        FROM `{schema}.{table}`
        """

        results = self.execute_query(query)
        if not results:
            raise QueryError(
                f"No results returned for table {schema}.{table}",
                component=self.component_id
            )

        row = results[0]
        total_rows = row['total_rows']

        # Calculate null rates
        null_rates = {}
        for col in columns:
            null_count = row.get(f'{col}_nulls', 0)
            null_rates[col] = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        return TableMetric(
            table_name=f"{schema}.{table}",
            row_count=total_rows,
            null_rates=null_rates,
            last_updated=datetime.now().isoformat()
        )


# -------------------------------------------------------------------------
# Redshift Connector
# -------------------------------------------------------------------------

class RedshiftConnector(DataSourceConnector):
    """
    Amazon Redshift connector.
    Uses psycopg2 library (PostgreSQL protocol).
    """

    def connect(self) -> None:
        """Establish connection to Redshift."""
        try:
            import psycopg2

            self.connection = psycopg2.connect(
                host=self.config.get('host'),
                port=self.config.get('port', 5439),
                database=self.config.get('database'),
                user=self.config.get('user'),
                password=self.config.get('password')
            )

            logger.info(f"[REDSHIFT] Connected to {self.config.get('host')}")

        except ImportError:
            raise ConnectionError(
                "psycopg2 not installed. Install with: pip install psycopg2-binary",
                component=self.component_id
            )
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to Redshift: {e}",
                component=self.component_id,
                context={"host": self.config.get('host')}
            )

    def disconnect(self) -> None:
        """Close Redshift connection."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("[REDSHIFT] Connection closed")
            except Exception as e:
                logger.error(f"[REDSHIFT] Error closing connection: {e}")

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query on Redshift."""
        if not self.connection:
            raise ConnectionError("Not connected to Redshift", component=self.component_id)

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)

            # Fetch column names
            columns = [desc[0] for desc in cursor.description]

            # Fetch results
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            cursor.close()
            return results

        except Exception as e:
            raise QueryError(
                f"Query execution failed: {e}",
                component=self.component_id,
                context={"query": query[:100]}
            )

    def get_table_row_count(self, schema: str, table: str) -> int:
        """Get row count from Redshift table."""
        query = f"SELECT COUNT(*) as row_count FROM {schema}.{table}"
        results = self.execute_query(query)
        return results[0]['row_count'] if results else 0

    def get_table_metrics(self, schema: str, table: str, columns: List[str]) -> TableMetric:
        """Get comprehensive metrics for Redshift table."""
        # Build query for null counts
        null_checks = ", ".join([
            f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) as {col}_nulls"
            for col in columns
        ])

        query = f"""
        SELECT
            COUNT(*) as total_rows,
            {null_checks}
        FROM {schema}.{table}
        """

        results = self.execute_query(query)
        if not results:
            raise QueryError(
                f"No results returned for table {schema}.{table}",
                component=self.component_id
            )

        row = results[0]
        total_rows = row['total_rows']

        # Calculate null rates
        null_rates = {}
        for col in columns:
            null_count = row.get(f'{col}_nulls', 0)
            null_rates[col] = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        return TableMetric(
            table_name=f"{schema}.{table}",
            row_count=total_rows,
            null_rates=null_rates,
            last_updated=datetime.now().isoformat()
        )


# -------------------------------------------------------------------------
# Connector Factory
# -------------------------------------------------------------------------

class ConnectorFactory:
    """Factory for creating data source connectors."""

    @staticmethod
    def create_connector(source_type: str, config: Dict[str, Any]) -> DataSourceConnector:
        """
        Create a connector based on source type.

        Args:
            source_type: Type of data source ('snowflake', 'bigquery', 'redshift')
            config: Connector configuration

        Returns:
            DataSourceConnector: Initialized connector

        Raises:
            ValueError: If source_type is not supported
        """
        connectors = {
            'snowflake': SnowflakeConnector,
            'bigquery': BigQueryConnector,
            'redshift': RedshiftConnector
        }

        connector_class = connectors.get(source_type.lower())
        if not connector_class:
            raise ValueError(
                f"Unsupported data source: {source_type}. "
                f"Supported types: {list(connectors.keys())}"
            )

        return connector_class(config)


# -------------------------------------------------------------------------
# TERMINAL EXECUTION BLOCK
# -------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "="*70)
    print("DATA SOURCE CONNECTORS - STANDALONE TEST")
    print("="*70 + "\n")

    print("This module provides connectors for:")
    print("  1. Snowflake")
    print("  2. Google BigQuery")
    print("  3. Amazon Redshift")
    print("\nAll connectors implement the DataSourceConnector interface.")
    print("\nTo use:")
    print("  from connectors import ConnectorFactory")
    print("  connector = ConnectorFactory.create_connector('snowflake', config)")
    print("  with connector:")
    print("      metrics = connector.get_table_metrics('schema', 'table', ['col1', 'col2'])")
    print("\n" + "="*70)
    print("✓ MODULE LOADED SUCCESSFULLY")
    print("="*70 + "\n")
