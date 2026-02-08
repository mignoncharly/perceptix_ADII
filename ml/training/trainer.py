"""
Model Training Pipeline
Orchestrates the complete training workflow for ML models.
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from datetime import datetime

from exceptions import MLModelError
from ml.ml_anomaly_detector import MLAnomalyDetector
from ml.training.feature_engineering import FeatureEngineer


logger = logging.getLogger("AnomalyModelTrainer")


class AnomalyModelTrainer:
    """
    Complete training pipeline for anomaly detection models.

    Workflow:
    1. Load historical data
    2. Extract features
    3. Split train/validation
    4. Train models
    5. Evaluate performance
    6. Save models
    """

    def __init__(self, models_dir: str = "models_saved"):
        """Initialize trainer."""
        self.models_dir = models_dir
        self.feature_engineer = FeatureEngineer()
        self.scaler = StandardScaler()

    def train_pipeline(
        self,
        historical_data: pd.DataFrame,
        test_size: float = 0.2,
        enable_scaling: bool = True,
        epochs_autoencoder: int = 100
    ) -> Dict[str, Any]:
        """
        Run complete training pipeline.

        Args:
            historical_data: Historical normal data
            test_size: Fraction for validation
            enable_scaling: Whether to scale features
            epochs_autoencoder: Training epochs for autoencoder

        Returns:
            Training results and metrics
        """
        try:
            logger.info("Starting training pipeline...")

            # Split data
            X_train, X_val = train_test_split(
                historical_data,
                test_size=test_size,
                random_state=42,
                shuffle=True
            )

            logger.info(f"Train samples: {len(X_train)}, Validation samples: {len(X_val)}")

            # Scale features
            if enable_scaling:
                X_train_scaled = pd.DataFrame(
                    self.scaler.fit_transform(X_train),
                    columns=X_train.columns
                )
                X_val_scaled = pd.DataFrame(
                    self.scaler.transform(X_val),
                    columns=X_val.columns
                )
            else:
                X_train_scaled = X_train
                X_val_scaled = X_val

            # Train ML detector
            ml_detector = MLAnomalyDetector(
                models_dir=self.models_dir,
                enable_isolation_forest=True,
                enable_autoencoder=True,
                enable_forecaster=False  # Trained separately
            )

            training_stats = ml_detector.train(
                X_train_scaled,
                epochs_autoencoder=epochs_autoencoder
            )

            # Evaluate on validation set
            eval_results = self.evaluate_model(ml_detector, X_val_scaled)

            # Save models
            ml_detector.save_models()

            results = {
                'training_stats': training_stats,
                'evaluation': eval_results,
                'training_date': datetime.now().isoformat(),
                'train_size': len(X_train),
                'val_size': len(X_val)
            }

            logger.info("Training pipeline complete")
            return results

        except Exception as e:
            raise MLModelError(
                f"Training pipeline failed: {str(e)}",
                component="AnomalyModelTrainer"
            )

    def evaluate_model(
        self,
        ml_detector: MLAnomalyDetector,
        X_val: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Evaluate model on validation set.

        Args:
            ml_detector: Trained ML detector
            X_val: Validation features

        Returns:
            Evaluation metrics
        """
        try:
            # Get predictions
            predictions = []
            scores = []

            for _, row in X_val.iterrows():
                # Create dummy metric for prediction
                from models import TableMetric
                metric = TableMetric(
                    table_name="validation",
                    row_count=int(row.get('row_count', 0)),
                    null_rates={},
                    timestamp=datetime.now()
                )

                pred = ml_detector.predict(metric, None)
                predictions.append(1 if pred.is_anomaly else 0)
                scores.append(pred.anomaly_score)

            # Calculate metrics (assuming normal data)
            anomaly_rate = np.mean(predictions)

            return {
                'anomaly_rate': float(anomaly_rate),
                'mean_score': float(np.mean(scores)),
                'std_score': float(np.std(scores)),
                'max_score': float(np.max(scores)),
                'samples_evaluated': len(predictions)
            }

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {'error': str(e)}
