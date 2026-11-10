@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0" || goto :failed

if not exist "scripts\compile_grammar.py" (
    echo [ERROR] scripts\compile_grammar.py was not found.
    goto :failed
)
if not exist "app.py" (
    echo [ERROR] app.py was not found.
    goto :failed
)

set "PY_CMD=python"
python -c "import sys" >nul 2>&1
if errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python 3 was not found. Install Python and enable PATH.
        goto :failed
    )
    set "PY_CMD=py -3"
)

if exist "venv" if not exist "venv\Scripts\python.exe" (
    echo [ERROR] The existing venv directory is not a Windows virtual environment.
    echo Rename the directory first, then run this script again.
    goto :failed
)

if not exist "venv\Scripts\python.exe" (
    echo Creating a Windows Python virtual environment...
    %PY_CMD% -m venv "venv"
    if errorlevel 1 goto :failed
)

"venv\Scripts\python.exe" -c "import fastapi, uvicorn, pydantic" >nul 2>&1
if errorlevel 1 (
    echo Installing required Python packages...
    "venv\Scripts\python.exe" -m pip install fastapi uvicorn pydantic
    if errorlevel 1 goto :failed
)

echo ==========================================
echo Compiling Julius grammar...
echo ==========================================
"venv\Scripts\python.exe" "scripts\compile_grammar.py"
if errorlevel 1 goto :failed

echo.
echo ==========================================
echo Starting FastAPI server...
echo Open http://localhost:8000 after the server starts.
echo Press Ctrl+C to stop the server.
echo ==========================================
"venv\Scripts\python.exe" -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
if errorlevel 1 goto :failed

goto :finished

:failed
echo.
echo [ERROR] The startup process failed. Check the message above.
pause
exit /b 1

:finished
echo.
echo Server stopped.
pause
exit /b 0
