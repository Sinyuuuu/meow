@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] The Python environment is not installed yet.
  echo Run install_and_start.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\launch_app.py

echo.
echo The server has stopped. Keep this window for troubleshooting.
pause
