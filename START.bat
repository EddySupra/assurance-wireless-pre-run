@echo off
setlocal
cd /d "%~dp0"

rem Double-click to run. First time: installs everything it needs.
rem Extra options pass straight through, e.g.  START.bat --start-row 103 --fast
rem With no options it runs every lead on the sheet with --fast.

if exist ".venv\Scripts\python.exe" goto run

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"

if not defined PY (
    echo Python is not installed. Installing Python 3.11...
    winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    echo.
    echo Python was just installed. CLOSE this window and double-click START.bat again.
    pause
    exit /b 1
)

echo First-time setup: creating environment and installing packages...
%PY% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Setup finished.
echo.

:run
if "%~1"=="" (
    ".venv\Scripts\python.exe" run.py --fast
) else (
    ".venv\Scripts\python.exe" run.py %*
)
echo.
pause
exit /b 0

:fail
echo.
echo Setup failed. Scroll up for the error.
pause
exit /b 1
