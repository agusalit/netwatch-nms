#!/usr/bin/env bash
# Starts NetWatch NMS for everyday background use. Called by the Windows
# launcher, but works fine on its own too:   bash scripts/run_server.sh
#
#  - no --reload, and --no-access-log: the dashboard polls every 5 s, so
#    access logging would fill the console/disk for no benefit
#  - runs at low CPU priority (nice 10), so it never competes with the work
#    you are doing in the foreground
#  - when started without a terminal (the hidden launcher), output goes to
#    logs/server.out; the application's own rotating log is logs/netwatch.log
set -e
cd "$(dirname "$0")/.."
source venv/bin/activate
mkdir -p logs

run() {
    exec nice -n 10 uvicorn app.main:app \
        --host "${NETWATCH_HOST:-127.0.0.1}" --port "${NETWATCH_PORT:-8000}" --no-access-log
}

if [ -t 1 ]; then
    run
else
    run > logs/server.out 2>&1
fi
