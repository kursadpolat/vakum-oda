#!/bin/bash
# Mac (asil lider) LaunchAgent kurulumu: oturum acilinca baslar, cokerse yeniden baslar (KeepAlive).
# Calistir: bash kurulum/mac-kur.sh
set -euo pipefail
KOK="$(cd "$(dirname "$0")/.." && pwd)"
ETIKET="com.vakumoda.sunucu"
PLIST="$HOME/Library/LaunchAgents/$ETIKET.plist"
PY="$KOK/.venv/bin/python"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIKET</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-u</string><string>$KOK/sunucu.py</string></array>
  <key>WorkingDirectory</key><string>$KOK</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$KOK/.gizli/sunucu.log</string>
  <key>StandardErrorPath</key><string>$KOK/.gizli/sunucu.log</string>
</dict>
</plist>
PL
launchctl bootout "gui/$(id -u)/$ETIKET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "kuruldu: $PLIST"
