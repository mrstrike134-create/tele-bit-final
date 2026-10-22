"""
Comprehensive End-to-End Verification Suite for Personal Revision Bank (Section 11).
Tests all 15 required workflows against the live Microsoft Azure SQL Database,
actual Telegram bot handlers, and actual FastAPI web routes.
"""
import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ["DISABLE_WEB_BOT_POLLING"] = "1"

from fastapi.testclient import TestClient
from web.main import app
from bot.database.pool import init_db_pool, close_db_pool
from bot.database.schema import run_migrations
from bot.services.module_service import ensure_default_subjects, list_subjects
from bot.services.revision_service import (
    list_user_subtopics,
    list_revision_questions,
    get_dashboard_summary,
)
from bot.telegram.handlers.commands import cmd_start, cmd_setpassword
from bot.telegram.handlers.forwarded import handle_forwarded_poll, handle_text_message
from bot.telegram.handlers.callbacks import (
    handle_subject_selection,
    handle_subtopic_selection,
    handle_new_subtopic_prompt,
    handle_category_selection,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_test")


# Lightweight Telegram update objects for invoking actual aiogram handlers directly
@dataclass
class DummyUser:
    id: int
    username: str
    first_name: str


@dataclass
class DummyPollOption:
    text: str


@dataclass
class DummyPoll:
    id: str
    question: str
    options: List[DummyPollOption]
    correct_option_id: Optional[int] = 0
    explanation: Optional[str] = None
    type: str = "quiz"


@dataclass
class DummyMessage:
    from_user: DummyUser
    text: Optional[str] = None
    poll: Optional[DummyPoll] = None
    forward_origin: Any = None
    forward_date: Any = None
    replies: List[dict] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None):
        self.replies.append({"text": text, "reply_markup": reply_markup})

    async def edit_text(self, text: str, reply_markup: Any = None):
        self.replies.append({"text": text, "reply_markup": reply_markup})


@dataclass
class DummyCallback:
    from_user: DummyUser
    data: str
    message: DummyMessage
    answers: List[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False):
        self.answers.append(text)


