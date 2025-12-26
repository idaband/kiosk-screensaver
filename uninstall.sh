#!/bin/bash
# Safe screensaver uninstall - only removes screensaver components
# Preserves user's existing labwc autostart and system configuration

echo "=========================================="
echo "Screensaver Safe Uninstall"
echo "=========================================="
echo ""

# 1. Stop and disable screensaver services
echo "[1/7] Stopping screensaver services..."
sudo systemctl stop screensaver.service 2>/dev/null || true
sudo systemctl stop screensaver-web.service 2>/dev/null || true
sudo systemctl disable screensaver.service 2>/dev/null || true
sudo systemctl disable screensaver-web.service 2>/dev/null || true

# 2. Remove only screensaver service files
echo "[2/7] Removing screensaver service files..."
sudo rm -f /etc/systemd/system/screensaver.service
sudo rm -f /etc/systemd/system/screensaver-web.service
sudo systemctl daemon-reload

# 3. Remove screensaver sudoers file
echo "[3/7] Removing screensaver sudoers configuration..."
sudo rm -f /etc/sudoers.d/kiosk-screensaver

# 4. Kill screensaver processes only (not dashboard chromium)
echo "[4/7] Stopping screensaver processes..."
pkill -f screensaver.main 2>/dev/null || true
pkill -f chromium.*slideshow.html 2>/dev/null || true
pkill -f chromium.*screensaver.html 2>/dev/null || true

# 5. Remove screensaver installation directory
echo "[5/7] Removing screensaver installation..."
rm -rf ~/kiosk-screensaver

# 6. Remove screensaver data files (not user config)
echo "[6/7] Removing screensaver data files..."
rm -f ~/photo-list.json
rm -f ~/.ha_token

# 7. Clean up screensaver temp directories
echo "[7/7] Cleaning temporary files..."
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
