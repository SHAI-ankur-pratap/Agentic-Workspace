#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

echo "=================================="
echo "  JobAgent — LinkedIn + Naukri"
echo "=================================="
echo ""
echo "Choose platform:"
echo "  1) LinkedIn only"
echo "  2) Naukri only"
echo "  3) Both (LinkedIn then Naukri)"
echo "  4) Start 24/7 daemon (headless, every 4h)"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
  1)
    echo "Starting LinkedIn agent..."
    PYTHONUNBUFFERED=1 python main.py --platform linkedin --autonomous --profile profile.yaml
    ;;
  2)
    echo "Starting Naukri agent..."
    PYTHONUNBUFFERED=1 python main.py --platform naukri --autonomous --profile profile.yaml
    ;;
  3)
    echo "Starting LinkedIn agent..."
    PYTHONUNBUFFERED=1 python main.py --platform linkedin --autonomous --profile profile.yaml
    echo ""
    echo "Starting Naukri agent..."
    PYTHONUNBUFFERED=1 python main.py --platform naukri --autonomous --profile profile.yaml
    ;;
  4)
    echo "Starting 24/7 daemon (Ctrl+C to stop)..."
    PYTHONUNBUFFERED=1 python main.py --daemon --profile profile.yaml
    ;;
  *)
    echo "Invalid choice."
    ;;
esac
