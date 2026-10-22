"""
Telegram Update Dispatcher and Router for Personal Revision Bank.
Supports both Webhooks (direct async dispatch) and Long-Polling (aiogram Dispatcher).
"""
import logging
from typing import Dict, Any
from aiogram import Dispatcher
from aiogram.types import Update

from bot.telegram.bot_instance import bot, dp
from bot.telegram.handlers import commands, forwarded, callbacks
from bot.telegram.handlers.commands import (
    cmd_start,
    cmd_id,
    cmd_login,
    cmd_setpassword,
    cmd_resetpassword,
    cmd_cancel,
    cmd_help,
)
from bot.telegram.handlers.forwarded import (
    handle_forwarded_poll,
    handle_text_message,
    handle_unsupported_message,
)
from bot.telegram.handlers.callbacks import handle_callback_query

logger = logging.getLogger(__name__)
_routers_registered = False


def normalize_telegram_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure raw Telegram update payloads have required fields expected by aiogram."""
    if not isinstance(d, dict):
        return d

    if "message" in d and isinstance(d["message"], dict):
        msg = d["message"]
        msg.setdefault("date", 1727700000)
        if "forward_origin" in msg and isinstance(msg["forward_origin"], dict):
            fo = msg["forward_origin"]
            fo.setdefault("date", 1727700000)
        if "poll" in msg and isinstance(msg["poll"], dict):
            poll = msg["poll"]
            poll.setdefault("total_voter_count", 0)
            poll.setdefault("is_closed", False)
            poll.setdefault("is_anonymous", True)
            poll.setdefault("allows_multiple_answers", False)
            poll.setdefault("allows_revoting", False)
            poll.setdefault("members_only", False)
            if "options" in poll and isinstance(poll["options"], list):
                for idx, opt in enumerate(poll["options"]):
                    if isinstance(opt, dict):
                        opt.setdefault("persistent_id", f"opt_{idx}")
                        opt.setdefault("voter_count", 0)

    if "callback_query" in d and isinstance(d["callback_query"], dict):
        cb = d["callback_query"]
        cb.setdefault("chat_instance", "chat_instance_default")
        if "message" in cb and isinstance(cb["message"], dict):
            cb["message"].setdefault("date", 1727700000)

    return d


async def process_telegram_update(update_data: Dict[str, Any], pool: Any) -> None:
    """
    Dispatch a raw Telegram update dictionary directly.
    Used by FastAPI webhook endpoint for low-latency execution.
    """
    update_data = normalize_telegram_dict(update_data)
    update = Update.model_validate(update_data, context={"bot": bot})

    if update.message:
        msg = update.message
        text = (msg.text or "").strip()

        if text.startswith("/start"):
            await cmd_start(msg, pool)
        elif text.startswith("/id"):
            await cmd_id(msg, pool)
        elif text.startswith("/login"):
            await cmd_login(msg, pool)
        elif text.startswith("/setpassword"):
            await cmd_setpassword(msg, pool)
        elif text.startswith("/resetpassword"):
            await cmd_resetpassword(msg, pool)
        elif text.startswith("/cancel"):
            await cmd_cancel(msg, pool)
        elif text.startswith("/help"):
            await cmd_help(msg)
        elif msg.poll is not None:
            await handle_forwarded_poll(msg, pool)
        elif text and not text.startswith("/"):
            await handle_text_message(msg, pool)
        else:
            await handle_unsupported_message(msg)

    elif update.callback_query:
        await handle_callback_query(update.callback_query, pool)


def setup_polling_handlers(pool: Any) -> Dispatcher:
    """Register routers and inject `db_pool` on the aiogram Dispatcher for long-polling."""
    global _routers_registered
    dp["db_pool"] = pool
    dp["pool"] = pool

    if not _routers_registered:
        dp.include_router(commands.router)
        dp.include_router(callbacks.router)
        dp.include_router(forwarded.router)
        _routers_registered = True

    return dp
