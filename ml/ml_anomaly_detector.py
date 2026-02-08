"""
ML Anomaly Detector - Main Orchestration Class
Coordinates multiple ML models for comprehensive anomaly detection.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from models import TableMetric, SystemState
from exceptions import MLModelError
from ml.models.isolation_forest import IsolationForestDetector
from ml.models.autoencoder import AutoencoderDetector
from ml.models.time_series_forecaster import TimeSeriesForecaster
from ml.training.feature_engineering import FeatureEngineer


logger = logging.getLogger("MLAnomalyDetector")


@dataclass
class MLPrediction:
    """Container for ML model predictions."""
    is_anomaly: bool
    anomaly_score: float
    model_scores: Dict[str, float]
    confidence: float
    feature_contributions: Dict[str, float]
    timestamp: datetime


class MLAnomalyDetector:
    """
    Main ML-based anomaly detection system.

    Orchestrates multiple ML models:
    - Isolation Forest: Multivariate outlier detection
    - Autoencoder: Deep learning reconstruction-based
    - Time Series Forecaster: Trend deviation detection

    Combines predictions using ensemble voting.
    """

    def __init__(
        self,
        models_dir: str = "models_saved",
        enable_isolation_forest: bool = True,
        enable_autoencoder: bool = True,
        enable_forecaster: bool = True,
        ensemble_threshold: float = 0.5
    ):
        """
        Initialize ML anomaly detector.

        Args:
            models_dir: Directory for saving/loading models
            enable_isolation_forest: Enable Isolation Forest
            enable_autoencoder: Enable Autoencoder
            enable_forecaster: Enable Time Series Forecaster
            ensemble_threshold: Threshold for ensemble voting (0.0-1.0)
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.enable_isolation_forest = enable_isolation_forest
        self.enable_autoencoder = enable_autoencoder
        self.enable_forecaster = enable_forecaster
        self.ensemble_threshold = ensemble_threshold

        # Initialize models
        self.isolation_forest: Optional[IsolationForestDetector] = None
        self.autoencoder: Optional[AutoencoderDetector] = None
        self.forecaster: Optional[TimeSeriesForecaster] = None

        # Feature engineer
        self.feature_engineer = FeatureEngineer()

        # State
        self.is_trained = False
        self.model_metadata: Dict[str, Any] = {}

        logger.info("MLAnomalyDetector initialized")

    def train(
        self,
        training_data: pd.DataFrame,
        feature_columns: Optional[List[str]] = None,
        epochs_autoencoder: int = 100
    ) -> Dict[str, Any]:
        """
        Train all enabled ML models.

        Args:
            training_data: Historical normal data for training
            feature_columns: Specific features to use (None = use all)
            epochs_autoencoder: Training epochs for autoencoder

        Returns:
            Dictionary with training statistics

        Raises:
            MLModelError: If training fails
        """
        try:
            logger.info("Starting ML model training...")

            if training_data.empty:
                raise MLModelError(
                    "Cannot train on empty dataset",
                    component="MLAnomalyDetector"
                )

            # Prepare features
            if feature_columns:
                X_train = training_data[feature_columns]
            else:
                X_train = training_data

            training_stats = {
                'training_samples': len(X_train),
                'feature_count': X_train.shape[1],
                'models_trained': []
            }

            # Train Isolation Forest
            if self.enable_isolation_forest:
                logger.info("Training Isolation Forest...")
                self.isolation_forest = IsolationForestDetector(
                    contamination=0.1,
                    n_estimators=100
                )
                self.isolation_forest.fit(X_train)
                training_stats['models_trained'].append('isolation_forest')
                logger.info("Isolation Forest trained successfully")

            # Train Autoencoder
            if self.enable_autoencoder:
                logger.info("Training Autoencoder...")
                self.autoencoder = AutoencoderDetector(
                    encoding_dim=min(16, X_train.shape[1] // 2),
                    hidden_layers=[32, 16]
                )
                self.autoencoder.fit(
                    X_train,
                    epochs=epochs_autoencoder,
                    verbose=0
                )
                training_stats['models_trained'].append('autoencoder')
                logger.info("Autoencoder trained successfully")

            # Note: Time Series Forecaster requires different data format
            # It's trained separately on time series data

            self.is_trained = True
            self.model_metadata = {
                'training_date': datetime.now().isoformat(),
                'training_stats': training_stats
            }

            logger.info(f"ML training complete. Models trained: {training_stats['models_trained']}")

            return training_stats

        except Exception as e:
            raise MLModelError(
                f"ML training failed: {str(e)}",
                component="MLAnomalyDetector"
            )

    def predict(
        self,
        metric: TableMetric,
        historical_metrics: Optional[List[TableMetric]] = None
    ) -> MLPrediction:
        """
        Predict if a metric is anomalous using ensemble of models.

        Args:
            metric: Current table metric to evaluate
            historical_metrics: Historical metrics for context

        Returns:
            MLPrediction with anomaly flag and scores

        Raises:
            MLModelError: If prediction fails
        """
        try:
            # Extract features
            features = self.feature_engineer.extract_features(
                metric,
                historical_metrics
            )

            # Get predictions from each model
            model_scores = {}
            predictions = []

            # Isolation Forest
            if self.isolation_forest and self.isolation_forest.is_fitted:
                try:
                    pred, score = self.isolation_forest.get_anomaly_score(features)
                    # Convert to 0-1 score (lower = more anomalous)
                    normalized_score = self._normalize_isolation_forest_score(score[0])
                    model_scores['isolation_forest'] = normalized_score
                    predictions.append(pred[0] == -1)  # -1 = anomaly
                except Exception as e:
                    logger.warning(f"Isolation Forest prediction failed: {e}")

            # Autoencoder
            if self.autoencoder and self.autoencoder.is_fitted:
                try:
                    pred, score = self.autoencoder.get_anomaly_score(features)
                    # Normalize reconstruction error to 0-1
                    normalized_score = self._normalize_autoencoder_score(
                        score[0],
                        self.autoencoder.threshold
                    )
                    model_scores['autoencoder'] = normalized_score
                    predictions.append(pred[0] == -1)  # -1 = anomaly
                except Exception as e:
                    logger.warning(f"Autoencoder prediction failed: {e}")

            # Time Series Forecaster (if available)
            if self.forecaster and self.forecaster.is_fitted:
                try:
                    # This would require time series data
                    # Skipping for now, can be added based on requirements
                    pass
                except Exception as e:
                    logger.warning(f"Time series forecast failed: {e}")

            # Ensemble prediction
            if predictions:
                # Vote-based ensemble
                anomaly_ratio = sum(predictions) / len(predictions)
                is_anomaly = anomaly_ratio >= self.ensemble_threshold

                # Average scores
                avg_score = np.mean(list(model_scores.values()))

                # Confidence based on model agreement
                confidence = self._calculate_confidence(predictions, model_scores)

                # Feature contributions (from Isolation Forest if available)
                feature_contributions = {}
                if self.isolation_forest:
                    feature_contributions = self.isolation_forest.get_feature_importance()

                return MLPrediction(
                    is_anomaly=is_anomaly,
                    anomaly_score=avg_score,
                    model_scores=model_scores,
                    confidence=confidence,
                    feature_contributions=feature_contributions,
                    timestamp=datetime.now()
                )
            else:
                # No models available
                return MLPrediction(
                    is_anomaly=False,
                    anomaly_score=0.0,
                    model_scores={},
                    confidence=0.0,
                    feature_contributions={},
                    timestamp=datetime.now()
                )

        except Exception as e:
            raise MLModelError(
                f"ML prediction failed: {str(e)}",
                component="MLAnomalyDetector"
            )

    def predict_batch(
        self,
        metrics: List[TableMetric]
    ) -> List[MLPrediction]:
        """
        Predict anomalies for multiple metrics.

        Args:
            metrics: List of table metrics

        Returns:
            List of ML predictions
        """
        predictions = []

        for i, metric in enumerate(metrics):
            # Use previous metrics as history
            historical = metrics[:i] if i > 0 else None

            pred = self.predict(metric, historical)
            predictions.append(pred)

        return predictions

    def save_models(self) -> None:
        """
        Save all trained models to disk.

        Raises:
            MLModelError: If save fails
        """
        try:
            if not self.is_trained:
                raise MLModelError(
                    "Cannot save untrained models",
                    component="MLAnomalyDetector"
                )

            logger.info("Saving ML models...")

            if self.isolation_forest:
                path = self.models_dir / "isolation_forest.pkl"
                self.isolation_forest.save(str(path))
                logger.info(f"Saved Isolation Forest to {path}")

            if self.autoencoder:
                path = self.models_dir / "autoencoder"
                self.autoencoder.save(str(path))
                logger.info(f"Saved Autoencoder to {path}")

            if self.forecaster:
                path = self.models_dir / "forecaster.pkl"
                self.forecaster.save(str(path))
                logger.info(f"Saved Forecaster to {path}")

            logger.info("All models saved successfully")

        except Exception as e:
            raise MLModelError(
                f"Failed to save models: {str(e)}",
                component="MLAnomalyDetector"
            )

    def load_models(self) -> None:
        """
        Load trained models from disk.

        Raises:
            MLModelError: If load fails
        """
        try:
            logger.info("Loading ML models...")

            # Load Isolation Forest
            if self.enable_isolation_forest:
                path = self.models_dir / "isolation_forest.pkl"
                if path.exists():
                    self.isolation_forest = IsolationForestDetector.load(str(path))
                    logger.info("Loaded Isolation Forest")

            # Load Autoencoder
            if self.enable_autoencoder:
                path = self.models_dir / "autoencoder"
                if (path.parent / f"{path.name}_model.h5").exists():
                    self.autoencoder = AutoencoderDetector.load(str(path))
                    logger.info("Loaded Autoencoder")

            # Load Forecaster
            if self.enable_forecaster:
                path = self.models_dir / "forecaster.pkl"
                if path.exists():
                    self.forecaster = TimeSeriesForecaster.load(str(path))
                    logger.info("Loaded Time Series Forecaster")

            self.is_trained = True
            logger.info("Models loaded successfully")

        except Exception as e:
            raise MLModelError(
                f"Failed to load models: {str(e)}",
                component="MLAnomalyDetector"
            )

    def _normalize_isolation_forest_score(self, score: float) -> float:
        """Normalize Isolation Forest score to 0-1 range."""
        # Score is typically in range [-0.5, 0.5]
        # Negative = anomaly, positive = normal
        # Normalize to [0, 1] where 1 = highly anomalous
        return max(0.0, min(1.0, 0.5 - score))

    def _normalize_autoencoder_score(self, score: float, threshold: float) -> float:
        """Normalize autoencoder reconstruction error to 0-1 range."""
        if threshold <= 0:
            return 0.0
        # Score / threshold, capped at 1.0
        return min(1.0, score / threshold)

    def _calculate_confidence(
        self,
        predictions: List[bool],
        scores: Dict[str, float]
    ) -> float:
        """
        Calculate confidence based on model agreement.

        Args:
            predictions: List of boolean predictions
            scores: Dictionary of model scores

        Returns:
            Confidence score (0.0-1.0)
        """
        if not predictions:
            return 0.0

        # Agreement level (all models agree = high confidence)
        agreement = sum(predictions) / len(predictions)

        # Confidence is high when:
        # - All models agree (agreement near 0 or 1)
        # - Scores are extreme (very high or very low)

        agreement_confidence = 1.0 - abs(agreement - 0.5) * 2

        # Score confidence
        if scores:
            avg_score = np.mean(list(scores.values()))
            score_confidence = abs(avg_score - 0.5) * 2
        else:
            score_confidence = 0.0

        # Combined confidence
        return (agreement_confidence + score_confidence) / 2

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about all loaded models."""
        info = {
            'is_trained': self.is_trained,
            'ensemble_threshold': self.ensemble_threshold,
            'models': {}
        }

        if self.isolation_forest:
            info['models']['isolation_forest'] = self.isolation_forest.get_model_info()

        if self.autoencoder:
            info['models']['autoencoder'] = self.autoencoder.get_model_info()

        if self.forecaster:
            info['models']['forecaster'] = self.forecaster.get_model_info()

        info['metadata'] = self.model_metadata

        return info
