@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No virtual environment found. Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" ftir_gui.py %*
if errorlevel 1 (
    echo The application exited with an error. See the message above.
    pause
    exit /b 1
)
