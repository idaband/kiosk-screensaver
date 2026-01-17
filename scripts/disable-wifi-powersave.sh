#!/bin/bash
# Disable WiFi Power Save to prevent network dropouts
# Run this script to disable WiFi power management on Raspberry Pi

set -e

echo "=========================================="
echo "  Disable WiFi Power Save"
echo "=========================================="
echo
echo "This script will:"
echo "1. Install 'iw' package if not present"
echo "2. Disable WiFi power save immediately"
echo "3. Create systemd service to disable on boot"
echo

# Check if running as root
if [ "$EUID" -eq 0 ]; then
   echo "⚠ Please do not run as root. Run as regular user with sudo access."
   exit 1
fi

# Install iw if not present
if ! command -v iw &> /dev/null; then
    echo "Installing 'iw' package..."
    sudo apt-get update
    sudo apt-get install -y iw
    echo "✓ iw package installed"
else
    echo "✓ iw package already installed"
fi

# Disable WiFi power save immediately
echo
echo "Disabling WiFi power save now..."
sudo iw dev wlan0 set power_save off 2>/dev/null && {
    echo "✓ WiFi power save disabled"
} || {
    echo "⚠ Could not disable WiFi power save (may not be using WiFi)"
    echo "  Attempting with iwconfig..."
    sudo iwconfig wlan0 power off 2>/dev/null && {
        echo "✓ WiFi power save disabled (iwconfig)"
    } || {
        echo "✗ Failed to disable WiFi power save"
        exit 1
    }
}

# Create systemd service for persistence
echo
echo "Creating systemd service for boot-time WiFi power save disable..."

WIFI_SERVICE_FILE="/etc/systemd/system/disable-wifi-powersave.service"

sudo tee "$WIFI_SERVICE_FILE" > /dev/null <<'EOF'
[Unit]
Description=Disable WiFi Power Save
After=network.target
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
# Disable power management on wlan0
ExecStart=/usr/sbin/iw dev wlan0 set power_save off
# If iw fails, try iwconfig
ExecStart=-/usr/sbin/iwconfig wlan0 power off

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable disable-wifi-powersave.service 2>/dev/null && {
    echo "✓ WiFi power save disable service enabled (will run on boot)"
} || {
    echo "⚠ Failed to enable service"
    exit 1
}

# Verify current status
echo
echo "=========================================="
echo "  Verification"
echo "=========================================="
echo
echo "Checking WiFi interface status:"
ip link show wlan0 | grep -i "state"

echo
echo "Checking if WiFi power management is disabled:"
if iw dev wlan0 get power_save 2>/dev/null | grep -q "off"; then
    echo "✓ WiFi power save is OFF"
elif iwconfig wlan0 2>&1 | grep -i "power management" | grep -q "off"; then
    echo "✓ WiFi power save is OFF (iwconfig)"
else
    echo "⚠ Could not verify power save status"
    echo "  Run manually: iw dev wlan0 get power_save"
fi

echo
echo "=========================================="
echo "✓ WiFi Power Save Disabled Successfully"
echo "=========================================="
echo
echo "This will prevent network dropouts during:"
echo "  - Wake from screensaver"
echo "  - High CPU/GPU load (photo transitions)"
echo "  - Extended idle periods"
echo
echo "The setting will persist across reboots."
