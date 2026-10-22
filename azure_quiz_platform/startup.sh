#!/bin/sh
set -e

echo "=== Starting Azure Quiz Platform on Azure App Service ==="

# Execute Azure SQL Database schema migrations
echo "Running database schema migrations..."
python scripts/run_migrations.py || {
    echo "Warning: Database migrations failed or database is provisioning. Continuing startup..."
}

# Start the FastAPI web application with uvicorn
echo "Launching FastAPI web server with uvicorn..."
exec uvicorn web.main:app --host 0.0.0.0 --port 8000 --workers 2
