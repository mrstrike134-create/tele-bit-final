"""
Personal Revision Bank Service (Azure SQL Database).
Manages user-owned subtopics, saved questions, Mistake/Difficult categories,
hierarchy organization (Subject -> Subtopic -> Question -> Category),
question editing (with copy-on-write isolation), filtering, search, and TXT export.
Every user strictly accesses only their own personal revision data.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from bot.database.pool import AzureSQLPool
from bot.services.auth_service import resolve_db_user_id
from bot.services.module_service import list_subjects, get_subject

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"mistake", "difficult"}

CATEGORY_LABELS = {
    "mistake": "❌ Mistake",
    "difficult": "⭐ Difficult",
}


def normalize_category(cat: Optional[str]) -> Optional[str]:
    """Normalize category filter/input strings to 'mistake' or 'difficult'."""
    if not cat:
        return None
    c = cat.strip().lower()
    if c in ("mistake", "mistakes"):
        return "mistake"
    if c in ("difficult", "hard", "starred"):
        return "difficult"
    return None


# ============================================================================
# User-Owned Subtopics Management
# ============================================================================

async def list_user_subtopics(
    pool: AzureSQLPool,
    user_id: int,
    subject_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    List personal subtopics belonging to `user_id`, optionally filtered by `subject_id`.
    Includes question count per subtopic for this user.
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    params: List[Any] = [db_uid, db_uid]
    where_clause = "WHERE us.user_id = ?"
    if subject_id is not None:
        where_clause += " AND us.subject_id = ?"
        params.append(subject_id)

    rows = await pool.fetchall(
        f"""
        SELECT
            us.id,
            us.user_id,
            us.subject_id,
            m.title AS subject_name,
            us.name,
            us.created_at,
            us.updated_at,
            (
                SELECT COUNT(DISTINCT sq.question_id)
                FROM saved_questions sq
                WHERE sq.user_id = ?
                  AND sq.subtopic_id = us.id
                  AND sq.source IN ('mistake', 'difficult')
            ) AS question_count
        FROM user_subtopics us
        INNER JOIN modules m ON us.subject_id = m.id
        {where_clause}
        ORDER BY m.sort_order ASC, m.title ASC, us.name ASC
        """,
        *params
    )
    return rows


async def get_user_subtopic(
    pool: AzureSQLPool,
    user_id: int,
    subtopic_id: int
) -> Optional[Dict[str, Any]]:
    """Retrieve a single personal subtopic owned by `user_id`."""
    db_uid = await resolve_db_user_id(pool, user_id)
    return await pool.fetchone(
        """
        SELECT us.id, us.user_id, us.subject_id, m.title AS subject_name, us.name, us.created_at, us.updated_at
        FROM user_subtopics us
        INNER JOIN modules m ON us.subject_id = m.id
        WHERE us.id = ? AND us.user_id = ?
        """,
        subtopic_id, db_uid
    )


async def get_or_create_user_subtopic(
    pool: AzureSQLPool,
    user_id: int,
    subject_id: int,
    name: str
) -> Dict[str, Any]:
    """
    Get an existing personal subtopic by (user_id, subject_id, name) or create a new one.
    """
    cleaned_name = " ".join((name or "").strip().split())
    if not cleaned_name:
        raise ValueError("Subtopic name cannot be empty.")
    if len(cleaned_name) > 200:
        cleaned_name = cleaned_name[:200]

    db_uid = await resolve_db_user_id(pool, user_id)

    subject = await get_subject(pool, subject_id)
    if not subject:
        raise ValueError("Selected subject does not exist.")

    existing = await pool.fetchone(
        """
        SELECT us.id, us.user_id, us.subject_id, m.title AS subject_name, us.name, us.created_at, us.updated_at
        FROM user_subtopics us
        INNER JOIN modules m ON us.subject_id = m.id
        WHERE us.user_id = ? AND us.subject_id = ? AND LOWER(us.name) = LOWER(?)
        """,
        db_uid, subject_id, cleaned_name
    )
    if existing:
        return existing

    subtopic_id = await pool.execute_Init_id(
        """
        INSERT INTO user_subtopics (user_id, subject_id, name, created_at, updated_at)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET())
        """,
        db_uid, subject_id, cleaned_name
    )
    return await get_user_subtopic(pool, db_uid, subtopic_id)


async def rename_user_subtopic(
    pool: AzureSQLPool,
    user_id: int,
    subtopic_id: int,
    new_name: str
) -> Tuple[bool, str]:
    """Rename a user-owned subtopic without affecting any other user."""
    cleaned = " ".join((new_name or "").strip().split())
    if not cleaned:
        return False, "Subtopic name cannot be empty."
    if len(cleaned) > 200:
        cleaned = cleaned[:200]

    db_uid = await resolve_db_user_id(pool, user_id)
    subtopic = await get_user_subtopic(pool, db_uid, subtopic_id)
    if not subtopic:
        return False, "Subtopic not found in your account."

    collision = await pool.fetchone(
        """
        SELECT id FROM user_subtopics
        WHERE user_id = ? AND subject_id = ? AND LOWER(name) = LOWER(?) AND id <> ?
        """,
        db_uid, subtopic["subject_id"], cleaned, subtopic_id
    )
    if collision:
        return False, f"A subtopic named '{cleaned}' already exists under {subtopic['subject_name']}."

    await pool.execute(
        """
        UPDATE user_subtopics
        SET name = ?, updated_at = SYSDATETIMEOFFSET()
        WHERE id = ? AND user_id = ?
        """,
        cleaned, subtopic_id, db_uid
    )
    return True, f"Subtopic renamed to '{cleaned}'."


async def move_user_subtopic(
    pool: AzureSQLPool,
    user_id: int,
    subtopic_id: int,
    target_subject_id: int
) -> Tuple[bool, str]:
    """Move a user's subtopic (and all questions in it) to another subject."""
    db_uid = await resolve_db_user_id(pool, user_id)
    subtopic = await get_user_subtopic(pool, db_uid, subtopic_id)
    if not subtopic:
        return False, "Subtopic not found in your account."

    target_subject = await get_subject(pool, target_subject_id)
    if not target_subject:
        return False, "Target subject not found."

    if subtopic["subject_id"] == target_subject_id:
        return True, "Subtopic is already under that subject."

    existing_in_target = await pool.fetchone(
        """
        SELECT id FROM user_subtopics
        WHERE user_id = ? AND subject_id = ? AND LOWER(name) = LOWER(?) AND id <> ?
        """,
        db_uid, target_subject_id, subtopic["name"], subtopic_id
    )

    async with pool.transaction() as cur:
        if existing_in_target:
            target_subtopic_id = existing_in_target["id"]
            await cur.execute(
                """
                UPDATE saved_questions
                SET subject_id = ?, subtopic_id = ?
                WHERE user_id = ? AND subtopic_id = ?
                """,
                (target_subject_id, target_subtopic_id, db_uid, subtopic_id)
            )
            await cur.execute(
                "DELETE FROM user_subtopics WHERE id = ? AND user_id = ?",
                (subtopic_id, db_uid)
            )
        else:
            await cur.execute(
                """
                UPDATE user_subtopics
                SET subject_id = ?, updated_at = SYSDATETIMEOFFSET()
                WHERE id = ? AND user_id = ?
                """,
                (target_subject_id, subtopic_id, db_uid)
            )
            await cur.execute(
                """
                UPDATE saved_questions
                SET subject_id = ?
                WHERE user_id = ? AND subtopic_id = ?
                """,
                (target_subject_id, db_uid, subtopic_id)
            )

    return True, f"Moved subtopic '{subtopic['name']}' to {target_subject['name']}."


