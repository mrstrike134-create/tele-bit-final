"""
Inline Keyboards for Telegram Bot Forwarded-Question Intake Workflow:
Subject -> Subtopic (existing or create new) -> Category (Mistake / Difficult).
"""
from typing import List, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_subject_keyboard(subjects: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Step 1: Choose an academic subject."""
    rows: List[List[InlineKeyboardButton]] = []
    current_row: List[InlineKeyboardButton] = []

    for s in subjects:
        btn = InlineKeyboardButton(
            text=f"📘 {s['name']}",
            callback_data=f"rev_subj:{s['id']}"
        )
        current_row.append(btn)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append([
        InlineKeyboardButton(text="✖️ Cancel", callback_data="rev_cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_subtopic_keyboard(
    subtopics: List[Dict[str, Any]],
    subject_id: int
) -> InlineKeyboardMarkup:
    """Step 2: Choose an existing personal subtopic or create a new one."""
    rows: List[List[InlineKeyboardButton]] = []
    current_row: List[InlineKeyboardButton] = []

    for st in subtopics:
        label = st["name"]
        if len(label) > 28:
            label = label[:25] + "..."
        btn = InlineKeyboardButton(
            text=f"📂 {label}",
            callback_data=f"rev_subt:{st['id']}"
        )
        current_row.append(btn)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append([
        InlineKeyboardButton(
            text="➕ Create New Subtopic",
            callback_data=f"rev_new_subt:{subject_id}"
        )
    ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Back to Subjects", callback_data="rev_back_subj"),
        InlineKeyboardButton(text="✖️ Cancel", callback_data="rev_cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_category_keyboard(subject_id: int) -> InlineKeyboardMarkup:
    """Step 3: Choose a category (Mistake or Difficult)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Mistake",
                    callback_data="rev_cat:mistake"
                ),
                InlineKeyboardButton(
                    text="⭐ Difficult",
                    callback_data="rev_cat:difficult"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Subtopics",
                    callback_data=f"rev_subj:{subject_id}"
                ),
                InlineKeyboardButton(
                    text="✖️ Cancel",
                    callback_data="rev_cancel"
                ),
            ],
        ]
    )


def build_also_save_keyboard(
    other_category: str,
    question_id: int,
    subject_id: Optional[int],
    subtopic_id: Optional[int]
) -> InlineKeyboardMarkup:
    """Optional 1-tap button on save confirmation to also save under the other category."""
    label = "⭐ Also Save as Difficult" if other_category == "difficult" else "❌ Also Save as Mistake"
    sid = subject_id or 0
    stid = subtopic_id or 0
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rev_also:{other_category}:{question_id}:{sid}:{stid}"
                )
            ]
        ]
    )


def build_account_credentials_keyboard() -> InlineKeyboardMarkup:
    """Quick-action buttons for login credentials and password reset."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔑 Get New Code",
                    callback_data="get_login_code"
                ),
                InlineKeyboardButton(
                    text="🔄 Reset Password",
                    callback_data="rev_reset_pw"
                ),
            ]
        ]
    )
