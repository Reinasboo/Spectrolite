"""
Adaptive Signal Weight Learner.

Tracks the predictive accuracy of each signal source independently and
adjusts their contribution to MemeScore dynamically using an exponential
moving average (EMA) of prediction-outcome correlation.

Signal sources tracked:
  - twitter_velocity     (SentimentEngine — Twitter)
  - telegram_velocity    (SentimentEngine — Telegram)
  - reddit_velocity      (SentimentEngine — Reddit)
  - wallet_swarm         (SwarmIntelligence consensus)
  - chain_volume         (ChainAnalyst — volume z-score)
  - holder_delta         (ChainAnalyst — holder change)
  - pump_predictor       (BiLSTM model output)
  - visual_hype          (CLIP visual analysis)
  - arb_spread           (CrossChainArbDetector)

Weights are applied as multiplicative bonuses in SignalFusionEngine.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_WEIGHT_FILE = Path(__file__).parent.parent.parent / "models" / "signal_weights.json"

# Default equal weights (1.0 = no adjustment)
DEFAULT_WEIGHTS: dict[str, float] = {
    "twitter_velocity":  1.0,
    "telegram_velocity": 1.0,
    "reddit_velocity":   1.0,
    "wallet_swarm":      1.0,
    "chain_volume":      1.0,
    "holder_delta":      1.0,
    "pump_predictor":    1.0,
    "visual_hype":       1.0,
    "arb_spread":        1.0,
}

# Min/max clamps so no single source gets completely muted or dominates
WEIGHT_MIN = 0.30
WEIGHT_MAX = 2.50
EMA_ALPHA = 0.05     # slow EMA — recency bias but stable
MIN_SAMPLES = 10     # need at least this many outcomes before adjusting a weight


class SignalWeightLearner:
    """
    Incremental online learner that adjusts signal source weights
    based on how well each source predicts profitable outcomes.

    Logic:
      After each closed trade, for each signal source that contributed:
        accuracy = 1 if trade was profitable else 0
        ema = EMA_ALPHA * accuracy + (1 - EMA_ALPHA) * prev_ema
        weight = clip(ema * 2, WEIGHT_MIN, WEIGHT_MAX)   # scale 0.5 EMA → weight 1.0
    """

    def __init__(self) -> None:
        self._weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        self._emas: dict[str, float] = {k: 0.5 for k in DEFAULT_WEIGHTS}
        self._counts: dict[str, int] = {k: 0 for k in DEFAULT_WEIGHTS}
        # Keep recent records for diagnostics
        self._recent: deque[dict[str, Any]] = deque(maxlen=500)
        self._load()

    # ── Public API ──────────────────────────────────────────────────────────

    def get_weights(self) -> dict[str, float]:
        """Return current signal weights (copy)."""
        return dict(self._weights)

    def get_weight(self, source: str) -> float:
        """Return weight for a specific source. Returns 1.0 if unknown."""
        return self._weights.get(source, 1.0)

    def record_outcome(
        self,
        signal_contributions: dict[str, float],   # source → contribution_magnitude (0-1)
        was_profitable: bool,
    ) -> None:
        """
        Update weights based on a closed trade outcome.

        Args:
            signal_contributions: each signal source's normalised contribution
                                   to this trade's entry decision (0 = not used, 1 = max)
            was_profitable: whether the trade closed with positive PnL
        """
        outcome = 1.0 if was_profitable else 0.0
        record: dict[str, Any] = {"outcome": outcome, "signals": {}}

        for source, magnitude in signal_contributions.items():
            if source not in self._emas:
                continue
            if magnitude < 0.01:
                continue   # source didn't meaningfully contribute

            self._counts[source] += 1
            if self._counts[source] < MIN_SAMPLES:
                continue   # not enough data yet

            # Update EMA weighted by contribution magnitude
            effective_outcome = outcome * magnitude + 0.5 * (1 - magnitude)
            self._emas[source] = (
                EMA_ALPHA * effective_outcome
                + (1 - EMA_ALPHA) * self._emas[source]
            )

            # Scale EMA → weight: EMA of 0.5 → weight 1.0 (neutral)
            raw_weight = self._emas[source] * 2.0
            self._weights[source] = float(np.clip(raw_weight, WEIGHT_MIN, WEIGHT_MAX))
            record["signals"][source] = {
                "ema": self._emas[source],
                "weight": self._weights[source],
            }

        self._recent.append(record)
        self._save()

        # Log weight changes
        if record["signals"]:
            changes = ", ".join(
                f"{s}={v['weight']:.2f}" for s, v in record["signals"].items()
            )
            logger.debug(f"Signal weights updated: {changes}")

    def report(self) -> str:
        """Return human-readable weight report."""
        lines = ["Signal Weight Report:", "─" * 40]
        for src, w in sorted(self._weights.items(), key=lambda x: -x[1]):
            ema = self._emas.get(src, 0.5)
            count = self._counts.get(src, 0)
            bar = "█" * int(w * 5)
            lines.append(f"  {src:<22} w={w:.2f} ema={ema:.3f} n={count:4d}  {bar}")
        return "\n".join(lines)

    # ── Persistence ─────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            _WEIGHT_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "weights": self._weights,
                "emas": self._emas,
                "counts": self._counts,
            }
            _WEIGHT_FILE.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            logger.debug(f"Weight save failed: {exc}")

    def _load(self) -> None:
        try:
            if _WEIGHT_FILE.exists():
                data = json.loads(_WEIGHT_FILE.read_text())
                self._weights.update(data.get("weights", {}))
                self._emas.update(data.get("emas", {}))
                self._counts.update(data.get("counts", {}))
                logger.info(f"Signal weights loaded from {_WEIGHT_FILE}")
        except Exception as exc:
            logger.warning(f"Weight load failed (using defaults): {exc}")
