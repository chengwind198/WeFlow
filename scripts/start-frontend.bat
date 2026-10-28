@echo off
setlocal enabledelayedexpansion

set PORT=5173
set "PROJECT_ROOT=%~dp0.."

echo ==============================================
echo   weflow - Start Frontend  (Ctrl+C to stop)
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
        echo   PID %%a is zombie - skipping
    )
)

cd /d "%PROJECT_ROOT%\frontend"
if not exist node_modules\ (
    echo   Installing dependencies...
    call npm install
)
echo   Starting Vite on http://127.0.0.1:%PORT%
echo ==============================================
echo.
start http://127.0.0.1:%PORT%
npx vite --host 127.0.0.1 --port %PORT%
