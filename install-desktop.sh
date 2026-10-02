#!/bin/bash
set -euo pipefail

if [[ "$EUID" -eq 0 ]]; then
    echo "Run this installer as the desktop user, not with sudo." >&2
    exit 1
fi

CURRENT_USER=$(id -un)
CURRENT_UID=$(id -u)
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)
INSTALL_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CONFIG_FILE="$INSTALL_DIR/config.yaml"
CONFIG_TEMPLATE="$INSTALL_DIR/config.yaml.template"
LABWC_DIR="$USER_HOME/.config/labwc"
AUTOSTART_FILE="$LABWC_DIR/autostart"
SHUTDOWN_FILE="$LABWC_DIR/shutdown"
USER_UNIT_DIR="$USER_HOME/.config/systemd/user"
SYSTEM_WEB_UNIT="/etc/systemd/system/screensaver-web.service"
AUTOSTART_BEGIN="# BEGIN kiosk-screensaver desktop session"
AUTOSTART_END="# END kiosk-screensaver desktop session"
SHUTDOWN_BEGIN="# BEGIN kiosk-screensaver desktop shutdown"
SHUTDOWN_END="# END kiosk-screensaver desktop shutdown"

if ! command -v labwc >/dev/null 2>&1; then
    echo "labwc is required for the desktop installer. Install/start the Raspberry Pi Wayland desktop first." >&2
    exit 1
fi

if ! pgrep -u "$CURRENT_UID" -x labwc >/dev/null 2>&1; then
    echo "No running labwc session was found for $CURRENT_USER. Start the desktop session, then rerun this installer." >&2
    exit 1
fi

if [[ -f "$AUTOSTART_FILE" ]] && ! grep -qF "$AUTOSTART_BEGIN" "$AUTOSTART_FILE"; then
    active_launches=$(grep -E '^[[:space:]]*[^#[:space:]].*(screensaver\.main|--kiosk)' "$AUTOSTART_FILE" || true)
    if [[ -n "$active_launches" ]]; then
        echo "Active Chromium kiosk/screensaver launch commands already exist in $AUTOSTART_FILE:" >&2
        printf '%s\n' "$active_launches" >&2
        echo "Back up and comment out the old dashboard and screensaver launch commands, then rerun this installer." >&2
        echo "No files have been changed." >&2
        exit 1
    fi
fi

