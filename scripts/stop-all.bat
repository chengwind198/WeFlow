@echo off
set "SCRIPT_DIR=%~dp0"
echo.
echo   ==========================================
echo     Stop All weflow Services
echo   ==========================================
echo.
echo ^>^>^> Stopping backend...
call "%SCRIPT_DIR%stop-backend.bat"
echo.
echo ^>^>^> Stopping frontend...
call "%SCRIPT_DIR%stop-frontend.bat"
echo.
echo   ==========================================
echo     All services stopped
echo     Restart: scripts\start-all.bat
echo   ==========================================
echo.