"""
Social Proof Scanner — real-time rug/scam detection via X/Twitter.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class RugWarning:
    source: str          # "twitter" | "reddit" | "telegram"
    author: str
    author_followers: int
    text: str
    timestamp: float
    credibility_score: float = 0.0


@dataclass
class SocialScanResult:
    token_symbol: str
    warnings: list[RugWarning] = field(default_factory=list)
    blacklisted: bool = False
    blacklist_until: float = 0.0
    high_credibility_warning: bool = False

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


# In-memory blacklist: { token_symbol → blacklist_expiry_timestamp }
_BLACKLIST: dict[str, float] = {}


class SocialScanner:
    """
    Scans X (Twitter) for rug/scam/honeypot mentions of a given token.
    Weights warnings by account age and follower credibility.
    Auto-blacklists tokens after credible rug warnings.
    """

    RUG_KEYWORDS = ["rug", "scam", "honeypot", "rugpull", "fraud", "rugpulled"]
    CREDIBLE_FOLLOWER_THRESHOLD = 10_000
    BLACKLIST_DURATION_SECONDS = 48 * 3600

    def __init__(
        self,
        twitter_bearer_token: str = "",
        apify_token: str = "",
        scan_window_hours: int = 2,
    ) -> None:
        self._twitter_bearer = twitter_bearer_token
        self._apify_token = apify_token
        self._scan_window_hours = scan_window_hours
        self._session: aiohttp.ClientSession | None = None

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self._twitter_bearer:
                headers["Authorization"] = f"Bearer {self._twitter_bearer}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    def is_blacklisted(self, token_symbol: str) -> bool:
        expiry = _BLACKLIST.get(token_symbol.upper(), 0)
        return time.time() < expiry

    def blacklist(self, token_symbol: str) -> None:
        _BLACKLIST[token_symbol.upper()] = time.time() + self.BLACKLIST_DURATION_SECONDS
        logger.warning(f"🚨 BLACKLISTED: ${token_symbol} for 48h")

    async def scan(self, token_symbol: str, token_address: str = "") -> SocialScanResult:
        """
        Perform full social rug-scan for a token.
        Returns SocialScanResult with warnings and blacklist status.
        """
        if self.is_blacklisted(token_symbol):
            return SocialScanResult(
                token_symbol=token_symbol,
                blacklisted=True,
                blacklist_until=_BLACKLIST.get(token_symbol.upper(), 0),
            )

        warnings = await self._scan_twitter(token_symbol, token_address)
        result = SocialScanResult(token_symbol=token_symbol, warnings=warnings)

        # Check for high-credibility warning (>10k followers)
        for w in warnings:
            if w.author_followers >= self.CREDIBLE_FOLLOWER_THRESHOLD:
                result.high_credibility_warning = True
                self.blacklist(token_symbol)
                result.blacklisted = True
                result.blacklist_until = _BLACKLIST.get(token_symbol.upper(), 0)
                logger.warning(
                    f"High-credibility rug warning for ${token_symbol} "
                    f"from @{w.author} ({w.author_followers:,} followers)"
                )
                break

        return result

    async def _scan_twitter(
        self, symbol: str, address: str = ""
    ) -> list[RugWarning]:
        """
        Search Twitter API v2 for rug/scam mentions of the token.
        """
        if not self._twitter_bearer:
            return []

        sess = await self._sess()
        queries = [f"${symbol} {kw}" for kw in self.RUG_KEYWORDS[:3]]
        warnings: list[RugWarning] = []

        for query in queries:
            try:
                url = "https://api.twitter.com/2/tweets/search/recent"
                params = {
                    "query": query,
                    "max_results": "10",
                    "expansions": "author_id",
                    "user.fields": "public_metrics",
                    "tweet.fields": "created_at,text",
                }
                async with sess.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for tweet in data.get("data", []):
                            followers = self._get_follower_count(
                                tweet.get("author_id", ""),
                                data.get("includes", {}).get("users", []),
                            )
                            w = RugWarning(
                                source="twitter",
                                author=tweet.get("author_id", "unknown"),
                                author_followers=followers,
                                text=tweet.get("text", ""),
                                timestamp=time.time(),
                                credibility_score=min(followers / 100_000, 1.0),
                            )
                            warnings.append(w)
            except Exception as exc:
                logger.debug(f"Twitter scan error: {exc}")

        return warnings

    def _get_follower_count(self, author_id: str, users: list[dict]) -> int:
        for u in users:
            if u.get("id") == author_id:
                return u.get("public_metrics", {}).get("followers_count", 0)
        return 0

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
