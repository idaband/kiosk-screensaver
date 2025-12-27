#!/bin/bash
# Installation script for Kiosk Screensaver
# For Raspberry Pi 5 running Raspberry Pi OS (64-bit) Debian Trixie or newer
#
# PREREQUISITES:
# - Fresh Raspberry Pi OS (64-bit) installation
# - Currently configured to boot into Desktop with auto-login
# - This script will:
#   1. Install required dependencies (labwc, ddcutil, wlopm, chromium, etc.)
#   2. Switch boot mode from Desktop to CLI
#   3. Configure labwc Wayland compositor to auto-start
#   4. Set up Home Assistant dashboard in kiosk mode
#   5. Install and configure screensaver system
#
# RECOMMENDED HARDWARE:
# - Raspberry Pi 5 (8GB RAM recommended)
# - DDC/CI-compliant monitor for brightness control
#   (Most modern monitors support DDC/CI, but not all)
#
# INSTALLATION:
# 1. Transfer this folder to ~/kiosk-screensaver on your Pi
# 2. Fix line endings if transferring from Windows:
#    find ~/kiosk-screensaver -name "*.sh" -exec sed -i 's/\r$//' {} \;
# 3. Run this script:
#    cd ~/kiosk-screensaver
#    bash install.sh

set -e

# Get current user and home directory
CURRENT_USER="$USER"
USER_HOME="$HOME"
INSTALL_DIR="$USER_HOME/kiosk-screensaver"
CONFIG_TEMPLATE="$INSTALL_DIR/config.yaml.template"
CONFIG_FILE="$INSTALL_DIR/config.yaml"

echo "========================================================"
echo "   Kiosk Screensaver Installation Script"
echo "   For Raspberry Pi 5 + Raspberry Pi OS (64-bit)"
echo "========================================================"
echo
echo "Installation directory: $INSTALL_DIR"
echo "User: $CURRENT_USER"
echo "Home: $USER_HOME"
echo

# Confirmation prompt
read -p "This will modify your system configuration. Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 1
fi

# ==============================================================================
# STEP 1: Install system dependencies
# ==============================================================================
echo
echo "========================================================"
echo "STEP 1/10: Installing System Dependencies"
echo "========================================================"
echo
echo "This will install:"
echo "  - labwc (Wayland compositor)"
echo "  - ddcutil (monitor brightness control via DDC/CI)"
echo "  - wlopm (Wayland output power management)"
echo "  - chromium (web browser for dashboard and slideshow)"
echo "  - rclone (file serving)"
echo "  - python3 and pip"
echo

read -p "Install dependencies? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Updating package lists..."
    sudo apt-get update

    echo "Installing packages..."
    sudo apt-get install -y \
        labwc \
        ddcutil \
        chromium \
        rclone \
        python3 \
        python3-pip \
        procps \
        i2c-tools

    # Check if wlopm is installed
    if ! command -v wlopm &> /dev/null; then
        echo
        echo "⚠ wlopm not found in repositories"
        echo "  You may need to install it manually from:"
        echo "  https://git.sr.ht/~leon_plickat/wlopm"
        echo
        read -p "Continue without wlopm? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    echo "✓ System dependencies installed"
else
    echo "Skipping dependency installation"
fi

# ==============================================================================
# STEP 2: Verify dependencies
# ==============================================================================
echo
echo "========================================================"
echo "STEP 2/10: Verifying Dependencies"
echo "========================================================"
MISSING_DEPS=()
for cmd in python3 pip3 chromium ddcutil rclone pgrep pkill labwc; do
    if ! command -v $cmd &> /dev/null; then
        MISSING_DEPS+=($cmd)
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "✗ Error: Missing required commands: ${MISSING_DEPS[*]}"
    echo
    echo "Please install them manually and run this script again."
    exit 1
fi

echo "✓ All required dependencies found"

# ==============================================================================
# STEP 3: Configure boot mode (Desktop -> CLI)
# ==============================================================================
echo
echo "========================================================"
echo "STEP 3/10: Configuring Boot Mode"
echo "========================================================"
echo
echo "Your system is currently configured to boot into Desktop mode."
echo "For a kiosk setup, we need to:"
echo "  1. Switch to CLI (console) boot mode"
echo "  2. Keep auto-login enabled"
echo "  3. Configure labwc to start automatically"
echo
read -p "Switch boot mode to CLI? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Configuring boot to CLI with auto-login..."
    # Use raspi-config nonint to set boot mode
    # B2 = Console Autologin (text console, automatically logged in as current user)
    sudo raspi-config nonint do_boot_behaviour B2
    echo "✓ Boot mode set to CLI with auto-login"
