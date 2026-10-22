-- ============================================================================
-- Migration 007: Per-Question Timing & Answer Audit Columns
-- Engine: Microsoft Azure SQL Database / SQL Server (T-SQL)
-- Concurrency & Idempotency: Safe to run repeatedly with GO batch separators
-- ============================================================================

-- 1. Add question_started_at to answers
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'question_started_at')
BEGIN
    ALTER TABLE answers ADD question_started_at DATETIMEOFFSET NULL;
END;
GO

-- 2. Add elapsed_ms to answers
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'elapsed_ms')
BEGIN
    ALTER TABLE answers ADD elapsed_ms INT NULL;
END;
GO

-- 3. Add time_limit_seconds to answers
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'time_limit_seconds')
BEGIN
    ALTER TABLE answers ADD time_limit_seconds INT NULL;
END;
GO

-- 4. Add xp_earned to answers
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'xp_earned')
BEGIN
    ALTER TABLE answers ADD xp_earned INT NULL;
END;
GO

-- 5. Add streak_after_answer to answers
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('answers') AND name = 'streak_after_answer')
BEGIN
    ALTER TABLE answers ADD streak_after_answer INT NULL;
END;
GO
