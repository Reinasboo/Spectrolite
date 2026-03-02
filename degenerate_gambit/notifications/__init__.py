"""
Notifications — Telegram bot, voice alerts, and SOBRIETY MODE autopsy PDF.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import pyttsx3
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


# ── Telegram ─────────────────────────────────────────────────────────────────

_telegram_bot: Optional[Bot] = None


def get_telegram_bot() -> Optional[Bot]:
    global _telegram_bot
    if _telegram_bot is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if token:
            _telegram_bot = Bot(token=token)
    return _telegram_bot


async def send_telegram_message(text: str, chat_id: str = "") -> bool:
    bot = get_telegram_bot()
    if not bot:
        logger.debug("No Telegram bot configured; skipping notification")
        return False
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat:
        return False
    try:
        await bot.send_message(chat_id=chat, text=text, parse_mode="HTML")
        return True
    except TelegramError as exc:
        logger.warning(f"Telegram send failed: {exc}")
        return False


async def send_telegram_meme_report(report: str, symbol: str = "") -> None:
    """Send post-trade meme report to Telegram channel."""
    header = f"<b>🚀 TRADE CLOSED: ${symbol}</b>\n\n" if symbol else ""
    await send_telegram_message(f"{header}<pre>{report[:4000]}</pre>")


# ── Voice Alerts ─────────────────────────────────────────────────────────────

_voice_engine: Optional[pyttsx3.Engine] = None


def _get_voice() -> Optional[pyttsx3.Engine]:
    global _voice_engine
    if _voice_engine is None:
        try:
            _voice_engine = pyttsx3.init()
            _voice_engine.setProperty("rate", 160)
        except Exception as exc:
            logger.warning(f"TTS engine unavailable: {exc}")
    return _voice_engine


def speak_alert(text: str) -> None:
    """Blocking voice alert — call from thread pool in production."""
    engine = _get_voice()
    if engine:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            logger.debug(f"Voice alert failed: {exc}")


VOICE_CUES: dict[str, str] = {
    "moon": "MOON DETECTED. ACTIVATING MOONSHOT PROTOCOL.",
    "abort": "ABORT ABORT. EXITING POSITION NOW.",
    "rug": "RUG DETECTED. CAPITAL PROTECTED.",
    "win": "WINNER WINNER CRYPTO DINNER.",
    "loss": "WE TAKE THOSE. MOVING ON.",
    "sobriety": "SOBRIETY MODE ACTIVATED. STAND DOWN.",
    "casino": "CASINO MODE UNLOCKED. LET'S GO GAMBLING.",
}


async def play_voice_cue(cue: str) -> None:
    cue_text = VOICE_CUES.get(cue, cue)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, speak_alert, cue_text)


# ── PDF Autopsy Report ───────────────────────────────────────────────────────

def generate_autopsy_pdf(report_text: str) -> bytes:
    """
    Render a PDF 'Autopsy of a Beautiful Disaster' from report text.
    Returns PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("AUTOPSY OF A BEAUTIFUL DISASTER", styles["Title"]))
    story.append(Paragraph("SPECTROLITE — DEGENERATE GAMBIT v2.0", styles["Heading2"]))
    story.append(Spacer(1, 20))

    for line in report_text.split("\n"):
        story.append(Paragraph(line or "&nbsp;", styles["Normal"]))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()


async def deliver_autopsy_report(report_text: str) -> None:
    """
    Email the PDF autopsy report to the configured user email address.
    """
    user_email = os.getenv("USER_EMAIL", "")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")

    if not user_email or not smtp_user:
        logger.warning("Email not configured; autopsy report logged to console only")
        logger.critical(report_text)
        return

    pdf_bytes = generate_autopsy_pdf(report_text)
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = user_email
    msg["Subject"] = "Autopsy of a Beautiful Disaster — SPECTROLITE Report"
    msg.attach(MIMEText(report_text, "plain"))

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename="autopsy_report.pdf")
    msg.attach(attachment)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _send_email(smtp_host, smtp_port, smtp_user, smtp_pass, user_email, msg),
    )
    logger.info(f"Autopsy report delivered to {user_email}")


def _send_email(host, port, user, password, to, msg) -> None:
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(user, to, msg.as_string())
