"""
Swarm Intelligence Execution — aggregates alpha wallet signals
and generates ensemble buy/sell decisions.
"""
from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass

from .wallet_tracker import WalletSignal, WalletTracker

logger = logging.getLogger(__name__)


@dataclass
class SwarmSignal:
    token_address: str
    token_symbol: str
    chain: str
    consensus_pct: float          # fraction of scored wallets agreeing
    weighted_score: float         # alpha-score-weighted conviction
    participating_wallets: int
    total_amount_usd: float
    entry_advance_seconds: float  # how many seconds to front-run tracked wallets
    apply_mutation: bool = False
    mutation_multiplier: float = 1.0


class SwarmIntelligence:
    """
    Aggregates WalletTracker signals into ensemble buy decisions.
    Applies "Degen Mutation" with 15% probability.
    """

    MIN_CONSENSUS_PCT = 0.65
    MUTATION_PROBABILITY = 0.15
    ENTRY_ADVANCE_SECONDS = 30.0
    JITTER_RANGE = (8, 45)

    def __init__(self, wallet_tracker: WalletTracker) -> None:
        self._tracker = wallet_tracker

    async def get_alpha_moves(
        self,
        window_seconds: int = 300,
        min_consensus_pct: float | None = None,
    ) -> list[SwarmSignal]:
        """
        Poll recent wallet buys and consolidate into swarm signals.
        Returns tokens meeting consensus threshold.
        """
        threshold = min_consensus_pct or self.MIN_CONSENSUS_PCT
        recent = await self._tracker.get_recent_buys(lookback_seconds=window_seconds)

        # Group by token
        token_signals: dict[str, list[WalletSignal]] = defaultdict(list)
        for sig in recent:
            token_signals[sig.token_address].append(sig)

        total_wallets = len(self._tracker.watchlist)
        if total_wallets == 0:
            return []

        results: list[SwarmSignal] = []
        for token_addr, sigs in token_signals.items():
            consensus_pct = len(sigs) / total_wallets
            if consensus_pct < threshold:
                continue

            # Alpha-weighted score
            total_alpha = sum(s.alpha_score for s in sigs)
            max_possible = sum(w.alpha_score for w in self._tracker.watchlist)
            weighted_score = total_alpha / max(max_possible, 1.0)

            # Degen Mutation
            mutation = random.random() < self.MUTATION_PROBABILITY
            multiplier = random.uniform(1.5, 2.0) if mutation else 1.0

            # Jitter for anti-front-run
            jitter = random.uniform(*self.JITTER_RANGE)

            swarm = SwarmSignal(
                token_address=token_addr,
                token_symbol=sigs[0].token_symbol,
                chain=sigs[0].chain,
                consensus_pct=consensus_pct,
                weighted_score=weighted_score,
                participating_wallets=len(sigs),
                total_amount_usd=sum(s.amount_usd for s in sigs),
                entry_advance_seconds=self.ENTRY_ADVANCE_SECONDS,
                apply_mutation=mutation,
                mutation_multiplier=multiplier,
            )
            results.append(swarm)
            logger.info(
                f"SWARM SIGNAL: ${swarm.token_symbol} consensus={consensus_pct*100:.0f}% "
                f"wallets={swarm.participating_wallets} mutation={mutation}"
            )

        return sorted(results, key=lambda s: s.weighted_score, reverse=True)

    @staticmethod
    def random_jitter_seconds() -> float:
        """Used to randomise all entry/exit timing for anti-copy privacy."""
        return random.uniform(8, 45)
