@echo off
set "SCRIPT_DIR=%~dp0"
echo.
echo   ==========================================
echo     weflow - Start All Services
echo   ==========================================
echo.
echo ^>^>^> Starting backend...
call "%SCRIPT_DIR%start-backend.bat"
echo.
echo ^>^>^> Starting frontend...
call "%SCRIPT_DIR%start-frontend.bat"
echo.
echo   ==========================================
echo     All services started
echo.
echo     Frontend : http://127.0.0.1:5173
echo     Backend  : http://127.0.0.1:8000
echo     API docs : http://127.0.0.1:8000/docs
echo     Logs     : logs\
echo     Stop     : scripts\stop-all.bat
echo   ==========================================
echo.