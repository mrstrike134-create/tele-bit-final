# Personal Revision Bank — Telegram Bot & Website (Azure SQL Edition)

A simple, reliable personal question-storage website connected to a Telegram bot, backed by **Microsoft Azure SQL Database** (`ODBC Driver 18 for SQL Server` with `aioodbc`/`pyodbc`).

---

## 1. Product Overview

The application consists of two connected components:

1. **Telegram Bot (`bot_runner.py` / webhook)**:
   - Registers user accounts (`/start`) and provides the user's Telegram ID and login credentials (`/id`, `/login`).
   - Allows setting and resetting permanent website passwords (`/setpassword`, `/resetpassword`).
   - Receives forwarded Telegram polls/quizzes, extracts the question text, answer options, correct answer (when available), and explanation (when available).
   - Walks the user through choosing a **Subject** → **Personal Subtopic** (existing or new) → **Category** (`❌ Mistake` or `⭐ Difficult`), saves to Azure SQL, and confirms the save.

2. **Personal Revision Website (`run.py` / `web.main:app`)**:
   - **Dashboard (`/`)**: Shows total saved questions, Mistake count, Difficult count, number of subjects used, and number of personal subtopics.
   - **My Questions (`/questions`)**: Organizes saved questions by `Subject → Subtopic → Question → Category`, with filters for Subject, Subtopic, Category (`All`, `Mistakes`, `Difficult`), and Search text. Supports creating, renaming, moving, and deleting personal subtopics; editing saved questions; changing a question's subject/subtopic; adding/removing `Mistake` and `Difficult` categories independently; deleting saved questions; and exporting to `.txt`.
   - **Settings / Account (`/settings`)**: Displays account details, password change/setup, and logout.

Every authenticated user sees and modifies strictly their own revision data and personal subtopics.

---

## 2. Running Locally

### Start the Website
```bash
python run.py
```

### Start the Telegram Bot (Polling)
```bash
python bot_runner.py
```

### Run End-to-End Verification Suite
```bash
python scripts/test_e2e_revision_bank.py
```
