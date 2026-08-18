#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

echo "⚙️ Running database migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

echo "🚀 Collecting static files..."
python manage.py collectstatic --noinput

# Execute the main container command (Gunicorn)
exec "$@"