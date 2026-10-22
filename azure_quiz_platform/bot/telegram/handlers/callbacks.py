"""
Callback Query Handlers for Forwarded-Question Intake Workflow:
  1. rev_subj:{subject_id} -> Choose Subject, then display user's Subtopics + "Create New Subtopic"
  2. rev_subt:{subtopic_id} -> Choose existing personal Subtopic, then display Categories
  3. rev_new_subt:{subject_id} -> Prompt user to type a new personal Subtopic name
  4. rev_cat:{category} -> Save question as Mistake or Difficult in Azure SQL and confirm
  5. rev_also:{category}:{question_id}:{subject_id}:{subtopic_id} -> Also save under the other category
"""
import html
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.pool import AzureSQLPool
from bot.services.auth_service import (
    generate_login_code,
    reset_student_password,
)
from bot.services.module_service import list_subjects, get_subject
from bot.services.revision_service import (
    CATEGORY_LABELS,
    get_dashboard_summary,
    list_user_subtopics,
    get_user_subtopic,
    save_question_to_revision_bank,
)
from bot.services.session_store import (
    get_user_session,
    save_user_session,
    clear_user_session,
)
from bot.telegram.keyboards import (
    build_subject_keyboard,
    build_subtopic_keyboard,
    build_category_keyboard,
    build_also_save_keyboard,
    build_account_credentials_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks_router")


@router.callback_query(F.data == "rev_cancel")
async def handle_cancel_callback(callback: CallbackQuery, db_pool: AzureSQLPool):
    user = callback.from_user
    if not user:
        return
    await clear_user_session(db_pool, user.id)
    await callback.answer("Cancelled")
    if callback.message:
        await callback.message.edit_text("✖️ Question save cancelled.")


@router.callback_query(F.data == "rev_back_subj")
async def handle_back_to_subjects(callback: CallbackQuery, db_pool: AzureSQLPool):
    user = callback.from_user
    if not user:
        return

    session = await get_user_session(db_pool, user.id)
    if not session or not session.get("pending_question_id"):
        await callback.answer("Session expired. Please forward the poll again.", show_alert=True)
        return

    subjects = await list_subjects(db_pool)
    await save_user_session(
        db_pool,
        telegram_id=user.id,
        pending_poll_id=session.get("pending_poll_id"),
        pending_question_id=int(session["pending_question_id"]),
        state="waiting_subject",
        selected_module_id=None,
        selected_subtopic=None,
        selected_subtopic_id=None,
        username=user.username,
        first_name=user.first_name or "User"
    )
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "<b>Step 1 of 3:</b> Choose a <b>Subject</b> for this question:",
            reply_markup=build_subject_keyboard(subjects)
        )


