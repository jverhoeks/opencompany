import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from opencompany.agents.runner import run_persona
from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def _resolve_persona(channel: str, chat_type: str, peer: str) -> Persona | None:
    """Resolve which persona handles this message based on bindings."""
    # Default to CEO for all messages for now
    async with async_session() as session:
        persona = await session.get(Persona, "ceo")
        return persona


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Welcome to OpenCompany. I'm the team. Ask me anything!")
    except Exception:
        logger.exception("Failed to send start message")


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_type = "group" if update.effective_chat.type in ("group", "supergroup") else "direct"
    peer = str(update.effective_user.id)

    persona = await _resolve_persona("telegram", chat_type, peer)
    if not persona:
        await update.message.reply_text("No persona available.")
        return

    await update.message.reply_text(f"[{persona.name}] Processing...")

    try:
        result = await run_persona(persona, user_message)
        # Telegram has a 4096 char limit
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i : i + 4000])
    except Exception:
        logger.exception("Error processing message from user %s", peer)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")


def create_telegram_app() -> Application | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping Telegram")
        return None

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    return app
