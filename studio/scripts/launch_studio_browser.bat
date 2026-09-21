@echo off
setlocal
echo =========================================================
echo  LinkedIn Studio: 1-Click Browser Launcher with Extension
echo =========================================================
echo.

cd /d "%~dp0\.."
python -c "from studio.backend.browser_launcher import launch_browser_with_extension; res = launch_browser_with_extension(); print(res.get('message', res))"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Python launch failed. Trying direct browser fallback...
    set "EXT_DIR=%~dp0..\extension"
    if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
        start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" "--load-extension=%EXT_DIR%" "https://www.linkedin.com/feed/"
        echo Launched Google Chrome with LinkedIn Studio Bridge.
        goto :done
    )
    if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
        start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "--load-extension=%EXT_DIR%" "https://www.linkedin.com/feed/"
        echo Launched Microsoft Edge with LinkedIn Studio Bridge.
        goto :done
    )
    echo Could not locate Chrome or Edge executable.
)

:done
echo.
echo Complete. Enjoy browsing LinkedIn!
timeout /t 3 >nul
