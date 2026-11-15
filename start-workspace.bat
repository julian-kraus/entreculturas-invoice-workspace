@echo off
cd /d "%~dp0"
start "" "http://localhost:8790"
python app\server.py
if errorlevel 1 pause
