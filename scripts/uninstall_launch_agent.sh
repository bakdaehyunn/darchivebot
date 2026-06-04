#!/usr/bin/env bash
set -euo pipefail

LAUNCH_DIR="$HOME/Library/LaunchAgents"
BOT_PLIST="$LAUNCH_DIR/com.hennei.darchivebot.telegram.plist"
PROCESS_PLIST="$LAUNCH_DIR/com.hennei.darchivebot.processor.plist"

launchctl unload "$BOT_PLIST" 2>/dev/null || true
launchctl unload "$PROCESS_PLIST" 2>/dev/null || true
rm -f "$BOT_PLIST" "$PROCESS_PLIST"
echo "uninstalled darchivebot launch agents"
