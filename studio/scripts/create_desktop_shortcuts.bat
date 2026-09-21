@echo off
setlocal
echo ==========================================================
echo  LinkedIn Studio: Create Desktop Shortcuts for All Browsers
echo ==========================================================
echo.

cd /d "%~dp0\.."
python -c "from studio.backend.browser_launcher import create_desktop_shortcuts; sc = create_desktop_shortcuts(); print(f'Created {len(sc)} desktop shortcuts:'); [print(' -', s.get('shortcut_path')) for s in sc if s.get('status') == 'created']"

echo.
echo Check your Desktop for "LinkedIn Studio (Browser).lnk" icons!
timeout /t 4 >nul
