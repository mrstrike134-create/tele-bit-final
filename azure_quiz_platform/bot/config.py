import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def get_runtime_env(key: str, default: str = "") -> str:
    """
    Retrieve configuration from runtime environment variables.
    On Windows, also checks HKCU\\Environment if the current process environment
    has not yet refreshed after OS-level configuration updates.
    Does not require a .env file or hardcoded credentials.
    """
    val = os.environ.get(key)
    if val is not None and val != "":
        return val
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg_key:
                reg_val, _ = winreg.QueryValueEx(reg_key, key)
                if reg_val:
                    return str(reg_val)
        except Exception:
            pass
    return default


AZURE_SQL_CONNECTION_STRING = get_runtime_env("AZURE_SQL_CONNECTION_STRING", "")
AZURE_SQL_SERVER = get_runtime_env("AZURE_SQL_SERVER", "tcp:quizplatform.database.windows.net,1433")
AZURE_SQL_DATABASE = get_runtime_env("AZURE_SQL_DATABASE", "quizplatform")
AZURE_SQL_USER = get_runtime_env("AZURE_SQL_USER", "")
AZURE_SQL_PASSWORD = get_runtime_env("AZURE_SQL_PASSWORD", "")
AZURE_SQL_DRIVER = get_runtime_env("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
AZURE_SQL_ENCRYPT = get_runtime_env("AZURE_SQL_ENCRYPT", "yes")
AZURE_SQL_TRUST_CERT = get_runtime_env("AZURE_SQL_TRUST_CERT", "no")


def get_best_available_driver() -> str:
    """Detect the optimal installed ODBC SQL Server driver."""
    if AZURE_SQL_DRIVER:
        return AZURE_SQL_DRIVER
    try:
        import pyodbc
        available = pyodbc.drivers()
        for preferred in [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ]:
            if preferred in available:
                return preferred
    except Exception:
        pass
    return "ODBC Driver 18 for SQL Server"


def get_connection_string() -> str:
    """Return the primary ODBC connection string for Azure SQL Database."""
    if AZURE_SQL_CONNECTION_STRING:
        return AZURE_SQL_CONNECTION_STRING
    driver = get_best_available_driver()
    return (
        f"Driver={{{driver}}};"
        f"Server={AZURE_SQL_SERVER};"
        f"Database={AZURE_SQL_DATABASE};"
        f"Uid={AZURE_SQL_USER};"
        f"Pwd={AZURE_SQL_PASSWORD};"
        f"Encrypt={AZURE_SQL_ENCRYPT};"
        f"TrustServerCertificate={AZURE_SQL_TRUST_CERT};"
        "Connection Timeout=30;"
    )


DB_POOL_MIN_SIZE = int(get_runtime_env("DB_POOL_MIN_SIZE", "2"))
DB_POOL_MAX_SIZE = int(get_runtime_env("DB_POOL_MAX_SIZE", "20"))

# Web Security & Session Configuration
SECRET_KEY = get_runtime_env("SECRET_KEY", "personal-revision-bank-session-secret")
WEB_HOST = get_runtime_env("WEB_HOST", "0.0.0.0")
WEB_PORT = int(get_runtime_env("WEB_PORT", "8000"))
ENVIRONMENT = get_runtime_env("ENVIRONMENT", "production").lower()
IS_PROD = ENVIRONMENT in ("prod", "production")

# Telegram Bot Configuration
BOT_TOKEN = get_runtime_env("BOT_TOKEN", "")
_raw_bot_username = get_runtime_env("BOT_USERNAME", "MistakesCore_bot").strip().lstrip("@")
if not _raw_bot_username or _raw_bot_username.lower() == "codeblueqvault_bot":
    _raw_bot_username = "MistakesCore_bot"
BOT_USERNAME = _raw_bot_username
BOT_URL = f"https://t.me/{BOT_USERNAME}"
TELEGRAM_WEBHOOK_SECRET = get_runtime_env("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_WEBHOOK_URL = get_runtime_env("TELEGRAM_WEBHOOK_URL", "")
BOT_SESSION_EXPIRY_SECONDS = int(get_runtime_env("BOT_SESSION_EXPIRY_SECONDS", "3600"))
LOGIN_CODE_EXPIRY_SECONDS = int(get_runtime_env("LOGIN_CODE_EXPIRY_SECONDS", "600"))
