"""
Isolation Forest Anomaly Detector
Unsupervised outlier detection using Isolation Forest algorithm.
"""
import numpy as np
import pandas as pd
import pickle
from typing import Dict, Optional, Tuple, Any
from pathlib import Path
from sklearn.ensemble import IsolationForest
from datetime import datetime

from exceptions import MLModelError


class IsolationForestDetector:
    """
    Isolation Forest based anomaly detector.

    Uses sklearn's IsolationForest for unsupervised outlier detection.
    Good for multivariate anomaly detection with no labeled data required.

    How it works:
    - Randomly selects features and split values
    - Anomalies are isolated faster (fewer splits needed)
    - Returns anomaly scores: -1 = anomaly, 1 = normal
    """

    def __init__(
        self,
        contamination: float = 0.1,
        n_estimators: int = 100,
        max_samples: int = 256,
        random_state: int = 42
    ):
        """
        Initialize Isolation Forest detector.

        Args:
            contamination: Expected proportion of outliers (0.0 to 0.5)
            n_estimators: Number of trees in the forest
            max_samples: Number of samples to draw for each tree
            random_state: Random seed for reproducibility
        """
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state

        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            max_samples=max_samples,
            random_state=random_state,
            n_jobs=-1  # Use all CPU cores
        )

        self.is_fitted = False
        self.feature_names: Optional[list] = None
        self.training_date: Optional[datetime] = None
        self.training_samples: int = 0

    def fit(self, X: pd.DataFrame) -> 'IsolationForestDetector':
        """
        Train the Isolation Forest on normal data.

        Args:
            X: Training data (features only, no labels needed)

        Returns:
            Self for method chaining

        Raises:
            MLModelError: If training fails
        """
        try:
            if X.empty:
                raise MLModelError(
                    "Cannot train on empty dataset",
                    component="IsolationForestDetector"
                )

            # Store feature names
            self.feature_names = list(X.columns)

            # Train model
            self.model.fit(X)

            # Update metadata
            self.is_fitted = True
            self.training_date = datetime.now()
            self.training_samples = len(X)

            return self

        except Exception as e:
            raise MLModelError(
                f"Failed to train Isolation Forest: {str(e)}",
                component="IsolationForestDetector"
            )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict anomaly labels.

        Args:
            X: Features to predict on

        Returns:
            Array of predictions: -1 = anomaly, 1 = normal

        Raises:
            MLModelError: If model not fitted or prediction fails
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Model must be fitted before prediction",
                    component="IsolationForestDetector"
                )

            # Validate features
            self._validate_features(X)

            # Make predictions
            predictions = self.model.predict(X)

            return predictions

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Prediction failed: {str(e)}",
                component="IsolationForestDetector"
            )

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Get anomaly scores (lower = more anomalous).

        Args:
            X: Features to score

        Returns:
            Array of anomaly scores (negative = anomaly)
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Model must be fitted before scoring",
                    component="IsolationForestDetector"
                )

            self._validate_features(X)

            # Get decision function scores
            # Negative scores indicate anomalies
            scores = self.model.decision_function(X)

            return scores

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Scoring failed: {str(e)}",
                component="IsolationForestDetector"
            )

    def get_anomaly_score(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get both labels and scores.

        Args:
            X: Features to evaluate

        Returns:
            Tuple of (predictions, scores)
        """
        predictions = self.predict(X)
        scores = self.predict_proba(X)
        return predictions, scores

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Estimate feature importance using permutation.

        Note: IsolationForest doesn't have native feature importance.
        This is a simplified approximation.

        Returns:
            Dictionary mapping feature names to importance scores
        """
        if not self.is_fitted or not self.feature_names:
            return {}

        # For IsolationForest, we approximate importance by the
        # frequency of feature use in splits (not directly available)
        # Return equal weights as baseline
        importance = {name: 1.0 / len(self.feature_names) for name in self.feature_names}

        return importance

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
                    component="IsolationForestDetector"
                )

            model_data = {
                'model': self.model,
                'feature_names': self.feature_names,
                'contamination': self.contamination,
                'n_estimators': self.n_estimators,
                'training_date': self.training_date,
                'training_samples': self.training_samples
            }

            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'wb') as f:
                pickle.dump(model_data, f)

        except Exception as e:
            raise MLModelError(
                f"Failed to save model: {str(e)}",
                component="IsolationForestDetector"
            )

    @classmethod
    def load(cls, filepath: str) -> 'IsolationForestDetector':
        """
        Load trained model from disk.

        Args:
            filepath: Path to load the model from

        Returns:
            Loaded IsolationForestDetector instance

        Raises:
            MLModelError: If load fails
        """
        try:
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)

            # Create instance
            detector = cls(
                contamination=model_data['contamination'],
                n_estimators=model_data['n_estimators']
            )

            # Restore state
            detector.model = model_data['model']
            detector.feature_names = model_data['feature_names']
            detector.training_date = model_data['training_date']
            detector.training_samples = model_data['training_samples']
            detector.is_fitted = True

            return detector

        except Exception as e:
            raise MLModelError(
                f"Failed to load model: {str(e)}",
                component="IsolationForestDetector"
            )

    def _validate_features(self, X: pd.DataFrame) -> None:
        """Validate that input features match training features."""
        if self.feature_names is None:
            return

        if list(X.columns) != self.feature_names:
            raise MLModelError(
                f"Feature mismatch. Expected {self.feature_names}, got {list(X.columns)}",
                component="IsolationForestDetector"
            )

    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata and statistics."""
        return {
            'model_type': 'IsolationForest',
            'is_fitted': self.is_fitted,
            'contamination': self.contamination,
            'n_estimators': self.n_estimators,
            'max_samples': self.max_samples,
            'training_date': self.training_date.isoformat() if self.training_date else None,
            'training_samples': self.training_samples,
            'feature_count': len(self.feature_names) if self.feature_names else 0,
            'feature_names': self.feature_names
        }
