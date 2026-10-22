-- ============================================================================
-- Migration 001: Consolidated Azure SQL Schema for Unified Quiz Platform
-- Engine: Microsoft Azure SQL Database / SQL Server (T-SQL)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schema_migrations')
BEGIN
    CREATE TABLE schema_migrations (
        version NVARCHAR(255) NOT NULL PRIMARY KEY,
        applied_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
END;

-- 1. Users Table (Stores student credentials & progress)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'users')
BEGIN
    CREATE TABLE users (
        id INT IDENTITY(1,1) PRIMARY KEY,
        telegram_user_id BIGINT NOT NULL UNIQUE,
        first_name NVARCHAR(255) NULL,
        username NVARCHAR(255) NULL,
        password_hash NVARCHAR(255) NULL,
        is_admin BIT NOT NULL DEFAULT 0,
        total_xp INT NOT NULL DEFAULT 0,
        level INT NOT NULL DEFAULT 1,
        current_streak INT NOT NULL DEFAULT 0,
        longest_streak INT NOT NULL DEFAULT 0,
        last_active_at DATETIMEOFFSET NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
    CREATE NONCLUSTERED INDEX idx_users_telegram_id ON users (telegram_user_id);
    CREATE NONCLUSTERED INDEX idx_users_xp ON users (total_xp DESC);
END;

-- 2. Web Sessions Table (Persistent cookie sessions)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'web_sessions')
BEGIN
    CREATE TABLE web_sessions (
        token NVARCHAR(128) NOT NULL PRIMARY KEY,
        user_id INT NOT NULL CONSTRAINT fk_web_sessions_users REFERENCES users(id) ON DELETE CASCADE,
        expires_at DATETIMEOFFSET NOT NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
    CREATE NONCLUSTERED INDEX idx_web_sessions_user_id ON web_sessions (user_id);
    CREATE NONCLUSTERED INDEX idx_web_sessions_expires_at ON web_sessions (expires_at);
END;

-- 3. Modules Table (Subject Categories)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'modules')
BEGIN
    CREATE TABLE modules (
        id INT IDENTITY(1,1) PRIMARY KEY,
        title NVARCHAR(255) NOT NULL,
        description NVARCHAR(MAX) NULL,
        icon NVARCHAR(50) NOT NULL DEFAULT 'book',
        sort_order INT NOT NULL DEFAULT 0,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
END;

-- 4. Quizzes Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'quizzes')
BEGIN
    CREATE TABLE quizzes (
        id INT IDENTITY(1,1) PRIMARY KEY,
        module_id INT NULL CONSTRAINT fk_quizzes_modules REFERENCES modules(id) ON DELETE SET NULL,
        title NVARCHAR(255) NOT NULL,
        description NVARCHAR(MAX) NULL,
        time_limit_minutes INT NOT NULL DEFAULT 10,
        passing_score INT NOT NULL DEFAULT 70,
        is_published BIT NOT NULL DEFAULT 1,
        sort_order INT NOT NULL DEFAULT 0,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
    CREATE NONCLUSTERED INDEX idx_quizzes_module ON quizzes (module_id);
    CREATE NONCLUSTERED INDEX idx_quizzes_published ON quizzes (is_published, sort_order);
END;

-- 5. Question Bank Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'question_bank')
BEGIN
    CREATE TABLE question_bank (
        id INT IDENTITY(1,1) PRIMARY KEY,
        module_id INT NULL CONSTRAINT fk_qbank_modules REFERENCES modules(id) ON DELETE SET NULL,
        text NVARCHAR(MAX) NOT NULL,
        explanation NVARCHAR(MAX) NULL,
        question_type NVARCHAR(50) NOT NULL DEFAULT 'single_choice',
        difficulty NVARCHAR(20) NOT NULL DEFAULT 'medium',
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
END;

-- 6. Question Bank Options Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'question_bank_options')
BEGIN
    CREATE TABLE question_bank_options (
        id INT IDENTITY(1,1) PRIMARY KEY,
        question_id INT NOT NULL CONSTRAINT fk_options_qbank REFERENCES question_bank(id) ON DELETE CASCADE,
        option_text NVARCHAR(MAX) NOT NULL,
        is_correct BIT NOT NULL DEFAULT 0,
        sort_order INT NOT NULL DEFAULT 0
    );
    CREATE NONCLUSTERED INDEX idx_qbank_options_question ON question_bank_options (question_id);
END;

-- 7. Quiz Questions Association Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'quiz_questions')
BEGIN
    CREATE TABLE quiz_questions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        quiz_id INT NOT NULL CONSTRAINT fk_qq_quizzes REFERENCES quizzes(id) ON DELETE CASCADE,
        question_id INT NOT NULL CONSTRAINT fk_qq_qbank REFERENCES question_bank(id) ON DELETE CASCADE,
        points INT NOT NULL DEFAULT 1,
        sort_order INT NOT NULL DEFAULT 0,
        CONSTRAINT uq_quiz_question UNIQUE (quiz_id, question_id)
    );
    CREATE NONCLUSTERED INDEX idx_quiz_questions_quiz ON quiz_questions (quiz_id, sort_order);
END;

