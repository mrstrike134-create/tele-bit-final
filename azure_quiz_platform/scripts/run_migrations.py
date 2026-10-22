import asyncio
import os
import sys
import logging

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from bot.database.pool import init_db_pool, close_db_pool
from bot.database.schema import run_migrations

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("azure_migrations")


async def main():
    logger.info("Connecting to Microsoft Azure SQL Database...")
    try:
        pool = await init_db_pool()
        logger.info("Executing Azure SQL schema migrations...")
        await run_migrations(pool)
        logger.info("All Azure SQL migrations applied successfully.")
        await close_db_pool(pool)
    except Exception as e:
        logger.error(f"Migration execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
