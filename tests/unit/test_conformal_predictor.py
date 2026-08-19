import numpy as np

from src.core.reasoning.conformal_predictor import ConformalPredictor


class _Model:
    classes_ = np.array([0, 1])

    def predict_proba(self, features):
        return np.asarray(features, dtype=float)


def test_conformal_predictor_returns_nonempty_95_percent_sets():
    predictor = ConformalPredictor(_Model()).fit([[0.9, 0.1], [0.1, 0.9]], [0, 1])

    prediction = predictor.predict([[0.6, 0.4], [0.2, 0.8]])

    assert prediction["coverage_target"] == 0.95
    assert all(prediction_set for prediction_set in prediction["sets"])
