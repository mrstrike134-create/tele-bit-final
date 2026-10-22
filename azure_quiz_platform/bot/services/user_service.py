"""
User Account Service for Personal Revision Bank.
Manages user registration and account profile details without quiz XP, levels, or leaderboards.
"""
import logging
from typing import Dict, Any, Optional
from bot.database.pool import AzureSQLPool
from bot.services.auth_service import ensure_user_exists, resolve_db_user_id

logger = logging.getLogger(__name__)


async def get_or_create_user(
    pool: AzureSQLPool,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> Dict[str, Any]:
    """Ensure a user record exists in Azure SQL and return their account info."""
    return await ensure_user_exists(pool, user_id, username=username, first_name=first_name)


async def get_user_account(pool: AzureSQLPool, user_or_telegram_id: int) -> Optional[Dict[str, Any]]:
    """Fetch user account information for the Settings / Account page."""
    db_uid = await resolve_db_user_id(pool, user_or_telegram_id)
    row = await pool.fetchone(
        """
        SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
        FROM users
        WHERE id = ?
        """,
        db_uid
    )
    if not row:
        return None

    return {
        "id": row["id"],
        "db_id": row["id"],
        "telegram_id": row["telegram_user_id"],
        "telegram_user_id": row["telegram_user_id"],
        "username": row.get("username"),
        "first_name": row.get("first_name") or "User",
        "has_password": bool(row.get("password_hash")),
        "password_updated_at": row.get("last_active_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("last_active_at"),
    }
