"""
Signal Fusion Engine — aggregates all sub-signals into a ScoredToken.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..config import get_settings
from ..models import (
    Chain, MemeScore, PumpPrediction, ScamAnalysis, ScoredToken,
)
from ..models.ensemble import EnsemblePredictor
from ..models.pump_predictor import PumpPredictorService  # kept for feature builder
from .signal_weight_learner import SignalWeightLearner

logger = logging.getLogger(__name__)
# Single shared instances — module-level singletons
_ensemble = EnsemblePredictor()
_weight_learner = SignalWeightLearner()
# Retain legacy predictor for build_feature_vector() helper
_predictor = PumpPredictorService()
_settings = get_settings()


class SignalFusionEngine:
    """
    Merges outputs from ChainAnalyst, SentimentEngine, WalletWhisperer,
    PumpPredictor, and ScamSlayer into a single ScoredToken per candidate.
    """

    def score_all(self, raw_signals: list[dict[str, Any]]) -> list[ScoredToken]:
        scored: list[ScoredToken] = []
        for sig in raw_signals:
            try:
                token = self._score_one(sig)
                if token:
                    scored.append(token)
            except Exception as exc:
                logger.warning(f"Scoring failed for {sig.get('address', '?')}: {exc}")
        # Sort highest meme score first
        return sorted(scored, key=lambda t: t.total_meme_score, reverse=True)

    def record_trade_outcome(
        self,
        signal_sources: list[str],
        prediction: Any,
        actual_gain_pct: float,
    ) -> None:
        """
        Feed trade outcomes back into the adaptive learners:
          - SignalWeightLearner: adjusts per-source EMA weights
          - EnsemblePredictor: updates Brier-score trackers for accuracy weighting

        Call this from the OverseerAgent whenever a position closes.
        """
        outcome_positive = actual_gain_pct > 0.0
        # record_outcome expects a dict[source → contribution_magnitude]
        contributions = {source: 1.0 for source in signal_sources}
        _weight_learner.record_outcome(contributions, outcome_positive)
        if prediction is not None:
            try:
                _ensemble.record_outcome(
                    lstm_pred=getattr(prediction, "lstm_prob", 0.5),
                    regime_pred=getattr(prediction, "regime_score", 0.5),
                    anomaly_pred=getattr(prediction, "anomaly_score", 0.5),
                    actual_gain_pct=actual_gain_pct,
                )
            except Exception as exc:
                logger.debug(f"[SignalFusion] ensemble outcome recording failed: {exc}")

    def _score_one(self, sig: dict[str, Any]) -> ScoredToken | None:
        cfg = _settings

        # ── Adaptive per-source signal weights ─────────────────────────────
        # SignalWeightLearner adjusts multipliers via EMA based on past accuracy.
        tw = _weight_learner.get_weight("twitter_velocity")
        tg = _weight_learner.get_weight("telegram_velocity")
        rw = _weight_learner.get_weight("wallet_swarm")
        cv = _weight_learner.get_weight("chain_volume")
        pp = _weight_learner.get_weight("pump_predictor")
        vh = _weight_learner.get_weight("visual_hype")

        # ── Meme Score (weighted) ───────────────────────────────────────────
        raw_velocity = sig.get("social_velocity_index", 0.0)
        # Blend Twitter velocity and holder/chain signals with learned weights
        blended_velocity = raw_velocity * ((tw + tg) / 2.0)

        ms = MemeScore(
            base_theme_bonus=sig.get("base_theme_bonus", 0.0),
            celebrity_endorsement=sig.get("celebrity_endorsement", 0.0),
            visual_hype_score=min(sig.get("visual_hype_score", 0.0) * vh, 30.0),
            social_velocity_index=min(blended_velocity, 20.0),
            narrative_alignment=min(sig.get("narrative_alignment", 0.0), 15.0),
            scam_probability_penalty=sig.get("scam_probability_penalty", 0.0),
        )

        # ── Scam Analysis ───────────────────────────────────────────────────
        sa = ScamAnalysis(
            scam_probability=sig.get("scam_probability", 0.5),
            static_critical_findings=sig.get("static_critical_findings", []),
            honeypot_detected=sig.get("honeypot_detected", False),
            sell_tax_pct=sig.get("sell_tax_pct", 0.0),
            rug_warnings_found=sig.get("rug_warnings_found", 0),
            mev_bundle_detected=sig.get("mev_bundle_detected", False),
            ownership_renounced=sig.get("ownership_renounced", True),
            mint_function_present=sig.get("mint_function_present", False),
            blacklist_capability=sig.get("blacklist_capability", False),
            proxy_upgradable=sig.get("proxy_upgradable", False),
        )

        # Hard reject if honeypot or critical findings
        if sa.honeypot_detected or sa.static_critical_findings:
            logger.info(f"Hard-rejected {sig.get('symbol')} — honeypot or critical finding")
            return None

        # ── Ensemble Prediction (PumpPredictor + RegimeClassifier + AnomalyScorer) ─
        # Build 18-feature vector for the pump predictor backbone
        feature_vec = _predictor.build_feature_vector(
            price_velocity=sig.get("price_velocity", 0.0),
            volume_z_score=sig.get("volume_z_score", 0.0),
            holder_delta=sig.get("holder_delta", 0.0),
            social_spike_index=sig.get("social_velocity_index", 0.0),
            meme_score=ms.total,
            liquidity_ratio=sig.get("liquidity_ratio", 0.5),
        )
        # Ensemble wraps the LSTM predictor and augments with regime + anomaly
        ensemble_result = _ensemble.predict(
            feature_sequence=feature_vec,
            current_price=sig.get("price_usd", 1.0),
        )

        pump_prob = ensemble_result.pump_probability * pp
        confidence = (ensemble_result.confidence_lower, ensemble_result.confidence_upper)
        entry_price = ensemble_result.suggested_entry_price

        pump_prob = max(0.0, min(1.0, pump_prob))

        pp_result = PumpPrediction(
            pump_probability=pump_prob,
            confidence_interval=confidence,
            suggested_entry_price=entry_price,
            horizon_minutes=15,
        )

        return ScoredToken(
            address=sig["address"],
            symbol=sig.get("symbol", "???"),
            chain=Chain(sig.get("chain", "solana")),
            price_usd=sig.get("price_usd", 0.0),
            liquidity_usd=sig.get("liquidity_usd", 0.0),
            volume_5m=sig.get("volume_5m", 0.0),
            volume_1h=sig.get("volume_1h", 0.0),
            holder_count=sig.get("holder_count", 0),
            meme_score=ms,
            scam_analysis=sa,
            pump_prediction=pp_result,
            viral_thesis=sig.get("viral_thesis", ""),
            bonding_curve_pct=sig.get("bonding_curve_pct", 0.0),
            timestamp=datetime.utcnow(),
        )
