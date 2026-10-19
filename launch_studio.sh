#!/usr/bin/env bash
# =================================================================
#   Inox Hydra - Desktop Launcher (Linux / macOS)
#   Your work stays on this machine - Port 8000
# =================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================="
echo "  Inox Hydra - Desktop Launcher"
echo "  100% local. Zero cloud egress. Port 8000."
echo "================================================================="
echo ""

# Determine python command
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[!] Error: python3 is not installed or not in PATH."
    exit 1
fi

# Check for tray argument
if [ "$1" = "--tray" ] || [ "$1" = "-tray" ]; then
    echo "[*] Starting Inox Hydra in System Tray Daemon mode..."
    nohup "$PYTHON_CMD" "$SCRIPT_DIR/studio_tray.py" >/dev/null 2>&1 &
    echo "[*] System Tray daemon active in background."
    exit 0
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
    echo "[*] Inox Hydra backend is already running on http://127.0.0.1:8000."
else
    # The log goes to the app home's logs folder, the one the diagnostics
    # bundle reads and the desktop shell writes engine.log into. It was a fixed
    # file in /tmp: shared by every account on the machine, overwritten on each
    # launch, never collected, and on systems with protected_regular a second
    # user could not open it, so the backend never started at all.
    LOG_DIR="$("$PYTHON_CMD" -c 'from studio.backend.paths import get_logs_dir; print(get_logs_dir())' 2>/dev/null || true)"
    if [ -z "$LOG_DIR" ]; then
        if [ -n "$INOX_HYDRA_HOME" ]; then
            LOG_DIR="$INOX_HYDRA_HOME/logs"
        elif [ "$(uname)" = "Darwin" ]; then
            LOG_DIR="$HOME/Library/Application Support/InoxHydra/logs"
        else
            LOG_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/inox-hydra/logs"
        fi
    fi
    mkdir -p "$LOG_DIR"
    LOG_FILE="$LOG_DIR/engine.log"
    # Bounded as the desktop shell bounds it: the log explains the launch that
    # just failed, it is not an archive.
    if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE" | tr -d ' ')" -gt 2097152 ]; then
        rm -f "$LOG_FILE"
    fi
    echo "--- engine launch at unix time $(date +%s) ---" >> "$LOG_FILE"

    echo "[*] Starting Inox Hydra backend daemon. Log: $LOG_FILE"
    nohup "$PYTHON_CMD" -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000 >>"$LOG_FILE" 2>&1 &

    # Wait for it to answer before opening a window onto it, so a backend
    # that fails at startup is reported here rather than as a dead page.
    STARTED=0
    if command -v curl >/dev/null 2>&1; then
        for _ in $(seq 1 30); do
            if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
                STARTED=1
                break
            fi
            sleep 0.5
        done
    else
        sleep 2
        STARTED=1
    fi
    if [ "$STARTED" -ne 1 ]; then
        echo "[!] The backend did not start. Its output is in: $LOG_FILE"
        exit 1
    fi
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
    echo "[*] Launching Inox Hydra in Native Desktop Window ($BROWSER_BIN)..."
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
