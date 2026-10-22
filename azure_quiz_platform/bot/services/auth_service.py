"""
Authentication & Session Service for Personal Revision Bank (Azure SQL Database).
Matches the live Azure SQL schema:
  - users (id INT PK, telegram_user_id BIGINT, first_name, username, password_hash, last_active_at, created_at)
  - auth_tokens (id, user_id, telegram_id, token_hash, plain_code, expires_at, used, created_at)
  - web_sessions (token PK, user_id, expires_at, created_at)
"""
import hashlib
import hmac
import logging
import secrets
import string
from typing import Optional, Dict, Any, Tuple

from bot.config import LOGIN_CODE_EXPIRY_SECONDS
from bot.database.pool import AzureSQLPool

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 200_000
ALPHABET_CLEAR = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_student_password() -> str:
    """Generate a human-friendly permanent password (e.g., MED-7482-XK)."""
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    letters = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2))
    return f"MED-{digits}-{letters}"


def normalize_code(code: str) -> str:
    """Normalize a login code by removing spaces/hyphens and converting to uppercase."""
    return (code or "").replace("-", "").replace(" ", "").strip().upper()


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        )
        return hmac.compare_digest(dk.hex(), expected_hex)
    except Exception as e:
        logger.warning(f"Password verification error: {e}")
        return False


def _format_user_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "db_id": row["id"],
        "telegram_id": row["telegram_user_id"],
        "telegram_user_id": row["telegram_user_id"],
        "username": row.get("username"),
        "first_name": row.get("first_name") or "User",
        "password_hash": row.get("password_hash"),
        "has_password": bool(row.get("password_hash")),
        "last_active_at": row.get("last_active_at"),
        "created_at": row.get("created_at"),
    }


