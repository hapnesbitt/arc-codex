#!/bin/bash
source /home/www/arc_stack/backend/venv/bin/activate

# BEST PRACTICES CONFIG:
# --timeout 600: Industry standard for heavy data (safe & reliable).
# --worker-class gthread: Lets 1 worker handle multiple requests simultaneously.
# --threads 8: Ideal for the Z230's CPU cores.

exec gunicorn \
    --bind 127.0.0.1:5005 \
    --workers 14 \
    --threads 8 \
    --worker-class gthread \
    --timeout 600 \
    --preload \
    --access-logfile /home/www/arc_stack/logs/gunicorn_access.log \
    --error-logfile /home/www/arc_stack/logs/gunicorn_error.log \
    main:app