printf '%s\n' "Kiosk Screensaver Desktop Installer" "Install directory: $INSTALL_DIR" "Desktop user: $CURRENT_USER" ""
read -r -p "Install desktop-session services without changing boot mode? (Y/n): " answer
if [[ "$answer" =~ ^[Nn]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    if [[ ! -f "$CONFIG_TEMPLATE" ]]; then
        echo "Config template not found: $CONFIG_TEMPLATE" >&2
        exit 1
    fi
    cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"
    read -r -p "Dashboard URL: " dashboard_url
    read -r -p "Photo source path: " photo_path
    python3 - "$CONFIG_FILE" "$INSTALL_DIR" "$dashboard_url" "$photo_path" <<'PY'
import os
import sys
import yaml

config_path, install_dir, dashboard_url, photo_path = sys.argv[1:]
with open(config_path, 'r') as config_file:
    data = yaml.safe_load(config_file)
data['paths']['slideshow_html'] = os.path.join(install_dir, 'static', 'slideshow.html')
data['paths']['screensaver_html'] = os.path.join(install_dir, 'static', 'screensaver.html')
data['network']['photo_source_path'] = os.path.expanduser(photo_path)
data['display']['dashboard_url'] = dashboard_url.strip()
data['display']['dashboard_scale'] = 1.0
data['display']['night_mode_monitor_off'] = False
data['network']['home_assistant']['enabled'] = False
data['network']['home_assistant']['url'] = ''
with open(config_path, 'w') as config_file:
    yaml.safe_dump(data, config_file, sort_keys=False)
PY
    echo "Created a new config with monitor power-off disabled for desktop mode."
else
    echo "Existing config found; preserving it."
    if grep -q 'night_mode_monitor_off: true' "$CONFIG_FILE"; then
        echo "Night mode currently powers off the output. This can disrupt desktop touch/output mapping."
        read -r -p "Set night_mode_monitor_off to false for this desktop setup? (Y/n): " answer
        if [[ ! "$answer" =~ ^[Nn]$ ]]; then
            python3 - "$CONFIG_FILE" <<'PY'
import sys
import yaml

config_path = sys.argv[1]
with open(config_path, 'r') as config_file:
    data = yaml.safe_load(config_file)
data.setdefault('display', {})['night_mode_monitor_off'] = False
with open(config_path, 'w') as config_file:
    yaml.safe_dump(data, config_file, sort_keys=False)
PY
            echo "Disabled night-mode output power-off in config.yaml."
        fi
    fi
fi

read -r -p "Install missing desktop dependencies now? (Y/n): " answer
if [[ ! "$answer" =~ ^[Nn]$ ]]; then
    sudo apt-get update
    packages=(labwc ddcutil rclone iw python3 python3-pip procps i2c-tools unclutter)
    if apt-cache show wlopm >/dev/null 2>&1; then
        packages+=(wlopm)
    fi
    sudo apt-get install -y "${packages[@]}"

    if [[ "$(dpkg-query -W -f='${db:Status-Status}' chromium 2>/dev/null || true)" != "installed" ]]; then
        mapfile -t held_packages < <(
            apt-mark showhold | grep -E '^(chromium|chromium-common|chromium-sandbox)$' || true
        )
        if (( ${#held_packages[@]} > 0 )); then
            sudo apt-mark unhold "${held_packages[@]}"
        fi
        sudo apt-get install -y chromium
    fi
fi

for command_name in python3 pip3 chromium rclone pgrep pkill labwc; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command not found: $command_name" >&2
        exit 1
    fi
done

pip3 install --user --break-system-packages -r "$INSTALL_DIR/requirements.txt"
PYTHONPATH="$INSTALL_DIR" python3 -m screensaver.main --validate -c "$CONFIG_FILE"

if ! id -nG "$CURRENT_USER" | tr ' ' '\n' | grep -qx input; then
    sudo usermod -a -G input "$CURRENT_USER"
    echo "Added $CURRENT_USER to the input group; log out and back in before testing touch wake."
fi
if ! id -nG "$CURRENT_USER" | tr ' ' '\n' | grep -qx i2c; then
    sudo usermod -a -G i2c "$CURRENT_USER"
    echo "Added $CURRENT_USER to the i2c group; log out and back in for DDC brightness control."
fi

web_port=$(PYTHONPATH="$INSTALL_DIR" python3 - "$CONFIG_FILE" <<'PY'
import sys
from screensaver.config import load_config
print(load_config(sys.argv[1]).get('network', 'web_admin_port', default=5000))
PY
)
if [[ ! "$web_port" =~ ^[0-9]+$ ]] || (( web_port < 1 || web_port > 65535 )); then
    echo "Invalid web_admin_port in $CONFIG_FILE: $web_port" >&2
    exit 1
fi

if [[ -f "$SYSTEM_WEB_UNIT" ]] && ! grep -qF "$INSTALL_DIR" "$SYSTEM_WEB_UNIT"; then
    sudo cp -a "$SYSTEM_WEB_UNIT" "$SYSTEM_WEB_UNIT.bak.$(date +%Y%m%d%H%M%S)"
fi
sudo tee "$SYSTEM_WEB_UNIT" >/dev/null <<EOF
[Unit]
Description=Kiosk Screensaver Web Admin
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=/usr/bin/python3 -m screensaver.web.app $CONFIG_FILE
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable screensaver-web.service
if systemctl is-active --quiet screensaver-web.service; then
    sudo systemctl restart screensaver-web.service
else
    sudo systemctl start screensaver-web.service
fi

if systemctl is-active --quiet screensaver.service || systemctl is-enabled --quiet screensaver.service; then
    echo "screensaver.service is active or enabled and could duplicate the desktop manager." >&2
    echo "Disable that system-level service manually, then rerun this installer." >&2
    exit 1
fi

if systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user stop kiosk-dashboard.service kiosk-screensaver-manager.service 2>/dev/null || true
fi
if pgrep -u "$CURRENT_UID" -f '[p]ython3 -m screensaver\.main' >/dev/null 2>&1; then
    echo "A screensaver manager is still running outside this install's user service." >&2
    echo "Stop it before rerunning to prevent duplicate input monitors." >&2
    exit 1
fi

mkdir -p "$USER_UNIT_DIR" "$LABWC_DIR"
cat > "$USER_UNIT_DIR/kiosk-screensaver-manager.service" <<EOF
[Unit]
Description=Kiosk Screensaver Manager (desktop session)
After=default.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=/usr/bin/python3 -m screensaver.main -c $CONFIG_FILE
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

cat > "$USER_UNIT_DIR/kiosk-dashboard.service" <<EOF
[Unit]
Description=Kiosk Dashboard (desktop session)
After=default.target

[Service]
Type=simple
Environment=LIBVA_DRIVER_NAME=v3d_video
ExecStart=/usr/bin/chromium --new-window --kiosk --user-data-dir=%h/.config/kiosk-screensaver-dashboard --ozone-platform=wayland --touch-events=enabled --noerrdialogs --disable-infobars --no-first-run --password-store=basic --disable-features=WakeLockSensor,IdleDetection,MediaSession --use-gl=egl --enable-features=VaapiVideoDecoder,VaapiVideoEncoder --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy --app=http://127.0.0.1:$web_port/dashboard
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

install_managed_block() {
    local file_path="$1" begin_marker="$2" end_marker="$3" block="$4"
    local temporary_file
    temporary_file=$(mktemp)
    if [[ -f "$file_path" ]]; then
        if ! awk -v begin="$begin_marker" -v end="$end_marker" '
            $0 == begin { if (inside) exit 2; inside=1; starts++; next }
            $0 == end { if (!inside) exit 3; inside=0; ends++; next }
            !inside { print }
            END { if (inside || starts != ends || starts > 1) exit 4 }
        ' "$file_path" > "$temporary_file"; then
            rm -f "$temporary_file"
            echo "Malformed managed block in $file_path; leaving it untouched." >&2
            return 1
        fi
        chmod --reference="$file_path" "$temporary_file"
    else
        : > "$temporary_file"
    fi
    printf '%s\n%s\n%s\n' "$begin_marker" "$block" "$end_marker" >> "$temporary_file"
    mv "$temporary_file" "$file_path"
}

backup_timestamp=$(date +%Y%m%d%H%M%S)
for labwc_file in "$AUTOSTART_FILE" "$SHUTDOWN_FILE"; do
    if [[ -f "$labwc_file" ]]; then
        cp -a "$labwc_file" "$labwc_file.bak.$backup_timestamp"
    fi
done

install_managed_block "$AUTOSTART_FILE" \
    "# BEGIN kiosk-screensaver desktop session" \
    "# END kiosk-screensaver desktop session" \
    "bash '$INSTALL_DIR/scripts/desktop-session.sh' start >> '$USER_HOME/kiosk-desktop-session.log' 2>&1 &"
install_managed_block "$SHUTDOWN_FILE" \
    "# BEGIN kiosk-screensaver desktop shutdown" \
    "# END kiosk-screensaver desktop shutdown" \
    "bash '$INSTALL_DIR/scripts/desktop-session.sh' stop >> '$USER_HOME/kiosk-desktop-session.log' 2>&1"
chmod +x "$SHUTDOWN_FILE"

sudo systemctl daemon-reload
if systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user daemon-reload
fi

echo
echo "Desktop session integration installed. Boot mode and firmware/touch configuration were not changed."
echo "Restart the labwc desktop session (or reboot) to start the dashboard and screensaver."
echo "Dashboard scale is controlled by display.dashboard_scale in the admin page (default 1.0)."
