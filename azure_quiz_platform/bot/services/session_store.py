"""
Persistent Telegram Bot Session Store backed by Azure SQL Database (user_sessions).
Stores temporary state when a user forwards a poll and selects Subject -> Subtopic -> Category.
"""
import logging
from typing import Optional, Dict, Any
from bot.config import BOT_SESSION_EXPIRY_SECONDS
from bot.database.pool import AzureSQLPool
from bot.services.auth_service import ensure_user_exists, resolve_db_user_id

logger = logging.getLogger(__name__)


async def save_user_session(
    pool: AzureSQLPool,
    telegram_id: int,
    pending_poll_id: Optional[str],
    pending_question_id: int,
    state: str = "waiting_subject",
    selected_module_id: Optional[int] = None,
    selected_subtopic: Optional[str] = None,
    selected_subtopic_id: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> None:
    """Create or update a user's forwarded-poll state in Azure SQL (`user_sessions`)."""
    user = await ensure_user_exists(pool, telegram_id, username=username, first_name=first_name)
    db_user_id = user["id"]

    existing = await pool.fetchone(
        "SELECT user_id FROM user_sessions WHERE user_id = ?",
        db_user_id
    )
    if existing:
        await pool.execute(
            """
            UPDATE user_sessions
            SET pending_poll_id = ?,
                question_id = ?,
                subject_id = ?,
                subtopic_name = ?,
                subtopic_id = ?,
                state = ?,
                updated_at = SYSDATETIMEOFFSET(),
                expires_at = DATEADD(SECOND, ?, SYSDATETIMEOFFSET())
            WHERE user_id = ?
            """,
            pending_poll_id,
            pending_question_id,
            selected_module_id,
            selected_subtopic,
            selected_subtopic_id,
            state,
            BOT_SESSION_EXPIRY_SECONDS,
            db_user_id,
        )
    else:
        await pool.execute(
            """
            INSERT INTO user_sessions (
                user_id, pending_poll_id, question_id,
                subject_id, subtopic_name, subtopic_id,
                state, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, SYSDATETIMEOFFSET(), DATEADD(SECOND, ?, SYSDATETIMEOFFSET()))
            """,
            db_user_id,
            pending_poll_id,
            pending_question_id,
            selected_module_id,
            selected_subtopic,
            selected_subtopic_id,
            state,
            BOT_SESSION_EXPIRY_SECONDS,
        )


async def get_user_session(pool: AzureSQLPool, telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve an active, non-expired session for a Telegram user."""
    db_user_id = await resolve_db_user_id(pool, telegram_id)
    row = await pool.fetchone(
        """
        SELECT
            user_id,
            pending_poll_id,
            question_id,
            question_id AS pending_question_id,
            subject_id,
            subject_id AS selected_module_id,
            subtopic_name,
            subtopic_name AS selected_subtopic,
            subtopic_id,
            subtopic_id AS selected_subtopic_id,
            state,
            updated_at,
            expires_at
        FROM user_sessions
        WHERE user_id = ? AND expires_at > SYSDATETIMEOFFSET()
        """,
        db_user_id
    )
    return row


async def clear_user_session(pool: AzureSQLPool, telegram_id: int) -> None:
    """Clear a user's pending poll session after saving or cancellation."""
    db_user_id = await resolve_db_user_id(pool, telegram_id)
    await pool.execute(
        "DELETE FROM user_sessions WHERE user_id = ?",
        db_user_id
    )