async def delete_user_subtopic(
    pool: AzureSQLPool,
    user_id: int,
    subtopic_id: int
) -> Tuple[bool, str]:
    """Delete a user's subtopic (questions remain in their subject with subtopic unassigned)."""
    db_uid = await resolve_db_user_id(pool, user_id)
    subtopic = await get_user_subtopic(pool, db_uid, subtopic_id)
    if not subtopic:
        return False, "Subtopic not found in your account."

    async with pool.transaction() as cur:
        await cur.execute(
            "UPDATE saved_questions SET subtopic_id = NULL WHERE user_id = ? AND subtopic_id = ?",
            (db_uid, subtopic_id)
        )
        await cur.execute(
            "DELETE FROM user_subtopics WHERE id = ? AND user_id = ?",
            (subtopic_id, db_uid)
        )
    return True, f"Subtopic '{subtopic['name']}' removed."


# ============================================================================
# Saving & Categorizing Questions
# ============================================================================

async def save_question_to_revision_bank(
    pool: AzureSQLPool,
    user_id: int,
    question_id: int,
    source: str,
    notes: Optional[str] = None,
    subject_id: Optional[int] = None,
    subtopic_id: Optional[int] = None,
    subtopic_name: Optional[str] = None,
    module_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Save a question into `user_id`'s personal revision bank under 'mistake' or 'difficult'.
    Prevents duplicate saves of the same question to the same category while allowing
    the same question to belong to both 'mistake' and 'difficult' simultaneously.
    """
    category = normalize_category(source)
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid revision category: {source}. Must be 'mistake' or 'difficult'.")

    db_uid = await resolve_db_user_id(pool, user_id)

    effective_subject_id = subject_id if subject_id is not None else module_id
    effective_subtopic_id = subtopic_id

    if effective_subtopic_id is not None:
        st_row = await get_user_subtopic(pool, db_uid, effective_subtopic_id)
        if not st_row:
            raise ValueError("Selected subtopic does not belong to this user.")
        if effective_subject_id is None:
            effective_subject_id = st_row["subject_id"]
        elif st_row["subject_id"] != effective_subject_id:
            effective_subject_id = st_row["subject_id"]

    elif subtopic_name and subtopic_name.strip() and effective_subject_id is not None:
        st_row = await get_or_create_user_subtopic(
            pool, db_uid, effective_subject_id, subtopic_name.strip()
        )
        effective_subtopic_id = st_row["id"]

    existing_any = await pool.fetchone(
        """
        SELECT TOP 1 id, subject_id, subtopic_id, notes
        FROM saved_questions
        WHERE user_id = ? AND question_id = ?
        ORDER BY created_at DESC
        """,
        db_uid, question_id
    )

    if existing_any:
        if effective_subject_id is None:
            effective_subject_id = existing_any.get("subject_id")
        if effective_subtopic_id is None and subject_id is None and module_id is None:
            effective_subtopic_id = existing_any.get("subtopic_id")

    if effective_subject_id is None:
        qb_row = await pool.fetchone(
            "SELECT module_id FROM question_bank WHERE id = ?", question_id
        )
        if qb_row and qb_row.get("module_id"):
            effective_subject_id = qb_row["module_id"]

    existing_cat = await pool.fetchone(
        """
        SELECT id, subject_id, subtopic_id
        FROM saved_questions
        WHERE user_id = ? AND question_id = ? AND source = ?
        """,
        db_uid, question_id, category
    )

    if existing_cat:
        if effective_subject_id is not None:
            await pool.execute(
                """
                UPDATE saved_questions
                SET subject_id = ?, subtopic_id = ?
                WHERE user_id = ? AND question_id = ?
                """,
                effective_subject_id, effective_subtopic_id, db_uid, question_id
            )
        if notes is not None:
            await pool.execute(
                "UPDATE saved_questions SET notes = ? WHERE id = ? AND user_id = ?",
                notes, existing_cat["id"], db_uid
            )
        return {
            "saved_id": existing_cat["id"],
            "already_exists": True,
            "source": category,
            "category": category,
            "subject_id": effective_subject_id,
            "subtopic_id": effective_subtopic_id,
        }

    saved_id = await pool.execute_Init_id(
        """
        INSERT INTO saved_questions (user_id, question_id, source, subject_id, subtopic_id, notes, created_at)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, SYSDATETIMEOFFSET())
        """,
        db_uid, question_id, category, effective_subject_id, effective_subtopic_id, notes
    )

    if effective_subject_id is not None:
        await pool.execute(
            """
            UPDATE saved_questions
            SET subject_id = ?, subtopic_id = ?
            WHERE user_id = ? AND question_id = ?
            """,
            effective_subject_id, effective_subtopic_id, db_uid, question_id
        )

    return {
        "saved_id": saved_id,
        "already_exists": False,
        "source": category,
        "category": category,
        "subject_id": effective_subject_id,
        "subtopic_id": effective_subtopic_id,
    }


async def set_question_category(
    pool: AzureSQLPool,
    user_id: int,
    question_id: int,
    category: str,
    action: str = "toggle"
) -> Tuple[bool, str]:
    """
    Add, remove, or toggle a category ('mistake' or 'difficult') for a user's saved question.
    """
    cat = normalize_category(category)
    if cat not in VALID_CATEGORIES:
        return False, "Invalid category."

    db_uid = await resolve_db_user_id(pool, user_id)

    existing_rows = await pool.fetchall(
        """
        SELECT id, source, subject_id, subtopic_id, notes
        FROM saved_questions
        WHERE user_id = ? AND question_id = ? AND source IN ('mistake', 'difficult')
        """,
        db_uid, question_id
    )
    if not existing_rows:
        return False, "Question not found in your revision bank."

    active_cats = {r["source"]: r for r in existing_rows}
    has_cat = cat in active_cats

    if action == "add" or (action == "toggle" and not has_cat):
        if has_cat:
            return True, f"Already marked as {CATEGORY_LABELS[cat]}."
        ref = existing_rows[0]
        await save_question_to_revision_bank(
            pool,
            user_id=db_uid,
            question_id=question_id,
            source=cat,
            notes=ref.get("notes"),
            subject_id=ref.get("subject_id"),
            subtopic_id=ref.get("subtopic_id"),
        )
        return True, f"Added {CATEGORY_LABELS[cat]} tag."

    elif action == "remove" or (action == "toggle" and has_cat):
        if not has_cat:
            return True, f"{CATEGORY_LABELS[cat]} tag is already removed."
        if len(active_cats) <= 1:
            return (
                False,
                "A saved question must keep at least one category (Mistake or Difficult). "
                "Add the other category first, or click Delete to remove the question."
            )
        await pool.execute(
            "DELETE FROM saved_questions WHERE user_id = ? AND question_id = ? AND source = ?",
            db_uid, question_id, cat
        )
        return True, f"Removed {CATEGORY_LABELS[cat]} tag."

    return False, "Invalid category action."


# ============================================================================
# Moving, Editing & Deleting Saved Questions (With Strict User Isolation)
# ============================================================================

async def move_saved_question(
    pool: AzureSQLPool,
    user_id: int,
    question_id: int,
    subject_id: int,
    subtopic_id: Optional[int] = None,
    new_subtopic_name: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Change the subject and/or personal subtopic of a user's saved question.
    Never modifies another user's organization.
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    owned = await pool.fetchone(
        "SELECT TOP 1 id FROM saved_questions WHERE user_id = ? AND question_id = ?",
        db_uid, question_id
    )
    if not owned:
        return False, "Question not found in your revision bank."

    subject = await get_subject(pool, subject_id)
    if not subject:
        return False, "Selected subject does not exist."

    resolved_subtopic_id: Optional[int] = None
    if new_subtopic_name and new_subtopic_name.strip():
        st = await get_or_create_user_subtopic(
            pool, db_uid, subject_id, new_subtopic_name.strip()
        )
        resolved_subtopic_id = st["id"]
    elif subtopic_id is not None:
        st = await get_user_subtopic(pool, db_uid, subtopic_id)
        if not st:
            return False, "Selected subtopic not found in your account."
        if st["subject_id"] != subject_id:
            return False, "Selected subtopic belongs to a different subject."
        resolved_subtopic_id = st["id"]

    await pool.execute(
        """
        UPDATE saved_questions
        SET subject_id = ?, subtopic_id = ?
        WHERE user_id = ? AND question_id = ?
        """,
        subject_id, resolved_subtopic_id, db_uid, question_id
    )
    return True, "Question organization updated."


async def edit_saved_question(
    pool: AzureSQLPool,
    user_id: int,
    question_id: int,
    question_text: str,
    options: List[str],
    correct_option_index: int = -1,
    explanation: Optional[str] = None,
    notes: Optional[str] = None,
    subject_id: Optional[int] = None,
    subtopic_id: Optional[int] = None,
    new_subtopic_name: Optional[str] = None,
) -> Tuple[bool, str, int]:
    """
    Edit a user's saved question.
    Uses copy-on-write if the underlying question_bank row is shared with other users
    or linked to a global telegram_poll_id, ensuring another user's record is never altered.
    Returns (success, message, effective_question_id).
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    owned_rows = await pool.fetchall(
        """
        SELECT id, source, subject_id, subtopic_id, notes
        FROM saved_questions
        WHERE user_id = ? AND question_id = ?
        """,
        db_uid, question_id
    )
    if not owned_rows:
        return False, "Question not found in your revision bank.", question_id

    cleaned_q = (question_text or "").strip()
    if not cleaned_q:
        return False, "Question text cannot be empty.", question_id

    cleaned_opts = [o.strip() for o in options if o and o.strip()]
    if len(cleaned_opts) < 2:
        return False, "Please provide at least 2 non-empty answer options.", question_id

    if correct_option_index is not None and 0 <= int(correct_option_index) < len(cleaned_opts):
        effective_correct_idx = int(correct_option_index)
    else:
        effective_correct_idx = -1

    cleaned_exp = (explanation or "").strip() or None
    cleaned_notes = (notes or "").strip() or None

    eff_subject_id = subject_id if subject_id is not None else owned_rows[0].get("subject_id")
    eff_subtopic_id = subtopic_id if subtopic_id is not None else owned_rows[0].get("subtopic_id")

    if new_subtopic_name and new_subtopic_name.strip() and eff_subject_id is not None:
        st = await get_or_create_user_subtopic(pool, db_uid, eff_subject_id, new_subtopic_name.strip())
        eff_subtopic_id = st["id"]
    elif eff_subtopic_id is not None:
        st = await get_user_subtopic(pool, db_uid, eff_subtopic_id)
        if not st or (eff_subject_id is not None and st["subject_id"] != eff_subject_id):
            eff_subtopic_id = None

    other_users_count = await pool.fetchval(
        "SELECT COUNT(*) FROM saved_questions WHERE question_id = ? AND user_id <> ?",
        question_id, db_uid
    )
    qb_row = await pool.fetchone(
        "SELECT id, telegram_poll_id FROM question_bank WHERE id = ?",
        question_id
    )
    needs_fork = bool(other_users_count and int(other_users_count) > 0) or bool(
        qb_row and qb_row.get("telegram_poll_id")
    )

    target_question_id = question_id

    async with pool.transaction() as cur:
        if needs_fork:
            await cur.execute(
                """
                INSERT INTO question_bank (
                    module_id, subtopic, text, explanation, question_type, difficulty,
                    correct_option_index, telegram_poll_id, created_at
                )
                OUTPUT INSERTED.id
                VALUES (?, NULL, ?, ?, N'multiple_choice', N'medium', ?, NULL, SYSDATETIMEOFFSET())
                """,
                (eff_subject_id, cleaned_q, cleaned_exp, effective_correct_idx)
            )
            fork_row = await cur.fetchone()
            target_question_id = int(fork_row[0])

            for idx, opt_text in enumerate(cleaned_opts):
                is_corr = 1 if (effective_correct_idx >= 0 and idx == effective_correct_idx) else 0
                await cur.execute(
                    """
                    INSERT INTO question_bank_options (question_id, option_text, is_correct, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (target_question_id, opt_text, is_corr, idx)
                )

            await cur.execute(
                """
                UPDATE saved_questions
                SET question_id = ?, subject_id = ?, subtopic_id = ?, notes = ?
                WHERE user_id = ? AND question_id = ?
                """,
                (target_question_id, eff_subject_id, eff_subtopic_id, cleaned_notes, db_uid, question_id)
            )
        else:
            await cur.execute(
                """
                UPDATE question_bank
                SET module_id = ?, text = ?, explanation = ?, correct_option_index = ?
                WHERE id = ?
                """,
                (eff_subject_id, cleaned_q, cleaned_exp, effective_correct_idx, question_id)
            )
            await cur.execute(
                "DELETE FROM question_bank_options WHERE question_id = ?",
                (question_id,)
            )
            for idx, opt_text in enumerate(cleaned_opts):
                is_corr = 1 if (effective_correct_idx >= 0 and idx == effective_correct_idx) else 0
                await cur.execute(
                    """
                    INSERT INTO question_bank_options (question_id, option_text, is_correct, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (question_id, opt_text, is_corr, idx)
                )
            await cur.execute(
                """
                UPDATE saved_questions
                SET subject_id = ?, subtopic_id = ?, notes = ?
                WHERE user_id = ? AND question_id = ?
                """,
                (eff_subject_id, eff_subtopic_id, cleaned_notes, db_uid, question_id)
            )

    return True, "Question updated successfully.", target_question_id


async def delete_saved_question(
    pool: AzureSQLPool,
    user_id: int,
    question_id: int
) -> bool:
    """
    Delete a question from `user_id`'s personal revision bank.
    Never deletes the shared source question in `question_bank` or any other user's record.
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    existing = await pool.fetchone(
        "SELECT TOP 1 id FROM saved_questions WHERE user_id = ? AND question_id = ?",
        db_uid, question_id
    )
    if not existing:
        return False

    await pool.execute(
        "DELETE FROM saved_questions WHERE user_id = ? AND question_id = ?",
        db_uid, question_id
    )
    return True


async def remove_saved_question(
    pool: AzureSQLPool,
    user_id: int,
    saved_id: int
) -> bool:
    """
    Delete a saved question by either `saved_questions.id` or `question_id` for `user_id` only.
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    row = await pool.fetchone(
        "SELECT question_id FROM saved_questions WHERE id = ? AND user_id = ?",
        saved_id, db_uid
    )
    if row:
        await pool.execute(
            "DELETE FROM saved_questions WHERE user_id = ? AND question_id = ?",
            db_uid, row["question_id"]
        )
        return True

    return await delete_saved_question(pool, db_uid, saved_id)


# ============================================================================
# Dashboard Statistics, Hierarchy & Filtered Question Listing
# ============================================================================

async def get_dashboard_summary(pool: AzureSQLPool, user_id: int) -> Dict[str, Any]:
    """
    Compute the personal revision bank overview for the Dashboard:
      - Total saved questions (distinct questions saved by this user)
      - Mistake count
      - Difficult count
      - Number of subjects used
      - Number of personal subtopics
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    counts_row = await pool.fetchone(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN source IN ('mistake', 'difficult') THEN question_id END) AS total_questions,
            COUNT(DISTINCT CASE WHEN source = 'mistake' THEN question_id END) AS mistake_count,
            COUNT(DISTINCT CASE WHEN source = 'difficult' THEN question_id END) AS difficult_count
        FROM saved_questions
        WHERE user_id = ?
        """,
        db_uid
    )

    subjects_used = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT subject_id)
        FROM (
            SELECT COALESCE(sq.subject_id, qb.module_id) AS subject_id
            FROM saved_questions sq
            INNER JOIN question_bank qb ON sq.question_id = qb.id
            WHERE sq.user_id = ?
              AND sq.source IN ('mistake', 'difficult')
              AND COALESCE(sq.subject_id, qb.module_id) IS NOT NULL
            UNION
            SELECT us.subject_id
            FROM user_subtopics us
            WHERE us.user_id = ?
        ) AS used_subjects
        """,
        db_uid, db_uid
    )

    subtopics_count = await pool.fetchval(
        "SELECT COUNT(*) FROM user_subtopics WHERE user_id = ?",
        db_uid
    )

    return {
        "total": int((counts_row or {}).get("total_questions") or 0),
        "mistake": int((counts_row or {}).get("mistake_count") or 0),
        "difficult": int((counts_row or {}).get("difficult_count") or 0),
        "subjects_used": int(subjects_used or 0),
        "subtopics_count": int(subtopics_count or 0),
    }


get_revision_summary = get_dashboard_summary


async def get_user_hierarchy(pool: AzureSQLPool, user_id: int) -> List[Dict[str, Any]]:
    """
    Return the Subject -> Subtopic hierarchy for `user_id`, including question counts
    per subject and per personal subtopic.
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    subjects = await list_subjects(pool)
    subtopics = await list_user_subtopics(pool, db_uid)

    subj_counts_rows = await pool.fetchall(
        """
        SELECT
            COALESCE(sq.subject_id, qb.module_id) AS subject_id,
            COUNT(DISTINCT sq.question_id) AS total_count,
            COUNT(DISTINCT CASE WHEN sq.source = 'mistake' THEN sq.question_id END) AS mistake_count,
            COUNT(DISTINCT CASE WHEN sq.source = 'difficult' THEN sq.question_id END) AS difficult_count
        FROM saved_questions sq
        INNER JOIN question_bank qb ON sq.question_id = qb.id
        WHERE sq.user_id = ? AND sq.source IN ('mistake', 'difficult')
        GROUP BY COALESCE(sq.subject_id, qb.module_id)
        """,
        db_uid
    )
    subj_counts = {r["subject_id"]: r for r in subj_counts_rows if r.get("subject_id") is not None}

    subtopics_by_subject: Dict[int, List[Dict[str, Any]]] = {}
    for st in subtopics:
        subtopics_by_subject.setdefault(st["subject_id"], []).append(st)

    hierarchy: List[Dict[str, Any]] = []
    for s in subjects:
        sid = s["id"]
        sc = subj_counts.get(sid, {})
        hierarchy.append({
            "id": sid,
            "name": s["name"],
            "description": s.get("description"),
            "total_count": int(sc.get("total_count") or 0),
            "mistake_count": int(sc.get("mistake_count") or 0),
            "difficult_count": int(sc.get("difficult_count") or 0),
            "subtopics": subtopics_by_subject.get(sid, []),
        })
    return hierarchy


