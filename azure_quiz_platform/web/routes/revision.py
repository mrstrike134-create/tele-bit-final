"""
My Questions / Personal Revision Bank Web Routes.
Supports:
  - Browsing saved questions organized by Subject -> Subtopic -> Question -> Category
  - Filtering by Subject, Subtopic, Category (All / Mistakes / Difficult), and Search text
  - Creating, renaming, moving, and deleting personal subtopics
  - Opening and editing a user's saved question (with copy-on-write isolation)
  - Changing a question's subject or subtopic
  - Adding or removing Mistake and Difficult categories independently
  - Deleting a question from the user's personal revision bank without affecting other users
  - Exporting filtered or selected questions to TXT
"""
import asyncio
import json
import urllib.parse
import urllib.request
from typing import Optional, List, Dict
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Form, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse

from bot.config import BOT_URL, BOT_USERNAME
from bot.services.module_service import list_subjects, get_subject
from bot.services.revision_service import (
    normalize_category,
    get_dashboard_summary,
    get_user_hierarchy,
    list_user_subtopics,
    get_user_subtopic,
    get_or_create_user_subtopic,
    rename_user_subtopic,
    move_user_subtopic,
    delete_user_subtopic,
    list_revision_questions,
    set_question_category,
    move_saved_question,
    edit_saved_question,
    remove_saved_question,
    export_revision_questions_txt,
)
from web.routes.auth import get_current_user
from web.template_engine import templates

router = APIRouter(tags=["My Questions"])


def _parse_optional_int(val: Optional[str]) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if s.isdigit():
        return int(s)
    return None


