-- ============================================================================
-- Migration 008: Personal Revision Bank Schema (User-Owned Subtopics & Isolation)
-- 1. Creates user_subtopics table for personal per-user subtopic organization.
-- 2. Adds subject_id and subtopic_id columns to saved_questions.
-- 3. Adds subtopic_id, subtopic_name, and pending_poll_id to user_sessions.
-- 4. Backfills existing saved_questions records non-destructively.
-- ============================================================================

-- 1. Create user_subtopics table (user-owned subtopics under subjects)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_subtopics')
BEGIN
    CREATE TABLE user_subtopics (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL,
        subject_id INT NOT NULL,
        name NVARCHAR(255) NOT NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_user_subtopics_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT FK_user_subtopics_subject FOREIGN KEY (subject_id) REFERENCES modules(id) ON DELETE CASCADE,
        CONSTRAINT UQ_user_subtopics_user_subject_name UNIQUE (user_id, subject_id, name)
    );

    CREATE INDEX IX_user_subtopics_user_subject ON user_subtopics(user_id, subject_id);
END
GO

-- 2. Add subject_id and subtopic_id to saved_questions for per-user organization
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('saved_questions') AND name = 'subject_id'
)
BEGIN
    ALTER TABLE saved_questions ADD subject_id INT NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('saved_questions') AND name = 'subtopic_id'
)
BEGIN
    ALTER TABLE saved_questions ADD subtopic_id INT NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys
    WHERE name = 'FK_saved_questions_subject' AND parent_object_id = OBJECT_ID('saved_questions')
)
BEGIN
    ALTER TABLE saved_questions
    ADD CONSTRAINT FK_saved_questions_subject FOREIGN KEY (subject_id) REFERENCES modules(id);
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys
    WHERE name = 'FK_saved_questions_subtopic' AND parent_object_id = OBJECT_ID('saved_questions')
)
BEGIN
    ALTER TABLE saved_questions
    ADD CONSTRAINT FK_saved_questions_subtopic FOREIGN KEY (subtopic_id) REFERENCES user_subtopics(id);
END
GO

-- 3. Extend user_sessions for Telegram bot conversation state
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('user_sessions') AND name = 'subtopic_id'
)
BEGIN
    ALTER TABLE user_sessions ADD subtopic_id INT NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('user_sessions') AND name = 'subtopic_name'
)
BEGIN
    ALTER TABLE user_sessions ADD subtopic_name NVARCHAR(255) NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('user_sessions') AND name = 'pending_poll_id'
)
BEGIN
    ALTER TABLE user_sessions ADD pending_poll_id NVARCHAR(255) NULL;
END
GO

-- 4. Preserve legacy 'important' saved_questions by mapping to 'difficult' where not duplicated
UPDATE sq
SET sq.source = N'difficult'
FROM saved_questions sq
WHERE sq.source = N'important'
  AND NOT EXISTS (
      SELECT 1 FROM saved_questions sq2
      WHERE sq2.user_id = sq.user_id
        AND sq2.question_id = sq.question_id
        AND sq2.source = N'difficult'
  );
GO

-- 5. Backfill saved_questions.subject_id from question_bank.module_id where missing
UPDATE sq
SET sq.subject_id = qb.module_id
FROM saved_questions sq
INNER JOIN question_bank qb ON sq.question_id = qb.id
WHERE sq.subject_id IS NULL AND qb.module_id IS NOT NULL;
GO

-- 6. Backfill user_subtopics from existing question_bank.subtopic for saved_questions
INSERT INTO user_subtopics (user_id, subject_id, name, created_at, updated_at)
SELECT DISTINCT
    sq.user_id,
    sq.subject_id,
    LTRIM(RTRIM(qb.subtopic)),
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
FROM saved_questions sq
INNER JOIN question_bank qb ON sq.question_id = qb.id
WHERE sq.subject_id IS NOT NULL
  AND qb.subtopic IS NOT NULL
  AND LTRIM(RTRIM(qb.subtopic)) <> N''
  AND NOT EXISTS (
      SELECT 1 FROM user_subtopics us
      WHERE us.user_id = sq.user_id
        AND us.subject_id = sq.subject_id
        AND us.name = LTRIM(RTRIM(qb.subtopic))
  );
GO

-- 7. Link saved_questions.subtopic_id to backfilled user_subtopics
UPDATE sq
SET sq.subtopic_id = us.id
FROM saved_questions sq
INNER JOIN question_bank qb ON sq.question_id = qb.id
INNER JOIN user_subtopics us
    ON us.user_id = sq.user_id
   AND us.subject_id = sq.subject_id
   AND us.name = LTRIM(RTRIM(qb.subtopic))
WHERE sq.subtopic_id IS NULL
  AND qb.subtopic IS NOT NULL
  AND LTRIM(RTRIM(qb.subtopic)) <> N'';
GO

-- 8. Create index on saved_questions for fast per-user filtering
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_saved_questions_user_subject_subtopic'
      AND object_id = OBJECT_ID('saved_questions')
)
BEGIN
    CREATE INDEX IX_saved_questions_user_subject_subtopic
    ON saved_questions(user_id, subject_id, subtopic_id, source);
END
GO
