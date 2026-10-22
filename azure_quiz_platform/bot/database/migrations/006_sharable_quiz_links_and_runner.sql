-- ============================================================================
-- Migration 006: Sharable Quiz Links & Server-Authoritative Quiz Runner
-- Engine: Microsoft Azure SQL Database / SQL Server (T-SQL)
-- Concurrency & Idempotency: Safe to run repeatedly
-- ============================================================================

-- 1. Ensure share_token on quizzes table
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'share_token')
BEGIN
    ALTER TABLE quizzes ADD share_token NVARCHAR(64) NULL;
END;
GO

-- 2. Backfill existing quizzes with unique clean share_token
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'share_token')
BEGIN
    EXEC sp_executesql N'UPDATE quizzes SET share_token = LOWER(SUBSTRING(CONVERT(VARCHAR(64), NEWID()), 1, 12)) WHERE share_token IS NULL;';
END;
GO

-- 3. Create unique index on share_token
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_quizzes_share_token' AND object_id = OBJECT_ID('quizzes'))
BEGIN
    EXEC sp_executesql N'CREATE UNIQUE NONCLUSTERED INDEX idx_quizzes_share_token ON quizzes (share_token) WHERE share_token IS NOT NULL;';
END;
GO

-- 4. Interactive Runner State Columns on quiz_attempts table
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quiz_attempts') AND name = 'current_question_index')
BEGIN
    ALTER TABLE quiz_attempts ADD current_question_index INT NOT NULL DEFAULT 0;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quiz_attempts') AND name = 'question_started_at')
BEGIN
    ALTER TABLE quiz_attempts ADD question_started_at DATETIMEOFFSET NULL;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quiz_attempts') AND name = 'current_streak')
BEGIN
    ALTER TABLE quiz_attempts ADD current_streak INT NOT NULL DEFAULT 0;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quiz_attempts') AND name = 'best_streak')
BEGIN
    ALTER TABLE quiz_attempts ADD best_streak INT NOT NULL DEFAULT 0;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quiz_attempts') AND name = 'total_xp_awarded')
BEGIN
    ALTER TABLE quiz_attempts ADD total_xp_awarded INT NOT NULL DEFAULT 0;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quiz_attempts') AND name = 'question_order')
BEGIN
    ALTER TABLE quiz_attempts ADD question_order NVARCHAR(MAX) NULL;
END;
GO

-- 5. Speed & Timeout tracking on answers table
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'response_time_seconds')
BEGIN
    ALTER TABLE answers ADD response_time_seconds FLOAT NULL DEFAULT 0.0;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'is_timeout')
BEGIN
    ALTER TABLE answers ADD is_timeout BIT NOT NULL DEFAULT 0;
END;
GO

-- 6. Anti-Duplicate Constraint on answers (attempt_id, question_id)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'uq_answers_attempt_question' AND object_id = OBJECT_ID('answers')
)
BEGIN
    ;WITH DuplicateCTE AS (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY attempt_id, question_id ORDER BY id ASC) as rn
        FROM answers
    )
    DELETE FROM DuplicateCTE WHERE rn > 1;

    ALTER TABLE answers ADD CONSTRAINT uq_answers_attempt_question UNIQUE (attempt_id, question_id);
END;
GO
