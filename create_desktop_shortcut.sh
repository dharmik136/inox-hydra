#!/usr/bin/env bash
# =================================================================
#   Creates a Desktop shortcut and Application Launcher for Linux
#   Strict Invariants: Zero em-dashes.
# =================================================================

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$INSTALL_DIR/launch_studio.sh"
ICON="$INSTALL_DIR/studio/extension/icons/icon-128.png"

if [ ! -f "$LAUNCHER" ]; then
    echo "[!] Could not find launch_studio.sh next to this script."
    echo "    Expected at: $LAUNCHER"
    exit 1
fi

chmod +x "$LAUNCHER"

if [ ! -f "$ICON" ]; then
    if [ -f "$INSTALL_DIR/desktop/src-tauri/icons/icon.png" ]; then
        ICON="$INSTALL_DIR/desktop/src-tauri/icons/icon.png"
    fi
fi

# Detect platform
OS_NAME="$(uname -s)"

if [ "$OS_NAME" = "Linux" ]; then
    APPS_DIR="$HOME/.local/share/applications"
    DESKTOP_DIR="$HOME/Desktop"

    mkdir -p "$APPS_DIR"

    SHORTCUT_CONTENT="[Desktop Entry]
Name=Inox Hydra (LinkedIn Studio)
Comment=Local privacy-first creator engine and analytics studio
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Type=Application
Categories=Development;Office;Network;
StartupWMClass=inox-hydra
"

    # Install to application menu
    APP_ENTRY="$APPS_DIR/inox-hydra.desktop"
    echo "$SHORTCUT_CONTENT" > "$APP_ENTRY"
    chmod +x "$APP_ENTRY"

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" 2>/dev/null || true
    fi

    echo "[*] Application menu entry created at: $APP_ENTRY"

    # Install to Desktop if directory exists
    if [ -d "$DESKTOP_DIR" ]; then
        DESKTOP_ENTRY="$DESKTOP_DIR/inox-hydra.desktop"
        echo "$SHORTCUT_CONTENT" > "$DESKTOP_ENTRY"
        chmod +x "$DESKTOP_ENTRY"
        # On Ubuntu / Mint, trust desktop file
        if command -v gio >/dev/null 2>&1; then
            gio set "$DESKTOP_ENTRY" metadata::trusted true 2>/dev/null || true
        fi
        echo "[*] Desktop shortcut created at: $DESKTOP_ENTRY"
    fi

    echo "[+] Linux desktop integration complete."
elif [ "$OS_NAME" = "Darwin" ]; then
    # macOS
    DESKTOP_DIR="$HOME/Desktop"
    SHORTCUT="$DESKTOP_DIR/Inox Hydra.command"
    cat << EOF > "$SHORTCUT"
#!/bin/bash
exec "$LAUNCHER"
EOF
    chmod +x "$SHORTCUT"
    echo "[*] macOS desktop shortcut created at: $SHORTCUT"
else
    echo "[!] Unsupported OS for shortcut creation: $OS_NAME"
    exit 1
fi

exit 0