-- 8. Quiz Attempts Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'quiz_attempts')
BEGIN
    CREATE TABLE quiz_attempts (
        id INT IDENTITY(1,1) PRIMARY KEY,
        quiz_id INT NOT NULL CONSTRAINT fk_attempts_quizzes REFERENCES quizzes(id) ON DELETE CASCADE,
        user_id INT NOT NULL CONSTRAINT fk_attempts_users REFERENCES users(id) ON DELETE CASCADE,
        score INT NOT NULL DEFAULT 0,
        max_score INT NOT NULL DEFAULT 0,
        percentage FLOAT NOT NULL DEFAULT 0.0,
        passed BIT NOT NULL DEFAULT 0,
        completed BIT NOT NULL DEFAULT 0,
        started_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        completed_at DATETIMEOFFSET NULL
    );
    CREATE NONCLUSTERED INDEX idx_quiz_attempts_user ON quiz_attempts (user_id, quiz_id);
    CREATE NONCLUSTERED INDEX idx_quiz_attempts_completed ON quiz_attempts (completed, percentage DESC);
END;

-- 9. Answers Table (Individual student responses)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'answers')
BEGIN
    CREATE TABLE answers (
        id INT IDENTITY(1,1) PRIMARY KEY,
        attempt_id INT NOT NULL CONSTRAINT fk_answers_attempts REFERENCES quiz_attempts(id) ON DELETE CASCADE,
        question_id INT NOT NULL CONSTRAINT fk_answers_qbank REFERENCES question_bank(id),
        selected_option_id INT NULL CONSTRAINT fk_answers_options REFERENCES question_bank_options(id),
        text_answer NVARCHAR(MAX) NULL,
        is_correct BIT NOT NULL DEFAULT 0,
        points_awarded INT NOT NULL DEFAULT 0,
        answered_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
    CREATE NONCLUSTERED INDEX idx_answers_attempt ON answers (attempt_id);
    CREATE NONCLUSTERED INDEX idx_answers_question_correct ON answers (question_id, is_correct);
END;

-- 10. Saved Questions Table (Revision Bank: mistakes, saved, difficult)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'saved_questions')
BEGIN
    CREATE TABLE saved_questions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL CONSTRAINT fk_saved_users REFERENCES users(id) ON DELETE CASCADE,
        question_id INT NOT NULL CONSTRAINT fk_saved_qbank REFERENCES question_bank(id) ON DELETE CASCADE,
        source NVARCHAR(50) NOT NULL DEFAULT 'manual', -- 'manual', 'mistake', 'difficult'
        notes NVARCHAR(MAX) NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT uq_user_saved_question UNIQUE (user_id, question_id)
    );
    CREATE NONCLUSTERED INDEX idx_saved_questions_user ON saved_questions (user_id);
END;

-- 11. Achievements Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'achievements')
BEGIN
    CREATE TABLE achievements (
        code NVARCHAR(100) NOT NULL PRIMARY KEY,
        category NVARCHAR(50) NOT NULL,
        title_en NVARCHAR(255) NOT NULL,
        title_ar NVARCHAR(255) NOT NULL,
        desc_en NVARCHAR(MAX) NOT NULL,
        desc_ar NVARCHAR(MAX) NOT NULL,
        icon NVARCHAR(50) NOT NULL,
        points INT NOT NULL DEFAULT 10,
        badge_color NVARCHAR(50) NOT NULL DEFAULT 'bronze',
        sort_order INT NOT NULL DEFAULT 0
    );
END;

-- 12. User Achievements Table (Unlocked badges)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_achievements')
BEGIN
    CREATE TABLE user_achievements (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL CONSTRAINT fk_ua_users REFERENCES users(id) ON DELETE CASCADE,
        achievement_code NVARCHAR(100) NOT NULL CONSTRAINT fk_ua_achievements REFERENCES achievements(code) ON DELETE CASCADE,
        unlocked_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT uq_user_achievement UNIQUE (user_id, achievement_code)
    );
    CREATE NONCLUSTERED INDEX idx_user_achievements_user ON user_achievements (user_id);
END;

-- 13. User Achievement Progress Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_achievement_progress')
BEGIN
    CREATE TABLE user_achievement_progress (
        user_id INT NOT NULL CONSTRAINT fk_uap_users REFERENCES users(id) ON DELETE CASCADE,
        achievement_code NVARCHAR(100) NOT NULL CONSTRAINT fk_uap_achievements REFERENCES achievements(code) ON DELETE CASCADE,
        current_val INT NOT NULL DEFAULT 0,
        target_val INT NOT NULL DEFAULT 1,
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT pk_user_achievement_progress PRIMARY KEY (user_id, achievement_code)
    );
END;

-- 14. XP Transactions Table (Gamification ledger)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'xp_transactions')
BEGIN
    CREATE TABLE xp_transactions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL CONSTRAINT fk_xptx_users REFERENCES users(id) ON DELETE CASCADE,
        amount INT NOT NULL,
        reason NVARCHAR(255) NOT NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
    CREATE NONCLUSTERED INDEX idx_xp_tx_user ON xp_transactions (user_id, created_at DESC);
END;

-- 15. System Settings Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'system_settings')
BEGIN
    CREATE TABLE system_settings (
        key_name NVARCHAR(100) NOT NULL PRIMARY KEY,
        value NVARCHAR(MAX) NOT NULL,
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
END;
