"""
Academic Subjects Service for Personal Revision Bank.
Reuses legitimate academic subjects in the Azure SQL `modules` table.
"""
import logging
from typing import List, Dict, Any, Optional
from bot.database.pool import AzureSQLPool

logger = logging.getLogger(__name__)

DEFAULT_SUBJECTS = [
    ("Anatomy", "Human Gross & Neuro Anatomy", "🫀", 1),
    ("Physiology", "Human Physiology & Organ Systems", "⚡", 2),
    ("Biochemistry", "Biochemistry & Molecular Biology", "🧪", 3),
    ("Histology", "Microscopic Anatomy & Tissues", "🔬", 4),
    ("PP", "Pathology & Pharmacology", "💊", 5),
]


async def ensure_default_subjects(pool: AzureSQLPool) -> None:
    """Ensure core academic subjects exist in the `modules` table."""
    for title, desc, icon, sort_order in DEFAULT_SUBJECTS:
        existing = await pool.fetchone(
            "SELECT id FROM modules WHERE title = ?", title
        )
        if not existing:
            await pool.execute(
                """
                INSERT INTO modules (title, description, icon, sort_order, created_at)
                VALUES (?, ?, ?, ?, SYSDATETIMEOFFSET())
                """,
                title, desc, icon, sort_order
            )


async def list_subjects(pool: AzureSQLPool) -> List[Dict[str, Any]]:
    """List all academic subjects."""
    rows = await pool.fetchall(
        """
        SELECT id, title AS name, title, description, icon, sort_order, created_at
        FROM modules
        ORDER BY
            CASE title
                WHEN 'Anatomy' THEN 1
                WHEN 'Physiology' THEN 2
                WHEN 'Biochemistry' THEN 3
                WHEN 'Histology' THEN 4
                WHEN 'PP' THEN 5
                ELSE 99
            END,
            sort_order ASC,
            title ASC
        """
    )
    if not rows:
        await ensure_default_subjects(pool)
        rows = await pool.fetchall(
            """
            SELECT id, title AS name, title, description, icon, sort_order, created_at
            FROM modules
            ORDER BY sort_order ASC, title ASC
            """
        )
    return rows


async def get_subject(pool: AzureSQLPool, subject_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single subject by ID."""
    return await pool.fetchone(
        "SELECT id, title AS name, title, description, icon, sort_order, created_at FROM modules WHERE id = ?",
        subject_id
    )


# Backward-compatible aliases
list_modules = list_subjects
get_module = get_subject
