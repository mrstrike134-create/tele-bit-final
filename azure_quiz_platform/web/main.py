"""
FastAPI Web Application for Personal Revision Bank (Microsoft Azure SQL Database).
Provides only:
  - Authentication (/login, /logout)
  - Dashboard (/)
  - My Questions (/questions, /revision)
  - Settings / Account (/settings, /account)
  - Telegram Bot Webhook (/api/telegram/webhook) + Automatic Local Polling
"""
import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from bot.config import SECRET_KEY, TELEGRAM_WEBHOOK_URL, TELEGRAM_WEBHOOK_SECRET, BOT_TOKEN
from bot.database.pool import init_db_pool, close_db_pool
from bot.database.schema import run_migrations
from bot.services.module_service import ensure_default_subjects
from bot.telegram.bot_instance import bot, dp
from bot.telegram.dispatcher import setup_polling_handlers

from web.routes import (
    auth,
    dashboard,
    revision,
    settings,
    telegram_webhook,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("revision_bank_web")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


async def _start_background_bot_polling():
    """Run Telegram bot long-polling in the background when no webhook URL is configured."""
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        logger.info(f"🤖 Telegram Bot polling active: @{me.username} (ID: {me.id})")
        await dp.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Background bot polling stopped (standalone bot_runner may be active): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Microsoft Azure SQL Database Pool...")
    pool = await init_db_pool()
    app.state.db_pool = pool

    try:
        logger.info("Verifying Azure SQL Database schema migrations...")
        await run_migrations(pool)
        await ensure_default_subjects(pool)
    except Exception as e:
        logger.warning(f"Migration check completed with warning: {e}")

    logger.info("Configuring Telegram Bot dispatcher...")
    setup_polling_handlers(pool)

    polling_task = None
    if TELEGRAM_WEBHOOK_URL:
        try:
            logger.info(f"Setting Telegram webhook to {TELEGRAM_WEBHOOK_URL}...")
            await bot.set_webhook(
                url=TELEGRAM_WEBHOOK_URL,
                secret_token=TELEGRAM_WEBHOOK_SECRET if TELEGRAM_WEBHOOK_SECRET else None,
                drop_pending_updates=False,
            )
        except Exception as e:
            logger.warning(f"Could not register Telegram webhook automatically: {e}")
    elif BOT_TOKEN and os.environ.get("DISABLE_WEB_BOT_POLLING") != "1":
        polling_task = asyncio.create_task(_start_background_bot_polling())

    logger.info("Personal Revision Bank is ready.")
    yield

    logger.info("Shutting down Personal Revision Bank...")
    if polling_task and not polling_task.done():
        polling_task.cancel()
        try:
            await dp.stop_polling()
        except Exception:
            pass
    try:
        await bot.session.close()
    except Exception:
        pass
    await close_db_pool(pool)


app = FastAPI(
    title="Personal Revision Bank",
    description="Personal Question-Storage Website & Telegram Bot powered by Microsoft Azure SQL Database",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="revision_bank_session",
    max_age=86400 * 14,
)

# Register Active Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(revision.router)
app.include_router(settings.router)
app.include_router(telegram_webhook.router)


@app.get("/health", tags=["System"])
async def health_check():
    """Azure App Service health probe endpoint."""
    return {"status": "healthy", "service": "personal_revision_bank", "database": "azure_sql"}
