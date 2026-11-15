@echo off
cd /d "%~dp0"
if not exist ".tools\uv.exe" (
  echo The workspace is not set up yet. Open this folder in Claude Code or Codex and ask: Set this up.
  pause
  exit /b 1
)
start "" "http://localhost:8790"
.tools\uv.exe run app\server.py
if errorlevel 1 pause
