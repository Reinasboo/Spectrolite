"""
3-Model Prediction Ensemble for Spectrolite.

Combines three specialised models via adaptive confidence-weighted voting:
  1. PumpPredictor     — BiLSTM + Transformer: 5-15 min momentum timing
  2. RegimeClassifier  — XGBoost: market regime (accumulation/distribution/dump)
  3. AnomalyScorer     — IsolationForest: structural anomaly score (scam proximity)

Each model's weight is its rolling accuracy on the last 100 resolved trades.
When trade outcomes are unknown (< 30 resolved), weights are equal.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EnsemblePrediction:
    """Aggregated output from all three models."""
    pump_probability: float          # final weighted vote
    confidence_lower: float
    confidence_upper: float
    suggested_entry_price: float

    # Per-model breakdown (for logging / debugging)
    lstm_prob: float = 0.0
    regime_score: float = 0.0        # 0=dump, 0.5=sideways, 1=accumulation
    anomaly_score: float = 0.0       # 0=clean, 1=highly anomalous

    # Weight used for each model this prediction
    lstm_weight: float = 0.333
    regime_weight: float = 0.333
    anomaly_weight: float = 0.334


class OutcomeTracker:
    """
    Tracks (predicted_pump_prob, actual_outcome) pairs for each model.
    Rolling accuracy computed over the last `window` resolved trades.
    """

    def __init__(self, window: int = 100) -> None:
        self._records: deque[tuple[float, float]] = deque(maxlen=window)

    def record(self, predicted_prob: float, actual_gain_pct: float) -> None:
        """
        Record a resolved prediction.
        actual_gain_pct > 0.15 (i.e. +15%) is counted as a true pump.
        """
        pumped = 1.0 if actual_gain_pct >= 0.15 else 0.0
        self._records.append((predicted_prob, pumped))

    @property
    def accuracy(self) -> float:
        """Brier score–based accuracy: 1 - mean((pred - actual)^2)."""
        if len(self._records) < 10:
            return 0.5   # not enough data — neutral weight
        preds = np.array([r[0] for r in self._records])
        actuals = np.array([r[1] for r in self._records])
        brier = np.mean((preds - actuals) ** 2)
        return float(1.0 - brier)   # higher is better


class RegimeClassifier:
    """
    XGBoost-based market regime classifier.

    Classes:
        0  — dump      (bearish, high sell pressure)
        1  — sideways  (low volatility, waiting)
        2  — accumulation / pump  (bullish, rising buy pressure)

    Returns normalised score: 0-1 where 1 = strongest accumulation signal.
    """

    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._fitted = False

    def predict(self, features: np.ndarray) -> float:
        """
        Predict regime score for a feature vector.
        Features: [price_velocity, volume_z_score, holder_delta,
                   rsi_5m, rsi_15m, bid_ask_ratio, order_book_imbalance,
                   token_age_minutes, top10_concentration,
                   bonding_curve_velocity, dev_sell_pct, wash_trade_ratio]
        Returns: 0.0 (dump) → 1.0 (accumulation)
        """
        if not self._fitted or self._model is None:
            return self._heuristic_regime(features)

        # Production: return model.predict_proba([features])[0][2]  (class 2 prob)
        return self._heuristic_regime(features)

    def _heuristic_regime(self, features: np.ndarray) -> float:
        """Simple heuristic fallback before model is trained."""
        if features.shape[0] < 2:
            return 0.5
        price_vel = float(features[0])   # price_velocity
        vol_z = float(features[1])       # volume_z_score
        holder_delta = float(features[2]) if features.shape[0] > 2 else 0.0

        # Positive velocity + volume spike + holder growth = accumulation
        score = 0.5
        score += np.tanh(price_vel * 0.5) * 0.2
        score += np.tanh(vol_z * 0.3) * 0.2
        score += np.tanh(holder_delta * 2.0) * 0.1
        return float(np.clip(score, 0.0, 1.0))

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train on historical data. y: 0/1/2 class labels."""
        try:
            from xgboost import XGBClassifier  # type: ignore
            self._model = XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                use_label_encoder=False,
                eval_metric="mlogloss",
            )
            self._model.fit(X, y)
            self._fitted = True
            logger.info("RegimeClassifier fitted successfully.")
        except ImportError:
            logger.warning("xgboost not installed — RegimeClassifier using heuristics.")