def _build_return_url(
    base_path: str = "/questions",
    subject_id: Optional[int] = None,
    subtopic_id: Optional[int] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    msg: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    params = {}
    if subject_id is not None:
        params["subject_id"] = str(subject_id)
    if subtopic_id is not None:
        params["subtopic_id"] = str(subtopic_id)
    if category and category != "all":
        params["category"] = category
    if q and q.strip():
        params["q"] = q.strip()
    if msg:
        params["msg"] = msg
    if error:
        params["error"] = error
    if not params:
        return base_path
    return f"{base_path}?{urlencode(params)}"


@router.get("/questions", response_class=HTMLResponse)
@router.get("/revision", response_class=HTMLResponse)
async def my_questions_page(
    request: Request,
    subject_id: Optional[str] = Query(None),
    module_id: Optional[str] = Query(None),
    subtopic_id: Optional[str] = Query(None),
    subtopic: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/questions", status_code=302)

    pool = request.app.state.db_pool
    selected_subject_id = _parse_optional_int(subject_id) or _parse_optional_int(module_id)
    selected_subtopic_id = _parse_optional_int(subtopic_id)
    selected_subtopic_name = subtopic.strip() if subtopic and subtopic.strip() else None

    raw_cat = category or source
    selected_category = normalize_category(raw_cat) if (raw_cat and raw_cat.lower() != "all") else None
    search_text = (q if q is not None else search) or ""

    # If a subtopic_id is selected, verify it belongs to this user
    active_subtopic_obj = None
    if selected_subtopic_id is not None:
        active_subtopic_obj = await get_user_subtopic(pool, user["id"], selected_subtopic_id)
        if active_subtopic_obj and selected_subject_id is None:
            selected_subject_id = active_subtopic_obj["subject_id"]
        elif not active_subtopic_obj:
            selected_subtopic_id = None

    active_subject_obj = None
    if selected_subject_id is not None:
        active_subject_obj = await get_subject(pool, selected_subject_id)

    summary = await get_dashboard_summary(pool, user["id"])
    hierarchy = await get_user_hierarchy(pool, user["id"])
    subjects = await list_subjects(pool)
    all_user_subtopics = await list_user_subtopics(pool, user["id"])
    subject_subtopics = (
        [st for st in all_user_subtopics if st["subject_id"] == selected_subject_id]
        if selected_subject_id is not None
        else all_user_subtopics
    )

    questions = await list_revision_questions(
        pool,
        user_id=user["id"],
        category=selected_category,
        subject_id=selected_subject_id,
        subtopic_id=selected_subtopic_id,
        subtopic=selected_subtopic_name,
        search_query=search_text,
    )

    return templates.TemplateResponse(
        "student/revision/index.html",
        {
            "request": request,
            "user": user,
            "summary": summary,
            "hierarchy": hierarchy,
            "subjects": subjects,
            "modules": subjects,
            "all_subtopics": all_user_subtopics,
            "subtopics": subject_subtopics,
            "questions": questions,
            "selected_subject_id": selected_subject_id,
            "selected_module_id": selected_subject_id,
            "selected_subtopic_id": selected_subtopic_id,
            "selected_subtopic": active_subtopic_obj["name"] if active_subtopic_obj else selected_subtopic_name,
            "active_subject": active_subject_obj,
            "active_subtopic": active_subtopic_obj,
            "selected_category": selected_category or "all",
            "selected_source": selected_category,
            "search_query": search_text,
            "msg": msg,
            "error": error,
            "bot_url": BOT_URL,
            "bot_username": BOT_USERNAME,
        },
    )


@router.get("/questions/export.txt", response_class=PlainTextResponse)
@router.get("/revision/export.txt", response_class=PlainTextResponse)
async def export_questions_txt(
    request: Request,
    subject_id: Optional[str] = Query(None),
    module_id: Optional[str] = Query(None),
    subtopic_id: Optional[str] = Query(None),
    subtopic: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    ids: Optional[str] = Query(None),
):
    user = await get_current_user(request)
    if not user:
        return PlainTextResponse("Unauthorized", status_code=401)

    pool = request.app.state.db_pool
    selected_subject_id = _parse_optional_int(subject_id) or _parse_optional_int(module_id)
    selected_subtopic_id = _parse_optional_int(subtopic_id)
    raw_cat = category or source
    selected_category = normalize_category(raw_cat) if (raw_cat and raw_cat.lower() != "all") else None

    question_ids: Optional[List[int]] = None
    if ids and ids.strip():
        parsed_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
        if parsed_ids:
            question_ids = parsed_ids

    questions = await list_revision_questions(
        pool,
        user_id=user["id"],
        category=selected_category,
        subject_id=selected_subject_id,
        subtopic_id=selected_subtopic_id,
        subtopic=subtopic.strip() if subtopic and subtopic.strip() else None,
        search_query=q,
        question_ids=question_ids,
    )

    title_parts = ["Personal Revision Bank"]
    if selected_category == "mistake":
        title_parts.append("Mistakes")
    elif selected_category == "difficult":
        title_parts.append("Difficult")
    txt_content = export_revision_questions_txt(questions, title=" - ".join(title_parts))

    filename = f"revision_{selected_category or 'all'}_questions.txt"
    return PlainTextResponse(
        content=txt_content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================================
# Subtopic Creation, Renaming, Moving & Deletion
# ============================================================================

@router.post("/questions/subtopics/create")
@router.post("/revision/subtopics/create")
async def create_subtopic_route(
    request: Request,
    subject_id: int = Form(...),
    name: str = Form(...),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    try:
        st = await get_or_create_user_subtopic(pool, user["id"], subject_id, name)
        return RedirectResponse(
            url=_build_return_url(
                subject_id=subject_id,
                subtopic_id=st["id"],
                msg=f"Subtopic '{st['name']}' ready under {st['subject_name']}.",
            ),
            status_code=302,
        )
    except Exception as e:
        return RedirectResponse(
            url=_build_return_url(subject_id=subject_id, error=str(e)),
            status_code=302,
        )


@router.post("/questions/subtopics/{subtopic_id}/rename")
@router.post("/revision/subtopics/{subtopic_id}/rename")
async def rename_subtopic_route(
    request: Request,
    subtopic_id: int,
    new_name: str = Form(...),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    st = await get_user_subtopic(pool, user["id"], subtopic_id)
    subj_id = st["subject_id"] if st else None
    ok, message = await rename_user_subtopic(pool, user["id"], subtopic_id, new_name)
    return RedirectResponse(
        url=_build_return_url(
            subject_id=subj_id,
            subtopic_id=subtopic_id if ok else None,
            msg=message if ok else None,
            error=None if ok else message,
        ),
        status_code=302,
    )


@router.post("/questions/subtopics/{subtopic_id}/move")
@router.post("/revision/subtopics/{subtopic_id}/move")
async def move_subtopic_route(
    request: Request,
    subtopic_id: int,
    target_subject_id: int = Form(...),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    ok, message = await move_user_subtopic(pool, user["id"], subtopic_id, target_subject_id)
    return RedirectResponse(
        url=_build_return_url(
            subject_id=target_subject_id if ok else None,
            msg=message if ok else None,
            error=None if ok else message,
        ),
        status_code=302,
    )


@router.post("/questions/subtopics/{subtopic_id}/delete")
@router.post("/revision/subtopics/{subtopic_id}/delete")
async def delete_subtopic_route(
    request: Request,
    subtopic_id: int,
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    st = await get_user_subtopic(pool, user["id"], subtopic_id)
    subj_id = st["subject_id"] if st else None
    ok, message = await delete_user_subtopic(pool, user["id"], subtopic_id)
    return RedirectResponse(
        url=_build_return_url(
            subject_id=subj_id,
            msg=message if ok else None,
            error=None if ok else message,
        ),
        status_code=302,
    )


# ============================================================================
# Question Categorization, Moving, Editing & Deletion
# ============================================================================

@router.post("/questions/{question_id}/category")
@router.post("/revision/{question_id}/category")
async def question_category_route(
    request: Request,
    question_id: int,
    category: str = Form(...),
    action: str = Form("toggle"),
    return_subject_id: Optional[str] = Form(None),
    return_subtopic_id: Optional[str] = Form(None),
    return_category: Optional[str] = Form(None),
    return_q: Optional[str] = Form(None),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    ok, message = await set_question_category(pool, user["id"], question_id, category, action=action)
    return RedirectResponse(
        url=_build_return_url(
            subject_id=_parse_optional_int(return_subject_id),
            subtopic_id=_parse_optional_int(return_subtopic_id),
            category=return_category,
            q=return_q,
            msg=message if ok else None,
            error=None if ok else message,
        ),
        status_code=302,
    )


@router.post("/questions/{question_id}/move")
@router.post("/revision/{question_id}/move")
async def move_question_route(
    request: Request,
    question_id: int,
    subject_id: int = Form(...),
    subtopic_id: Optional[str] = Form(None),
    new_subtopic_name: Optional[str] = Form(None),
    return_category: Optional[str] = Form(None),
    return_q: Optional[str] = Form(None),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    parsed_subtopic_id = _parse_optional_int(subtopic_id)
    ok, message = await move_saved_question(
        pool,
        user_id=user["id"],
        question_id=question_id,
        subject_id=subject_id,
        subtopic_id=parsed_subtopic_id,
        new_subtopic_name=new_subtopic_name,
    )
    return RedirectResponse(
        url=_build_return_url(
            subject_id=subject_id if ok else None,
            subtopic_id=parsed_subtopic_id if (ok and not new_subtopic_name) else None,
            category=return_category,
            q=return_q,
            msg=message if ok else None,
            error=None if ok else message,
        ),
        status_code=302,
    )


@router.post("/questions/{question_id}/edit")
@router.post("/revision/{question_id}/edit")
async def edit_question_route(
    request: Request,
    question_id: int,
    question_text: str = Form(...),
    options_text: Optional[str] = Form(None),
    correct_option_index: int = Form(-1),
    explanation: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    subject_id: Optional[str] = Form(None),
    subtopic_id: Optional[str] = Form(None),
    new_subtopic_name: Optional[str] = Form(None),
    return_category: Optional[str] = Form(None),
    return_q: Optional[str] = Form(None),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    form_data = await request.form()

    options: List[str] = []
    if options_text and options_text.strip():
        options = [line.strip() for line in options_text.splitlines() if line.strip()]
    else:
        for i in range(10):
            opt_val = form_data.get(f"option_{i}")
            if opt_val and str(opt_val).strip():
                options.append(str(opt_val).strip())

    parsed_subj_id = _parse_optional_int(subject_id)
    parsed_subt_id = _parse_optional_int(subtopic_id)

    ok, message, _ = await edit_saved_question(
        pool,
        user_id=user["id"],
        question_id=question_id,
        question_text=question_text,
        options=options,
        correct_option_index=correct_option_index,
        explanation=explanation,
        notes=notes,
        subject_id=parsed_subj_id,
        subtopic_id=parsed_subt_id,
        new_subtopic_name=new_subtopic_name,
    )

    return RedirectResponse(
        url=_build_return_url(
            subject_id=parsed_subj_id,
            subtopic_id=parsed_subt_id if not new_subtopic_name else None,
            category=return_category,
            q=return_q,
            msg=message if ok else None,
            error=None if ok else message,
        ),
        status_code=302,
    )


@router.post("/questions/{question_id}/delete")
@router.post("/revision/{question_id}/delete")
@router.post("/revision/delete/{question_id}")
async def delete_question_route(
    request: Request,
    question_id: int,
    return_subject_id: Optional[str] = Form(None),
    return_subtopic_id: Optional[str] = Form(None),
    return_category: Optional[str] = Form(None),
    return_q: Optional[str] = Form(None),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pool = request.app.state.db_pool
    deleted = await remove_saved_question(pool, user["id"], question_id)
    return RedirectResponse(
        url=_build_return_url(
            subject_id=_parse_optional_int(return_subject_id),
            subtopic_id=_parse_optional_int(return_subtopic_id),
            category=return_category,
            q=return_q,
            msg="Question removed from your personal revision bank." if deleted else None,
            error=None if deleted else "Question not found in your revision bank.",
        ),
        status_code=302,
    )


_TRANSLATION_CACHE: Dict[str, str] = {}


def _fetch_ar_translation_sync(text: str) -> str:
    """Translate text to Arabic using Google Translate's lightweight JSON endpoint with in-memory caching."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if cleaned in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cleaned]

    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ar&dt=t&q="
        + urllib.parse.quote(cleaned)
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        translated_parts = [seg[0] for seg in (data[0] or []) if seg and seg[0]]
        result = "".join(translated_parts).strip()
        if result:
            if len(_TRANSLATION_CACHE) > 2000:
                _TRANSLATION_CACHE.clear()
            _TRANSLATION_CACHE[cleaned] = result
        return result or cleaned


@router.post("/api/translate", response_class=JSONResponse)
async def translate_to_arabic_api(payload: Dict[str, List[str]] = Body(...)):
    """
    Lightweight, non-blocking Arabic translation endpoint with in-memory caching.
    Does not touch Azure SQL or the Telegram bot.
    """
    texts = payload.get("texts") or []
    if not isinstance(texts, list) or not texts:
        return JSONResponse({"translations": []})

    capped = [str(t or "")[:2500] for t in texts[:30]]

    async def _translate_all():
        results = []
        for item in capped:
            if not item.strip():
                results.append("")
                continue
            if item.strip() in _TRANSLATION_CACHE:
                results.append(_TRANSLATION_CACHE[item.strip()])
                continue
            try:
                tr = await asyncio.to_thread(_fetch_ar_translation_sync, item)
                results.append(tr)
            except Exception:
                results.append(item)
        return results

    translations = await _translate_all()
    return JSONResponse({"translations": translations})
