"""
Cross-Chain Arbitrage Detector for Spectrolite.
Monitors price lag between chains and executes flash-swap arb sequences.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MIN_ARB_SPREAD = 0.04   # 4% after gas/slippage/bridge fees


@dataclass
class ArbOpportunity:
    source_chain: str
    dest_chain: str
    token_symbol: str
    source_address: str
    dest_address: str
    source_price: float
    dest_price: float
    spread_pct: float
    estimated_profit_usd: float
    bridge: str = "wormhole"
    gas_estimate_usd: float = 0.0
    bridge_fee_usd: float = 0.0
    net_spread_pct: float = 0.0


class CrossChainArbDetector:
    """
    Monitors equivalent / bridged tokens across chains simultaneously.
    Triggers when a Solana token pumps while its Base/ETH equivalent lags.
    """

    def __init__(
        self,
        chain_prices: dict[str, dict[str, float]] | None = None,
    ) -> None:
        # { chain → { symbol → price_usd } }
        self._prices: dict[str, dict[str, float]] = chain_prices or {}
        self._known_bridges: dict[str, dict[str, str]] = {}  # symbol → {chain → address}

    def update_price(self, chain: str, symbol: str, price: float) -> None:
        self._prices.setdefault(chain, {})[symbol] = price

    def register_bridge_mapping(
        self, symbol: str, chain_to_address: dict[str, str]
    ) -> None:
        self._known_bridges[symbol] = chain_to_address

    async def scan_arb_opportunities(
        self,
        min_spread: float = MIN_ARB_SPREAD,
    ) -> list[ArbOpportunity]:
        """
        Returns list of arb opportunities exceeding the net spread threshold.
        """
        opps: list[ArbOpportunity] = []

        for symbol, chain_addr_map in self._known_bridges.items():
            chains = list(chain_addr_map.keys())
            for i, src in enumerate(chains):
                for dst in chains[i + 1:]:
                    src_price = self._prices.get(src, {}).get(symbol)
                    dst_price = self._prices.get(dst, {}).get(symbol)
                    if not src_price or not dst_price:
                        continue
                    if src_price <= 0 or dst_price <= 0:
                        continue

                    spread = abs(src_price - dst_price) / min(src_price, dst_price)
                    gas_approx = self._estimate_gas(src, dst)
                    net_spread = spread - gas_approx

                    if net_spread >= min_spread:
                        # Source = higher price (sell side), dest = lower price (buy side)
                        if src_price > dst_price:
                            buy_chain, sell_chain = dst, src
                            buy_price, sell_price = dst_price, src_price
                        else:
                            buy_chain, sell_chain = src, dst
                            buy_price, sell_price = src_price, dst_price

                        opp = ArbOpportunity(
                            source_chain=buy_chain,
                            dest_chain=sell_chain,
                            token_symbol=symbol,
                            source_address=chain_addr_map[buy_chain],
                            dest_address=chain_addr_map[sell_chain],
                            source_price=buy_price,
                            dest_price=sell_price,
                            spread_pct=spread,
                            net_spread_pct=net_spread,
                            estimated_profit_usd=net_spread * 1000,  # per $1k notional
                            bridge="wormhole",
                            gas_estimate_usd=gas_approx * 1000,
                        )
                        opps.append(opp)
                        logger.info(
                            f"ARB FOUND: ${symbol} {buy_chain}→{sell_chain} "
                            f"spread={net_spread*100:.2f}%"
                        )

        return sorted(opps, key=lambda o: o.net_spread_pct, reverse=True)

    def _estimate_gas(self, src_chain: str, dst_chain: str) -> float:
        """
        Approximate gas + bridge cost as percentage of notional.
        Production: fetch live gas prices from chain RPCs.
        """
        gas_table: dict[str, float] = {
            "solana": 0.001,
            "base": 0.002,
            "bnb": 0.003,
            "ethereum": 0.015,
        }
        bridge_fee = 0.001   # Wormhole ~0.1%
        return gas_table.get(src_chain, 0.005) + gas_table.get(dst_chain, 0.005) + bridge_fee
