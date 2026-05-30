#!/bin/bash
# Open Chrome on screen (visible mode) and run the dashboard sync worker
cd "$(dirname "$0")"
echo "Initializing Python Virtual Environment..."
source venv/bin/activate
echo "Starting Playwright Dashboard Worker..."
python -u run_dashboard_worker.py
