"""
FastAPI Telegram Webhook Endpoint.
Handles incoming Telegram webhook updates with secret token validation
and asynchronous dispatching.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request
from bot.config import TELEGRAM_WEBHOOK_SECRET
from bot.telegram.dispatcher import process_telegram_update

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Telegram Webhook"])


@router.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token")
):
    if TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Rejected Telegram webhook: invalid secret token")
            raise HTTPException(status_code=401, detail="Invalid webhook secret token")

    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    update_id = update_data.get("update_id")
    if update_id is None:
        return {"ok": True, "skipped": "no_update_id"}

    pool = getattr(request.app.state, "db_pool", None) or getattr(request.app.state, "pool", None)

    try:
        await process_telegram_update(update_data, pool)
    except Exception as e:
        logger.error(f"Error processing Telegram update {update_id}: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}

    return {"ok": True}
