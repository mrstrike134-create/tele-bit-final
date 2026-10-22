import asyncio
import datetime
import logging
import struct
from typing import Any, Dict, List, Optional, Sequence
import aioodbc
from bot.config import (
    get_connection_string,
    DB_POOL_MIN_SIZE,
    DB_POOL_MAX_SIZE,
)

logger = logging.getLogger(__name__)


def _handle_datetimeoffset(dto_value):
    """
    Decodes SQL Server -155 (SQL_SS_TIMESTAMPOFFSET_STRUCT) into Python datetime.
    Layout: year, month, day, hour, minute, second, fraction, tz_hour, tz_min.
    """
    if dto_value is None:
        return None
    if isinstance(dto_value, bytes) and len(dto_value) >= 16:
        try:
            padded = dto_value[:20] if len(dto_value) >= 20 else dto_value[:16] + b'\x00' * (20 - len(dto_value))
            year, month, day, hour, minute, second, fraction, tz_hour, tz_min = struct.unpack('<hhhhhhihh', padded)
            tz = datetime.timezone(datetime.timedelta(hours=tz_hour, minutes=tz_min))
            microsecond = min(999999, max(0, fraction // 1000))
            return datetime.datetime(year, month, day, hour, minute, second, microsecond, tzinfo=tz)
        except Exception:
            return str(dto_value)
    return str(dto_value)


AZURE_SQL_TRANSIENT_CODES = {
    4060,
    40197,
    40501,
    40613,
    49918,
    49919,
    49920,
    10928,
    10929,
    1205,
}


class AzureRecord(dict):
    """
    A dictionary-based record representation supporting both item access (row['col'])
    and attribute access (row.col).
    """
    def __init__(self, mapping: Dict[str, Any]):
        super().__init__(mapping)
        self.__dict__.update(mapping)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'AzureRecord' has no attribute '{name}'")


def _normalize_args(args: Sequence[Any]) -> Sequence[Any]:
    """Convert Python types into T-SQL friendly types (e.g. booleans to 1/0)."""
    if len(args) == 1 and isinstance(args[0], (tuple, list)):
        args = args[0]
    normalized = []
    for arg in args:
        if isinstance(arg, bool):
            normalized.append(1 if arg else 0)
        else:
            normalized.append(arg)
    return tuple(normalized)


class AzureTransactionCursor:
    """Cursor wrapper inside a pool.transaction() block supporting tuple or vararg parameters."""
    def __init__(self, raw_cursor):
        self.raw_cursor = raw_cursor

    async def execute(self, query: str, *args):
        params = _normalize_args(args)
        if params:
            return await self.raw_cursor.execute(query, *params)
        return await self.raw_cursor.execute(query)

    async def fetchone(self):
        return await self.raw_cursor.fetchone()

    async def fetchall(self):
        return await self.raw_cursor.fetchall()


class AzurePoolTransaction:
    """Async context manager acquiring a connection and managing BEGIN / COMMIT / ROLLBACK."""
    def __init__(self, pool: "AzureSqlPool"):
        self.pool = pool
        self._conn_ctx = None
        self._conn = None
        self._cur_ctx = None
        self._cur = None

    async def __aenter__(self) -> AzureTransactionCursor:
        self._conn_ctx = self.pool.acquire()
        self._conn = await self._conn_ctx.__aenter__()
        self._cur_ctx = self._conn.cursor()
        self._cur = await self._cur_ctx.__aenter__()
        await self._cur.execute("BEGIN TRANSACTION")
        return AzureTransactionCursor(self._cur)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._cur is not None:
                if exc_type is not None:
                    await self._cur.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
                    logger.warning(f"Transaction rolled back due to error: {exc_val}")
                else:
                    await self._cur.execute("IF @@TRANCOUNT > 0 COMMIT TRANSACTION")
        finally:
            if self._cur_ctx is not None:
                await self._cur_ctx.__aexit__(exc_type, exc_val, exc_tb)
            if self._conn_ctx is not None:
                await self._conn_ctx.__aexit__(exc_type, exc_val, exc_tb)


class AzureTransaction:
    """Async transaction context manager on an existing AzureSqlConnection."""
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        async with self.conn.cursor() as cur:
            await cur.execute("BEGIN TRANSACTION")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self.conn.cursor() as cur:
            if exc_type is not None:
                await cur.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
                logger.warning(f"Transaction rolled back due to error: {exc_val}")
            else:
                await cur.execute("IF @@TRANCOUNT > 0 COMMIT TRANSACTION")


class AzureSqlConnection:
    """Wrapper around an aioodbc connection providing helper methods with T-SQL semantics."""
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn
        try:
            raw_conn.add_output_converter(-155, _handle_datetimeoffset)
        except Exception:
            pass

    def transaction(self) -> AzureTransaction:
        return AzureTransaction(self)

    def cursor(self):
        return self.raw_conn.cursor()

    async def fetch(self, query: str, *args) -> List[AzureRecord]:
        async with self.raw_conn.cursor() as cur:
            params = _normalize_args(args)
            if params:
                await cur.execute(query, *params)
            else:
                await cur.execute(query)
            if not cur.description:
                return []
            columns = [c[0] for c in cur.description]
            rows = await cur.fetchall()
            return [AzureRecord(dict(zip(columns, row))) for row in rows]

    async def fetchrow(self, query: str, *args) -> Optional[AzureRecord]:
        async with self.raw_conn.cursor() as cur:
            params = _normalize_args(args)
            if params:
                await cur.execute(query, *params)
            else:
                await cur.execute(query)
            if not cur.description:
                return None
            columns = [c[0] for c in cur.description]
            row = await cur.fetchone()
            if row is None:
                return None
            return AzureRecord(dict(zip(columns, row)))

    async def fetchval(self, query: str, *args) -> Any:
        async with self.raw_conn.cursor() as cur:
            params = _normalize_args(args)
            if params:
                await cur.execute(query, *params)
            else:
                await cur.execute(query)
            row = await cur.fetchone()
            if row is None:
                return None
            return row[0]

    async def execute(self, query: str, *args) -> None:
        async with self.raw_conn.cursor() as cur:
            params = _normalize_args(args)
            if params:
                await cur.execute(query, *params)
            else:
                await cur.execute(query)


class AzureSqlPool:
    """
    High-level Azure SQL Database Connection Pool wrapper with retry resilience,
    transaction support, and dict-like records.
    """
    def __init__(self, raw_pool: aioodbc.Pool):
        self.raw_pool = raw_pool

    async def close(self):
        self.raw_pool.close()
        await self.raw_pool.wait_closed()
        logger.info("Azure SQL connection pool closed.")

    class _AcquireContext:
        def __init__(self, pool_context):
            self.pool_context = pool_context
            self.raw_conn = None

        async def __aenter__(self) -> AzureSqlConnection:
            self.raw_conn = await self.pool_context.__aenter__()
            return AzureSqlConnection(self.raw_conn)

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return await self.pool_context.__aexit__(exc_type, exc_val, exc_tb)

    def acquire(self) -> _AcquireContext:
        return self._AcquireContext(self.raw_pool.acquire())

    def transaction(self) -> AzurePoolTransaction:
        return AzurePoolTransaction(self)

    async def fetch(self, query: str, *args, max_retries: int = 3) -> List[AzureRecord]:
        return await self._execute_with_retry(lambda conn: conn.fetch(query, *args), max_retries)

    async def fetchall(self, query: str, *args, max_retries: int = 3) -> List[AzureRecord]:
        return await self.fetch(query, *args, max_retries=max_retries)

    async def fetchrow(self, query: str, *args, max_retries: int = 3) -> Optional[AzureRecord]:
        return await self._execute_with_retry(lambda conn: conn.fetchrow(query, *args), max_retries)

    async def fetchone(self, query: str, *args, max_retries: int = 3) -> Optional[AzureRecord]:
        return await self.fetchrow(query, *args, max_retries=max_retries)

    async def fetchval(self, query: str, *args, max_retries: int = 3) -> Any:
        return await self._execute_with_retry(lambda conn: conn.fetchval(query, *args), max_retries)

    async def execute(self, query: str, *args, max_retries: int = 3) -> None:
        return await self._execute_with_retry(lambda conn: conn.execute(query, *args), max_retries)

    async def execute_Init_id(self, query: str, *args, max_retries: int = 3) -> int:
        val = await self.fetchval(query, *args, max_retries=max_retries)
        return int(val)

    async def _execute_with_retry(self, operation, max_retries: int):
        last_exception = None
        for attempt in range(max_retries):
            try:
                async with self.acquire() as conn:
                    return await operation(conn)
            except Exception as e:
                last_exception = e
                if _is_transient_error(e) and attempt < max_retries - 1:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(
                        f"Transient Azure SQL error (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise
        if last_exception:
            raise last_exception


# Alias so both AzureSQLPool and AzureSqlPool imports succeed
AzureSQLPool = AzureSqlPool


def _is_transient_error(exc: Exception) -> bool:
    """Determine whether an exception is an Azure SQL transient fault eligible for retry."""
    err_str = str(exc)
    for code in AZURE_SQL_TRANSIENT_CODES:
        if str(code) in err_str:
            return True
    if any(keyword in err_str.lower() for keyword in ["deadlock", "timeout", "busy", "throttl"]):
        return True
    return False


async def init_db_pool(connection_string: Optional[str] = None, max_retries: int = 5) -> AzureSqlPool:
    """Initialize the aioodbc connection pool with retry for Azure SQL Serverless auto-resume (code 40613)."""
    conn_str = connection_string or get_connection_string()
    logger.info("Initializing Azure SQL connection pool...")
    last_err = None
    for attempt in range(max_retries):
        try:
            raw_pool = await aioodbc.create_pool(
                dsn=conn_str,
                minsize=DB_POOL_MIN_SIZE,
                maxsize=DB_POOL_MAX_SIZE,
                autocommit=True,
                timeout=30,
            )
            logger.info("Azure SQL connection pool initialized successfully.")
            return AzureSqlPool(raw_pool)
        except Exception as e:
            last_err = e
            if _is_transient_error(e) and attempt < max_retries - 1:
                backoff = 3.0 * (attempt + 1)
                logger.warning(
                    f"Azure SQL Database warming up / auto-resuming (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {backoff:.1f}s..."
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(f"Failed to initialize Azure SQL connection pool: {e}")
                raise
    raise last_err


async def close_db_pool(pool: Optional[AzureSqlPool]):
    """Safely close the Azure SQL connection pool."""
    if pool:
        await pool.close()
