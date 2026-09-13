#!/bin/bash
export CHECKER_THREADS="${CHECKER_THREADS:-200}"
export CHECKER_RETRIES="${CHECKER_RETRIES:-1}"
export LOG_LEVEL="${LOG_LEVEL:-WARNING}"
exec python3 -u -m uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --loop uvloop \
  --http httptools \
  --timeout-keep-alive 60 \
  --log-level warning
