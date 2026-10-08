#!/bin/sh
# Installs the desktop launcher + icon for the current user and checks
# for the FreeBSD packages the app needs.
set -e

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APPS_DIR="$HOME/.local/share/applications"

mkdir -p "$ICON_DIR" "$APPS_DIR"
cp "$REPO_DIR/data/icons/claude-console-gui.svg" "$ICON_DIR/io.josiahwelch.ClaudeConsoleGui.svg"
sed "s|^Exec=.*|Exec=$REPO_DIR/claude-console-gui|; s|^Icon=.*|Icon=io.josiahwelch.ClaudeConsoleGui|" \
  "$REPO_DIR/data/io.josiahwelch.ClaudeConsoleGui.desktop" \
  > "$APPS_DIR/io.josiahwelch.ClaudeConsoleGui.desktop"

command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" || true

echo "Installed launcher and icon for the current user."

missing=""
for pkg in libadwaita py312-pygobject adwaita-icon-theme; do
  pkg info -e "$pkg" >/dev/null 2>&1 || missing="$missing $pkg"
done

if [ -n "$missing" ]; then
  echo
  echo "Missing FreeBSD packages:$missing"
  echo "Run: sudo pkg install$missing"
else
  echo "All required packages are installed."
fi

if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  echo
  echo "Claude Code (the claude command) isn't installed. On FreeBSD:"
  echo "  sudo sysrc linux_enable=YES && sudo service linux start"
  echo "  sudo pkg install claude-code"
  echo "Then run 'claude' once in a terminal to sign in."
fi
