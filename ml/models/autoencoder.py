"""
Autoencoder Anomaly Detector
Deep learning-based anomaly detection using reconstruction error.
"""
import numpy as np
import pandas as pd
import pickle
from typing import Dict, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime

from exceptions import MLModelError

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, models
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    keras = None


class AutoencoderDetector:
    """
    Autoencoder-based anomaly detector using neural networks.

    How it works:
    - Trains a neural network to reconstruct normal data
    - High reconstruction error indicates anomaly
    - Uses MSE (Mean Squared Error) as anomaly score

    Architecture:
    - Encoder: Compresses input to lower dimension
    - Decoder: Reconstructs input from compressed representation
    - Training: Minimize reconstruction error on normal data
    """

    def __init__(
        self,
        encoding_dim: int = 16,
        hidden_layers: list = None,
        learning_rate: float = 0.001,
        random_state: int = 42
    ):
        """
        Initialize Autoencoder detector.

        Args:
            encoding_dim: Dimension of encoding layer (bottleneck)
            hidden_layers: List of hidden layer sizes (default: [32, 16])
            learning_rate: Learning rate for optimizer
            random_state: Random seed
        """
        if not TF_AVAILABLE:
            raise MLModelError(
                "TensorFlow not available. Install with: pip install tensorflow",
                component="AutoencoderDetector"
            )

        self.encoding_dim = encoding_dim
        self.hidden_layers = hidden_layers or [32, 16]
        self.learning_rate = learning_rate
        self.random_state = random_state

        # Set random seeds
        np.random.seed(random_state)
        tf.random.set_seed(random_state)

        self.model: Optional[keras.Model] = None
        self.threshold: Optional[float] = None
        self.is_fitted = False
        self.feature_names: Optional[list] = None
        self.training_date: Optional[datetime] = None
        self.training_samples: int = 0
        self.input_dim: Optional[int] = None

    def _build_model(self, input_dim: int) -> keras.Model:
        """
        Build autoencoder architecture.

        Args:
            input_dim: Number of input features

        Returns:
            Compiled Keras model
        """
        # Input layer
        input_layer = layers.Input(shape=(input_dim,))

        # Encoder
        encoded = input_layer
        for units in self.hidden_layers:
            encoded = layers.Dense(units, activation='relu')(encoded)

        # Bottleneck (encoding layer)
        encoded = layers.Dense(self.encoding_dim, activation='relu', name='encoding')(encoded)

        # Decoder
        decoded = encoded
        for units in reversed(self.hidden_layers):
            decoded = layers.Dense(units, activation='relu')(decoded)

        # Output layer (reconstruct input)
        decoded = layers.Dense(input_dim, activation='linear')(decoded)

        # Create model
        autoencoder = models.Model(inputs=input_layer, outputs=decoded)

        # Compile
        autoencoder.compile(
            optimizer=keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss='mse'
        )

        return autoencoder

    def fit(
        self,
        X: pd.DataFrame,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.2,
        verbose: int = 0
    ) -> 'AutoencoderDetector':
        """
        Train autoencoder on normal data.

        Args:
            X: Training data (normal samples only)
            epochs: Number of training epochs
            batch_size: Batch size for training
            validation_split: Fraction of data for validation
            verbose: Verbosity mode (0=silent, 1=progress bar, 2=one line per epoch)

        Returns:
            Self for method chaining

        Raises:
            MLModelError: If training fails
        """
        try:
            if X.empty:
                raise MLModelError(
                    "Cannot train on empty dataset",
                    component="AutoencoderDetector"
                )

            # Store metadata
            self.feature_names = list(X.columns)
            self.input_dim = X.shape[1]

            # Build model
            self.model = self._build_model(self.input_dim)

            # Convert to numpy
            X_train = X.values.astype(np.float32)

            # Train model
            history = self.model.fit(
                X_train, X_train,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=validation_split,
                shuffle=True,
                verbose=verbose
            )

            # Calculate reconstruction errors on training data
            reconstructions = self.model.predict(X_train, verbose=0)
            mse = np.mean(np.square(X_train - reconstructions), axis=1)

            # Set threshold as 95th percentile of training reconstruction error
            self.threshold = np.percentile(mse, 95)

            # Update metadata
            self.is_fitted = True
            self.training_date = datetime.now()
            self.training_samples = len(X)

            return self

        except Exception as e:
            raise MLModelError(
                f"Failed to train Autoencoder: {str(e)}",
                component="AutoencoderDetector"
            )

    def predict(self, X: pd.DataFrame, threshold: Optional[float] = None) -> np.ndarray:
        """
        Predict anomaly labels based on reconstruction error.

        Args:
            X: Features to predict on
            threshold: Custom threshold (uses trained threshold if None)

        Returns:
            Array of predictions: -1 = anomaly, 1 = normal

        Raises:
            MLModelError: If model not fitted or prediction fails
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Model must be fitted before prediction",
                    component="AutoencoderDetector"
                )

            self._validate_features(X)

            # Get reconstruction errors
            scores = self.predict_proba(X)

            # Apply threshold
            threshold = threshold or self.threshold
            predictions = np.where(scores > threshold, -1, 1)

            return predictions

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Prediction failed: {str(e)}",
                component="AutoencoderDetector"
            )

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Get reconstruction error scores (higher = more anomalous).

        Args:
            X: Features to score

        Returns:
            Array of reconstruction errors
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Model must be fitted before scoring",
                    component="AutoencoderDetector"
                )

            self._validate_features(X)

            # Convert to numpy
            X_array = X.values.astype(np.float32)

            # Get reconstructions
            reconstructions = self.model.predict(X_array, verbose=0)

            # Calculate MSE per sample
            mse = np.mean(np.square(X_array - reconstructions), axis=1)

            return mse

        except MLModelError:
            raise
        except Exception as e:
            raise MLModelError(
                f"Scoring failed: {str(e)}",
                component="AutoencoderDetector"
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

    def get_reconstruction(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Get reconstructed data.

        Args:
            X: Input data

        Returns:
            Reconstructed data as DataFrame
        """
        if not self.is_fitted:
            raise MLModelError(
                "Model must be fitted first",
                component="AutoencoderDetector"
            )

        X_array = X.values.astype(np.float32)
        reconstructed = self.model.predict(X_array, verbose=0)

        return pd.DataFrame(reconstructed, columns=X.columns, index=X.index)

    def save(self, filepath: str) -> None:
        """
        Save trained model to disk.

        Args:
            filepath: Path to save the model (without extension)

        Raises:
            MLModelError: If save fails
        """
        try:
            if not self.is_fitted:
                raise MLModelError(
                    "Cannot save unfitted model",
                    component="AutoencoderDetector"
                )

            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            # Save Keras model
            model_path = f"{filepath}_model.h5"
            self.model.save(model_path)

            # Save metadata
            metadata = {
                'feature_names': self.feature_names,
                'encoding_dim': self.encoding_dim,
                'hidden_layers': self.hidden_layers,
                'threshold': self.threshold,
                'training_date': self.training_date,
                'training_samples': self.training_samples,
                'input_dim': self.input_dim
            }

            metadata_path = f"{filepath}_metadata.pkl"
            with open(metadata_path, 'wb') as f:
                pickle.dump(metadata, f)

        except Exception as e:
            raise MLModelError(
                f"Failed to save model: {str(e)}",
                component="AutoencoderDetector"
            )

    @classmethod
    def load(cls, filepath: str) -> 'AutoencoderDetector':
        """
        Load trained model from disk.

        Args:
            filepath: Path to load the model from (without extension)

        Returns:
            Loaded AutoencoderDetector instance

        Raises:
            MLModelError: If load fails
        """
        try:
            # Load Keras model
            model_path = f"{filepath}_model.h5"
            keras_model = keras.models.load_model(model_path)

            # Load metadata
            metadata_path = f"{filepath}_metadata.pkl"
            with open(metadata_path, 'rb') as f:
                metadata = pickle.load(f)

            # Create instance
            detector = cls(
                encoding_dim=metadata['encoding_dim'],
                hidden_layers=metadata['hidden_layers']
            )

            # Restore state
            detector.model = keras_model
            detector.feature_names = metadata['feature_names']
            detector.threshold = metadata['threshold']
            detector.training_date = metadata['training_date']
            detector.training_samples = metadata['training_samples']
            detector.input_dim = metadata['input_dim']
            detector.is_fitted = True

            return detector

        except Exception as e:
            raise MLModelError(
                f"Failed to load model: {str(e)}",
                component="AutoencoderDetector"
            )

    def _validate_features(self, X: pd.DataFrame) -> None:
        """Validate that input features match training features."""
        if self.feature_names is None:
            return

        if list(X.columns) != self.feature_names:
            raise MLModelError(
                f"Feature mismatch. Expected {self.feature_names}, got {list(X.columns)}",
                component="AutoencoderDetector"
            )

    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata and statistics."""
        return {
            'model_type': 'Autoencoder',
            'is_fitted': self.is_fitted,
            'encoding_dim': self.encoding_dim,
            'hidden_layers': self.hidden_layers,
            'threshold': self.threshold,
            'training_date': self.training_date.isoformat() if self.training_date else None,
            'training_samples': self.training_samples,
            'feature_count': len(self.feature_names) if self.feature_names else 0,
            'input_dim': self.input_dim
        }
