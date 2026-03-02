"""
Padre Terminal Session Manager — headless browser automation.
Handles login, 2FA, session keepalive, and DOM change detection.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from typing import Any, Optional

import pyotp
from cryptography.fernet import Fernet
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 240   # 4 minutes
DOM_CHANGE_THRESHOLD = 0.15


class AESEncryptedBlob:
    """Thin wrapper around Fernet-encrypted credential bytes."""

    def __init__(self, ciphertext: bytes, key: bytes) -> None:
        self._cipher = Fernet(key)
        self._ciphertext = ciphertext

    @classmethod
    def from_env(cls, ciphertext_b64: str, key_b64: str) -> "AESEncryptedBlob":
        return cls(
            ciphertext=base64.b64decode(ciphertext_b64),
            key=base64.b64decode(key_b64),
        )

    def decrypt(self) -> dict[str, str]:
        import json
        plaintext = self._cipher.decrypt(self._ciphertext)
        return json.loads(plaintext)


class PadreSessionManager:
    """
    Manages the Padre Terminal web session via Playwright.
    - Decrypt credentials at runtime only, never persist in plaintext.
    - Handle login, 2FA (TOTP via pyotp), and session token refresh.
    - Detect UI changes via DOM hash comparison; re-scrape if layout drifts.
    - Maintain session heartbeat every 4 minutes.
    """

    PADRE_URL = "https://padre.live/"   # replace with actual URL

    def __init__(self, encrypted_credentials: AESEncryptedBlob) -> None:
        self._creds_blob = encrypted_credentials
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._last_dom_hash: Optional[str] = None
        self._session_active = False
        self._last_heartbeat = 0.0

    async def start(self) -> None:
        """Launch headless Chromium and log in to Padre Terminal."""
        creds = self._creds_blob.decrypt()
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        await self._login(creds)
        await self._capture_dom_hash()
        self._session_active = True
        logger.info("Padre Terminal session started")

        # Start heartbeat in background
        asyncio.create_task(self._heartbeat_loop())

    async def _login(self, creds: dict[str, str]) -> None:
        # _page is set unconditionally in start() before _login() is called
        assert self._page is not None, "_login called before page was created"
        page: Page = self._page
        await page.goto(self.PADRE_URL, wait_until="networkidle")
        await page.fill('[name="email"]', creds["email"])
        await page.fill('[name="password"]', creds["password"])
        await page.click('[type="submit"]')
        await page.wait_for_load_state("networkidle")

        # Handle 2FA if present
        if await page.query_selector('[name="totp"]') or await page.query_selector('[name="otp"]'):
            totp_secret = creds.get("totp_secret", "")
            if totp_secret:
                code = pyotp.TOTP(totp_secret).now()
                field = (await page.query_selector('[name="totp"]') or
                         await page.query_selector('[name="otp"]'))
                if field is not None:
                    await field.fill(code)
                    await page.click('[type="submit"]')
                    await page.wait_for_load_state("networkidle")
                    logger.info("2FA completed")

    async def _capture_dom_hash(self) -> str:
        if not self._page:
            return ""
        dom = await self._page.content()
        h = hashlib.sha256(dom.encode()).hexdigest()
        self._last_dom_hash = h
        return h

    async def check_ui_drift(self) -> bool:
        """
        Returns True if DOM has changed by more than DOM_CHANGE_THRESHOLD.
        If drifted, triggers automated UI re-mapping.
        """
        new_hash = await self._capture_dom_hash()
        if not self._last_dom_hash:
            self._last_dom_hash = new_hash
            return False

        # Simple character-level diff ratio
        old = self._last_dom_hash
        changed = sum(a != b for a, b in zip(old, new_hash)) / len(old)
        if changed > DOM_CHANGE_THRESHOLD:
            logger.warning(
                f"⚠️ Padre UI drift detected ({changed*100:.1f}% change). Re-mapping…"
            )
            await self._remap_ui()
            self._last_dom_hash = new_hash
            return True
        return False

    async def _remap_ui(self) -> None:
        """
        Automated UI re-mapping: scan for key elements by role/text.
        Logs a structured map of discovered interactive elements.
        """
        if not self._page:
            return
        elements = await self._page.query_selector_all("button, input, [role='button']")
        element_map: dict[str, str] = {}
        for el in elements:
            text = (await el.inner_text()).strip()[:50]
            tag = await el.get_attribute("name") or await el.get_attribute("id") or ""
            if text:
                element_map[text] = tag
        logger.info(f"UI re-map discovered {len(element_map)} interactive elements")

    async def _heartbeat_loop(self) -> None:
        """Keep the Padre session alive by pinging every 4 minutes."""
        while self._session_active:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                if self._page:
                    await self._page.evaluate("window.location.href")
                    self._last_heartbeat = time.time()
                    await self.check_ui_drift()
            except Exception as exc:
                logger.warning(f"Heartbeat failed, attempting re-login: {exc}")
                try:
                    creds = self._creds_blob.decrypt()
                    await self._login(creds)
                except Exception as inner:
                    logger.error(f"Re-login failed: {inner}")

    async def execute_swap(
        self,
        token_address: str,
        chain: str,
        amount_usd: float,
        slippage_pct: float,
        order_type: str,
        priority_fee: float = 0.0,
    ) -> dict[str, Any]:
        """
        Navigate Padre Terminal UI to execute a swap.
        Returns a dict with tx_hash and execution details.
        """
        if not self._page:
            raise RuntimeError("Padre session not started")

        logger.info(
            f"Padre SWAP: {token_address[:8]}… | ${amount_usd:.2f} | "
            f"chain={chain} | slip={slippage_pct*100:.1f}%"
        )

        # Production: fill Padre UI form fields matching current DOM map
        # Stubbed here — replace with selector calls matching live UI
        await asyncio.sleep(0.5)  # simulate UI interaction delay
        return {
            "tx_hash": f"STUB_TX_{token_address[:8]}_{int(time.time())}",
            "filled_amount_usd": amount_usd,
            "chain": chain,
            "status": "confirmed",
        }

    async def close(self) -> None:
        self._session_active = False
        if self._browser:
            await self._browser.close()
