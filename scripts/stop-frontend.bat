@echo off
setlocal enabledelayedexpansion

set PORT=5173
set "PROJECT_ROOT=%~dp0.."
set "PID_FILE=%PROJECT_ROOT%\logs\frontend.pid"

echo ==============================================
echo   Stop Frontend
echo ==============================================

if exist "%PID_FILE%" (
    set /p SAVED_PID=<"%PID_FILE%"
    if defined SAVED_PID (
        echo [1] Killing PID=!SAVED_PID! from PID file...
        taskkill /PID !SAVED_PID! /F >nul 2>&1 && echo   Killed || echo   Process not found
        del "%PID_FILE%" >nul 2>&1
    )
)

echo [2] Check port %PORT% ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo   Port %PORT% occupied by PID=%%a, killing...
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 (echo   Killed PID=%%a) else (echo   Kill failed, may be zombie)
    goto :done
)
echo   Port %PORT% free

:done
echo   Frontend stopped
echo ==============================================