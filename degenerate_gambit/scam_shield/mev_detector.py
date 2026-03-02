"""
Bundle & MEV Detection — Isolation Forest anomaly detection on
transaction patterns preceding new token launches.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


@dataclass
class MEVDetectionResult:
    token_address: str
    bundle_detected: bool
    anomaly_score: float          # higher = more anomalous (0.5 is typical)
    recommended_delay_seconds: float
    should_skip: bool = False
    notes: str = ""


class MEVBundleDetector:
    """
    Monitors mempool for suspicious pre-launch bundle activity.
    Uses Isolation Forest to detect coordinated transaction patterns.
    Uses Bloxroute / Jito APIs for mempool visibility.
    """

    ANOMALY_THRESHOLD = -0.1      # IsolationForest scores below this = anomalous
    DELAY_RANGE = (30, 90)        # seconds to wait when bundle detected

    def __init__(
        self,
        bloxroute_ws: str = "",
        jito_url: str = "",
        contamination: float = 0.05,
    ) -> None:
        self._bloxroute_ws = bloxroute_ws
        self._jito_url = jito_url
        self._clf = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=200,
        )
        self._is_fitted = False
        self._recent_patterns: list[list[float]] = []

    def _build_feature_vector(self, txs: list[dict[str, Any]]) -> list[float]:
        """
        Extract feature vector from a cluster of mempool transactions.
        Features: [tx_count, avg_gas, std_gas, time_delta_std, wallet_unique_count, avg_amount]
        """
        if not txs:
            return [0.0] * 6

        gas_prices = [t.get("gas_price", 0) for t in txs]
        amounts = [t.get("amount", 0) for t in txs]
        timestamps = [t.get("timestamp", 0) for t in txs]
        wallets = {t.get("wallet", "") for t in txs}

        time_deltas = np.diff(sorted(timestamps)) if len(timestamps) > 1 else [0]

        return [
            float(len(txs)),
            float(np.mean(gas_prices)),
            float(np.std(gas_prices)),
            float(np.std(time_deltas)),
            float(len(wallets)),
            float(np.mean(amounts)),
        ]

    def fit(self, historical_patterns: list[list[float]]) -> None:
        """Fit Isolation Forest on historical benign transaction patterns."""
        if len(historical_patterns) < 10:
            logger.warning("Insufficient training data for MEV detector")
            return
        self._clf.fit(np.array(historical_patterns))
        self._is_fitted = True
        logger.info(f"MEV IsolationForest fitted on {len(historical_patterns)} patterns")

    async def check_token(
        self,
        token_address: str,
        chain: str = "solana",
    ) -> MEVDetectionResult:
        """
        Check if there's suspicious coordinated bundle activity around a token.
        """
        raw_txs = await self._fetch_mempool_activity(token_address, chain)
        features = self._build_feature_vector(raw_txs)
        self._recent_patterns.append(features)

        bundle_detected = False
        anomaly_score = 0.0

        if self._is_fitted and features:
            score = self._clf.score_samples([features])[0]
            anomaly_score = float(score)
            bundle_detected = score < self.ANOMALY_THRESHOLD

        if bundle_detected:
            delay = random.uniform(*self.DELAY_RANGE)
            logger.warning(
                f"🚨 MEV BUNDLE DETECTED for {token_address} "
                f"(score={anomaly_score:.3f}). Delaying {delay:.0f}s"
            )
            return MEVDetectionResult(
                token_address=token_address,
                bundle_detected=True,
                anomaly_score=anomaly_score,
                recommended_delay_seconds=delay,
                notes=f"IsolationForest score: {anomaly_score:.3f}",
            )

        return MEVDetectionResult(
            token_address=token_address,
            bundle_detected=False,
            anomaly_score=anomaly_score,
            recommended_delay_seconds=0.0,
        )

    async def _fetch_mempool_activity(
        self, token_address: str, chain: str
    ) -> list[dict[str, Any]]:
        """
        In production: query Bloxroute or Jito APIs for pending transactions
        involving the target token address.
        """
        await asyncio.sleep(0)
        return []   # stub — replace with live mempool feed

    def auto_fit_from_recent(self) -> None:
        """Periodically refit the model on recent observations."""
        if len(self._recent_patterns) >= 50:
            self.fit(self._recent_patterns[-500:])
