"""
Synthetic Training Data Generator
Creates realistic synthetic data for training ML models.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


class SyntheticDataGenerator:
    """Generate synthetic metrics data for ML model training."""

    def __init__(self, random_state: int = 42):
        """Initialize generator."""
        self.random_state = random_state
        np.random.seed(random_state)

    def generate_normal_data(
        self,
        n_samples: int = 1000,
        n_features: int = 30
    ) -> pd.DataFrame:
        """
        Generate normal (non-anomalous) training data.

        Args:
            n_samples: Number of samples to generate
            n_features: Number of features

        Returns:
            DataFrame with synthetic features
        """
        data = {}

        # Row count features (normally distributed)
        data['row_count'] = np.random.normal(loc=100000, scale=10000, size=n_samples)
        data['row_count'] = np.clip(data['row_count'], 0, None)  # No negative values
        data['row_count_log'] = np.log1p(data['row_count'])

        # Null rate features (low rates for normal data)
        data['null_rate_mean'] = np.random.beta(a=2, b=20, size=n_samples)
        data['null_rate_std'] = np.random.uniform(0.0, 0.05, size=n_samples)
        data['null_rate_max'] = data['null_rate_mean'] + np.random.uniform(0.0, 0.1, size=n_samples)
        data['null_rate_min'] = np.maximum(0, data['null_rate_mean'] - np.random.uniform(0.0, 0.05, size=n_samples))

        # Column count
        data['column_count'] = np.random.randint(20, 50, size=n_samples)

        # High null columns
        data['high_null_columns'] = np.random.poisson(lam=1, size=n_samples)

        # Percentiles
        data['null_rate_p25'] = data['null_rate_mean'] * 0.5
        data['null_rate_p50'] = data['null_rate_mean']
        data['null_rate_p75'] = data['null_rate_mean'] * 1.5
        data['null_rate_p90'] = data['null_rate_max']

        # Time features
        data['hour'] = np.random.randint(0, 24, size=n_samples)
        data['day_of_week'] = np.random.randint(0, 7, size=n_samples)
        data['day_of_month'] = np.random.randint(1, 29, size=n_samples)
        data['is_weekend'] = (data['day_of_week'] >= 5).astype(float)
        data['is_business_hours'] = ((data['hour'] >= 9) & (data['hour'] <= 17)).astype(float)
        data['is_night'] = ((data['hour'] < 6) | (data['hour'] >= 22)).astype(float)

        # Delta features (normal small changes)
        data['row_count_delta'] = np.random.normal(0, 1000, size=n_samples)
        data['row_count_delta_pct'] = np.random.normal(0, 2, size=n_samples)
        data['row_count_delta_abs'] = np.abs(data['row_count_delta'])
        data['null_rate_delta'] = np.random.normal(0, 0.01, size=n_samples)
        data['null_rate_delta_abs'] = np.abs(data['null_rate_delta'])

        # Rolling features
        data['row_count_rolling_mean'] = data['row_count'] * np.random.uniform(0.95, 1.05, size=n_samples)
        data['row_count_rolling_std'] = np.random.normal(5000, 1000, size=n_samples)
        data['row_count_rolling_min'] = data['row_count'] * 0.9
        data['row_count_rolling_max'] = data['row_count'] * 1.1
        data['row_count_rolling_range'] = data['row_count_rolling_max'] - data['row_count_rolling_min']
        data['row_count_z_score'] = np.random.normal(0, 1, size=n_samples)

        # Lag features
        for lag in range(1, 4):
            data[f'row_count_lag_{lag}'] = data['row_count'] * np.random.uniform(0.95, 1.05, size=n_samples)
            data[f'null_rate_mean_lag_{lag}'] = data['null_rate_mean'] * np.random.uniform(0.9, 1.1, size=n_samples)

        df = pd.DataFrame(data)
        df = df.fillna(0)  # Fill any NaN values

        return df

    def generate_anomalous_data(
        self,
        n_samples: int = 100
    ) -> pd.DataFrame:
        """
        Generate anomalous data for testing.

        Args:
            n_samples: Number of anomalous samples

        Returns:
            DataFrame with anomalous features
        """
        # Start with normal data
        df = self.generate_normal_data(n_samples=n_samples)

        # Introduce anomalies

        # Type 1: Row count drop
        drop_indices = np.random.choice(df.index, size=n_samples // 4, replace=False)
        df.loc[drop_indices, 'row_count'] *= np.random.uniform(0.1, 0.5, size=len(drop_indices))
        df.loc[drop_indices, 'row_count_log'] = np.log1p(df.loc[drop_indices, 'row_count'])
        df.loc[drop_indices, 'row_count_delta_pct'] = np.random.uniform(-80, -50, size=len(drop_indices))

        # Type 2: High null rates
        null_indices = np.random.choice(df.index, size=n_samples // 4, replace=False)
        df.loc[null_indices, 'null_rate_mean'] = np.random.uniform(0.3, 0.8, size=len(null_indices))
        df.loc[null_indices, 'null_rate_max'] = np.random.uniform(0.5, 1.0, size=len(null_indices))
        df.loc[null_indices, 'high_null_columns'] = np.random.randint(5, 20, size=len(null_indices))

        # Type 3: Extreme z-scores
        z_indices = np.random.choice(df.index, size=n_samples // 4, replace=False)
        df.loc[z_indices, 'row_count_z_score'] = np.random.choice([-5, -4, 4, 5], size=len(z_indices))

        # Type 4: Multiple anomalous features
        multi_indices = np.random.choice(df.index, size=n_samples // 4, replace=False)
        df.loc[multi_indices, 'row_count_delta_pct'] = np.random.uniform(50, 200, size=len(multi_indices))
        df.loc[multi_indices, 'null_rate_delta'] = np.random.uniform(0.2, 0.5, size=len(multi_indices))

        return df

    def generate_time_series(
        self,
        n_points: int = 1000,
        freq: str = 'H',
        add_seasonality: bool = True,
        add_trend: bool = True,
        add_noise: bool = True
    ) -> pd.DataFrame:
        """
        Generate synthetic time series data.

        Args:
            n_points: Number of time points
            freq: Frequency ('H'=hourly, 'D'=daily)
            add_seasonality: Add seasonal patterns
            add_trend: Add trend component
            add_noise: Add random noise

        Returns:
            DataFrame with timestamp and value columns
        """
        # Generate timestamps
        start_date = datetime.now() - timedelta(hours=n_points)
        timestamps = pd.date_range(start=start_date, periods=n_points, freq=freq)

        # Base value
        values = np.ones(n_points) * 100000

        # Add trend
        if add_trend:
            trend = np.linspace(0, 10000, n_points)
            values += trend

        # Add seasonality
        if add_seasonality:
            # Daily seasonality
            daily_pattern = 5000 * np.sin(2 * np.pi * np.arange(n_points) / 24)
            values += daily_pattern

            # Weekly seasonality
            weekly_pattern = 3000 * np.sin(2 * np.pi * np.arange(n_points) / (24 * 7))
            values += weekly_pattern

        # Add noise
        if add_noise:
            noise = np.random.normal(0, 1000, n_points)
            values += noise

        # Add some anomalies
        anomaly_indices = np.random.choice(n_points, size=int(n_points * 0.05), replace=False)
        values[anomaly_indices] *= np.random.uniform(0.5, 1.5, size=len(anomaly_indices))

        df = pd.DataFrame({
            'timestamp': timestamps,
            'value': values
        })

        return df