else
    echo "⚠ Skipping boot mode configuration"
    echo "  Note: You may need to manually configure this for proper operation"
fi

# ==============================================================================
# STEP 4: Collect user configuration
# ==============================================================================
echo
echo "========================================================"
echo "STEP 4/10: Configuration Setup"
echo "========================================================"
echo

# Home Assistant URL
echo "--- Home Assistant Configuration ---"
echo
read -p "Do you want to enable Home Assistant integration? (Y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    HA_ENABLED="false"
    HA_URL=""
    echo "Home Assistant integration disabled"
else
    HA_ENABLED="true"
    echo "Enter your Home Assistant URL (including https:// and port)"
    echo "Example: https://192.168.1.100:8123"
    echo
    echo "IMPORTANT: Use your LOCAL network IP address, NOT DuckDNS or external URL"
    echo "The screensaver runs on the same local network as Home Assistant"
    read -p "HA URL: " HA_URL
    echo "✓ Home Assistant URL: $HA_URL"
fi

# Dashboard URL
echo
echo "--- Dashboard Configuration ---"
echo
echo "Enter your kiosk dashboard URL (this will open in Chromium kiosk mode)"
echo "This can be the same as your Home Assistant URL, or a different dashboard"
echo "Example: https://192.168.1.100:8123"
echo
echo "IMPORTANT: Use your LOCAL network IP address, NOT DuckDNS or external URL"
echo "External URLs may cause connectivity issues or slow loading"
read -p "Dashboard URL: " DASHBOARD_URL
echo "✓ Dashboard URL: $DASHBOARD_URL"

# Photo source path
echo
echo "--- Photo Source Configuration ---"
echo
echo "Enter the path to your photos folder"
echo "Examples:"
echo "  Local folder: /home/$CURRENT_USER/Pictures"
echo "  Network mount: /mnt/photos"
echo "  Windows share mount: /mnt/windows-photos"
echo
read -p "Photo path: " PHOTO_PATH

# Expand ~ to actual home directory
PHOTO_PATH="${PHOTO_PATH/#\~/$USER_HOME}"

