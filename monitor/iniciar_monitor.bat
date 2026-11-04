@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv314\Scripts\python.exe" (
  ".venv314\Scripts\python.exe" "monitor\server.py"
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "monitor\server.py"
) else (
  py -3 "monitor\server.py"
)
if errorlevel 1 pause
