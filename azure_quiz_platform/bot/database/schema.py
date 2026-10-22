import os
import re
import logging
from bot.database.pool import AzureSQLPool

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def split_tsql_batches(sql_text: str):
    """Split T-SQL script into batches separated by 'GO' on its own line."""
    batches = re.split(r"^\s*GO\s*$", sql_text, flags=re.MULTILINE | re.IGNORECASE)
    return [b.strip() for b in batches if b.strip()]


async def ensure_migrations_table(pool: AzureSQLPool):
    """Ensure the schema_migrations tracking table exists in Azure SQL."""
    sql = """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schema_migrations')
    BEGIN
        CREATE TABLE schema_migrations (
            version NVARCHAR(255) NOT NULL PRIMARY KEY,
            applied_at DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET()
        );
    END
    """
    await pool.execute(sql)


async def run_migrations(pool: AzureSQLPool):
    """Run all pending T-SQL migrations in alphabetical order after backing up existing data."""
    await ensure_migrations_table(pool)

    applied_rows = await pool.fetchall("SELECT version FROM schema_migrations")
    applied = {r["version"] for r in applied_rows}

    if not os.path.exists(MIGRATIONS_DIR):
        logger.warning(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return

    migration_files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")
    )

    pending = [f for f in migration_files if f not in applied]
    if pending:
        try:
            from scripts.backup_database import backup_database
            await backup_database(pool, label="before_migration")
        except Exception as e:
            logger.warning(f"Pre-migration backup warning: {e}")

    for filename in migration_files:
        if filename in applied:
            continue

        filepath = os.path.join(MIGRATIONS_DIR, filename)
        logger.info(f"Applying Azure SQL migration: {filename}")
        with open(filepath, "r", encoding="utf-8") as f:
            sql_content = f.read()

        batches = split_tsql_batches(sql_content)
        for idx, batch in enumerate(batches, start=1):
            try:
                await pool.execute(batch)
            except Exception as e:
                logger.error(f"Error executing batch #{idx} in {filename}: {e}")
                raise

        await pool.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, SYSDATETIMEOFFSET())",
            filename
        )
        logger.info(f"Successfully applied migration: {filename}")
