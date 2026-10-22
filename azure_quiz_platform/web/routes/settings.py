"""
Settings / Account Routes for Personal Revision Bank.
Allows authenticated users to view their account information,
change or set their password, and log out.
"""
from typing import Optional
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from bot.config import BOT_URL, BOT_USERNAME
from bot.services.auth_service import change_user_password
from bot.services.revision_service import get_dashboard_summary
from bot.services.user_service import get_user_account
from web.routes.auth import get_current_user
from web.template_engine import templates

router = APIRouter(tags=["Settings & Account"])


@router.get("/settings", response_class=HTMLResponse)
@router.get("/account", response_class=HTMLResponse)
@router.get("/profile", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/settings", status_code=302)

    pool = request.app.state.db_pool
    account = await get_user_account(pool, user["id"]) or user
    summary = await get_dashboard_summary(pool, user["id"])

    return templates.TemplateResponse(
        "settings/index.html",
        {
            "request": request,
            "user": account,
            "account": account,
            "summary": summary,
            "msg": msg,
            "error": error,
            "bot_url": BOT_URL,
            "bot_username": BOT_USERNAME,
        },
    )


@router.post("/settings/password")
@router.post("/account/password")
async def update_password_submit(
    request: Request,
    current_password: Optional[str] = Form(None),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if new_password.strip() != confirm_password.strip():
        return RedirectResponse(
            url=f"/settings?{urlencode({'error': 'New password and confirmation do not match.'})}",
            status_code=302,
        )

    pool = request.app.state.db_pool
    ok, message = await change_user_password(
        pool,
        user_or_telegram_id=user["id"],
        current_password=current_password,
        new_password=new_password,
    )
    param_key = "msg" if ok else "error"
    return RedirectResponse(
        url=f"/settings?{urlencode({param_key: message})}",
        status_code=302,
    )
