#!/usr/bin/env bash
# =================================================================
#   LinkedIn Studio Enterprise - Desktop Launcher (Linux / macOS)
#   Your work stays on this machine - Port 8000
# =================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================="
echo "  LinkedIn Studio Enterprise - Desktop Launcher"
echo "  100% local. Zero cloud egress. Port 8000."
echo "================================================================="
echo ""

# Check for tray argument
if [ "$1" = "--tray" ] || [ "$1" = "-tray" ]; then
    echo "[*] Starting Inox Hydra in System Tray Daemon mode..."
    nohup python3 "$SCRIPT_DIR/studio_tray.py" >/dev/null 2>&1 &
    echo "[*] System Tray daemon active in background."
    exit 0
fi

# Determine python command
PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1; then
        PYTHON_CMD="python"
    else
        echo "[!] Error: python3 is not installed or not in PATH."
        exit 1
    fi
fi

# Check if studio interface has been built
if [ ! -f "$SCRIPT_DIR/studio/frontend_next/index.html" ]; then
    echo "[*] The studio interface has not been built yet."
    if command -v npm >/dev/null 2>&1; then
        echo "[*] Building interface via npm..."
        npm --prefix "$SCRIPT_DIR/studio/ui" ci
        npm --prefix "$SCRIPT_DIR/studio/ui" run build
        if [ ! -f "$SCRIPT_DIR/studio/frontend_next/index.html" ]; then
            echo "[!] Build completed but studio/frontend_next/index.html was not generated."
            exit 1
        fi
        echo "[*] Interface built successfully."
    else
        echo "[!] Warning: npm not found on PATH. If frontend files are missing, server will serve 503."
    fi
fi

# Check if server is already running on port 8000
SERVER_RUNNING=0
if command -v nc >/dev/null 2>&1; then
    if nc -z 127.0.0.1 8000 >/dev/null 2>&1; then
        SERVER_RUNNING=1
    fi
elif command -v curl >/dev/null 2>&1; then
    if curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        SERVER_RUNNING=1
    fi
fi

if [ "$SERVER_RUNNING" -eq 1 ]; then
    echo "[*] LinkedIn Studio backend is already running on http://127.0.0.1:8000."
else
    echo "[*] Starting LinkedIn Studio backend daemon..."
    nohup "$PYTHON_CMD" -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000 >/tmp/inox_studio_backend.log 2>&1 &
    sleep 2
fi

# Locate browser for native App Mode (borderless desktop window)
BROWSER_BIN=""
CANDIDATES=(
    "google-chrome"
    "google-chrome-stable"
    "chromium"
    "chromium-browser"
    "brave-browser"
    "brave"
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
)

for cand in "${CANDIDATES[@]}"; do
    if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then
        BROWSER_BIN="$cand"
        break
    fi
done

if [ -n "$BROWSER_BIN" ]; then
    echo "[*] Launching LinkedIn Studio in Native Desktop Window ($BROWSER_BIN)..."
    nohup "$BROWSER_BIN" --app="http://127.0.0.1:8000" --window-size=1440,920 >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
    echo "[*] Chrome not found. Opening via xdg-open..."
    xdg-open "http://127.0.0.1:8000" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    echo "[*] Chrome not found. Opening via open (macOS)..."
    open "http://127.0.0.1:8000" >/dev/null 2>&1 &
else
    echo "[*] Studio is running at: http://127.0.0.1:8000"
fi

echo "[*] Desktop session established."
exit 0