@router.callback_query(F.data.startswith("rev_subj:"))
async def handle_subject_selection(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Step 1 complete -> Show user's personal subtopics for the chosen subject."""
    user = callback.from_user
    if not user or not callback.data:
        return

    try:
        subject_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid subject.", show_alert=True)
        return

    session = await get_user_session(db_pool, user.id)
    if not session or not session.get("pending_question_id"):
        await callback.answer("Session expired. Please forward the poll again.", show_alert=True)
        if callback.message:
            await callback.message.edit_text("⚠️ Session expired. Please forward the poll again.")
        return

    subject = await get_subject(db_pool, subject_id)
    if not subject:
        await callback.answer("Subject not found.", show_alert=True)
        return

    subtopics = await list_user_subtopics(db_pool, user_id=user.id, subject_id=subject_id)

    await save_user_session(
        db_pool,
        telegram_id=user.id,
        pending_poll_id=session.get("pending_poll_id"),
        pending_question_id=int(session["pending_question_id"]),
        state="waiting_subtopic",
        selected_module_id=subject_id,
        selected_subtopic=None,
        selected_subtopic_id=None,
        username=user.username,
        first_name=user.first_name or "User"
    )

    await callback.answer(f"Selected {subject['name']}")
    if callback.message:
        if subtopics:
            prompt_text = (
                f"📘 <b>Subject:</b> {html.escape(subject['name'])}\n\n"
                f"<b>Step 2 of 3:</b> Select one of your existing subtopics below, "
                f"or tap <b>➕ Create New Subtopic</b> (or simply type a new subtopic name in chat):"
            )
        else:
            prompt_text = (
                f"📘 <b>Subject:</b> {html.escape(subject['name'])}\n\n"
                f"<b>Step 2 of 3:</b> You don't have any subtopics under <b>{html.escape(subject['name'])}</b> yet.\n"
                f"Tap <b>➕ Create New Subtopic</b> or reply with a subtopic name (e.g., <i>Upper Limb</i>):"
            )
        await callback.message.edit_text(
            prompt_text,
            reply_markup=build_subtopic_keyboard(subtopics, subject_id)
        )


@router.callback_query(F.data.startswith("rev_new_subt:"))
async def handle_new_subtopic_prompt(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Prompt the user to type the name of a new personal subtopic."""
    user = callback.from_user
    if not user or not callback.data:
        return

    try:
        subject_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid subject.", show_alert=True)
        return

    session = await get_user_session(db_pool, user.id)
    if not session or not session.get("pending_question_id"):
        await callback.answer("Session expired. Please forward the poll again.", show_alert=True)
        return

    subject = await get_subject(db_pool, subject_id)
    subject_name = subject["name"] if subject else "Selected Subject"

    await save_user_session(
        db_pool,
        telegram_id=user.id,
        pending_poll_id=session.get("pending_poll_id"),
        pending_question_id=int(session["pending_question_id"]),
        state="waiting_new_subtopic",
        selected_module_id=subject_id,
        selected_subtopic=None,
        selected_subtopic_id=None,
        username=user.username,
        first_name=user.first_name or "User"
    )

    await callback.answer("Type your new subtopic name")
    if callback.message:
        await callback.message.edit_text(
            f"📘 <b>Subject:</b> {html.escape(subject_name)}\n\n"
            f"✏️ <b>Please send a message with the name of your new subtopic</b>\n"
            f"<i>(for example: Upper Limb, Endocrine, Cardiovascular)</i>\n\n"
            f"Or send <code>/cancel</code> to abort."
        )


@router.callback_query(F.data.startswith("rev_subt:"))
async def handle_subtopic_selection(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Step 2 complete -> User selected an existing personal subtopic; now ask for Category."""
    user = callback.from_user
    if not user or not callback.data:
        return

    try:
        subtopic_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid subtopic.", show_alert=True)
        return

    session = await get_user_session(db_pool, user.id)
    if not session or not session.get("pending_question_id"):
        await callback.answer("Session expired. Please forward the poll again.", show_alert=True)
        if callback.message:
            await callback.message.edit_text("⚠️ Session expired. Please forward the poll again.")
        return

    subtopic = await get_user_subtopic(db_pool, user_id=user.id, subtopic_id=subtopic_id)
    if not subtopic:
        await callback.answer("Subtopic not found in your account.", show_alert=True)
        return

    await save_user_session(
        db_pool,
        telegram_id=user.id,
        pending_poll_id=session.get("pending_poll_id"),
        pending_question_id=int(session["pending_question_id"]),
        state="waiting_category",
        selected_module_id=int(subtopic["subject_id"]),
        selected_subtopic=subtopic["name"],
        selected_subtopic_id=int(subtopic["id"]),
        username=user.username,
        first_name=user.first_name or "User"
    )

    await callback.answer(f"Subtopic: {subtopic['name']}")
    if callback.message:
        await callback.message.edit_text(
            f"📘 <b>{html.escape(subtopic['subject_name'])}</b> → 📂 <b>{html.escape(subtopic['name'])}</b>\n\n"
            f"<b>Step 3 of 3:</b> Choose a category for this question:",
            reply_markup=build_category_keyboard(int(subtopic["subject_id"]))
        )


@router.callback_query(F.data.startswith("rev_cat:"))
async def handle_category_selection(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Step 3 complete -> Save question to user's personal revision bank in Azure SQL."""
    user = callback.from_user
    if not user or not callback.data:
        return

    category = callback.data.split(":", 1)[1].strip().lower()
    if category not in ("mistake", "difficult"):
        await callback.answer("Invalid category. Choose Mistake or Difficult.", show_alert=True)
        return

    session = await get_user_session(db_pool, user.id)
    if not session or not session.get("pending_question_id"):
        await callback.answer("Session expired. Please forward the poll again.", show_alert=True)
        if callback.message:
            await callback.message.edit_text("⚠️ Session expired. Please forward the poll again.")
        return

    question_id = int(session["pending_question_id"])
    subject_id = session.get("selected_module_id")
    subtopic_id = session.get("selected_subtopic_id")
    subtopic_name = session.get("selected_subtopic")

    if not subject_id:
        await callback.answer("Please select a subject first.", show_alert=True)
        return

    try:
        result = await save_question_to_revision_bank(
            db_pool,
            user_id=user.id,
            question_id=question_id,
            source=category,
            subject_id=int(subject_id),
            subtopic_id=int(subtopic_id) if subtopic_id else None,
            subtopic_name=subtopic_name,
        )
        await clear_user_session(db_pool, user.id)

        subject = await get_subject(db_pool, int(subject_id))
        subject_name = subject["name"] if subject else "Subject"

        resolved_subtopic_name = subtopic_name
        if result.get("subtopic_id") and not resolved_subtopic_name:
            st = await get_user_subtopic(db_pool, user.id, int(result["subtopic_id"]))
            if st:
                resolved_subtopic_name = st["name"]

        cat_label = CATEGORY_LABELS.get(category, category)
        other_category = "difficult" if category == "mistake" else "mistake"

        org_path = f"📘 <b>{html.escape(subject_name)}</b>"
        if resolved_subtopic_name:
            org_path += f" → 📂 <b>{html.escape(resolved_subtopic_name)}</b>"

        if result["already_exists"]:
            await callback.answer(f"Already in {cat_label}")
            msg_text = (
                f"ℹ️ <b>Already Saved in {cat_label}</b>\n\n"
                f"📍 <b>Organization:</b> {org_path}\n"
                f"🏷 <b>Category:</b> {cat_label}\n\n"
                f"<i>No duplicate record was created.</i>"
            )
        else:
            await callback.answer(f"Saved to {cat_label}!")
            msg_text = (
                f"✅ <b>Question Saved to Your Revision Bank!</b>\n\n"
                f"📍 <b>Organization:</b> {org_path}\n"
                f"🏷 <b>Category:</b> {cat_label}\n\n"
                f"<i>You can review and organize this question anytime on the website.</i>"
            )

        if callback.message:
            await callback.message.edit_text(
                msg_text,
                reply_markup=build_also_save_keyboard(
                    other_category=other_category,
                    question_id=question_id,
                    subject_id=result.get("subject_id"),
                    subtopic_id=result.get("subtopic_id"),
                )
            )
    except Exception as e:
        logger.error(f"Error saving question {question_id} for user {user.id}: {e}")
        await callback.answer("Error saving question.", show_alert=True)


@router.callback_query(F.data.startswith("rev_also:"))
async def handle_also_save_category(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Allow saving the same question to the second category (Mistake + Difficult) in 1 tap."""
    user = callback.from_user
    if not user or not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("Invalid request.", show_alert=True)
        return

    category = parts[1].strip().lower()
    if category not in ("mistake", "difficult"):
        await callback.answer("Invalid category.", show_alert=True)
        return

    try:
        question_id = int(parts[2])
        subject_id = int(parts[3]) if int(parts[3]) > 0 else None
        subtopic_id = int(parts[4]) if int(parts[4]) > 0 else None
    except ValueError:
        await callback.answer("Invalid parameters.", show_alert=True)
        return

    try:
        result = await save_question_to_revision_bank(
            db_pool,
            user_id=user.id,
            question_id=question_id,
            source=category,
            subject_id=subject_id,
            subtopic_id=subtopic_id,
        )

        subject_name = "Subject"
        if result.get("subject_id"):
            subj = await get_subject(db_pool, int(result["subject_id"]))
            if subj:
                subject_name = subj["name"]

        subtopic_name = None
        if result.get("subtopic_id"):
            st = await get_user_subtopic(db_pool, user.id, int(result["subtopic_id"]))
            if st:
                subtopic_name = st["name"]

        org_path = f"📘 <b>{html.escape(subject_name)}</b>"
        if subtopic_name:
            org_path += f" → 📂 <b>{html.escape(subtopic_name)}</b>"

        await callback.answer("Saved to both categories!")
        if callback.message:
            await callback.message.edit_text(
                f"✅ <b>Question Saved to Both Categories!</b>\n\n"
                f"📍 <b>Organization:</b> {org_path}\n"
                f"🏷 <b>Categories:</b> ❌ Mistake &amp; ⭐ Difficult\n\n"
                f"<i>This question now appears under both Mistakes and Difficult without duplicates.</i>"
            )
    except Exception as e:
        logger.error(f"Error adding second category for user {user.id}: {e}")
        await callback.answer("Could not add category.", show_alert=True)


@router.callback_query(F.data == "get_login_code")
async def handle_get_login_code_callback(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Generate a fresh 6-digit login code when the user taps 'Get New Code'."""
    user = callback.from_user
    if not user:
        return

    code = await generate_login_code(
        db_pool,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "User"
    )
    await callback.answer("Fresh login code generated!")
    text = (
        f"🔐 <b>Fresh Website Login Code</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🔢 <b>6-Digit Login Code:</b> <code>{code}</code> <i>(valid for 10 minutes)</i>\n\n"
        f"Enter your Telegram ID and this code on the website login page, or tap <b>🔄 Reset Password</b> for a permanent password."
    )
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=build_account_credentials_keyboard())
        except Exception:
            await callback.message.answer(text, reply_markup=build_account_credentials_keyboard())


@router.callback_query(F.data == "rev_reset_pw")
async def handle_reset_password_callback(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Generate a new permanent password when the user taps 'Reset Password'."""
    user = callback.from_user
    if not user:
        return

    new_pw = await reset_student_password(
        db_pool,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "User"
    )
    code = await generate_login_code(
        db_pool,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "User"
    )
    await callback.answer("New password generated!")
    text = (
        f"✅ <b>Your Website Password Has Been Reset!</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🔑 <b>New Permanent Password:</b> <code>{new_pw}</code>\n"
        f"🔢 <b>6-Digit Login Code:</b> <code>{code}</code>\n\n"
        f"<i>Use either the new permanent password or the 6-digit code to sign in.</i>"
    )
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=build_account_credentials_keyboard())
        except Exception:
            await callback.message.answer(text, reply_markup=build_account_credentials_keyboard())


@router.callback_query(F.data == "view_questions")
async def handle_view_questions_callback(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Display the user's revision bank summary from Azure SQL."""
    user = callback.from_user
    if not user:
        return

    summary = await get_dashboard_summary(db_pool, user.id)
    await callback.answer()
    text = (
        f"📚 <b>Your Personal Revision Bank</b>\n\n"
        f"📖 <b>Total Saved Questions:</b> {summary['total_questions']}\n"
        f"❌ <b>Mistakes:</b> {summary['mistake_count']}\n"
        f"⭐ <b>Difficult:</b> {summary['difficult_count']}\n"
        f"📘 <b>Subjects Used:</b> {summary['subjects_count']}\n"
        f"📂 <b>Personal Subtopics:</b> {summary['subtopics_count']}"
    )
    if callback.message:
        await callback.message.answer(text, reply_markup=build_account_credentials_keyboard())


async def handle_callback_query(callback: CallbackQuery, db_pool: AzureSQLPool):
    """Unified callback dispatcher for both webhook and polling modes."""
    data = callback.data or ""
    if data == "rev_cancel":
        await handle_cancel_callback(callback, db_pool)
    elif data == "rev_back_subj":
        await handle_back_to_subjects(callback, db_pool)
    elif data == "get_login_code":
        await handle_get_login_code_callback(callback, db_pool)
    elif data == "rev_reset_pw":
        await handle_reset_password_callback(callback, db_pool)
    elif data == "view_questions":
        await handle_view_questions_callback(callback, db_pool)
    elif data.startswith("rev_subj:"):
        await handle_subject_selection(callback, db_pool)
    elif data.startswith("rev_new_subt:"):
        await handle_new_subtopic_prompt(callback, db_pool)
    elif data.startswith("rev_subt:"):
        await handle_subtopic_selection(callback, db_pool)
    elif data.startswith("rev_cat:"):
        await handle_category_selection(callback, db_pool)
    elif data.startswith("rev_also:"):
        await handle_also_save_category(callback, db_pool)
    else:
        await callback.answer("Unknown action.")