if [ -d "$PHOTO_PATH" ]; then
    PHOTO_COUNT=$(find "$PHOTO_PATH" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.gif" \) 2>/dev/null | wc -l)
    echo "✓ Photo path exists: $PHOTO_PATH"
    echo "  Found approximately $PHOTO_COUNT photo files"
else
    echo "⚠ Warning: Photo path does not exist: $PHOTO_PATH"
    echo "  You can mount it later before starting the screensaver"
fi

# ==============================================================================
# STEP 5: Generate configuration file
# ==============================================================================
echo
echo "========================================================"
echo "STEP 5/10: Generating Configuration File"
echo "========================================================"

# Create config from template
if [ ! -f "$CONFIG_TEMPLATE" ]; then
    echo "✗ Error: Template file not found: $CONFIG_TEMPLATE"
    exit 1
fi

cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"

# Replace placeholders
sed -i "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$CONFIG_FILE"
sed -i "s|__PHOTO_PATH__|$PHOTO_PATH|g" "$CONFIG_FILE"
sed -i "s|__HA_ENABLED__|$HA_ENABLED|g" "$CONFIG_FILE"
sed -i "s|__HA_URL__|$HA_URL|g" "$CONFIG_FILE"
sed -i "s|__DASHBOARD_URL__|$DASHBOARD_URL|g" "$CONFIG_FILE"

echo "✓ Configuration file created: $CONFIG_FILE"

# ==============================================================================
# STEP 6: Install Python dependencies
# ==============================================================================
echo
echo "========================================================"
echo "STEP 6/10: Installing Python Dependencies"
echo "========================================================"
pip3 install --user --break-system-packages -r "$INSTALL_DIR/requirements.txt"
echo "✓ Python dependencies installed"

# ==============================================================================
# STEP 7: Configure user permissions
# ==============================================================================
echo
echo "========================================================"
echo "STEP 7/10: Configuring User Permissions"
echo "========================================================"

# Add user to input group for keyboard/mouse monitoring
if ! groups $CURRENT_USER | grep -q '\binput\b'; then
    echo "Adding $CURRENT_USER to 'input' group for device monitoring..."
    sudo usermod -a -G input $CURRENT_USER
    echo "✓ Added to input group (logout required to take effect)"
    NEED_LOGOUT=true
else
    echo "✓ User already in input group"
fi

# Add user to i2c group for DDC/CI monitor control
if ! groups $CURRENT_USER | grep -q '\bi2c\b'; then
    echo "Adding $CURRENT_USER to 'i2c' group for DDC/CI monitor control..."
    sudo usermod -a -G i2c $CURRENT_USER
    echo "✓ Added to i2c group (logout required to take effect)"
    NEED_LOGOUT=true
else
    echo "✓ User already in i2c group"
fi

# Configure sudo permissions for web interface reboot
echo "Configuring sudo permissions for reboot..."
echo "$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/reboot" | sudo tee /etc/sudoers.d/kiosk-screensaver > /dev/null
sudo chmod 0440 /etc/sudoers.d/kiosk-screensaver

# Validate sudoers syntax
if sudo visudo -c -f /etc/sudoers.d/kiosk-screensaver > /dev/null 2>&1; then
    echo "✓ Sudo permissions configured (web interface can trigger reboot)"
else
    echo "⚠ Warning: Sudoers file has syntax errors, removing it"
    sudo rm -f /etc/sudoers.d/kiosk-screensaver
fi

# ==============================================================================
# STEP 8: Install systemd services
# ==============================================================================
echo
echo "========================================================"
echo "STEP 8/10: Installing Systemd Services"
echo "========================================================"

# Create systemd service files with correct paths
cat > /tmp/screensaver.service <<EOF
[Unit]
Description=Kiosk Screensaver
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u $CURRENT_USER)
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 -m screensaver.main -c $INSTALL_DIR/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /tmp/screensaver-web.service <<EOF
[Unit]
Description=Kiosk Screensaver Web Admin
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 -m screensaver.web.app $INSTALL_DIR/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "This requires sudo password..."
sudo cp /tmp/screensaver.service /etc/systemd/system/
sudo cp /tmp/screensaver-web.service /etc/systemd/system/
sudo systemctl daemon-reload

rm /tmp/screensaver.service /tmp/screensaver-web.service

echo "✓ Systemd services installed"

# ==============================================================================
# STEP 9: Configure labwc autostart
# ==============================================================================
echo
echo "========================================================"
echo "STEP 9/10: Configuring Wayland Compositor Autostart"
echo "========================================================"

AUTOSTART_DIR="$USER_HOME/.config/labwc"
AUTOSTART_FILE="$AUTOSTART_DIR/autostart"

# Create labwc config directory if it doesn't exist
mkdir -p "$AUTOSTART_DIR"

# Create or update autostart file
if [ -f "$AUTOSTART_FILE" ]; then
    echo "Updating existing autostart file..."
    # Remove old screensaver entries if present
    sed -i '/screensaver.main/d' "$AUTOSTART_FILE"
    sed -i '/# Kiosk Screensaver/d' "$AUTOSTART_FILE"
    sed -i '/# Home Assistant Dashboard/d' "$AUTOSTART_FILE"
    sed -i '/chromium.*--kiosk/d' "$AUTOSTART_FILE"
else
    echo "Creating new autostart file..."
    touch "$AUTOSTART_FILE"
fi

# Add Home Assistant dashboard (starts first)
cat >> "$AUTOSTART_FILE" <<EOF

# Home Assistant Dashboard (Chromium Kiosk Mode)
chromium --kiosk --noerrdialogs --disable-infobars --no-first-run --check-for-update-interval=31536000 --password-store=basic --disable-features=WakeLockSensor,IdleDetection,MediaSession --use-gl=egl --enable-features=VaapiVideoDecoder,VaapiVideoEncoder --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy --ignore-certificate-errors $DASHBOARD_URL &

# Kiosk Screensaver (Python version)
cd $INSTALL_DIR && python3 -m screensaver.main -c $INSTALL_DIR/config.yaml &
EOF

