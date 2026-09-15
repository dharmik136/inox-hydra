@echo off
title LinkedIn Studio Enterprise Launcher
cd /d "%~dp0"

echo =================================================================
echo   LinkedIn Studio Enterprise - Executive Desktop Launcher
echo   100%% Local Engine - Zero Cloud Egress - Port 8000
echo =================================================================
echo.

:: Check if server is already running on port 8000
powershell -Command "$tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue; if ($tcp) { exit 0 } else { exit 1 }"
if %ERRORLEVEL% EQU 0 (
    echo [*] LinkedIn Studio backend is already running on http://127.0.0.1:8000.
) else (
    echo [*] Starting LinkedIn Studio backend daemon...
    start /min "LinkedIn Studio Backend" python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000
    timeout /t 3 /nobreak > nul
)

:: Launch in Dedicated Chrome App Window (Borderless Native App Mode)
set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_PATH% set CHROME_PATH="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

if exist %CHROME_PATH% (
    echo [*] Launching LinkedIn Studio in Native Desktop Window...
    start "" %CHROME_PATH% --app="http://127.0.0.1:8000" --window-size=1440,920
) else (
    echo [*] Chrome not found at default location. Launching default browser...
    start http://127.0.0.1:8000
)

echo [*] Desktop session established.
exit /b 0
