"""
Forwarded Telegram Poll & Subtopic Input Handlers.
Workflow:
  1. Receive forwarded Telegram poll -> extract question, options, correct answer, explanation.
  2. Ask user to select a Subject.
  3. Ask user to select an existing personal Subtopic or type/create a new one.
  4. Ask user to choose Category (❌ Mistake or ⭐ Difficult).
  5. Save to personal revision bank in Azure SQL and confirm.
"""
import html
import logging
from aiogram import Router, F
from aiogram.types import Message

from bot.database.pool import AzureSQLPool
from bot.services.auth_service import ensure_user_exists
from bot.services.module_service import list_subjects
from bot.services.poll_service import extract_poll_data, resolve_or_register_poll
from bot.services.revision_service import get_or_create_user_subtopic
from bot.services.session_store import save_user_session, get_user_session
from bot.telegram.keyboards import build_subject_keyboard, build_category_keyboard

logger = logging.getLogger(__name__)
router = Router(name="forwarded_poll_router")


@router.message(F.poll)
async def handle_forwarded_poll(message: Message, db_pool: AzureSQLPool):
    """Handle any message containing a Telegram poll or quiz."""
    user = message.from_user
    if not user:
        return

    try:
        poll_data = extract_poll_data(message.poll)
    except ValueError as ve:
        await message.answer(
            f"⚠️ <b>Could not parse this poll:</b>\n{html.escape(str(ve))}\n\n"
            f"Please forward a valid Telegram poll with a question and at least 2 answer options."
        )
        return
    except Exception as e:
        logger.error(f"Unexpected error parsing poll from user {user.id}: {e}")
        await message.answer(
            "⚠️ <b>Unable to read this poll.</b>\n"
            "Please forward a standard Telegram quiz or poll containing a question and answer options."
        )
        return

    try:
        await ensure_user_exists(
            db_pool,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name or "User"
        )
        question, is_new, _ = await resolve_or_register_poll(
            db_pool,
            poll_data=poll_data,
            user_id=user.id
        )
        if not question:
            await message.answer("⚠️ Could not register this question in the database. Please try again.")
            return

        subjects = await list_subjects(db_pool)
        if not subjects:
            await message.answer("⚠️ No academic subjects are configured yet.")
            return

        await save_user_session(
            db_pool,
            telegram_id=user.id,
            pending_poll_id=poll_data.get("telegram_poll_id"),
            pending_question_id=question["id"],
            state="waiting_subject",
            selected_module_id=None,
            selected_subtopic=None,
            selected_subtopic_id=None,
            username=user.username,
            first_name=user.first_name or "User"
        )

        q_preview = question["question_text"]
        if len(q_preview) > 220:
            q_preview = q_preview[:217] + "..."

        opts_count = len(poll_data.get("options", []))
        has_ans = poll_data.get("has_correct_answer", False)
        has_exp = bool(poll_data.get("explanation"))

        meta_parts = [f"{opts_count} options"]
        if has_ans:
            corr_idx = poll_data["correct_option_index"]
            corr_letter = chr(65 + corr_idx) if 0 <= corr_idx < 26 else str(corr_idx + 1)
            meta_parts.append(f"Answer: {corr_letter} ✅")
        if has_exp:
            meta_parts.append("Explanation preserved 💡")

        text = (
            f"📥 <b>Question Extracted</b>\n\n"
            f"❓ <i>{html.escape(q_preview)}</i>\n"
            f"📋 <code>{' • '.join(meta_parts)}</code>\n\n"
            f"<b>Step 1 of 3:</b> Choose a <b>Subject</b> for this question:"
        )
        await message.answer(
            text,
            reply_markup=build_subject_keyboard(subjects)
        )
    except Exception as e:
        logger.error(f"Error handling forwarded poll for user {user.id}: {e}")
        await message.answer(
            "⚠️ An error occurred while processing your poll. Please try forwarding it again."
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message, db_pool: AzureSQLPool):
    """
    Handle text messages:
      - If the user is currently in `waiting_new_subtopic` or `waiting_subtopic`, treat the text
        as the name of the personal subtopic to create/select under their chosen Subject.
      - Otherwise, guide the user to forward a Telegram poll.
    """
    user = message.from_user
    if not user or not message.text:
        return

    session = await get_user_session(db_pool, user.id)
    if session and session.get("state") in ("waiting_new_subtopic", "waiting_subtopic"):
        subject_id = session.get("selected_module_id")
        question_id = session.get("pending_question_id")
        subtopic_name = message.text.strip()

        if not subject_id or not question_id:
            await message.answer("⚠️ Session expired. Please forward your poll again.")
            return

        if len(subtopic_name) < 1 or len(subtopic_name) > 200:
            await message.answer("⚠️ Please enter a valid subtopic name (1–200 characters).")
            return

        try:
            subtopic = await get_or_create_user_subtopic(
                db_pool,
                user_id=user.id,
                subject_id=int(subject_id),
                name=subtopic_name
            )
            await save_user_session(
                db_pool,
                telegram_id=user.id,
                pending_poll_id=session.get("pending_poll_id"),
                pending_question_id=int(question_id),
                state="waiting_category",
                selected_module_id=int(subject_id),
                selected_subtopic=subtopic["name"],
                selected_subtopic_id=subtopic["id"],
                username=user.username,
                first_name=user.first_name or "User"
            )

            await message.answer(
                f"📂 <b>Organization Selected:</b>\n"
                f"📘 <b>{html.escape(subtopic['subject_name'])}</b> → 📂 <b>{html.escape(subtopic['name'])}</b>\n\n"
                f"<b>Step 3 of 3:</b> Choose a category to save this question:",
                reply_markup=build_category_keyboard(int(subject_id))
            )
            return
        except Exception as e:
            logger.error(f"Error creating subtopic for user {user.id}: {e}")
            await message.answer("⚠️ Could not save that subtopic name. Please try again.")
            return

    # If the user forwarded a text message instead of a Telegram poll
    if message.forward_origin or message.forward_date:
        await message.answer(
            "⚠️ <b>Could not parse a question from this message.</b>\n\n"
            "Please forward a <b>Telegram Poll / Quiz</b> message (with question text and multiple-choice options) "
            "to save it to your Personal Revision Bank."
        )
    else:
        await message.answer(
            "💡 Forward a <b>Telegram Poll / Quiz</b> to save it to your Personal Revision Bank, "
            "or send <code>/help</code> to view available commands."
        )


@router.message()
async def handle_unsupported_message(message: Message):
    """Graceful handler for unsupported media or non-poll forwards."""
    await message.answer(
        "⚠️ <b>Unsupported message format.</b>\n"
        "Please forward a supported <b>Telegram Poll / Quiz</b> so the question and options can be extracted."
    )
