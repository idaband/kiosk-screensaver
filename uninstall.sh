#!/bin/bash
# Safe screensaver uninstall - only removes screensaver components
# Preserves user's existing labwc autostart and system configuration

echo "=========================================="
echo "Screensaver Safe Uninstall"
echo "=========================================="
echo ""

# 1. Kill screensaver processes (not dashboard chromium)
echo "[1/5] Stopping screensaver processes..."
pkill -f screensaver.main 2>/dev/null || true
pkill -f chromium.*slideshow.html 2>/dev/null || true
pkill -f chromium.*screensaver.html 2>/dev/null || true

# 2. Remove screensaver from labwc autostart
echo "[2/5] Removing screensaver from autostart..."
if [ -f ~/.config/labwc/autostart ]; then
    sed -i '/# Kiosk Screensaver/d' ~/.config/labwc/autostart
    sed -i '/screensaver.main/d' ~/.config/labwc/autostart
    echo "✓ Screensaver entries removed from autostart"
else
    echo "  No autostart file found"
fi

# 3. Remove screensaver installation directory
echo "[3/5] Removing screensaver installation..."
rm -rf ~/kiosk-screensaver

# 4. Remove screensaver data files
echo "[4/5] Removing screensaver data files..."
rm -f ~/photo-list.json
rm -f ~/.ha_token
rm -f ~/kiosk-screensaver.log
rm -f ~/screensaver-startup.log

# 5. Clean up screensaver temp directories
echo "[5/5] Cleaning temporary files..."
rm -rf /tmp/chromium-slideshow
rm -rf /tmp/chromium-screensaver-night

echo ""
echo "=========================================="
echo "Screensaver uninstall complete!"
echo "=========================================="
echo ""
echo "Your system's existing configuration has been preserved."
echo "Dashboard autostart and other settings remain unchanged."
echo ""
echo "To install fresh screensaver:"
echo "  1. Transfer kiosk-screensaver folder to ~/kiosk-screensaver"
echo "  2. Fix line endings: find ~/kiosk-screensaver -name \"*.sh\" -exec sed -i 's/\r$//' {} \;"
echo "  3. Edit config: nano ~/kiosk-screensaver/config.yaml"
echo "  4. Run: cd ~/kiosk-screensaver && bash install.sh"
echo ""