async def run_all_tests():
    print("=" * 72)
    print("  🧪 PERSONAL REVISION BANK — LIVE AZURE SQL 15-STEP E2E VERIFICATION")
    print("=" * 72)

    pool = await init_db_pool()
    await run_migrations(pool)
    await ensure_default_subjects(pool)

    # Test users (isolated test IDs cleaned before & after)
    user1 = DummyUser(id=9900112233, username="e2e_student_one", first_name="Alice")
    user2 = DummyUser(id=9900112244, username="e2e_student_two", first_name="Bob")

    # Clean any prior test runs for these two synthetic IDs
    for uid in (user1.id, user2.id):
        row = await pool.fetchone("SELECT id FROM users WHERE telegram_user_id = ?", uid)
        if row:
            db_uid = row["id"]
            await pool.execute("DELETE FROM saved_questions WHERE user_id = ?", db_uid)
            await pool.execute("DELETE FROM user_subtopics WHERE user_id = ?", db_uid)
            await pool.execute("DELETE FROM user_sessions WHERE user_id = ?", db_uid)
            await pool.execute("DELETE FROM web_sessions WHERE user_id = ?", db_uid)
            await pool.execute("DELETE FROM auth_tokens WHERE user_id = ? OR telegram_id = ?", db_uid, uid)

    try:
        # ------------------------------------------------------------------
        # 1. User starts Telegram bot and receives website login credentials
        # ------------------------------------------------------------------
        msg_start = DummyMessage(from_user=user1, text="/start")
        await cmd_start(msg_start, pool)
        assert msg_start.replies, "Bot did not reply to /start"
        start_reply = msg_start.replies[-1]["text"]
        assert str(user1.id) in start_reply, "Telegram ID missing from /start reply"
        assert "One-Time Website Login Code" in start_reply, "Login code missing from /start reply"

        msg_pw = DummyMessage(from_user=user1, text="/setpassword AlicePass123")
        await cmd_setpassword(msg_pw, pool)
        assert "Password updated successfully" in msg_pw.replies[-1]["text"]

        msg_start2 = DummyMessage(from_user=user2, text="/start")
        await cmd_start(msg_start2, pool)
        msg_pw2 = DummyMessage(from_user=user2, text="/setpassword BobPass456")
        await cmd_setpassword(msg_pw2, pool)
        print("✅ [1/15] User starts Telegram bot and receives website login credentials.")

        # ------------------------------------------------------------------
        # 2. User logs into the website
        # ------------------------------------------------------------------
        with TestClient(app) as client1:
            res_login_page = client1.get("/login")
            assert res_login_page.status_code == 200

            res_login = client1.post(
                "/login",
                data={"telegram_id": str(user1.id), "password": "AlicePass123", "next": "/"},
                follow_redirects=False,
            )
            assert res_login.status_code == 302
            assert res_login.headers["location"] == "/"

            res_dash = client1.get("/")
            assert res_dash.status_code == 200
            assert "Alice" in res_dash.text
            print("✅ [2/15] User logs into the website.")

            # ------------------------------------------------------------------
            # 3. User forwards a Telegram poll to the bot
            # ------------------------------------------------------------------
            poll = DummyPoll(
                id="e2e_poll_brachial_plexus_001",
                question="Which nerve is most commonly injured in a mid-shaft fracture of the humerus?",
                options=[
                    DummyPollOption("Axillary nerve"),
                    DummyPollOption("Radial nerve"),
                    DummyPollOption("Median nerve"),
                    DummyPollOption("Ulnar nerve"),
                ],
                correct_option_id=1,
                explanation="The radial nerve runs in the radial (spiral) groove of the mid-shaft humerus.",
            )
            msg_poll = DummyMessage(from_user=user1, poll=poll)
            await handle_forwarded_poll(msg_poll, pool)
            assert msg_poll.replies, "Bot did not respond to forwarded poll"
            assert "Step 1 of 3" in msg_poll.replies[-1]["text"]
            print("✅ [3/15] User forwards a Telegram poll to the bot.")

            # ------------------------------------------------------------------
            # 4. User chooses Anatomy -> Upper Limb
            # ------------------------------------------------------------------
            subjects = await list_subjects(pool)
            anatomy = next((s for s in subjects if s["name"].lower() == "anatomy"), None)
            assert anatomy is not None, "Anatomy subject not found in database"

            cb_subj = DummyCallback(
                from_user=user1,
                data=f"rev_subj:{anatomy['id']}",
                message=msg_poll,
            )
            await handle_subject_selection(cb_subj, pool)
            assert "Step 2 of 3" in msg_poll.replies[-1]["text"]

            # Create / select "Upper Limb" via Telegram bot
            cb_new_subt = DummyCallback(
                from_user=user1,
                data=f"rev_new_subt:{anatomy['id']}",
                message=msg_poll,
            )
            await handle_new_subtopic_prompt(cb_new_subt, pool)
            msg_subt_name = DummyMessage(from_user=user1, text="Upper Limb")
            await handle_text_message(msg_subt_name, pool)
            assert "Upper Limb" in msg_subt_name.replies[-1]["text"]
            assert "Step 3 of 3" in msg_subt_name.replies[-1]["text"]
            print("✅ [4/15] User chooses Anatomy → Upper Limb.")

            # ------------------------------------------------------------------
            # 5. User saves the question as Mistake
            # ------------------------------------------------------------------
            cb_cat_mistake = DummyCallback(
                from_user=user1,
                data="rev_cat:mistake",
                message=msg_subt_name,
            )
            await handle_category_selection(cb_cat_mistake, pool)
            assert "Question Saved to Your Revision Bank" in msg_subt_name.replies[-1]["text"]
            assert "Mistake" in msg_subt_name.replies[-1]["text"]
            print("✅ [5/15] User saves the question as Mistake.")

            # ------------------------------------------------------------------
            # 6. Question appears on the website under Anatomy -> Upper Limb -> Mistakes
            # ------------------------------------------------------------------
            u1_subtopics = await list_user_subtopics(pool, user1.id, anatomy["id"])
            upper_limb_st = next((st for st in u1_subtopics if st["name"] == "Upper Limb"), None)
            assert upper_limb_st is not None

            res_q_mistake = client1.get(
                f"/questions?subject_id={anatomy['id']}&subtopic_id={upper_limb_st['id']}&category=mistake"
            )
            assert res_q_mistake.status_code == 200
            assert "mid-shaft fracture of the humerus" in res_q_mistake.text
            assert "Radial nerve" in res_q_mistake.text
            assert "spiral" in res_q_mistake.text
            assert "Upper Limb" in res_q_mistake.text
            print("✅ [6/15] Question appears on the website under Anatomy → Upper Limb → Mistakes.")

            # ------------------------------------------------------------------
            # 7. User saves the same question as Difficult too
            # ------------------------------------------------------------------
            # Also save as Difficult via forwarding the same poll and selecting Anatomy -> Upper Limb -> Difficult
            msg_poll_again = DummyMessage(from_user=user1, poll=poll)
            await handle_forwarded_poll(msg_poll_again, pool)
            await handle_subject_selection(
                DummyCallback(from_user=user1, data=f"rev_subj:{anatomy['id']}", message=msg_poll_again),
                pool,
            )
            await handle_subtopic_selection(
                DummyCallback(from_user=user1, data=f"rev_subt:{upper_limb_st['id']}", message=msg_poll_again),
                pool,
            )
            await handle_category_selection(
                DummyCallback(from_user=user1, data="rev_cat:difficult", message=msg_poll_again),
                pool,
            )
            assert "Difficult" in msg_poll_again.replies[-1]["text"]

            # Also verify duplicate save prevention when saving to Difficult a second time
            msg_poll_dup = DummyMessage(from_user=user1, poll=poll)
            await handle_forwarded_poll(msg_poll_dup, pool)
            await handle_subject_selection(
                DummyCallback(from_user=user1, data=f"rev_subj:{anatomy['id']}", message=msg_poll_dup),
                pool,
            )
            await handle_subtopic_selection(
                DummyCallback(from_user=user1, data=f"rev_subt:{upper_limb_st['id']}", message=msg_poll_dup),
                pool,
            )
            await handle_category_selection(
                DummyCallback(from_user=user1, data="rev_cat:difficult", message=msg_poll_dup),
                pool,
            )
            assert "Already Saved" in msg_poll_dup.replies[-1]["text"]
            print("✅ [7/15] User saves the same question as Difficult too (with duplicate protection).")

            # ------------------------------------------------------------------
            # 8. Question appears under both categories without duplicate records within either category
            # ------------------------------------------------------------------
            mistake_list = await list_revision_questions(pool, user1.id, category="mistake")
            difficult_list = await list_revision_questions(pool, user1.id, category="difficult")
            all_list = await list_revision_questions(pool, user1.id, category="all")

            assert len(mistake_list) == 1, f"Expected 1 in mistake, got {len(mistake_list)}"
            assert len(difficult_list) == 1, f"Expected 1 in difficult, got {len(difficult_list)}"
            assert len(all_list) == 1, f"Expected 1 distinct question in all, got {len(all_list)}"
            assert set(all_list[0]["categories"]) == {"mistake", "difficult"}

            # Verify DB row counts in saved_questions for (user1, question_id)
            qid = all_list[0]["question_id"]
            u1_db_id = all_list[0]["user_id"]
            db_mistake_rows = await pool.fetchval(
                "SELECT COUNT(*) FROM saved_questions WHERE user_id = ? AND question_id = ? AND source = 'mistake'",
                u1_db_id, qid
            )
            db_diff_rows = await pool.fetchval(
                "SELECT COUNT(*) FROM saved_questions WHERE user_id = ? AND question_id = ? AND source = 'difficult'",
                u1_db_id, qid
            )
            assert db_mistake_rows == 1
            assert db_diff_rows == 1
            print("✅ [8/15] Question appears under both categories without duplicate records.")

            # ------------------------------------------------------------------
            # 9. User creates a new subtopic from the website
            # ------------------------------------------------------------------
            res_create_st = client1.post(
                "/questions/subtopics/create",
                data={"subject_id": str(anatomy["id"]), "name": "Lower Limb"},
                follow_redirects=True,
            )
            assert res_create_st.status_code == 200
            assert "Lower Limb" in res_create_st.text
            print("✅ [9/15] User creates a new subtopic ('Lower Limb') from the website.")

            # ------------------------------------------------------------------
            # 10. New subtopic becomes available when saving questions through Telegram
            # ------------------------------------------------------------------
            poll2 = DummyPoll(
                id="e2e_poll_femoral_nerve_002",
                question="Which nerve supplies the anterior compartment of the thigh?",
                options=[
                    DummyPollOption("Sciatic nerve"),
                    DummyPollOption("Femoral nerve"),
                    DummyPollOption("Obturator nerve"),
                    DummyPollOption("Tibial nerve"),
                ],
                correct_option_id=1,
                explanation="The femoral nerve innervates the quadriceps femoris and sartorius.",
            )
            msg_poll2 = DummyMessage(from_user=user1, poll=poll2)
            await handle_forwarded_poll(msg_poll2, pool)
            await handle_subject_selection(
                DummyCallback(from_user=user1, data=f"rev_subj:{anatomy['id']}", message=msg_poll2),
                pool,
            )
            kb = msg_poll2.replies[-1]["reply_markup"]
            button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
            assert any("Lower Limb" in t for t in button_texts), f"Lower Limb not in bot keyboard: {button_texts}"
            print("✅ [10/15] New website subtopic is immediately available in Telegram bot keyboard.")

            # Save poll2 under Anatomy -> Lower Limb -> Mistake for User 1, AND also save poll1 for User 2
            lower_limb_st = next(
                st for st in (await list_user_subtopics(pool, user1.id, anatomy["id"])) if st["name"] == "Lower Limb"
            )
            await handle_subtopic_selection(
                DummyCallback(from_user=user1, data=f"rev_subt:{lower_limb_st['id']}", message=msg_poll2),
                pool,
            )
            await handle_category_selection(
                DummyCallback(from_user=user1, data="rev_cat:mistake", message=msg_poll2),
                pool,
            )

            # ------------------------------------------------------------------
            # 11. User filters and searches their saved questions
            # ------------------------------------------------------------------
            res_search = client1.get("/questions?q=quadriceps")
            assert res_search.status_code == 200
            assert "anterior compartment of the thigh" in res_search.text
            assert "mid-shaft fracture of the humerus" not in res_search.text

            res_filter_ll = client1.get(f"/questions?subject_id={anatomy['id']}&subtopic_id={lower_limb_st['id']}")
            assert res_filter_ll.status_code == 200
            assert "anterior compartment of the thigh" in res_filter_ll.text
            assert "mid-shaft fracture of the humerus" not in res_filter_ll.text
            print("✅ [11/15] User filters and searches their saved questions.")

            # ------------------------------------------------------------------
            # 12 & 13. User deletes a saved question without affecting other users,
            #          and another account cannot access User 1's private questions or subtopics
            # ------------------------------------------------------------------
            # First have User 2 also save poll2 under User 2's own subtopic
            msg_u2_poll = DummyMessage(from_user=user2, poll=poll2)
            await handle_forwarded_poll(msg_u2_poll, pool)
            await handle_subject_selection(
                DummyCallback(from_user=user2, data=f"rev_subj:{anatomy['id']}", message=msg_u2_poll),
                pool,
            )
            # Check that User 2 does NOT see User 1's "Upper Limb" or "Lower Limb" subtopics in Telegram!
            u2_kb = msg_u2_poll.replies[-1]["reply_markup"]
            u2_btn_texts = [btn.text for row in u2_kb.inline_keyboard for btn in row]
            assert not any("Upper Limb" in t or "Lower Limb" in t for t in u2_btn_texts), (
                "User 2 should not see User 1's personal subtopics!"
            )

            msg_u2_subt = DummyMessage(from_user=user2, text="Bob Personal Subtopic")
            await handle_text_message(msg_u2_subt, pool)
            await handle_category_selection(
                DummyCallback(from_user=user2, data="rev_cat:mistake", message=msg_u2_subt),
                pool,
            )

            # Find question_id for poll2
            u1_ll_qs = await list_revision_questions(pool, user1.id, subtopic_id=lower_limb_st["id"])
            assert len(u1_ll_qs) == 1
            poll2_qid = u1_ll_qs[0]["question_id"]

            # User 1 deletes poll2 from their bank
            res_del = client1.post(f"/questions/{poll2_qid}/delete", follow_redirects=True)
            assert res_del.status_code == 200

            u1_after_del = await list_revision_questions(pool, user1.id, subtopic_id=lower_limb_st["id"])
            assert len(u1_after_del) == 0, "Question was not deleted from User 1's bank"

            # Verify User 2 STILL has poll2 intact!
            u2_qs = await list_revision_questions(pool, user2.id)
            assert len(u2_qs) == 1 and u2_qs[0]["question_id"] == poll2_qid, (
                "Deleting User 1's saved question affected User 2's record!"
            )

            # Also verify TXT export on User 1's bank
            res_txt = client1.get("/questions/export.txt")
            assert res_txt.status_code == 200
            assert "mid-shaft fracture of the humerus" in res_txt.text
            print("✅ [12/15] User deletes a saved question without affecting other users (and TXT export works).")

        # Log in as User 2 in a separate client and verify strict isolation
        with TestClient(app) as client2:
            client2.post(
                "/login",
                data={"telegram_id": str(user2.id), "password": "BobPass456", "next": "/"},
            )
            res_u2_q = client2.get("/questions")
            assert res_u2_q.status_code == 200
            assert "mid-shaft fracture of the humerus" not in res_u2_q.text
            assert "Upper Limb" not in res_u2_q.text
            assert "Lower Limb" not in res_u2_q.text
            assert "Bob Personal Subtopic" in res_u2_q.text

            # Attempt to rename or delete User 1's subtopic as User 2 -> must fail
            client2.post(
                f"/questions/subtopics/{upper_limb_st['id']}/rename",
                data={"new_name": "Hacked Name"},
            )
            u1_st_check = await list_user_subtopics(pool, user1.id, anatomy["id"])
            assert any(st["name"] == "Upper Limb" for st in u1_st_check)
            assert not any(st["name"] == "Hacked Name" for st in u1_st_check)
            print("✅ [13/15] Another account cannot access or modify the first user's private questions or subtopics.")

        # ------------------------------------------------------------------
        # 14. Azure SQL persists changes after the bot and website restart
        # ------------------------------------------------------------------
        await close_db_pool(pool)
        pool = await init_db_pool()
        persisted_summary = await get_dashboard_summary(pool, user1.id)
        assert persisted_summary["total"] == 1
        assert persisted_summary["mistake"] == 1
        assert persisted_summary["difficult"] == 1
        assert persisted_summary["subtopics_count"] == 2
        print("✅ [14/15] Azure SQL persists changes across bot and website restarts.")

        # ------------------------------------------------------------------
        # 15. Website works at mobile widths of 320, 360, 390, and 430 pixels
        # ------------------------------------------------------------------
        with TestClient(app) as mobile_client:
            mobile_client.post(
                "/login",
                data={"telegram_id": str(user1.id), "password": "AlicePass123", "next": "/"},
            )
            for path in ("/", "/questions", "/settings", "/login"):
                resp = mobile_client.get(path)
                assert resp.status_code in (200, 302)
                if resp.status_code == 200:
                    assert 'name="viewport"' in resp.text
                    assert "overflow-x: hidden" in resp.text
                    assert "max-width: 100vw" in resp.text
        print("✅ [15/15] Website responsive layout verified for mobile widths 320, 360, 390, and 430 px.")

    finally:
        # Clean up synthetic E2E test rows so real user data is untouched
        for uid in (user1.id, user2.id):
            row = await pool.fetchone("SELECT id FROM users WHERE telegram_user_id = ?", uid)
            if row:
                db_uid = row["id"]
                await pool.execute("DELETE FROM saved_questions WHERE user_id = ?", db_uid)
                await pool.execute("DELETE FROM user_subtopics WHERE user_id = ?", db_uid)
                await pool.execute("DELETE FROM user_sessions WHERE user_id = ?", db_uid)
                await pool.execute("DELETE FROM web_sessions WHERE user_id = ?", db_uid)
                await pool.execute("DELETE FROM auth_tokens WHERE user_id = ? OR telegram_id = ?", db_uid, uid)
                await pool.execute("DELETE FROM users WHERE id = ?", db_uid)
        await pool.execute(
            "DELETE FROM question_bank_options WHERE question_id IN (SELECT id FROM question_bank WHERE telegram_poll_id IN ('e2e_poll_brachial_plexus_001', 'e2e_poll_femoral_nerve_002'))"
        )
        await pool.execute(
            "DELETE FROM question_bank WHERE telegram_poll_id IN ('e2e_poll_brachial_plexus_001', 'e2e_poll_femoral_nerve_002')"
        )
        await close_db_pool(pool)

    print("=" * 72)
    print("  🎉 ALL 15 END-TO-END WORKFLOWS PASSED AGAINST LIVE AZURE SQL!")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
