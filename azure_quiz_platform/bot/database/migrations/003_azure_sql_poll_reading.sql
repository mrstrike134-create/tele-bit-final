-- ============================================================================
-- Migration 003: Poll Reading & Telegram Forwarding Integration
-- Engine: Microsoft Azure SQL Database / SQL Server (T-SQL)
-- ============================================================================

-- 1. Extend question_bank with poll identifiers
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('question_bank') AND name = 'telegram_poll_id')
BEGIN
    ALTER TABLE question_bank ADD telegram_poll_id NVARCHAR(255) NULL;
    CREATE NONCLUSTERED INDEX idx_qbank_telegram_poll_id ON question_bank (telegram_poll_id);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('question_bank') AND name = 'source_chat_id')
BEGIN
    ALTER TABLE question_bank ADD source_chat_id BIGINT NULL;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('question_bank') AND name = 'source_message_id')
BEGIN
    ALTER TABLE question_bank ADD source_message_id BIGINT NULL;
    CREATE NONCLUSTERED INDEX idx_qbank_source_msg ON question_bank (source_chat_id, source_message_id);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('question_bank') AND name = 'correct_option_index')
BEGIN
    ALTER TABLE question_bank ADD correct_option_index INT NULL;
END;

-- 2. User sessions table for bot inline keyboard conversational state
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_sessions')
BEGIN
    CREATE TABLE user_sessions (
        user_id INT NOT NULL PRIMARY KEY CONSTRAINT fk_user_sessions_users REFERENCES users(id) ON DELETE CASCADE,
        state NVARCHAR(100) NOT NULL,
        question_id INT NOT NULL CONSTRAINT fk_user_sessions_qbank REFERENCES question_bank(id) ON DELETE CASCADE,
        subject_id INT NULL CONSTRAINT fk_user_sessions_modules REFERENCES modules(id) ON DELETE SET NULL,
        expires_at DATETIMEOFFSET NOT NULL,
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
END;

-- 3. One-time website login codes generated via Telegram /login or /start
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'auth_tokens')
BEGIN
    CREATE TABLE auth_tokens (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL CONSTRAINT fk_auth_tokens_users REFERENCES users(id) ON DELETE CASCADE,
        telegram_id BIGINT NOT NULL,
        token_hash NVARCHAR(255) NOT NULL,
        plain_code NVARCHAR(50) NOT NULL,
        expires_at DATETIMEOFFSET NOT NULL,
        used BIT NOT NULL DEFAULT 0,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
    CREATE NONCLUSTERED INDEX idx_auth_tokens_lookup ON auth_tokens (telegram_id, plain_code, used);
END;

-- 4. Processed updates table for Telegram update idempotency
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'processed_updates')
BEGIN
    CREATE TABLE processed_updates (
        update_id BIGINT NOT NULL PRIMARY KEY,
        processed_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
    );
END;
