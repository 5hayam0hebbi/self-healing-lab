#!/usr/bin/env bash
# Break the app, then watch the lab heal it. Run from the repo folder: bash scripts/demo.sh [break|crash]
set -euo pipefail
mode="${1:-break}"
echo "Breaking the app with /chaos/$mode ..."
curl -s -X POST "http://localhost:8000/chaos/$mode" || true
echo
echo "Watching the health check (Ctrl+C to stop):"
for i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || true)
  echo "$(date +%H:%M:%S)  health=$code"
  if [ "$code" = "200" ] && [ "$i" -gt 3 ]; then echo "Healed."; exit 0; fi
  sleep 2
done
echo "Not healed after 90 seconds: check 'docker compose logs remediator'."