echo "✓ labwc autostart configured"
echo "  Dashboard will launch first, then screensaver"

# Configure labwc to start on login (tty1 only)
echo
echo "Configuring labwc to start on login..."

# Check if already configured
if grep -q "exec labwc" "$USER_HOME/.bash_profile" 2>/dev/null; then
    echo "✓ labwc auto-start already configured in .bash_profile"
else
    cat >> "$USER_HOME/.bash_profile" <<'EOF'

# Start labwc Wayland compositor on login (tty1 only)
if [ -z "$WAYLAND_DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
  exec labwc
fi
EOF
    echo "✓ labwc will auto-start on console login"
fi

# ==============================================================================
# STEP 10: Enable and start web admin service
# ==============================================================================
echo
echo "========================================================"
echo "STEP 10/10: Configuring Web Admin Service"
echo "========================================================"

sudo systemctl enable screensaver-web.service 2>/dev/null && {
    echo "✓ Web admin service enabled (will start on boot)"
} || {
    echo "⚠ Failed to enable web admin service"
}

sudo systemctl start screensaver-web.service 2>/dev/null && {
    echo "✓ Web admin service started"
    WEB_PORT=$(grep "web_admin_port:" "$CONFIG_FILE" | awk '{print $2}')
    WEB_PORT=${WEB_PORT:-5000}
    echo "  Access at: http://$(hostname -I | awk '{print $1}'):$WEB_PORT"
} || {
    echo "⚠ Failed to start web admin service (check logs with: sudo journalctl -u screensaver-web)"
}

# ==============================================================================
# Installation Complete
# ==============================================================================
echo
echo "========================================================"
echo "   Installation Complete!"
echo "========================================================"
echo
echo "Your system has been configured as a kiosk screensaver."
echo
echo "CONFIGURATION SUMMARY:"
echo "  - Boot mode: CLI with auto-login"
echo "  - Dashboard URL: $DASHBOARD_URL"
if [ "$HA_ENABLED" = "true" ]; then
echo "  - Home Assistant: $HA_URL"
fi
echo "  - Photo path: $PHOTO_PATH"
echo "  - Install directory: $INSTALL_DIR"
echo
echo "NEXT STEPS:"
echo
if [ "$NEED_LOGOUT" = true ]; then
echo "1. IMPORTANT: Logout and login again for group permissions to take effect"
echo "   (input and i2c groups required for screensaver operation)"
echo
fi
echo "2. Reboot your system to activate CLI boot mode and start the kiosk"
echo "   sudo reboot"
echo
echo "3. After reboot, the system will:"
echo "   - Start in CLI mode with auto-login"
echo "   - Launch labwc Wayland compositor"
echo "   - Open Home Assistant dashboard in Chromium kiosk mode"
echo "   - Start the screensaver system in the background"
echo
echo "4. Configure Home Assistant integration (if enabled):"
echo "   - Create input_boolean.disable_screensaver in Home Assistant"
echo "   - Get long-lived access token from HA profile"
echo "   - Save token to ~/.ha_token"
echo
echo "5. Access web admin panel:"
WEB_PORT=$(grep "web_admin_port:" "$CONFIG_FILE" | awk '{print $2}')
WEB_PORT=${WEB_PORT:-5000}
echo "   http://$(hostname -I | awk '{print $1}'):$WEB_PORT"
echo "   Use it to:"
echo "   - Adjust timing settings (idle timeout, day/night mode times)"
echo "   - Configure photo slideshow interval"
echo "   - Set up scheduled reboots"
echo "   - Test Home Assistant connection"
echo "   - Manually trigger photo list regeneration"
echo
echo "6. DDC/CI Monitor Control (optional):"
echo "   - Most modern monitors support DDC/CI for brightness control"
echo "   - Test with: ddcutil detect"
echo "   - If your monitor is not detected, screensaver will still work"
echo "     but brightness control will be skipped"
echo
echo "MANUAL CONFIGURATION:"
echo "  - Edit config: nano $CONFIG_FILE"
echo "  - View logs: journalctl -u screensaver-web -f"
echo "  - Restart services: sudo systemctl restart screensaver-web"
echo
echo "========================================================"
echo
