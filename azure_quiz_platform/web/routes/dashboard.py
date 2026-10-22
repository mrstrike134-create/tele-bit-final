"""
Dashboard Route for Personal Revision Bank.
Displays the user's saved material overview:
  - Total saved questions
  - Mistake count
  - Difficult count
  - Number of subjects used
  - Number of personal subtopics
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from bot.config import BOT_URL, BOT_USERNAME
from bot.services.revision_service import (
    get_dashboard_summary,
    get_user_hierarchy,
    list_revision_questions,
)
from web.routes.auth import get_current_user
from web.template_engine import templates

router = APIRouter(tags=["Dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    summary = await get_dashboard_summary(pool, user["id"])
    hierarchy = await get_user_hierarchy(pool, user["id"])
    recent_questions = (await list_revision_questions(pool, user_id=user["id"]))[:5]

    return templates.TemplateResponse(
        "student/dashboard.html",
        {
            "request": request,
            "user": user,
            "summary": summary,
            "hierarchy": hierarchy,
            "recent_questions": recent_questions,
            "bot_url": BOT_URL,
            "bot_username": BOT_USERNAME,
        },
    )
