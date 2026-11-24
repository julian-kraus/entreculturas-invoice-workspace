#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -x .tools/uv ]; then
  echo "The workspace is not set up yet. Open this folder in Claude Code or Codex and ask: Set this up."
  read -r -p "Press Enter to close."
  exit 1
fi
exec ./.tools/uv run --locked app/server.py --open-browser
