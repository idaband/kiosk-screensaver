#!/bin/bash
# Force night screensaver temporarily (Movie Mode)
# Works with Python-based kiosk screensaver system

# Detect install directory
INSTALL_DIR="$HOME/kiosk-screensaver"
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Error: Installation directory not found: $INSTALL_DIR"
    exit 1
fi

# Set environment variables for Wayland
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export WAYLAND_DISPLAY=$(ls $XDG_RUNTIME_DIR/wayland-* 2>/dev/null | head -1 | xargs basename)
if [ -z "$WAYLAND_DISPLAY" ]; then
    export WAYLAND_DISPLAY=wayland-0
fi

# Kill any existing slideshow Chromium
pkill -f "chromium.*slideshow.html"
sleep 1

# Launch night mode (blank screen)
chromium --new-window --user-data-dir=/tmp/chromium-screensaver-night \
    --ozone-platform=wayland --start-fullscreen --noerrdialogs \
    --disable-infobars --no-first-run --kiosk-printing \
    --use-gl=egl --enable-features=VaapiVideoDecoder,VaapiVideoEncoder \
    --ignore-gpu-rasterization --enable-zero-copy \
    --force-dark-mode --enable-features=WebUIDarkMode \
    --app=file://$INSTALL_DIR/static/screensaver.html &

sleep 1

# Turn off monitor
ddcutil setvcp 10 0

# Wait for ANY input event (mouse, keyboard, touch)
echo "Movie mode active - tap screen or press any key to exit..."
inotifywait -qq /dev/input/event*

# Wake up - kill night mode screensaver
pkill -f "chromium.*screensaver.html"
sleep 1

# Turn monitor back on
ddcutil setvcp 10 80

# The Python screensaver manager will automatically restart the slideshow
# after detecting the activity from inotifywait, so we don't need to do anything else

echo "Movie mode ended - returning to normal operation"
