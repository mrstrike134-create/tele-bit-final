import os
import sys
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from bot.config import WEB_HOST, WEB_PORT

if __name__ == "__main__":
    print("=" * 65)
    print("  📚 Starting Personal Revision Bank (Microsoft Azure SQL DB)")
    print(f"  🌐 URL: http://{WEB_HOST if WEB_HOST != '0.0.0.0' else '127.0.0.1'}:{WEB_PORT}")
    print("=" * 65)

    uvicorn.run(
        "web.main:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
        log_level="info"
    )
