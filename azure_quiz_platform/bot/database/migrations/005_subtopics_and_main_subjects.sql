-- ============================================================================
-- Migration 005: Add Quiz Timers, Subtopics, and Seed Main Medical Subjects
-- Engine: Microsoft Azure SQL Database / SQL Server (T-SQL)
-- ============================================================================

-- 1. Ensure Quiz Setting Columns on quizzes table
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'default_time_limit')
BEGIN
    ALTER TABLE quizzes ADD default_time_limit INT NOT NULL DEFAULT 60;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'allow_retry')
BEGIN
    ALTER TABLE quizzes ADD allow_retry BIT NOT NULL DEFAULT 0;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'shuffle_questions')
BEGIN
    ALTER TABLE quizzes ADD shuffle_questions BIT NOT NULL DEFAULT 1;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'shuffle_options')
BEGIN
    ALTER TABLE quizzes ADD shuffle_options BIT NOT NULL DEFAULT 1;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'show_answers')
BEGIN
    ALTER TABLE quizzes ADD show_answers BIT NOT NULL DEFAULT 1;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'created_by')
BEGIN
    ALTER TABLE quizzes ADD created_by BIGINT NULL;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('quizzes') AND name = 'subtopic')
BEGIN
    ALTER TABLE quizzes ADD subtopic NVARCHAR(100) NULL;
END;

-- 2. Add subtopic to question_bank table
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('question_bank') AND name = 'subtopic')
BEGIN
    ALTER TABLE question_bank ADD subtopic NVARCHAR(100) NULL;
END;

-- 3. Seed 5 Main Subjects into modules table (Idempotent MERGE)
MERGE INTO modules AS target
USING (VALUES
    (N'Biochemistry', N'Biochemistry & Molecular Biology', N'🧪', 1),
    (N'Anatomy', N'Human Gross & Neuro Anatomy', N'🫀', 2),
    (N'Physiology', N'Human Physiology & Organ Systems', N'⚡', 3),
    (N'Histology', N'Microscopic Anatomy & Tissues', N'🔬', 4),
    (N'PP', N'Pathology & Pharmacology', N'💊', 5)
) AS src (title, description, icon, sort_order)
ON target.title = src.title
WHEN MATCHED THEN
    UPDATE SET 
        target.description = src.description,
        target.icon = src.icon,
        target.sort_order = src.sort_order
WHEN NOT MATCHED THEN
    INSERT (title, description, icon, sort_order, created_at)
    VALUES (src.title, src.description, src.icon, src.sort_order, SYSDATETIMEOFFSET());
