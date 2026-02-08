"""ML Training Package"""
from ml.training.feature_engineering import FeatureEngineer, FeatureSet

# Lazy import to avoid circular dependency
def __getattr__(name):
    if name == 'AnomalyModelTrainer':
        from ml.training.trainer import AnomalyModelTrainer
        return AnomalyModelTrainer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['FeatureEngineer', 'FeatureSet', 'AnomalyModelTrainer']
