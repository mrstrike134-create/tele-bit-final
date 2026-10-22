"""
Web Authentication Routes for Personal Revision Bank.
Supports login via Telegram ID + permanent password (or 6-digit one-time login code)
and logout with session revocation in Azure SQL.
"""
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from bot.config import BOT_URL, BOT_USERNAME
from bot.services.auth_service import (
    authenticate_user_credentials,
    create_auth_session,
    validate_auth_session,
    revoke_auth_session,
)
from bot.services.user_service import get_user_account
from web.template_engine import templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Authentication"])


async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Resolve the currently authenticated user from session/cookie token."""
    pool = getattr(request.app.state, "db_pool", None)
    if not pool:
        return None

    token = request.session.get("auth_token") or request.cookies.get("auth_token")
    if token:
        user = await validate_auth_session(pool, token)
        if user:
            request.session["user_id"] = user["id"]
            request.session["first_name"] = user["first_name"]
            request.session["username"] = user.get("username")
            return user

    user_id = request.session.get("user_id")
    if user_id:
        try:
            account = await get_user_account(pool, int(user_id))
            if account:
                return account
        except Exception:
            pass

    return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    user = await get_current_user(request)
    if user:
        target = next if (next and next.startswith("/") and not next.startswith("//")) else "/"
        return RedirectResponse(url=target, status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "user": None,
            "error": None,
            "next": next or "/",
            "bot_url": BOT_URL,
            "bot_username": BOT_USERNAME,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    telegram_id: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    pool = request.app.state.db_pool
    tid_clean = (telegram_id or "").strip()

    if not tid_clean.isdigit():
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "Please enter a valid numeric Telegram ID (send /id to the bot to find yours).",
                "telegram_id": tid_clean,
                "next": next or "/",
                "bot_url": BOT_URL,
                "bot_username": BOT_USERNAME,
            },
            status_code=400,
        )

    tid = int(tid_clean)
    user, auth_msg = await authenticate_user_credentials(pool, tid, password)

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": auth_msg,
                "telegram_id": tid_clean,
                "next": next or "/",
                "bot_url": BOT_URL,
                "bot_username": BOT_USERNAME,
            },
            status_code=401,
        )

    token = await create_auth_session(pool, user["id"])
    request.session.clear()
    request.session["auth_token"] = token
    request.session["user_id"] = user["id"]
    request.session["first_name"] = user["first_name"]
    request.session["username"] = user.get("username")

    target = next if (next and next.startswith("/") and not next.startswith("//")) else "/"
    if auth_msg == "login_code" and not user.get("has_password") and target == "/":
        target = "/settings?msg=Welcome!+You+can+set+a+permanent+password+below."

    response = RedirectResponse(url=target, status_code=302)
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=14 * 86400,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    token = request.session.get("auth_token") or request.cookies.get("auth_token")
    if pool and token:
        try:
            await revoke_auth_session(pool, token)
        except Exception as e:
            logger.warning(f"Error revoking session token: {e}")

    request.session.clear()
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("auth_token")
    return response
