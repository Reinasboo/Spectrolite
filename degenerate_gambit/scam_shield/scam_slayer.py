"""
Scam Slayer — orchestrates all four Scam Shield layers.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..models import ScamAnalysis, ScoredToken
from .dynamic_simulator import DynamicSimulator
from .mev_detector import MEVBundleDetector
from .social_scanner import SocialScanner
from .static_analyzer import StaticAnalyzer

logger = logging.getLogger(__name__)


class ScamSlayer:
    """
    Multi-layer Scam Shield:
      1. Static contract analysis (Slither / GoPlus)
      2. Dynamic trade simulation (Foundry anvil)
      3. Social proof scan (Twitter rug search)
      4. Bundle / MEV detection (Isolation Forest)
    """

    def __init__(
        self,
        static: StaticAnalyzer | None = None,
        simulator: DynamicSimulator | None = None,
        social: SocialScanner | None = None,
        mev: MEVBundleDetector | None = None,
        max_scam_probability: float = 0.40,
        rpc_urls: dict[str, str] | None = None,
    ) -> None:
        self._static = static or StaticAnalyzer()
        self._simulator = simulator or DynamicSimulator()
        self._social = social or SocialScanner()
        self._mev = mev or MEVBundleDetector()
        self._max_scam_prob = max_scam_probability
        self._rpc_urls = rpc_urls or {}

    async def prescreen_new_tokens(
        self,
        tokens: list[dict],
    ) -> list[dict]:
        """
        Quick pre-screen without full simulation; used in the main loop's
        initial filtering pass.  Returns tokens that pass the quick check.
        """
        passed: list[dict] = []
        for token in tokens:
            symbol = token.get("symbol", "?")
            chain = token.get("chain", "solana")
            address = token.get("address", "")

            # 1. Social blacklist check (fastest, no API call needed)
            if self._social.is_blacklisted(symbol):
                logger.info(f"⛔ Pre-screen: ${symbol} is blacklisted")
                continue

            # 2. Quick scam probability floor
            if token.get("scam_probability", 0) >= self._max_scam_prob:
                logger.info(f"⛔ Pre-screen: ${symbol} scam_prob too high")
                continue

            passed.append(token)
        return passed

    async def full_analysis(
        self,
        address: str,
        symbol: str,
        chain: str,
        test_amount_usd: float = 10.0,
    ) -> ScamAnalysis:
        """
        Run the complete 4-layer Scam Shield analysis.
        Returns a ScamAnalysis dataclass with combined probability score.
        """
        rpc = self._rpc_urls.get(chain, "")

        # Run all layers concurrently
        static_task = self._static.analyze_evm(address, chain, rpc)
        social_task = self._social.scan(symbol, address)
        mev_task = self._mev.check_token(address, chain)
        sim_task = self._simulator.simulate(address, chain, test_amount_usd, rpc)

        _g: list[Any] = list(await asyncio.gather(
            static_task, social_task, mev_task, sim_task,
            return_exceptions=True,
        ))
        static_r: Any = _g[0]
        social_r: Any = _g[1]
        mev_r: Any = _g[2]
        sim_r: Any = _g[3]

        # Aggregate findings
        static_findings: list[str] = []
        ownership_renounced = True
        mint_present = False
        blacklist_cap = False
        proxy_upgrade = False

        if not isinstance(static_r, Exception):
            static_findings = static_r.get("critical_findings", [])
            ownership_renounced = static_r.get("ownership_renounced", True)
            mint_present = static_r.get("mint_function_present", False)
            blacklist_cap = static_r.get("blacklist_capability", False)
            proxy_upgrade = static_r.get("proxy_upgradable", False)

        honeypot = False
        sell_tax = 0.0
        if not isinstance(sim_r, Exception):
            honeypot = sim_r.is_honeypot
            sell_tax = sim_r.sell_tax_pct

        rug_warnings = 0
        if not isinstance(social_r, Exception):
            rug_warnings = social_r.warning_count

        bundle = False
        if not isinstance(mev_r, Exception):
            bundle = mev_r.bundle_detected

        # Composite probability model
        probability = self._calculate_scam_probability(
            critical_findings=static_findings,
            honeypot=honeypot,
            sell_tax=sell_tax,
            rug_warnings=rug_warnings,
            bundle_detected=bundle,
            ownership_renounced=ownership_renounced,
            mint_present=mint_present,
        )

        return ScamAnalysis(
            scam_probability=probability,
            static_critical_findings=static_findings,
            honeypot_detected=honeypot,
            sell_tax_pct=sell_tax,
            rug_warnings_found=rug_warnings,
            mev_bundle_detected=bundle,
            ownership_renounced=ownership_renounced,
            mint_function_present=mint_present,
            blacklist_capability=blacklist_cap,
            proxy_upgradable=proxy_upgrade,
        )

    async def dynamic_simulation(self, token: ScoredToken) -> bool:
        """
        Quick check: returns True if simulation passes (not a honeypot).
        Used as pre-flight assertion in TradeExecutor.
        """
        rpc = self._rpc_urls.get(token.chain.value, "")
        result = await self._simulator.simulate(
            token.address, token.chain.value, rpc_url=rpc
        )
        return not result.is_honeypot

    def _calculate_scam_probability(
        self,
        critical_findings: list[str],
        honeypot: bool,
        sell_tax: float,
        rug_warnings: int,
        bundle_detected: bool,
        ownership_renounced: bool,
        mint_present: bool,
    ) -> float:
        """
        Weighted probability model combining all Scam Shield signals.
        """
        prob = 0.05   # base rate

        # Hard flags
        if honeypot:
            prob += 0.70
        if critical_findings:
            prob += 0.10 * min(len(critical_findings), 3)
        if sell_tax >= 0.10:
            prob += 0.30
        elif sell_tax >= 0.05:
            prob += 0.15

        # Soft flags
        if not ownership_renounced:
            prob += 0.10
        if mint_present:
            prob += 0.10
        if bundle_detected:
            prob += 0.20

        # Social warnings
        prob += min(rug_warnings * 0.05, 0.30)

        return min(prob, 1.0)
