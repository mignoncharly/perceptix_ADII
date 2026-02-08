"""
Feature Engineering Module
Extracts and transforms features from raw metrics for ML models.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from models import TableMetric, SystemState
from exceptions import FeatureEngineeringError


@dataclass
class FeatureSet:
    """Container for engineered features."""
    features: pd.DataFrame
    feature_names: List[str]
    timestamp: datetime
    metadata: Dict[str, Any]


class FeatureEngineer:
    """
    Extract and engineer features from raw metrics for anomaly detection.

    Features include:
    - Statistical features (mean, std, min, max, percentiles)
    - Time-based features (hour, day_of_week, is_weekend)
    - Rolling window features (24h avg, std)
    - Lag features (previous observations)
    - Rate of change features
    """

    def __init__(self, window_size: int = 24, lag_periods: int = 3):
        """
        Initialize feature engineer.

        Args:
            window_size: Rolling window size for statistics (default 24 hours)
            lag_periods: Number of lag periods to include (default 3)
        """
        self.window_size = window_size
        self.lag_periods = lag_periods
        self.feature_names: List[str] = []

    def extract_features(
        self,
        metric: TableMetric,
        historical_metrics: Optional[List[TableMetric]] = None
    ) -> pd.DataFrame:
        """
        Extract comprehensive features from a table metric.

        Args:
            metric: Current table metric
            historical_metrics: Historical metrics for time-based features

        Returns:
            DataFrame with engineered features

        Raises:
            FeatureEngineeringError: If feature extraction fails
        """
        try:
            features = {}

            # Basic statistical features
            features.update(self._extract_basic_features(metric))

            # Time-based features
            features.update(self._extract_time_features(metric.timestamp))

            # Delta features (rate of change)
            if historical_metrics and len(historical_metrics) > 0:
                features.update(self._extract_delta_features(metric, historical_metrics))

                # Rolling statistics
                features.update(self._extract_rolling_features(
                    metric, historical_metrics
                ))

                # Lag features
                features.update(self._extract_lag_features(
                    metric, historical_metrics
                ))
            else:
                # Fill with defaults if no historical data
                features.update(self._get_default_temporal_features())

            # Convert to DataFrame
            df = pd.DataFrame([features])
            self.feature_names = list(df.columns)

            return df

        except Exception as e:
            raise FeatureEngineeringError(
                f"Failed to extract features: {str(e)}",
                component="FeatureEngineer"
            )

    def _extract_basic_features(self, metric: TableMetric) -> Dict[str, float]:
        """Extract basic statistical features from metric."""
        features = {
            # Row count features
            'row_count': float(metric.row_count),
            'row_count_log': np.log1p(metric.row_count),

            # Null rate features
            'null_rate_mean': np.mean(list(metric.null_rates.values())) if metric.null_rates else 0.0,
            'null_rate_std': np.std(list(metric.null_rates.values())) if metric.null_rates else 0.0,
            'null_rate_max': max(metric.null_rates.values()) if metric.null_rates else 0.0,
            'null_rate_min': min(metric.null_rates.values()) if metric.null_rates else 0.0,

            # Column count
            'column_count': float(len(metric.null_rates)) if metric.null_rates else 0.0,

            # Columns with high null rate (>10%)
            'high_null_columns': float(sum(1 for v in metric.null_rates.values() if v > 0.10)) if metric.null_rates else 0.0,
        }

        # Null rate percentiles
        if metric.null_rates:
            null_values = list(metric.null_rates.values())
            features['null_rate_p25'] = np.percentile(null_values, 25)
            features['null_rate_p50'] = np.percentile(null_values, 50)
            features['null_rate_p75'] = np.percentile(null_values, 75)
            features['null_rate_p90'] = np.percentile(null_values, 90)
        else:
            features['null_rate_p25'] = 0.0
            features['null_rate_p50'] = 0.0
            features['null_rate_p75'] = 0.0
            features['null_rate_p90'] = 0.0

        return features

    def _extract_time_features(self, timestamp: datetime) -> Dict[str, float]:
        """Extract time-based features."""
        return {
            'hour': float(timestamp.hour),
            'day_of_week': float(timestamp.weekday()),
            'day_of_month': float(timestamp.day),
            'is_weekend': float(timestamp.weekday() >= 5),
            'is_business_hours': float(9 <= timestamp.hour <= 17),
            'is_night': float(timestamp.hour < 6 or timestamp.hour >= 22),
        }

    def _extract_delta_features(
        self,
        current: TableMetric,
        historical: List[TableMetric]
    ) -> Dict[str, float]:
        """Extract rate of change features."""
        if not historical:
            return self._get_default_delta_features()

        # Get most recent historical metric
        prev = historical[-1]

        # Row count delta
        row_delta = current.row_count - prev.row_count
        row_delta_pct = (row_delta / prev.row_count * 100) if prev.row_count > 0 else 0.0

        # Null rate delta
        null_delta = 0.0
        if current.null_rates and prev.null_rates:
            common_cols = set(current.null_rates.keys()) & set(prev.null_rates.keys())
            if common_cols:
                deltas = [current.null_rates[col] - prev.null_rates[col] for col in common_cols]
                null_delta = np.mean(deltas)

        return {
            'row_count_delta': float(row_delta),
            'row_count_delta_pct': float(row_delta_pct),
            'row_count_delta_abs': float(abs(row_delta)),
            'null_rate_delta': float(null_delta),
            'null_rate_delta_abs': float(abs(null_delta)),
        }

    def _extract_rolling_features(
        self,
        current: TableMetric,
        historical: List[TableMetric]
    ) -> Dict[str, float]:
        """Extract rolling window statistics."""
        if len(historical) < 2:
            return self._get_default_rolling_features()

        # Get recent metrics within window
        recent = historical[-self.window_size:] if len(historical) >= self.window_size else historical

        # Extract row counts
        row_counts = [m.row_count for m in recent]

        # Calculate rolling statistics
        features = {
            'row_count_rolling_mean': float(np.mean(row_counts)),
            'row_count_rolling_std': float(np.std(row_counts)),
            'row_count_rolling_min': float(np.min(row_counts)),
            'row_count_rolling_max': float(np.max(row_counts)),
            'row_count_rolling_range': float(np.max(row_counts) - np.min(row_counts)),
        }

        # Deviation from rolling mean
        if features['row_count_rolling_std'] > 0:
            features['row_count_z_score'] = (
                (current.row_count - features['row_count_rolling_mean']) /
                features['row_count_rolling_std']
            )
        else:
            features['row_count_z_score'] = 0.0

        return features

    def _extract_lag_features(
        self,
        current: TableMetric,
        historical: List[TableMetric]
    ) -> Dict[str, float]:
        """Extract lagged observations."""
        features = {}

        for lag in range(1, self.lag_periods + 1):
            if len(historical) >= lag:
                lagged_metric = historical[-lag]
                features[f'row_count_lag_{lag}'] = float(lagged_metric.row_count)

                if lagged_metric.null_rates:
                    features[f'null_rate_mean_lag_{lag}'] = float(
                        np.mean(list(lagged_metric.null_rates.values()))
                    )
                else:
                    features[f'null_rate_mean_lag_{lag}'] = 0.0
            else:
                features[f'row_count_lag_{lag}'] = float(current.row_count)
                features[f'null_rate_mean_lag_{lag}'] = 0.0

        return features

    def _get_default_temporal_features(self) -> Dict[str, float]:
        """Get default values for temporal features when no history available."""
        features = self._get_default_delta_features()
        features.update(self._get_default_rolling_features())
        features.update(self._get_default_lag_features())
        return features

    def _get_default_delta_features(self) -> Dict[str, float]:
        """Default delta features."""
        return {
            'row_count_delta': 0.0,
            'row_count_delta_pct': 0.0,
            'row_count_delta_abs': 0.0,
            'null_rate_delta': 0.0,
            'null_rate_delta_abs': 0.0,
        }

    def _get_default_rolling_features(self) -> Dict[str, float]:
        """Default rolling features."""
        return {
            'row_count_rolling_mean': 0.0,
            'row_count_rolling_std': 0.0,
            'row_count_rolling_min': 0.0,
            'row_count_rolling_max': 0.0,
            'row_count_rolling_range': 0.0,
            'row_count_z_score': 0.0,
        }

    def _get_default_lag_features(self) -> Dict[str, float]:
        """Default lag features."""
        features = {}
        for lag in range(1, self.lag_periods + 1):
            features[f'row_count_lag_{lag}'] = 0.0
            features[f'null_rate_mean_lag_{lag}'] = 0.0
        return features

    def extract_features_from_system_state(
        self,
        system_state: SystemState,
        historical_states: Optional[List[SystemState]] = None
    ) -> pd.DataFrame:
        """
        Extract features from complete system state.

        Args:
            system_state: Current system state
            historical_states: Historical system states

        Returns:
            DataFrame with system-level features
        """
        features = {}

        # Aggregate metrics across all tables
        if system_state.metrics:
            row_counts = [m.row_count for m in system_state.metrics]
            null_rates_all = []
            for m in system_state.metrics:
                if m.null_rates:
                    null_rates_all.extend(m.null_rates.values())

            features['total_row_count'] = float(sum(row_counts))
            features['avg_row_count'] = float(np.mean(row_counts))
            features['std_row_count'] = float(np.std(row_counts))
            features['min_row_count'] = float(min(row_counts))
            features['max_row_count'] = float(max(row_counts))

            if null_rates_all:
                features['avg_null_rate'] = float(np.mean(null_rates_all))
                features['max_null_rate'] = float(max(null_rates_all))
        else:
            features.update({
                'total_row_count': 0.0,
                'avg_row_count': 0.0,
                'std_row_count': 0.0,
                'min_row_count': 0.0,
                'max_row_count': 0.0,
                'avg_null_rate': 0.0,
                'max_null_rate': 0.0,
            })

        # Time features
        features.update(self._extract_time_features(system_state.timestamp))

        # Table count
        features['table_count'] = float(len(system_state.metrics)) if system_state.metrics else 0.0

        return pd.DataFrame([features])

    def get_feature_names(self) -> List[str]:
        """Get list of feature names."""
        return self.feature_names.copy()

    def get_feature_importance_mapping(self) -> Dict[str, str]:
        """Get human-readable descriptions of features."""
        return {
            'row_count': 'Current row count',
            'row_count_log': 'Log-transformed row count',
            'null_rate_mean': 'Average null rate across columns',
            'null_rate_std': 'Standard deviation of null rates',
            'null_rate_max': 'Maximum null rate',
            'hour': 'Hour of day (0-23)',
            'day_of_week': 'Day of week (0=Monday, 6=Sunday)',
            'is_weekend': 'Whether it is weekend',
            'row_count_delta': 'Change in row count',
            'row_count_delta_pct': 'Percentage change in row count',
            'null_rate_delta': 'Change in average null rate',
            'row_count_rolling_mean': '24h rolling mean of row count',
            'row_count_rolling_std': '24h rolling std of row count',
            'row_count_z_score': 'Z-score relative to rolling mean',
        }
