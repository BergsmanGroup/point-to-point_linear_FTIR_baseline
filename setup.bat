@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv ".venv"
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -c "import tkinter, matplotlib, numpy; print('Setup complete. Run run_gui.bat to start.')"
if errorlevel 1 goto :failed
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.10 or newer with Tcl/Tk support and check the error above.
pause
exit /b 1
