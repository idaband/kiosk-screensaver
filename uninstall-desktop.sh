#!/bin/bash
set -euo pipefail

CURRENT_USER=$(id -un)
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)
AUTOSTART_FILE="$USER_HOME/.config/labwc/autostart"
SHUTDOWN_FILE="$USER_HOME/.config/labwc/shutdown"
USER_UNIT_DIR="$USER_HOME/.config/systemd/user"
USER_UNITS=(kiosk-dashboard.service kiosk-screensaver-manager.service)

read -r -p "Remove the desktop session launcher and user services? (y/N): " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

systemctl --user stop "${USER_UNITS[@]}" 2>/dev/null || true

remove_managed_block() {
    local file_path="$1" begin_marker="$2" end_marker="$3"
    [[ -f "$file_path" ]] || return 0
    local temporary_file
    temporary_file=$(mktemp)
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
    mv "$temporary_file" "$file_path"
}

remove_managed_block "$AUTOSTART_FILE" \
    "# BEGIN kiosk-screensaver desktop session" \
    "# END kiosk-screensaver desktop session"
remove_managed_block "$SHUTDOWN_FILE" \
    "# BEGIN kiosk-screensaver desktop shutdown" \
    "# END kiosk-screensaver desktop shutdown"

for unit in "${USER_UNITS[@]}"; do
    rm -f "$USER_UNIT_DIR/$unit"
done
systemctl --user daemon-reload 2>/dev/null || true

echo "Desktop kiosk user services and managed labwc blocks removed."
echo "The shared screensaver-web.service, config.yaml, photos, touch settings, and firmware were left unchanged."