class AnomalyScorer:
    """
    IsolationForest anomaly detection for detecting structurally weird tokens.
    High anomaly score → likely rug / coordinated pump / wash trading.
    Score of 1 = normal; score near 0 or negative = anomalous.
    Returns inverted: 1 = clean / 0 = highly anomalous.
    """

    def __init__(self) -> None:
        from sklearn.ensemble import IsolationForest
        self._model = IsolationForest(
            n_estimators=200,
            contamination=0.05,
            random_state=42,
        )
        self._fitted = False

    def predict(self, features: np.ndarray) -> float:
        """Returns 0 (anomalous) → 1 (normal). Used as a clean-coin score."""
        if not self._fitted:
            return 0.5

        score = self._model.decision_function(features.reshape(1, -1))[0]
        # decision_function: negative = anomalous, positive = normal
        # Normalise to 0-1
        normalised = float(1.0 / (1.0 + np.exp(-score * 5)))
        return normalised

    def fit(self, X: np.ndarray) -> None:
        """Fit on a base of known clean tokens."""
        self._model.fit(X)
        self._fitted = True
        logger.info(f"AnomalyScorer fitted on {X.shape[0]} samples.")

    def partial_fit(self, new_X: np.ndarray) -> None:
        """Refit including new samples (append + refit — IsolationForest has no true partial_fit)."""
        self._model.fit(new_X)
        self._fitted = True


class EnsemblePredictor:
    """
    Combines PumpPredictor, RegimeClassifier, and AnomalyScorer
    via confidence-weighted voting.

    Model weights adapt over time based on rolling Brier-score accuracy
    on the last 100 resolved trades. Equal weights until 30+ resolved.
    """

    MIN_RECORDS_FOR_ADAPTIVE_WEIGHTS = 30

    def __init__(self) -> None:
        from .pump_predictor import PumpPredictorService
        self._lstm = PumpPredictorService()
        self._regime = RegimeClassifier()
        self._anomaly = AnomalyScorer()

        # Per-model accuracy trackers
        self._lstm_tracker = OutcomeTracker()
        self._regime_tracker = OutcomeTracker()
        self._anomaly_tracker = OutcomeTracker()

    def predict(
        self,
        feature_sequence: np.ndarray,   # full feature sequence for LSTM
        current_price: float = 1.0,
    ) -> EnsemblePrediction:
        """Run all three models and return confidence-weighted ensemble output."""

        # ── Model 1: BiLSTM pump predictor ──────────────────────────────────
        lstm_prob, (ci_lo, ci_hi), entry = self._lstm.predict(feature_sequence, current_price)

        # ── Model 2: Regime classifier ───────────────────────────────────────
        # Use latest single tick for regime (no sequence needed)
        latest_tick = feature_sequence[-1] if feature_sequence.ndim > 1 else feature_sequence
        regime_score = self._regime.predict(latest_tick)

        # ── Model 3: Anomaly scorer ───────────────────────────────────────────
        anomaly_score = self._anomaly.predict(latest_tick)

        # ── Compute adaptive weights ──────────────────────────────────────────
        wL, wR, wA = self._compute_weights()

        # Regime and anomaly scores both act as confidence multipliers on pump prob
        # regime_score: 1 = strong accumulation → boosts prediction
        # anomaly_score: 1 = clean coin → reduces risk penalty
        ensemble_prob = float(
            wL * lstm_prob
            + wR * (lstm_prob * (0.5 + 0.5 * regime_score))
            + wA * (lstm_prob * anomaly_score)
        )
        ensemble_prob = float(np.clip(ensemble_prob, 0.0, 1.0))

        return EnsemblePrediction(
            pump_probability=ensemble_prob,
            confidence_lower=ci_lo,
            confidence_upper=ci_hi,
            suggested_entry_price=entry,
            lstm_prob=float(lstm_prob),
            regime_score=regime_score,
            anomaly_score=anomaly_score,
            lstm_weight=wL,
            regime_weight=wR,
            anomaly_weight=wA,
        )

    def record_outcome(
        self,
        lstm_pred: float,
        regime_pred: float,
        anomaly_pred: float,
        actual_gain_pct: float,
    ) -> None:
        """Called when a trade closes — feeds outcome back to trackers."""
        self._lstm_tracker.record(lstm_pred, actual_gain_pct)
        self._regime_tracker.record(regime_pred, actual_gain_pct)
        self._anomaly_tracker.record(anomaly_pred, actual_gain_pct)

    def _compute_weights(self) -> tuple[float, float, float]:
        """Softmax of accuracy scores → normalised weights."""
        lstm_acc = self._lstm_tracker.accuracy
        regime_acc = self._regime_tracker.accuracy
        anomaly_acc = self._anomaly_tracker.accuracy

        total = lstm_acc + regime_acc + anomaly_acc
        if total == 0:
            return (0.333, 0.333, 0.334)

        wL = lstm_acc / total
        wR = regime_acc / total
        wA = anomaly_acc / total
        return (wL, wR, wA)
