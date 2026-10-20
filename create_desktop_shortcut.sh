#!/usr/bin/env bash
# =================================================================
#   Creates a Desktop shortcut and Application Launcher for Linux
#   Strict Invariants: Zero em-dashes.
# =================================================================

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The portable folder has InoxHydra.sh; a source checkout has launch_studio.sh.
# Only the second was looked for, so in the portable folder, where this script
# also ships, it always stopped with "Could not find launch_studio.sh".
LAUNCHER=""
for CANDIDATE in "$INSTALL_DIR/InoxHydra.sh" "$INSTALL_DIR/launch_studio.sh"; do
    if [ -f "$CANDIDATE" ]; then
        LAUNCHER="$CANDIDATE"
        break
    fi
done

if [ -z "$LAUNCHER" ]; then
    echo "[!] Could not find InoxHydra.sh or launch_studio.sh next to this script."
    echo "    Looked in: $INSTALL_DIR"
    exit 1
fi

chmod +x "$LAUNCHER"

ICON=""
for CANDIDATE in "$INSTALL_DIR/assets/inox_hydra.png" \
                 "$INSTALL_DIR/studio/extension/icons/icon-128.png" \
                 "$INSTALL_DIR/extension/icons/icon-128.png" \
                 "$INSTALL_DIR/desktop/src-tauri/icons/icon.png"; do
    if [ -f "$CANDIDATE" ]; then
        ICON="$CANDIDATE"
        break
    fi
done

# Detect platform
OS_NAME="$(uname -s)"

if [ "$OS_NAME" = "Linux" ]; then
    APPS_DIR="$HOME/.local/share/applications"
    DESKTOP_DIR="$HOME/Desktop"

    mkdir -p "$APPS_DIR"

    # Exec splits on spaces, so the launcher path is quoted as the Desktop
    # Entry spec requires: inside the quotes a double quote, backtick, dollar
    # sign or backslash takes a backslash, every backslash is then doubled
    # once more, and % is doubled.
    EXEC_ARG="$(printf '%s' "$LAUNCHER" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g' -e 's/%/%%/g')"

    SHORTCUT_CONTENT="[Desktop Entry]
Name=Inox Hydra
Comment=Local privacy-first creator engine and analytics studio
Exec=\"$EXEC_ARG\"
Icon=$ICON
Terminal=false
Type=Application
Categories=Development;Office;Network;
StartupWMClass=inox-hydra
"

    # Install to application menu
    APP_ENTRY="$APPS_DIR/inox-hydra.desktop"
    printf '%s\n' "$SHORTCUT_CONTENT" > "$APP_ENTRY"
    chmod +x "$APP_ENTRY"

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" 2>/dev/null || true
    fi

    echo "[*] Application menu entry created at: $APP_ENTRY"

    # Install to Desktop if directory exists
    if [ -d "$DESKTOP_DIR" ]; then
        DESKTOP_ENTRY="$DESKTOP_DIR/inox-hydra.desktop"
        printf '%s\n' "$SHORTCUT_CONTENT" > "$DESKTOP_ENTRY"
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
    mkdir -p "$DESKTOP_DIR"
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
