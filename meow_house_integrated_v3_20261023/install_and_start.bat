@echo off
setlocal
cd /d "%~dp0"
set "MEOW_TEMP=%CD%\work\installer_temp"
if not exist "%MEOW_TEMP%" mkdir "%MEOW_TEMP%"
set "TEMP=%MEOW_TEMP%"
set "TMP=%MEOW_TEMP%"

echo ====================================================
echo   Meow House - First-time setup
echo ====================================================
echo This step needs an Internet connection.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating a Python virtual environment...
  py -3.12 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv .venv
  ) else (
    py -3.11 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      py -3.11 -m venv .venv
    ) else (
      if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
        "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv .venv
      ) else (
        goto python_missing
      )
    )
  )
  if not exist ".venv\Scripts\python.exe" goto python_missing
)

".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo Repairing pip in the virtual environment...
  ".venv\Scripts\python.exe" -m ensurepip --upgrade --default-pip
  if errorlevel 1 goto install_failed
)

echo [2/3] Installing project packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed

if not exist ".env" copy /Y ".env.example" ".env" >nul

echo [3/3] Starting Meow House...
".venv\Scripts\python.exe" scripts\launch_app.py
goto finished

:python_missing
echo.
echo [ERROR] A working Python 3.11 or newer installation was not found.
echo Install Python 3.11 or newer from https://www.python.org/downloads/
goto failed

:install_failed
echo.
echo [ERROR] Package installation failed.
echo Check the Internet connection and run this file again.
goto failed

:finished
echo.
echo The server has stopped.
pause
exit /b 0

:failed
pause
exit /b 1
