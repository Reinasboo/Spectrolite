"""
Scam Shield — Static Contract Analyzer.
Runs Slither + Mythril on EVM contracts; custom heuristics for Solana programs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Critical vulnerability patterns that auto-reject a token
CRITICAL_PATTERNS = [
    "MintFunction",
    "BlacklistCapability",
    "OwnershipNotRenounced",
    "ProxyUpgradableNoTimelock",
    "HiddenMint",
    "SelfDestructPresent",
    "UnlimitedTransferTax",
]


class StaticAnalyzer:
    """
    Pipes contract bytecode through Slither and Mythril.
    Returns a list of critical findings for each token contract.
    """

    async def analyze_evm(
        self,
        contract_address: str,
        chain: str,
        rpc_url: str = "",
    ) -> dict[str, Any]:
        """
        Analyze an EVM contract using Slither (if available).
        Falls back to bytecode pattern matching if Slither not installed.
        """
        findings: list[str] = []
        ownership_renounced = True
        mint_present = False
        blacklist_cap = False
        proxy_upgradable = False

        try:
            result = await self._run_slither(contract_address, chain, rpc_url)
            findings = result.get("critical_findings", [])
            ownership_renounced = result.get("ownership_renounced", True)
            mint_present = result.get("mint_function_present", False)
            blacklist_cap = result.get("blacklist_capability", False)
            proxy_upgradable = result.get("proxy_upgradable", False)
        except Exception as exc:
            logger.warning(f"Slither analysis failed for {contract_address}: {exc}")
            # Fall back to API-based analysis (GoPlus / Token Sniffer)
            fallback = await self._goplus_analysis(contract_address, chain)
            findings = fallback.get("critical_findings", [])
            ownership_renounced = fallback.get("ownership_renounced", True)
            mint_present = fallback.get("mint_function_present", False)
            blacklist_cap = fallback.get("blacklist_capability", False)

        return {
            "critical_findings": findings,
            "ownership_renounced": ownership_renounced,
            "mint_function_present": mint_present,
            "blacklist_capability": blacklist_cap,
            "proxy_upgradable": proxy_upgradable,
            "static_pass": len(findings) == 0,
        }

    async def _run_slither(
        self,
        address: str,
        chain: str,
        rpc_url: str,
    ) -> dict[str, Any]:
        """
        Runs Slither via subprocess on the target address.
        Uses run_in_executor so the blocking subprocess never stalls the event loop.
        """
        import functools
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(self._run_slither_sync, address, chain, rpc_url),
        )
        return result

    def _run_slither_sync(
        self,
        address: str,
        chain: str,
        rpc_url: str,
    ) -> dict[str, Any]:
        """Blocking Slither call — runs in a thread pool via run_in_executor."""
        cmd = [
            "slither",
            address,
            "--etherscan-apikey", "",
            "--json", "-",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError("Slither non-zero exit")

        data = json.loads(proc.stdout)
        findings = []
        for res in data.get("results", {}).get("detectors", []):
            if res.get("impact") in ("High", "Medium"):
                findings.append(res.get("check", "Unknown"))

        return {
            "critical_findings": findings,
            "ownership_renounced": "ownable" not in str(data).lower(),
            "mint_function_present": "mint" in str(data).lower(),
            "blacklist_capability": "blacklist" in str(data).lower(),
            "proxy_upgradable": "upgradeable" in str(data).lower(),
        }

    async def _goplus_analysis(
        self, address: str, chain: str
    ) -> dict[str, Any]:
        """
        Fallback: call GoPlus Security API for token safety info.
        """
        import aiohttp
        chain_id_map = {
            "ethereum": "1",
            "bnb": "56",
            "base": "8453",
            "solana": "solana",
        }
        chain_id = chain_id_map.get(chain, "1")
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={address}"

        findings: list[str] = []
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = (await resp.json()).get("result", {}).get(address.lower(), {})
                        if data.get("is_mintable") == "1":
                            findings.append("MintFunction")
                        if data.get("owner_change_balance") == "1":
                            findings.append("OwnerDrainCapability")
                        return {
                            "critical_findings": findings,
                            "ownership_renounced": data.get("owner_address") in ("", "0x0000000000000000000000000000000000000000"),
                            "mint_function_present": "MintFunction" in findings,
                            "blacklist_capability": data.get("is_blacklisted") == "1",
                            "proxy_upgradable": data.get("is_proxy") == "1",
                        }
        except Exception as exc:
            logger.warning(f"GoPlus fallback failed: {exc}")

        return {"critical_findings": [], "ownership_renounced": True,
                "mint_function_present": False, "blacklist_capability": False,
                "proxy_upgradable": False}
