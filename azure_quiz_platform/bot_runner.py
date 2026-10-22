"""
Standalone Telegram Bot Runner (Long-Polling).
Used for local development, background workers, and testing.
Connects directly to Microsoft Azure SQL Database.
"""
import asyncio
import logging
import sys
import os

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from bot.config import BOT_TOKEN
from bot.database.pool import init_db_pool, close_db_pool
from bot.database.schema import run_migrations
from bot.telegram.bot_instance import bot, dp
from bot.telegram.dispatcher import setup_polling_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("azure_quiz_bot_runner")


async def main():
    logger.info("Initializing Microsoft Azure SQL Database pool for Telegram Bot...")
    pool = await init_db_pool()

    try:
        logger.info("Verifying Azure SQL schema migrations...")
        await run_migrations(pool)
    except Exception as e:
        logger.warning(f"Migration check completed with notice: {e}")

    logger.info("Configuring aiogram 3 event dispatcher...")
    setup_polling_handlers(pool)

    # Delete existing webhook if set so polling works smoothly
    try:
        logger.info("Checking bot webhook status...")
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.info(f"Removing old webhook: {webhook_info.url}")
            await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.warning(f"Notice querying webhook: {e}")

    bot_info = await bot.get_me()
    logger.info(f"🤖 Bot online: @{bot_info.username} (ID: {bot_info.id})")
    logger.info("Polling for Telegram updates (polls, commands, callbacks)...")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down Telegram Bot...")
        await bot.session.close()
        await close_db_pool(pool)
        logger.info("Telegram Bot stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution terminated by user.")
