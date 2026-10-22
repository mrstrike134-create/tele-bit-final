"""
Telegram Poll Extraction & Question Bank Resolution Service.
Matches live Azure SQL schema:
  - question_bank (id, module_id, text, explanation, question_type, difficulty, created_at,
                   telegram_poll_id, source_chat_id, source_message_id, correct_option_index,
                   created_by_admin, subtopic)
  - question_bank_options (id, question_id, option_text, is_correct, sort_order)
"""
import hashlib
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from bot.database.pool import AzureSQLPool

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize whitespace and casing for deterministic question matching."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return cleaned


def compute_question_hash(question_text: str, options: List[str]) -> str:
    """Compute SHA-256 hash of normalized question text + option texts."""
    norm_q = normalize_text(question_text)
    norm_opts = "|".join(normalize_text(opt) for opt in options)
    payload = f"{norm_q}||{norm_opts}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_poll_data(poll: Any) -> Dict[str, Any]:
    """
    Extract structured fields from an aiogram Poll object or dict.
    Raises ValueError with a user-friendly message if the poll cannot be parsed.
    """
    if poll is None:
        raise ValueError("No poll data found in the forwarded message.")

    raw_question = getattr(poll, "question", None)
    if raw_question is None and isinstance(poll, dict):
        raw_question = poll.get("question")
    question_text = (raw_question or "").strip()
    if not question_text:
        raise ValueError("The forwarded poll does not contain question text.")

    raw_options = getattr(poll, "options", None)
    if raw_options is None and isinstance(poll, dict):
        raw_options = poll.get("options")
    if not raw_options or len(raw_options) < 2:
        raise ValueError("The forwarded poll must contain at least 2 answer options.")

    options: List[str] = []
    for opt in raw_options:
        opt_text = getattr(opt, "text", None)
        if opt_text is None and isinstance(opt, dict):
            opt_text = opt.get("text")
        cleaned_opt = (opt_text or "").strip()
        if cleaned_opt:
            options.append(cleaned_opt)

    if len(options) < 2:
        raise ValueError("The forwarded poll must have at least 2 non-empty answer options.")

    poll_id = getattr(poll, "id", None)
    if poll_id is None and isinstance(poll, dict):
        poll_id = poll.get("id")
    poll_id_str = str(poll_id) if poll_id is not None else None

    poll_type = getattr(poll, "type", None)
    if poll_type is None and isinstance(poll, dict):
        poll_type = poll.get("type")
    poll_type_str = str(poll_type or "regular")

    correct_option_id = getattr(poll, "correct_option_id", None)
    if correct_option_id is None and isinstance(poll, dict):
        correct_option_id = poll.get("correct_option_id")

    if correct_option_id is not None:
        try:
            idx = int(correct_option_id)
            correct_index = idx if 0 <= idx < len(options) else -1
        except (ValueError, TypeError):
            correct_index = -1
    else:
        correct_index = -1

    explanation = getattr(poll, "explanation", None)
    if explanation is None and isinstance(poll, dict):
        explanation = poll.get("explanation")
    explanation_clean = (explanation or "").strip() or None

    q_hash = compute_question_hash(question_text, options)

    return {
        "telegram_poll_id": poll_id_str,
        "question_text": question_text,
        "options": options,
        "correct_option_index": correct_index,
        "has_correct_answer": correct_index >= 0,
        "explanation": explanation_clean,
        "poll_type": poll_type_str,
        "question_hash": q_hash,
    }


async def resolve_or_register_poll(
    pool: AzureSQLPool,
    poll_data: Dict[str, Any],
    user_id: Optional[int] = None,
    module_id: Optional[int] = None,
) -> Tuple[Optional[Dict[str, Any]], bool, str]:
    """
    Find an existing question in question_bank or register a new one from a forwarded poll.
    Available to all authenticated/registered users.
    Returns (question_dict, is_newly_created, status_reason).
    """
    poll_id = poll_data.get("telegram_poll_id")
    question_text = poll_data["question_text"]
    options = poll_data["options"]
    correct_idx = poll_data.get("correct_option_index", -1)
    explanation = poll_data.get("explanation")

    existing = None
    if poll_id:
        existing = await pool.fetchone(
            """
            SELECT id, module_id, subtopic, text AS question_text, text,
                   explanation, correct_option_index, telegram_poll_id
            FROM question_bank
            WHERE telegram_poll_id = ?
            """,
            poll_id
        )

    if not existing:
        existing = await pool.fetchone(
            """
            SELECT TOP 1 id, module_id, subtopic, text AS question_text, text,
                   explanation, correct_option_index, telegram_poll_id
            FROM question_bank
            WHERE LOWER(LTRIM(RTRIM(text))) = LOWER(LTRIM(RTRIM(?)))
            ORDER BY id DESC
            """,
            question_text
        )

    if existing:
        updates = []
        params: List[Any] = []
        if poll_id and not existing.get("telegram_poll_id"):
            updates.append("telegram_poll_id = ?")
            params.append(poll_id)
        if correct_idx >= 0 and (existing.get("correct_option_index") is None or existing.get("correct_option_index", -1) < 0):
            updates.append("correct_option_index = ?")
            params.append(correct_idx)
        if explanation and not existing.get("explanation"):
            updates.append("explanation = ?")
            params.append(explanation)

        if updates:
            params.append(existing["id"])
            await pool.execute(
                f"UPDATE question_bank SET {', '.join(updates)} WHERE id = ?",
                *params
            )
            if correct_idx >= 0 and (existing.get("correct_option_index") is None or existing.get("correct_option_index", -1) < 0):
                await pool.execute(
                    "UPDATE question_bank_options SET is_correct = CASE WHEN sort_order = ? THEN 1 ELSE 0 END WHERE question_id = ?",
                    correct_idx, existing["id"]
                )
            existing = await pool.fetchone(
                """
                SELECT id, module_id, subtopic, text AS question_text, text,
                       explanation, correct_option_index, telegram_poll_id
                FROM question_bank
                WHERE id = ?
                """,
                existing["id"]
            )
        return existing, False, "matched"

    async with pool.transaction() as cur:
        await cur.execute(
            """
            INSERT INTO question_bank (
                module_id, subtopic, text, explanation, question_type, difficulty,
                correct_option_index, telegram_poll_id, created_at
            )
            OUTPUT INSERTED.id
            VALUES (?, NULL, ?, ?, N'multiple_choice', N'medium', ?, ?, SYSDATETIMEOFFSET())
            """,
            (
                module_id,
                question_text,
                explanation,
                correct_idx,
                poll_id,
            )
        )
        row = await cur.fetchone()
        question_id = int(row[0])

        for idx, opt_text in enumerate(options):
            is_correct = 1 if (correct_idx >= 0 and idx == correct_idx) else 0
            await cur.execute(
                """
                INSERT INTO question_bank_options (question_id, option_text, is_correct, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (question_id, opt_text, is_correct, idx)
            )

    created = await pool.fetchone(
        """
        SELECT id, module_id, subtopic, text AS question_text, text,
               explanation, correct_option_index, telegram_poll_id
        FROM question_bank
        WHERE id = ?
        """,
        question_id
    )
    return created, True, "registered"
