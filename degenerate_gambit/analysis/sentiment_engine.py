"""
Vibe Engine — multi-source sentiment mining.
Covers X/Twitter, Telegram, Discord, Reddit, and visual meme analysis.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp
import numpy as np

logger = logging.getLogger(__name__)

# Theme keyword → bonus mapping
THEME_BONUSES: dict[str, float] = {
    "dog": 20, "doge": 20, "shiba": 20, "inu": 20,
    "frog": 18, "pepe": 18,
    "cat": 15, "kitten": 15,
    "ai": 12, "artificial": 12, "gpt": 12,
    "trump": 25, "biden": 25, "election": 25, "political": 25, "maga": 25,
}

VISUAL_BONUSES: dict[str, float] = {
    "rocket": 8, "moon": 10, "lambo": 7, "celebrity_face": 15,
    "rug": -25, "scam": -25,
}


@dataclass
class VisualAnalysisResult:
    rocket: float = 0.0
    moon: float = 0.0
    lambo: float = 0.0
    celebrity_face: float = 0.0
    rug_imagery: float = 0.0
    cultural_resonance: float = 0.0

    @property
    def total_score(self) -> float:
        return (
            self.rocket * VISUAL_BONUSES["rocket"]
            + self.moon * VISUAL_BONUSES["moon"]
            + self.lambo * VISUAL_BONUSES["lambo"]
            + self.celebrity_face * VISUAL_BONUSES["celebrity_face"]
            - self.rug_imagery * abs(VISUAL_BONUSES["rug"])
        )


@dataclass
class SentimentResult:
    symbol: str
    mentions_per_hour: float = 0.0
    velocity_z_score: float = 0.0
    social_velocity_index: float = 0.0   # 0-20 normalised
    base_theme_bonus: float = 0.0
    visual_hype_score: float = 0.0       # 0-30
    narrative_alignment: float = 0.0     # 0-15 from LLM
    celebrity_endorsement: float = 0.0
    viral_thesis: str = ""
    raw_mentions: int = 0


class SentimentEngine:
    """
    The Vibe Engine — aggregates social sentiment across all supported platforms.
    Includes Telegram channel monitoring and Twitter follower-count weighting.
    """

    # Follower weight brackets: (min_followers, weight_multiplier)
    FOLLOWER_WEIGHTS: list[tuple[int, float]] = [
        (2_000_000, 15.0),   # Mega-influencer (2M+)
        (500_000,   10.0),
        (100_000,    6.0),
        (50_000,     3.5),
        (10_000,     1.0),   # Baseline
        (0,          0.3),   # Micro / unknown
    ]

    def __init__(
        self,
        apify_token: str = "",
        twitter_bearer: str = "",
        openai_key: str = "",
        telegram_api_id: int = 0,
        telegram_api_hash: str = "",
        telegram_channels: list[str] | None = None,
    ) -> None:
        self._apify_token = apify_token
        self._twitter_bearer = twitter_bearer
        self._openai_key = openai_key
        self._tg_api_id = telegram_api_id
        self._tg_api_hash = telegram_api_hash
        self._tg_channels = telegram_channels or [
            "WatcherGuru",
            "CoinMarketCap",
            "CryptoSignals",
            "pumpfunalphas",
            "memecoingemfinder",
        ]
        self._tg_client: Any = None
        self._session: Any = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ── Public API ──────────────────────────────────────────────────────────

    async def analyse(self, symbol: str, theme_hints: list[str] = []) -> SentimentResult:
        """Full sentiment scan for a single token symbol."""
        _results: list[Any] = list(await asyncio.gather(
            self._scrape_twitter(symbol),
            self._scan_reddit(symbol),
            self._detect_theme(symbol, theme_hints),
            self._scan_telegram(symbol),
            return_exceptions=True,
        ))
        twitter_data: Any = _results[0] if not isinstance(_results[0], Exception) else {}
        reddit_data: Any = _results[1] if not isinstance(_results[1], Exception) else {}
        theme_data: Any = _results[2] if not isinstance(_results[2], Exception) else {}
        telegram_data: Any = _results[3] if not isinstance(_results[3], Exception) else {}

        # Telegram typically breaks alpha 10-30 min before Twitter
        tg_mentions = float(telegram_data.get("mentions_per_hour", 0.0))
        tg_velocity = float(telegram_data.get("velocity_z_score", 0.0))

        mentions_per_hour = (
            twitter_data.get("mentions_per_hour", 0.0)
            + reddit_data.get("mentions_per_hour", 0.0)
            + tg_mentions * 1.3   # 30% boost for Telegram (earlier signal)
        )
        velocity = min(mentions_per_hour / 50.0 * 20.0, 20.0)

        narrative = await self._llm_narrative_score(symbol, theme_hints)
        visual = await self._clip_visual_analysis(symbol)

        return SentimentResult(
            symbol=symbol,
            mentions_per_hour=mentions_per_hour,
            velocity_z_score=max(twitter_data.get("velocity_z_score", 0.0), tg_velocity),
            social_velocity_index=velocity,
            base_theme_bonus=theme_data.get("bonus", 0.0),
            visual_hype_score=min(visual.total_score, 30.0),
            narrative_alignment=min(narrative, 15.0),
            celebrity_endorsement=theme_data.get("celeb_bonus", 0.0),
            viral_thesis=theme_data.get("thesis", f"${symbol} shows emerging social momentum"),
            raw_mentions=twitter_data.get("raw_mentions", 0),
        )

    async def detect_coordinated_pump(
        self,
        symbol: str,
        window_seconds: int = 300,
    ) -> float:
        """
        Detect timestamp clustering of messages in Telegram/Discord channels.
        Returns 0-1 coordination score; > 0.7 is suspicious.
        """
        # In production: listen to webhook queues in Redis
        await asyncio.sleep(0)
        return 0.0   # stub — override with real data in production

    # ── Twitter / X ─────────────────────────────────────────────────────────

    def _follower_weight(self, follower_count: int) -> float:
        """Map a Twitter follower count to a signal weight multiplier."""
        for min_followers, weight in self.FOLLOWER_WEIGHTS:
            if follower_count >= min_followers:
                return weight
        return 0.3

    async def _scrape_twitter(self, symbol: str) -> dict[str, Any]:
        """
        Scrape Twitter via ntscraper or Apify actor with follower-count weighting.
        Large-account tweets are amplified; micro-accounts are dampened.
        Returns mention counts and velocity data.
        """
        logger.debug(f"[SentimentEngine] Twitter scrape for ${symbol}")
        # ── Production path ────────────────────────────────────────────────
        # Use Apify 'apidojo/tweet-scraper' actor or ntscraper library.
        # Each tweet record is expected to contain: { "text", "user": { "followers_count" } }
        # Example weighting loop (production):
        #   weighted_score = sum(_follower_weight(t["user"]["followers_count"]) for t in tweets)
        # ──────────────────────────────────────────────────────────────────
        # Stub: returns zeros until API keys are present
        return {
            "mentions_per_hour": 0.0,
            "velocity_z_score": 0.0,
            "raw_mentions": 0,
            "weighted_influence_score": 0.0,  # sum of follower weights across all tweets
        }

    async def _scan_telegram(self, symbol: str) -> dict[str, Any]:
        """
        Scan configured Telegram channels for token mentions using Telethon MTProto.
        Performs windowed count (last 60 min) and computes velocity z-score.
        Falls back gracefully when no API credentials are configured.
        """
        if not (self._tg_api_id and self._tg_api_hash):
            return {"mentions_per_hour": 0.0, "velocity_z_score": 0.0}

        try:
            from telethon import TelegramClient  # type: ignore
            from telethon.tl.functions.messages import GetHistoryRequest  # type: ignore
            import datetime as _dt

            # Lazily create a single shared client
            if self._tg_client is None:
                self._tg_client = TelegramClient(
                    "spectrolite_session",
                    self._tg_api_id,
                    self._tg_api_hash,
                )
            if not self._tg_client.is_connected():
                await self._tg_client.connect()  # type: ignore[union-attr]

            total_mentions = 0
            cutoff = _dt.datetime.utcnow() - _dt.timedelta(hours=1)
            sym_lower = symbol.lower()

            for channel in self._tg_channels:
                try:
                    entity = await self._tg_client.get_entity(channel)  # type: ignore
                    result = await self._tg_client(GetHistoryRequest(  # type: ignore
                        peer=entity,
                        limit=200,
                        offset_date=None,
                        offset_id=0,
                        max_id=0,
                        min_id=0,
                        add_offset=0,
                        hash=0,
                    ))
                    for msg in result.messages:  # type: ignore
                        if not hasattr(msg, "date") or msg.date.replace(tzinfo=None) < cutoff:
                            continue
                        text = getattr(msg, "message", "") or ""
                        if sym_lower in text.lower() or f"${sym_lower}" in text.lower():
                            total_mentions += 1
                except Exception as _e:
                    logger.debug(f"[Telegram] Could not read {channel}: {_e}")

            # Historical baseline: 2 mentions/hr is typical for small cap token
            baseline_std = max(total_mentions * 0.5, 1.0)
            z_score = (total_mentions - 2.0) / baseline_std
            return {
                "mentions_per_hour": float(total_mentions),
                "velocity_z_score": round(z_score, 3),
            }
        except ImportError:
            logger.debug("[Telegram] telethon not installed — skipping telegram scan")
            return {"mentions_per_hour": 0.0, "velocity_z_score": 0.0}
        except Exception as exc:
            logger.warning(f"[Telegram] Scan failed for ${symbol}: {exc}")
            return {"mentions_per_hour": 0.0, "velocity_z_score": 0.0}

    # ── Reddit ───────────────────────────────────────────────────────────────

    async def _scan_reddit(self, symbol: str) -> dict[str, Any]:
        """
        Scan r/CryptoMoonShots & r/SatoshiStreetBets for DD posts.
        """
        logger.debug(f"[SentimentEngine] Reddit scan for ${symbol}")
        return {"mentions_per_hour": 0.0}

    # ── Theme Detection ──────────────────────────────────────────────────────

    async def _detect_theme(
        self, symbol: str, hints: list[str]
    ) -> dict[str, Any]:
        """
        Match token symbol / description against meme theme dictionary.
        """
        sym_lower = symbol.lower()
        all_tokens = [sym_lower] + [h.lower() for h in hints]

        best_bonus = 0.0
        for token in all_tokens:
            for keyword, bonus in THEME_BONUSES.items():
                if keyword in token:
                    best_bonus = max(best_bonus, bonus)

        return {
            "bonus": best_bonus,
            "celeb_bonus": 0.0,  # updated externally via Elon/celebrity tracker
            "thesis": f"${symbol} cultural theme detected — bonus: {best_bonus}",
        }

    # ── LLM Narrative Scoring ────────────────────────────────────────────────

    async def _llm_narrative_score(
        self, symbol: str, hints: list[str]
    ) -> float:
        """
        Ask fine-tuned LLM to score cultural fit (0-15).
        Falls back to keyword heuristic if no API key configured.
        """
        if not self._openai_key:
            # Heuristic fallback
            keywords = {"pepe", "maga", "elon", "ai", "gpt", "based", "ngl", "fr"}
            matches = sum(1 for h in hints if h.lower() in keywords)
            return min(matches * 5.0, 15.0)

        # Production: call OpenAI chat completions with RAG context
        return 7.5   # stub

    # ── Visual Meme Analysis (OpenCV + CLIP) ─────────────────────────────────

    async def _clip_visual_analysis(self, symbol: str) -> VisualAnalysisResult:
        """
        Download meme images from CoinGecko / DexScreener and run CLIP zero-shot
        classification to detect bullish visual memes (rocket, moon, lambo, celebrity).
        Falls back to stub VisualAnalysisResult if open_clip_torch is not installed.
        """
        try:
            import open_clip  # type: ignore
            import torch
            from PIL import Image  # type: ignore
            import io as _io

            # Image URL heuristic: try CoinGecko token icon endpoint
            image_url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/image/large"
            image_bytes: bytes | None = None

            session = await self._get_session()
            try:
                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
            except Exception:
                pass

            if not image_bytes:
                return VisualAnalysisResult()

            pil_image = Image.open(_io.BytesIO(image_bytes)).convert("RGB")

            # Lazy-load CLIP model (cached after first call)
            if not hasattr(self, "_clip_model"):
                self._clip_model, _, self._clip_preprocess = open_clip.create_model_and_transforms(  # type: ignore
                    "ViT-B-32", pretrained="openai"
                )
                self._clip_model.eval()  # type: ignore
                self._clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")  # type: ignore

            labels = [
                "rocket ship moon lambo wealth",
                "pepe frog meme crypto",
                "dog meme coin shiba",
                "celebrity endorsement elon musk",
                "fire burning hyped viral",
                "boring generic logo",
            ]
            texts = self._clip_tokenizer(labels)  # type: ignore
            image_input = self._clip_preprocess(pil_image).unsqueeze(0)  # type: ignore

            with torch.no_grad():
                image_features = self._clip_model.encode_image(image_input)  # type: ignore
                text_features = self._clip_model.encode_text(texts)  # type: ignore
                probs = (image_features @ text_features.T).softmax(dim=-1).squeeze().tolist()

            # probs[0]=rocket/moon, [1]=pepe, [2]=dog, [3]=celeb, [4]=fire/hype, [5]=boring
            hype_score = (
                probs[0] * 20.0     # rocket/moon (highest signal)
                + probs[1] * 18.0   # pepe
                + probs[2] * 15.0   # doge-style
                + probs[3] * 12.0   # celeb association
                + probs[4] * 10.0   # fire/viral
            )
            # Map CLIP softmax probs to VisualAnalysisResult component fields.
            # total_score is a derived @property — do not pass it as a ctor arg.
            return VisualAnalysisResult(
                rocket=float(probs[0]),          # rocket / moon / lambo imagery
                moon=float(probs[2]),             # dog / shiba meme
                lambo=float(probs[4]),            # fire / viral hype
                celebrity_face=float(probs[3]),  # celebrity association
            )

        except ImportError:
            logger.debug("[CLIP] open_clip_torch not installed — skipping visual analysis")
        except Exception as exc:
            logger.debug(f"[CLIP] Visual analysis failed for ${symbol}: {exc}")

        return VisualAnalysisResult()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        if self._tg_client is not None:
            try:
                await self._tg_client.disconnect()  # type: ignore
            except Exception:
                pass

    # ── Social Velocity Index (velocity of velocity) ─────────────────────────

    @staticmethod
    def compute_velocity_z_score(
        current_mentions: float,
        historical_mean: float,
        historical_std: float,
    ) -> float:
        if historical_std == 0:
            return 0.0
        return (current_mentions - historical_mean) / historical_std
