@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Run install_and_start.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\database_admin.py backup
pause
