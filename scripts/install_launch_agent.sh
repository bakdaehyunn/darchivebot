#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
BOT_PLIST="$LAUNCH_DIR/com.hennei.darchivebot.telegram.plist"
PROCESS_PLIST="$LAUNCH_DIR/com.hennei.darchivebot.processor.plist"

mkdir -p "$LAUNCH_DIR" "$ROOT/.local/logs"

cat > "$BOT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.hennei.darchivebot.telegram</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/darchive</string>
    <string>telegram</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$ROOT/.local/logs/telegram.launchd.out</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/.local/logs/telegram.launchd.err</string>
</dict>
</plist>
PLIST

cat > "$PROCESS_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.hennei.darchivebot.processor</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/darchive</string>
    <string>process</string>
    <string>--export-graph</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>StandardOutPath</key>
  <string>$ROOT/.local/logs/processor.launchd.out</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/.local/logs/processor.launchd.err</string>
</dict>
</plist>
PLIST

launchctl unload "$BOT_PLIST" 2>/dev/null || true
launchctl unload "$PROCESS_PLIST" 2>/dev/null || true
launchctl load "$BOT_PLIST"
launchctl load "$PROCESS_PLIST"
echo "installed $BOT_PLIST"
echo "installed $PROCESS_PLIST"
