#!/bin/bash
cd "$(dirname "$0")" || exit 1
PYTHON=python3
command -v python3 >/dev/null 2>&1 || PYTHON=python
( sleep 1 && open "http://localhost:8790" ) &
"$PYTHON" app/server.py
