#!/bin/bash
set -euo pipefail

ACTION=${1:-start}
SERVICES=(kiosk-dashboard.service kiosk-screensaver-manager.service)

case "$ACTION" in
    start)
        if [[ -z "${WAYLAND_DISPLAY:-}" || -z "${XDG_RUNTIME_DIR:-}" ]]; then
            echo "Desktop kiosk startup requires WAYLAND_DISPLAY and XDG_RUNTIME_DIR" >&2
            exit 1
        fi

        SESSION_VARS=()
        for variable in WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS DISPLAY LIBVA_DRIVER_NAME; do
            if [[ -n "${!variable:-}" ]]; then
                SESSION_VARS+=("$variable")
            fi
        done

        systemctl --user import-environment "${SESSION_VARS[@]}"
        systemctl --user daemon-reload

        SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
        INSTALL_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
        WEB_ADMIN_PORT=$(PYTHONPATH="$INSTALL_DIR" python3 - "$INSTALL_DIR/config.yaml" <<'PY'
import sys
from screensaver.config import load_config
print(load_config(sys.argv[1]).get('network', 'web_admin_port', default=5000))
PY
)
        web_ready=false
        for attempt in {1..30}; do
            if python3 -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:${WEB_ADMIN_PORT}/api/dashboard-settings', timeout=1)" >/dev/null 2>&1; then
                web_ready=true
                break
            fi
            sleep 1
        done

        if [[ "$web_ready" != true ]]; then
            echo "Dashboard settings endpoint did not become ready; starting the screensaver manager only." >&2
            systemctl --user start kiosk-screensaver-manager.service
            exit 0
        fi

        systemctl --user start "${SERVICES[@]}"
        ;;
    stop)
        systemctl --user stop "${SERVICES[@]}"
        ;;
    *)
        echo "Usage: $0 {start|stop}" >&2
        exit 2
        ;;
esac