async def ensure_user_exists(
    pool: AzureSQLPool,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> Dict[str, Any]:
    """
    Ensure a user row exists in Azure SQL (matching either telegram_user_id or internal id)
    and return formatted user details.
    """
    row = await pool.fetchone(
        """
        SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
        FROM users
        WHERE telegram_user_id = ?
        """,
        telegram_id
    )
    if not row and telegram_id <= 2_147_483_647:
        row = await pool.fetchone(
            """
            SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
            FROM users
            WHERE id = ?
            """,
            telegram_id
        )

    if not row:
        await pool.execute(
            """
            INSERT INTO users (
                telegram_user_id, first_name, username, is_admin,
                total_xp, level, current_streak, longest_streak,
                last_active_at, created_at
            )
            VALUES (?, ?, ?, 0, 0, 1, 0, 0, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET())
            """,
            telegram_id, first_name or "User", username
        )
        row = await pool.fetchone(
            """
            SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
            FROM users
            WHERE telegram_user_id = ?
            """,
            telegram_id
        )
    else:
        if (username and username != row.get("username")) or (
            first_name and first_name != "User" and first_name != row.get("first_name")
        ):
            await pool.execute(
                """
                UPDATE users
                SET username = COALESCE(?, username),
                    first_name = COALESCE(?, first_name),
                    last_active_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                username, first_name, row["id"]
            )
            row = await pool.fetchone(
                """
                SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
                FROM users
                WHERE id = ?
                """,
                row["id"]
            )

    return _format_user_row(row)


async def ensure_user_with_password(
    pool: AzureSQLPool,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Ensure a user exists and has a permanent password.
    If the user does not have a password yet, auto-generates one (e.g. MED-1234-AB)
    and returns (user_dict, generated_password). Otherwise returns (user_dict, None).
    """
    user = await ensure_user_exists(pool, telegram_id, username, first_name)
    if not user.get("password_hash"):
        plain_pw = generate_student_password()
        pw_hash = hash_password(plain_pw)
        await pool.execute(
            """
            UPDATE users
            SET password_hash = ?,
                last_active_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            pw_hash, user["id"]
        )
        user["password_hash"] = pw_hash
        user["has_password"] = True
        return user, plain_pw
    return user, None


async def reset_student_password(
    pool: AzureSQLPool,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> str:
    """
    Generate a fresh permanent password (MED-XXXX-XX), save its hash to `users.password_hash`,
    and return the plaintext password.
    """
    user = await ensure_user_exists(pool, telegram_id, username, first_name)
    plain_pw = generate_student_password()
    pw_hash = hash_password(plain_pw)
    await pool.execute(
        """
        UPDATE users
        SET password_hash = ?,
            last_active_at = SYSDATETIMEOFFSET()
        WHERE id = ?
        """,
        pw_hash, user["id"]
    )
    return plain_pw


async def resolve_db_user_id(pool: AzureSQLPool, user_or_telegram_id: int) -> int:
    """
    Resolve either an internal `users.id` (INT) or `users.telegram_user_id` (BIGINT)
    to the authoritative `users.id` (INT) foreign key.
    """
    if user_or_telegram_id <= 2_147_483_647:
        row = await pool.fetchone("SELECT id FROM users WHERE id = ?", user_or_telegram_id)
        if row:
            return int(row["id"])

    row = await pool.fetchone(
        "SELECT id FROM users WHERE telegram_user_id = ?", user_or_telegram_id
    )
    if row:
        return int(row["id"])

    user = await ensure_user_exists(pool, user_or_telegram_id)
    return int(user["id"])


async def set_user_password(
    pool: AzureSQLPool,
    telegram_id: int,
    new_password: str,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> Tuple[bool, str]:
    """Set or reset a user's permanent password in Azure SQL."""
    cleaned = (new_password or "").strip()
    if len(cleaned) < 6:
        return False, "Password must be at least 6 characters long."
    if len(cleaned) > 128:
        return False, "Password cannot exceed 128 characters."

    user = await ensure_user_exists(pool, telegram_id, username, first_name)
    pw_hash = hash_password(cleaned)

    await pool.execute(
        """
        UPDATE users
        SET password_hash = ?,
            last_active_at = SYSDATETIMEOFFSET()
        WHERE id = ?
        """,
        pw_hash, user["id"]
    )
    return True, "Password updated successfully."


async def change_user_password(
    pool: AzureSQLPool,
    user_or_telegram_id: int,
    current_password: Optional[str],
    new_password: str
) -> Tuple[bool, str]:
    """
    Change password from the web Settings page.
    If the user already has a password set, verifies current_password first.
    """
    user = await ensure_user_exists(pool, user_or_telegram_id)
    existing_hash = user.get("password_hash")
    if existing_hash:
        curr_clean = (current_password or "").strip()
        if not curr_clean or not (
            verify_password(curr_clean, existing_hash)
            or verify_password(curr_clean.upper(), existing_hash)
        ):
            return False, "Current password is incorrect."

    return await set_user_password(pool, user["telegram_id"], new_password)


async def generate_login_code(
    pool: AzureSQLPool,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = "User"
) -> str:
    """Generate a 6-digit one-time login code valid for 10 minutes in `auth_tokens`."""
    user = await ensure_user_exists(pool, telegram_id, username, first_name)

    code = f"{secrets.randbelow(900000) + 100000}"
    token_hash = hashlib.sha256(f"{user['telegram_id']}:{code}".encode("utf-8")).hexdigest()

    await pool.execute(
        """
        INSERT INTO auth_tokens (user_id, telegram_id, token_hash, plain_code, expires_at, used, created_at)
        VALUES (?, ?, ?, ?, DATEADD(SECOND, ?, SYSDATETIMEOFFSET()), 0, SYSDATETIMEOFFSET())
        """,
        user["id"], user["telegram_id"], token_hash, code, LOGIN_CODE_EXPIRY_SECONDS
    )
    return code


async def authenticate_user_credentials(
    pool: AzureSQLPool,
    telegram_id: int,
    secret: str
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Authenticate a user by Telegram ID and either:
      1. Their permanent password (exact or case-insensitive for generated passwords), OR
      2. A valid temporary login code generated by the Telegram bot (6-digit or formatted code).
    Returns (user_dict, auth_method_or_error).
    """
    secret_clean = (secret or "").strip()
    if not secret_clean:
        return None, "Please enter your password or login code from @MistakesCore_bot."

    row = await pool.fetchone(
        """
        SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
        FROM users
        WHERE telegram_user_id = ?
        """,
        telegram_id
    )
    if not row and telegram_id <= 2_147_483_647:
        row = await pool.fetchone(
            """
            SELECT id, telegram_user_id, username, first_name, password_hash, last_active_at, created_at
            FROM users
            WHERE id = ?
            """,
            telegram_id
        )

    if not row:
        return None, "Account not found. Send /start to @MistakesCore_bot on Telegram first to register."

    user = _format_user_row(row)

    # 1. Check permanent password if set (exact match or uppercase match for MED-XXXX-XX codes)
    if user.get("password_hash"):
        if verify_password(secret_clean, user["password_hash"]) or verify_password(secret_clean.upper(), user["password_hash"]):
            return user, "password"

    # 2. Check temporary login code in auth_tokens (supports 6-digit or XXXX-XXXX-XXXX-XXXX codes)
    norm_code = normalize_code(secret_clean)
    hash_tid_code = hashlib.sha256(f"{user['telegram_id']}:{secret_clean}".encode("utf-8")).hexdigest()
    hash_norm_code = hashlib.sha256(norm_code.encode("utf-8")).hexdigest()

    code_row = await pool.fetchone(
        """
        SELECT TOP 1 id
        FROM auth_tokens
        WHERE (telegram_id = ? OR user_id = ?)
          AND (
              plain_code = ?
              OR plain_code = ?
              OR token_hash = ?
              OR token_hash = ?
          )
          AND used = 0
          AND expires_at > SYSDATETIMEOFFSET()
        ORDER BY id DESC
        """,
        user["telegram_id"],
        user["id"],
        secret_clean,
        norm_code,
        hash_tid_code,
        hash_norm_code,
    )
    if code_row:
        await pool.execute(
            "UPDATE auth_tokens SET used = 1 WHERE id = ?",
            code_row["id"]
        )
        return user, "login_code"

    if user.get("password_hash"):
        return None, "Invalid password or expired login code. Send /resetpassword or /login to @MistakesCore_bot on Telegram to get a new password."
    return None, "Invalid or expired login code. Send /start or /login to @MistakesCore_bot on Telegram to get a fresh login code."


async def create_auth_session(pool: AzureSQLPool, user_or_telegram_id: int, days: int = 14) -> str:
    """Create a persistent web session token in `web_sessions`."""
    db_user_id = await resolve_db_user_id(pool, user_or_telegram_id)
    token = secrets.token_urlsafe(32)
    await pool.execute(
        """
        INSERT INTO web_sessions (token, user_id, expires_at, created_at)
        VALUES (?, ?, DATEADD(DAY, ?, SYSDATETIMEOFFSET()), SYSDATETIMEOFFSET())
        """,
        token, db_user_id, days
    )
    return token


async def validate_auth_session(pool: AzureSQLPool, token: str) -> Optional[Dict[str, Any]]:
    """Validate a web session token in `web_sessions` and return the authenticated user dictionary."""
    if not token:
        return None

    row = await pool.fetchone(
        """
        SELECT u.id, u.telegram_user_id, u.username, u.first_name, u.password_hash, u.last_active_at, u.created_at
        FROM web_sessions ws
        INNER JOIN users u ON ws.user_id = u.id
        WHERE ws.token = ? AND ws.expires_at > SYSDATETIMEOFFSET()
        """,
        token
    )
    if not row:
        return None

    return _format_user_row(row)


async def revoke_auth_session(pool: AzureSQLPool, token: str):
    """Delete a web session token on logout."""
    if token:
        await pool.execute("DELETE FROM web_sessions WHERE token = ?", token)
