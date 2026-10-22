"""
Telegram Bot Command Handlers for Personal Revision Bank.
Supports account registration, Telegram ID & login credentials, password setup/reset,
session cancellation, and help instructions.
"""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database.pool import AzureSQLPool
from bot.services.auth_service import (
    ensure_user_exists,
    ensure_user_with_password,
    generate_login_code,
    reset_student_password,
    set_user_password,
)
from bot.services.session_store import clear_user_session
from bot.telegram.keyboards import build_account_credentials_keyboard

logger = logging.getLogger(__name__)
router = Router(name="commands_router")


@router.message(Command("start"))
async def cmd_start(message: Message, db_pool: AzureSQLPool):
    user = message.from_user
    if not user:
        return

    db_user, generated_pw = await ensure_user_with_password(
        db_pool,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "User"
    )
    login_code = await generate_login_code(
        db_pool,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "User"
    )

    if generated_pw:
        pw_line = f"🔒 <b>Permanent Password:</b> <code>{generated_pw}</code>\n"
    else:
        pw_line = "🔒 <b>Permanent Password:</b> Configured ✅ <i>(send <code>/resetpassword</code> to get a new one)</i>\n"

    text = (
        f"👋 <b>Welcome to Your Personal Revision Bank, {user.first_name or 'Student'}!</b>\n\n"
        f"🆔 <b>Your Telegram ID:</b> <code>{user.id}</code>\n"
        f"🔑 <b>One-Time Website Login Code:</b> <code>{login_code}</code> <i>(valid for 10 min)</i>\n"
        f"{pw_line}\n"
        f"📌 <b>How to Save Questions:</b>\n"
        f"1. Forward any Telegram quiz/poll to this bot.\n"
        f"2. Choose a <b>Subject</b> (e.g., Anatomy, Physiology).\n"
        f"3. Select an existing <b>Subtopic</b> or create a new one.\n"
        f"4. Choose <b>❌ Mistake</b> or <b>⭐ Difficult</b>.\n\n"
        f"🛠 <b>Account Commands:</b>\n"
        f"• <code>/id</code> — View your Telegram ID\n"
        f"• <code>/login</code> — Get a fresh login code\n"
        f"• <code>/resetpassword</code> — Generate a new permanent password\n"
        f"• <code>/setpassword &lt;password&gt;</code> — Set a custom website password\n"
        f"• <code>/cancel</code> — Cancel a pending question save"
    )
    await message.answer(text, reply_markup=build_account_credentials_keyboard())


@router.message(Command("id"))
async def cmd_id(message: Message, db_pool: AzureSQLPool):
    user = message.from_user
    if not user:
        return

    await ensure_user_exists(
        db_pool,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "User"
    )
    await message.answer(
        f"🆔 <b>Your Telegram ID:</b> <code>{user.id}</code>\n"
        f"Use this ID along with your password (or <code>/login</code> code) to sign into the website."
    )


@router.message(Command("login"))
async def cmd_login(message: Message, db_pool: AzureSQLPool):
    user = message.from_user
    if not user:
        return

    db_user, generated_pw = await ensure_user_with_password(
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

    pw_info = (
        f"🔒 <b>Permanent Password:</b> <code>{generated_pw}</code>\n"
        if generated_pw
        else "🔒 <b>Permanent Password:</b> Configured ✅ <i>(send <code>/resetpassword</code> to reset)</i>\n"
    )

    text = (
        f"🔐 <b>Website Login Credentials</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🔢 <b>6-Digit Login Code:</b> <code>{code}</code> <i>(valid for 10 minutes)</i>\n"
        f"{pw_info}\n"
        f"Enter your <b>Telegram ID</b> and either your permanent password or the 6-digit login code on the website login page."
    )
    await message.answer(text, reply_markup=build_account_credentials_keyboard())


@router.message(Command("setpassword"))
async def cmd_setpassword(message: Message, db_pool: AzureSQLPool):
    user = message.from_user
    if not user or not message.text:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "🔒 <b>Set Your Website Password</b>\n\n"
            "Usage:\n"
            "<code>/setpassword your_new_password</code>\n\n"
            "<i>Password must be at least 6 characters long. Or send <code>/resetpassword</code> to auto-generate one.</i>"
        )
        return

    new_password = parts[1].strip()
    ok, msg = await set_user_password(
        db_pool,
        telegram_id=user.id,
        new_password=new_password,
        username=user.username,
        first_name=user.first_name or "User"
    )
    if ok:
        await message.answer(
            f"✅ <b>{msg}</b>\n\n"
            f"You can now log into the website anytime using:\n"
            f"• <b>Telegram ID:</b> <code>{user.id}</code>\n"
            f"• <b>Password:</b> <code>{new_password}</code>"
        )
    else:
        await message.answer(f"⚠️ {msg}")


@router.message(Command("resetpassword"))
async def cmd_resetpassword(message: Message, db_pool: AzureSQLPool):
    user = message.from_user
    if not user or not message.text:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        new_password = parts[1].strip()
        ok, msg = await set_user_password(
            db_pool,
            telegram_id=user.id,
            new_password=new_password,
            username=user.username,
            first_name=user.first_name or "User"
        )
        if ok:
            await message.answer(
                f"✅ <b>Password Reset Complete</b>\n\n"
                f"Your website password has been updated:\n"
                f"• <b>Telegram ID:</b> <code>{user.id}</code>\n"
                f"• <b>New Password:</b> <code>{new_password}</code>"
            )
        else:
            await message.answer(f"⚠️ {msg}")
        return

    # Auto-generate a fresh permanent password immediately when called without arguments
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
    await message.answer(
        f"✅ <b>Your Website Password Has Been Reset!</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🔑 <b>New Permanent Password:</b> <code>{new_pw}</code>\n"
        f"🔢 <b>6-Digit Login Code:</b> <code>{code}</code>\n\n"
        f"<i>Copy and paste either the new password or the 6-digit code on the website login page.</i>",
        reply_markup=build_account_credentials_keyboard()
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, db_pool: AzureSQLPool):
    user = message.from_user
    if not user:
        return
    await clear_user_session(db_pool, user.id)
    await message.answer("✖️ Any pending question save operation has been cancelled.")


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📚 <b>Personal Revision Bank — Help</b>\n\n"
        "<b>Saving Questions:</b>\n"
        "1. Forward a Telegram poll/quiz question to this chat.\n"
        "2. Select a <b>Subject</b> (e.g., Anatomy, Physiology).\n"
        "3. Select an existing <b>Subtopic</b> or create a new one.\n"
        "4. Choose <b>❌ Mistake</b> or <b>⭐ Difficult</b>.\n\n"
        "<b>Commands:</b>\n"
        "• <code>/start</code> — Register &amp; view login details\n"
        "• <code>/id</code> — View your Telegram ID\n"
        "• <code>/login</code> — Generate a 10-minute website login code\n"
        "• <code>/resetpassword</code> — Generate a new website password\n"
        "• <code>/setpassword &lt;password&gt;</code> — Set a custom website password\n"
        "• <code>/cancel</code> — Cancel current question save"
    )
    await message.answer(text)


# Aliases for direct dispatcher compatibility
handle_start_command = cmd_start
handle_id_command = cmd_id
handle_login_command = cmd_login
handle_setpassword_command = cmd_setpassword
handle_resetpassword_command = cmd_resetpassword
handle_cancel_command = cmd_cancel
handle_help_command = cmd_help
