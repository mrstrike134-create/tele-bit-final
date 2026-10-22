"""
Azure SQL Database Non-Destructive Backup Utility.
Exports existing data from core tables (users, modules, question_bank,
question_bank_options, saved_questions, user_subtopics) to a timestamped JSON file
before schema migrations or maintenance operations.
"""
import asyncio
import datetime
import json
import logging
import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from bot.database.pool import AzureSQLPool, init_db_pool, close_db_pool

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(ROOT_DIR, "backups")

TABLES_TO_BACKUP = [
    "users",
    "modules",
    "question_bank",
    "question_bank_options",
    "saved_questions",
    "user_subtopics",
]


def _serialize_value(val: Any) -> Any:
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return val.hex()
    return val


async def backup_database(pool: AzureSQLPool, label: str = "pre_migration") -> str:
    """Export all existing core tables to a JSON backup file in backups/."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"azure_sql_backup_{label}_{timestamp}.json")

    snapshot: Dict[str, Any] = {
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "label": label,
        "tables": {},
    }

    for table in TABLES_TO_BACKUP:
        try:
            exists = await pool.fetchval(
                "SELECT COUNT(*) FROM sys.tables WHERE name = ?", table
            )
            if not exists:
                snapshot["tables"][table] = []
                continue
            rows = await pool.fetchall(f"SELECT * FROM [{table}]")
            serialized_rows = [
                {k: _serialize_value(v) for k, v in row.items()} for row in rows
            ]
            snapshot["tables"][table] = serialized_rows
            logger.info(f"Backed up {len(serialized_rows)} rows from [{table}]")
        except Exception as e:
            logger.warning(f"Could not back up table [{table}]: {e}")
            snapshot["tables"][table] = {"error": str(e)}

    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    logger.info(f"Database backup saved to: {backup_path}")
    return backup_path


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    pool = await init_db_pool()
    try:
        path = await backup_database(pool, label="manual")
        print(f"Backup completed: {path}")
    finally:
        await close_db_pool(pool)


if __name__ == "__main__":
    asyncio.run(main())
