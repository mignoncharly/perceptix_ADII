"""
Time Series Forecaster for Anomaly Detection
Uses Prophet or ARIMA for forecasting with confidence intervals.
"""
import numpy as np
import pandas as pd
import pickle
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime, timedelta

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

from exceptions import MLModelError


class TimeSeriesForecaster:
    """
    Time series forecasting for anomaly detection.

    Trains a forecasting model (Prophet) on historical data,
    then detects anomalies as values outside confidence intervals.

    Features:
    - Automatic seasonality detection
    - Holiday effects
    - Trend changes
    - Confidence intervals for anomaly detection
    """

    def __init__(
        self,
        model_type: str = 'prophet',
        interval_width: float = 0.95,
        changepoint_prior_scale: float = 0.05,
        seasonality_mode: str = 'additive'
    ):
        """
        Initialize time series forecaster.

        Args:
            model_type: Model type ('prophet' or 'arima')
            interval_width: Confidence interval width (0.0-1.0)
            changepoint_prior_scale: Flexibility of trend changes
            seasonality_mode: 'additive' or 'multiplicative'
        """
        if model_type == 'prophet' and not PROPHET_AVAILABLE:
            raise MLModelError(
                "Prophet not available. Install with: pip install prophet",
                component="TimeSeriesForecaster"
            )

        self.model_type = model_type
        self.interval_width = interval_width
        self.changepoint_prior_scale = changepoint_prior_scale
        self.seasonality_mode = seasonality_mode

        self.model: Optional[Any] = None
        self.is_fitted = False
        self.training_date: Optional[datetime] = None
        self.training_samples: int = 0
        self.metric_name: str = "value"

    def fit(
        self,
        ts_data: pd.DataFrame,
        metric_col: str = 'value',
        timestamp_col: str = 'timestamp'
    ) -> 'TimeSeriesForecaster':
        """
        Train forecasting model on historical time series.

        Args:
            ts_data: Time series DataFrame
            metric_col: Name of column containing values
            timestamp_col: Name of column containing timestamps

        Returns:
            Self for method chaining

        Raises:
            MLModelError: If training fails
        """
        try:
            if ts_data.empty:
                raise MLModelError(
                    "Cannot train on empty dataset",
                    component="TimeSeriesForecaster"
                )

            if metric_col not in ts_data.columns:
                raise MLModelError(
                    f"Metric column '{metric_col}' not found",
                    component="TimeSeriesForecaster"
                )

            self.metric_name = metric_col

            if self.model_type == 'prophet':
                self._fit_prophet(ts_data, metric_col, timestamp_col)
            else:
                raise MLModelError(
                    f"Model type '{self.model_type}' not implemented",
                    component="TimeSeriesForecaster"
                )

            # Update metadata
            self.is_fitted = True
            self.training_date = datetime.now()
            self.training_samples = len(ts_data)

            return self

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Failed to train forecaster: {str(e)}",
                component="TimeSeriesForecaster"
            )

    def _fit_prophet(
        self,
        ts_data: pd.DataFrame,
        metric_col: str,
        timestamp_col: str
    ) -> None:
        """Fit Prophet model."""
        # Prepare data in Prophet format (ds, y)
        df_prophet = pd.DataFrame({
            'ds': pd.to_datetime(ts_data[timestamp_col]),
            'y': ts_data[metric_col]
        })

        # Initialize Prophet
        self.model = Prophet(
            interval_width=self.interval_width,
            changepoint_prior_scale=self.changepoint_prior_scale,
            seasonality_mode=self.seasonality_mode,
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality='auto'
        )

        # Fit model (suppress output)
        import logging
        logging.getLogger('prophet').setLevel(logging.ERROR)
        logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

        self.model.fit(df_prophet)

    def forecast(
        self,
        periods: int = 24,
        freq: str = 'H'
    ) -> pd.DataFrame:
        """
        Generate forecast with confidence intervals.

        Args:
            periods: Number of periods to forecast
            freq: Frequency ('H'=hourly, 'D'=daily, etc.)

        Returns:
            DataFrame with columns: timestamp, yhat, yhat_lower, yhat_upper

        Raises:
            MLModelError: If model not fitted
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Model must be fitted before forecasting",
                    component="TimeSeriesForecaster"
                )

            if self.model_type == 'prophet':
                return self._forecast_prophet(periods, freq)
            else:
                raise MLModelError(
                    f"Forecast not implemented for {self.model_type}",
                    component="TimeSeriesForecaster"
                )

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Forecasting failed: {str(e)}",
                component="TimeSeriesForecaster"
            )

    def _forecast_prophet(self, periods: int, freq: str) -> pd.DataFrame:
        """Generate Prophet forecast."""
        # Create future dataframe
        future = self.model.make_future_dataframe(periods=periods, freq=freq)

        # Forecast
        forecast = self.model.predict(future)

        # Extract relevant columns
        result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
        result.columns = ['timestamp', 'forecast', 'lower_bound', 'upper_bound']

        return result

    def detect_anomalies(
        self,
        ts_data: pd.DataFrame,
        metric_col: str = 'value',
        timestamp_col: str = 'timestamp'
    ) -> pd.DataFrame:
        """
        Detect anomalies as values outside confidence intervals.

        Args:
            ts_data: Time series data to check
            metric_col: Name of value column
            timestamp_col: Name of timestamp column

        Returns:
            DataFrame with anomaly flags and scores

        Raises:
            MLModelError: If model not fitted
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Model must be fitted before anomaly detection",
                    component="TimeSeriesForecaster"
                )

            # Prepare data
            df_prophet = pd.DataFrame({
                'ds': pd.to_datetime(ts_data[timestamp_col]),
                'y': ts_data[metric_col]
            })

            # Get forecast for the same period
            forecast = self.model.predict(df_prophet)

            # Detect anomalies
            anomalies = []
            for i, row in forecast.iterrows():
                actual = df_prophet.loc[i, 'y']
                lower = row['yhat_lower']
                upper = row['yhat_upper']
                predicted = row['yhat']

                # Check if outside confidence interval
                is_anomaly = (actual < lower) or (actual > upper)

                # Calculate anomaly score (distance from bounds)
                if actual < lower:
                    score = abs(actual - lower) / (upper - lower)
                elif actual > upper:
                    score = abs(actual - upper) / (upper - lower)
                else:
                    score = 0.0

                anomalies.append({
                    'timestamp': df_prophet.loc[i, 'ds'],
                    'actual': actual,
                    'forecast': predicted,
                    'lower_bound': lower,
                    'upper_bound': upper,
                    'is_anomaly': is_anomaly,
                    'anomaly_score': score,
                    'direction': 'high' if actual > upper else ('low' if actual < lower else 'normal')
                })

            return pd.DataFrame(anomalies)

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Anomaly detection failed: {str(e)}",
                component="TimeSeriesForecaster"
            )

    def get_anomaly_indices(
        self,
        ts_data: pd.DataFrame,
        metric_col: str = 'value',
        timestamp_col: str = 'timestamp'
    ) -> List[int]:
        """
        Get indices of anomalous points.

        Args:
            ts_data: Time series data
            metric_col: Name of value column
            timestamp_col: Name of timestamp column

        Returns:
            List of anomaly indices
        """
        anomalies_df = self.detect_anomalies(ts_data, metric_col, timestamp_col)
        indices = anomalies_df[anomalies_df['is_anomaly']].index.tolist()
        return indices

    def save(self, filepath: str) -> None:
        """
        Save trained model to disk.

        Args:
            filepath: Path to save the model

        Raises:
            MLModelError: If save fails
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Cannot save unfitted model",
                    component="TimeSeriesForecaster"
                )

            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            model_data = {
                'model': self.model,
                'model_type': self.model_type,
                'interval_width': self.interval_width,
                'metric_name': self.metric_name,
                'training_date': self.training_date,
                'training_samples': self.training_samples
            }

            with open(filepath, 'wb') as f:
                pickle.dump(model_data, f)

        except Exception as e:
            raise MLModelError(
                f"Failed to save model: {str(e)}",
                component="TimeSeriesForecaster"
            )

    @classmethod
    def load(cls, filepath: str) -> 'TimeSeriesForecaster':
        """
        Load trained model from disk.

        Args:
            filepath: Path to load the model from

        Returns:
            Loaded TimeSeriesForecaster instance

        Raises:
            MLModelError: If load fails
        """
        try:
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)

            # Create instance
            forecaster = cls(
                model_type=model_data['model_type'],
                interval_width=model_data['interval_width']
            )

            # Restore state
            forecaster.model = model_data['model']
            forecaster.metric_name = model_data['metric_name']
            forecaster.training_date = model_data['training_date']
            forecaster.training_samples = model_data['training_samples']
            forecaster.is_fitted = True

            return forecaster

        except Exception as e:
            raise MLModelError(
                f"Failed to load model: {str(e)}",
                component="TimeSeriesForecaster"
            )

    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata and statistics."""
        return {
            'model_type': self.model_type,
            'is_fitted': self.is_fitted,
            'interval_width': self.interval_width,
            'metric_name': self.metric_name,
            'training_date': self.training_date.isoformat() if self.training_date else None,
            'training_samples': self.training_samples,
            'changepoint_prior_scale': self.changepoint_prior_scale,
            'seasonality_mode': self.seasonality_mode
        }
