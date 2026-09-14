#!/bin/bash
CHECKER_THREADS=${CHECKER_THREADS:-10} \
CHECKER_RETRIES=${CHECKER_RETRIES:-2} \
python3 -u -m uvicorn api_server:app \
  --host 0.0.0.0 \
  --port ${PORT:-8000} \
  --workers 1 \
  --timeout-keep-alive 120 \
  --log-level info
