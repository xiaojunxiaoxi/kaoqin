@echo off
chcp 65001 >nul
echo ????????...
echo.

:: Start Flask server in background
start /B python app.py

:: Wait for Flask to start
timeout /t 3 /nobreak >nul

:: Start localtunnel and capture URL
echo ??????????...
for /f "tokens=*" %%a in ('lt --port 5000 2^>nul') do set TUNNEL_URL=%%a

:: Show info
echo.
echo ========================================
echo   ???????
echo   ??????: %TUNNEL_URL%
echo   ??App??: ??[??] -> ?????
echo ========================================
echo.
echo ? ??? ?????
pause >nul

:: Cleanup
taskkill /f /im python.exe /fi "WINDOWTITLE eq app.py" >nul 2>nul
echo ??????
