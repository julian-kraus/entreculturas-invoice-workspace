@echo off
cd /d "%~dp0"
if not exist ".tools\uv.exe" (
  echo The workspace is not set up yet. Open this folder in Claude Code or Codex and ask: Set this up.
  pause
  exit /b 1
)
.tools\uv.exe run --locked app\server.py --open-browser
if errorlevel 1 pause
