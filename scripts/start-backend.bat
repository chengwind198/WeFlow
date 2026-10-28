@echo off
setlocal enabledelayedexpansion

set PORT=8000
set "PROJECT_ROOT=%~dp0.."

echo ==============================================
echo   weflow - Start Backend  (Ctrl+C to stop)
echo ==============================================

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo   Port %PORT% occupied by PID=%%a

    tasklist /FI "PID eq %%a" 2>nul | findstr "%%a" >nul
    if !errorlevel! equ 0 (
        echo   Killing process %%a ...
        taskkill /PID %%a /F >nul 2>&1
        if !errorlevel! equ 0 (
            echo   Killed PID=%%a
        ) else (
            echo   Kill failed - may need Administrator
            exit /b 1
        )
        timeout /t 2 /nobreak >nul
    ) else (
        echo   PID %%a is zombie ^(process gone, TCP entry remains^)
        echo   Windows will clean it up in 2-4 minutes
        echo   Trying to start anyway ...
    )
)

echo   Starting uvicorn on http://127.0.0.1:%PORT%
echo   API docs: http://127.0.0.1:%PORT%/docs
echo ==============================================
echo.
cd /d "%PROJECT_ROOT%\backend"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port %PORT%
