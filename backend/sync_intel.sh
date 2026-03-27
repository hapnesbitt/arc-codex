#!/bin/bash
# Arc Codex - Autonomous Intelligence Sync

APP_DIR="/home/www/arc_stack/backend"
LOG_FILE="/home/www/arc_stack/logs/sync_intel.log"

# Ensure we are in the right directory for imports to work
cd $APP_DIR

# Activate Venv
source venv/bin/activate

echo "[$(date)] --- STARTING HOURLY BROADCAST ---" >> $LOG_FILE

# Run the three key generators headlessly
python3 -c "
import kasmir7
from termcolor import colored
r = kasmir7.connect_redis()
kasmir7.generate_sitemap(r)
kasmir7.generate_rss(r)
kasmir7.generate_news_sitemap(r)
" >> $LOG_FILE 2>&1

echo "[$(date)] --- BROADCAST COMPLETE ---" >> $LOG_FILE