async def list_revision_questions(
    pool: AzureSQLPool,
    user_id: int,
    source: Optional[str] = None,
    category: Optional[str] = None,
    module_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    subtopic_id: Optional[int] = None,
    subtopic: Optional[str] = None,
    search_query: Optional[str] = None,
    question_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch saved questions for `user_id` with full options, subject, personal subtopic,
    and all active category tags ('mistake', 'difficult').
    Returns one card per distinct question_id so there are never duplicate cards.
    """
    db_uid = await resolve_db_user_id(pool, user_id)
    eff_category = normalize_category(category or source)
    eff_subject_id = subject_id if subject_id is not None else module_id

    rows = await pool.fetchall(
        """
        SELECT
            sq.id AS saved_id,
            sq.user_id,
            sq.question_id,
            sq.source,
            sq.notes,
            sq.created_at,
            COALESCE(sq.subject_id, qb.module_id) AS subject_id,
            m.title AS subject_name,
            sq.subtopic_id,
            COALESCE(us.name, qb.subtopic) AS subtopic_name,
            qb.text AS question_text,
            qb.explanation,
            qb.correct_option_index
        FROM saved_questions sq
        INNER JOIN question_bank qb ON sq.question_id = qb.id
        LEFT JOIN modules m ON COALESCE(sq.subject_id, qb.module_id) = m.id
        LEFT JOIN user_subtopics us ON sq.subtopic_id = us.id AND us.user_id = sq.user_id
        WHERE sq.user_id = ?
          AND sq.source IN ('mistake', 'difficult')
        ORDER BY sq.created_at DESC, sq.id DESC
        """,
        db_uid
    )

    if not rows:
        return []

    grouped: Dict[int, Dict[str, Any]] = {}
    ordered_qids: List[int] = []

    for r in rows:
        qid = r["question_id"]
        cat = r["source"]
        if qid not in grouped:
            ordered_qids.append(qid)
            grouped[qid] = {
                "saved_id": r["saved_id"],
                "question_id": qid,
                "user_id": r["user_id"],
                "subject_id": r.get("subject_id"),
                "subject_name": r.get("subject_name") or "Uncategorized",
                "module_id": r.get("subject_id"),
                "module_name": r.get("subject_name") or "Uncategorized",
                "subtopic_id": r.get("subtopic_id"),
                "subtopic_name": r.get("subtopic_name"),
                "subtopic": r.get("subtopic_name"),
                "question_text": r["question_text"],
                "explanation": r.get("explanation"),
                "correct_option_index": r.get("correct_option_index") if r.get("correct_option_index") is not None else -1,
                "notes": r.get("notes"),
                "created_at": r.get("created_at"),
                "categories": [cat],
                "saved_ids_by_category": {cat: r["saved_id"]},
            }
        else:
            item = grouped[qid]
            if cat not in item["categories"]:
                item["categories"].append(cat)
            item["saved_ids_by_category"][cat] = r["saved_id"]
            if not item.get("notes") and r.get("notes"):
                item["notes"] = r["notes"]
            if not item.get("subject_id") and r.get("subject_id"):
                item["subject_id"] = r["subject_id"]
                item["module_id"] = r["subject_id"]
                item["subject_name"] = r.get("subject_name") or "Uncategorized"
                item["module_name"] = item["subject_name"]
            if not item.get("subtopic_id") and r.get("subtopic_id"):
                item["subtopic_id"] = r["subtopic_id"]
                item["subtopic_name"] = r.get("subtopic_name")
                item["subtopic"] = r.get("subtopic_name")

    placeholders = ",".join("?" for _ in ordered_qids)
    opt_rows = await pool.fetchall(
        f"""
        SELECT id, question_id, option_text, is_correct, sort_order AS option_order, sort_order
        FROM question_bank_options
        WHERE question_id IN ({placeholders})
        ORDER BY question_id ASC, sort_order ASC
        """,
        *ordered_qids
    )
    opts_by_qid: Dict[int, List[Dict[str, Any]]] = {}
    for opt in opt_rows:
        order_idx = int(opt.get("option_order") or 0)
        letter = chr(65 + order_idx) if 0 <= order_idx < 26 else str(order_idx + 1)
        opt_dict = dict(opt)
        opt_dict["letter"] = letter
        opts_by_qid.setdefault(opt["question_id"], []).append(opt_dict)

    search_lower = search_query.strip().lower() if search_query and search_query.strip() else None
    subtopic_name_lower = subtopic.strip().lower() if subtopic and subtopic.strip() else None
    qid_filter_set = set(question_ids) if question_ids else None

    results: List[Dict[str, Any]] = []
    for qid in ordered_qids:
        item = grouped[qid]
        cats = item["categories"]
        item["categories"] = [c for c in ("mistake", "difficult") if c in cats]
        item["is_mistake"] = "mistake" in item["categories"]
        item["is_difficult"] = "difficult" in item["categories"]
        item["source"] = eff_category if (eff_category and eff_category in item["categories"]) else item["categories"][0]

        options = opts_by_qid.get(qid, [])
        item["options"] = options

        corr_idx = item.get("correct_option_index", -1)
        correct_opt_text = None
        for opt in options:
            if opt.get("is_correct") or (corr_idx is not None and corr_idx >= 0 and opt.get("option_order") == corr_idx):
                correct_opt_text = f"{opt['letter']}. {opt['option_text']}"
                break
        item["has_correct_answer"] = correct_opt_text is not None
        item["correct_option_text"] = correct_opt_text

        if qid_filter_set is not None and qid not in qid_filter_set:
            continue
        if eff_category and eff_category not in item["categories"]:
            continue
        if eff_subject_id is not None and item.get("subject_id") != eff_subject_id:
            continue
        if subtopic_id is not None and item.get("subtopic_id") != subtopic_id:
            continue
        if subtopic_name_lower and (item.get("subtopic_name") or "").strip().lower() != subtopic_name_lower:
            continue
        if search_lower:
            haystack = " ".join([
                item.get("question_text") or "",
                item.get("explanation") or "",
                item.get("subject_name") or "",
                item.get("subtopic_name") or "",
                item.get("notes") or "",
                " ".join(o.get("option_text") or "" for o in options),
            ]).lower()
            if search_lower not in haystack:
                continue

        results.append(item)

    return results


def export_revision_questions_txt(questions: List[Dict[str, Any]], title: str = "Personal Revision Bank") -> str:
    """Format saved revision questions into a clean, readable TXT export."""
    lines = [
        f"# {title}",
        f"# Total Questions: {len(questions)}",
        "",
    ]

    for idx, q in enumerate(questions, start=1):
        subj = q.get("subject_name") or "Uncategorized"
        subt = q.get("subtopic_name")
        tags = ", ".join(CATEGORY_LABELS.get(c, c) for c in q.get("categories", []))
        header_meta = f"[{subj}" + (f" -> {subt}" if subt else "") + (f" | {tags}]" if tags else "]")

        lines.append(f"{idx}. {q['question_text']}")
        lines.append(f"   Organization: {header_meta}")

        options = q.get("options", [])
        corr_idx = q.get("correct_option_index", -1)
        correct_letter = None

        for opt_idx, opt in enumerate(options):
            letter = opt.get("letter") or chr(65 + opt_idx)
            lines.append(f"{letter}) {opt['option_text']}")
            if opt.get("is_correct") or (corr_idx is not None and corr_idx >= 0 and opt_idx == corr_idx):
                correct_letter = letter

        if correct_letter:
            lines.append(f"Answer: {correct_letter}")
        if q.get("explanation"):
            lines.append(f"Explanation: {q['explanation']}")
        if q.get("notes"):
            lines.append(f"Notes: {q['notes']}")
        lines.append("")

    return "\n".join(lines)
