@echo off
title LinkedIn Studio Enterprise Launcher
cd /d "%~dp0"

echo =================================================================
echo   LinkedIn Studio Enterprise - Executive Desktop Launcher
echo   Your work stays on this machine - Port 8000
echo =================================================================
echo.

:: Check if --tray argument is passed to launch background daemon
if /i "%~1"=="--tray" (
    echo [*] Starting Inox Hydra in System Tray Daemon mode...
    start "" pythonw "%~dp0studio_tray.py"
    echo [*] System Tray daemon active in background.
    exit /b 0
)
if /i "%~1"=="/tray" (
    echo [*] Starting Inox Hydra in System Tray Daemon mode...
    start "" pythonw "%~dp0studio_tray.py"
    echo [*] System Tray daemon active in background.
    exit /b 0
)

:: The interface is a build artifact, gitignored because it is reproducible,
:: and the server has no fallback page without it. A fresh clone that skipped
:: the build used to start cleanly and then answer 503 for every request, which
:: from a double-clicked launcher looks like the product itself is broken.
if not exist "%~dp0studio\frontend_next\index.html" (
    echo [*] The studio interface has not been built yet. Building it now.
    echo     This runs once per checkout and needs Node 22 or newer.
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [!] npm was not found on PATH.
        echo     Install Node 22+ from https://nodejs.org, then run this again.
        echo     Or build it yourself, from the repository root:
        echo         npm --prefix studio/ui ci
        echo         npm --prefix studio/ui run build
        pause
        exit /b 1
    )
    call npm --prefix "%~dp0studio\ui" ci
    call npm --prefix "%~dp0studio\ui" run build
    if not exist "%~dp0studio\frontend_next\index.html" (
        echo [!] The build finished but produced no interface. Not starting the
        echo     server, because it would only serve a 503. See the npm output above.
        pause
        exit /b 1
    )
    echo [*] Interface built.
)

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
