#!/bin/bash
# Pi 5 Kiosk System Snapshot - Maximum Detail for AI Analysis
# Reports everything needed to diagnose leaks and performance issues

echo "=========================================="
echo "KIOSK SYSTEM SNAPSHOT - DETAILED"
echo "=========================================="
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
UPTIME_SHORT=$(uptime -p)
TEMP_SHORT=$(vcgencmd measure_temp | cut -d= -f2)
echo "Time: $TIMESTAMP"
echo "Uptime: $UPTIME_SHORT"
echo "Temperature: $TEMP_SHORT"
echo ""

echo "=== CRITICAL SERVICES ==="
systemctl is-active screensaver-web.service > /dev/null 2>&1 && echo "screensaver-web: Running" || echo "screensaver-web: STOPPED"
pgrep -f "python.*screensaver.main" > /dev/null 2>&1 && echo "screensaver-main: Running" || echo "screensaver-main: STOPPED"
pgrep -f "python.*http.server.*8091" > /dev/null 2>&1 && echo "HTTP server (8091): Running" || echo "HTTP server (8091): STOPPED"
pgrep -f "python.*web.app" > /dev/null 2>&1 && echo "Web admin (5000): Running" || echo "Web admin (5000): STOPPED"
pgrep -f "chromium.*--kiosk" > /dev/null 2>&1 && echo "Dashboard: Running" || echo "Dashboard: STOPPED"
pgrep labwc > /dev/null 2>&1 && echo "labwc: Running" || echo "labwc: STOPPED"
echo ""

echo "=== CHROMIUM PROCESS COUNTS ==="
DASHBOARD_COUNT=$(ps aux | grep "chromium.*--kiosk" | grep -v grep | wc -l)
SLIDESHOW_COUNT=$(ps aux | grep "chromium.*slideshow.html" | grep -v grep | wc -l)
NIGHT_COUNT=$(ps aux | grep "chromium.*screensaver.html" | grep -v grep | wc -l)
TOTAL_CHROMIUM=$(ps aux | grep chromium | grep -v grep | wc -l)
BROKER=$(ps aux | grep chromium | grep "type=broker" | grep -v grep | wc -l)
RENDERER=$(ps aux | grep chromium | grep "type=renderer" | grep -v grep | wc -l)
GPU=$(ps aux | grep chromium | grep "type=gpu-process" | grep -v grep | wc -l)
UTILITY=$(ps aux | grep chromium | grep "type=utility" | grep -v grep | wc -l)
ZYGOTE=$(ps aux | grep chromium | grep "type=zygote" | grep -v grep | wc -l)

echo "Dashboard: $DASHBOARD_COUNT processes"
echo "Slideshow: $SLIDESHOW_COUNT processes"
echo "Night mode: $NIGHT_COUNT processes"
echo "Total: $TOTAL_CHROMIUM processes"
echo "  Brokers: $BROKER | Renderers: $RENDERER | GPU: $GPU | Utility: $UTILITY | Zygote: $ZYGOTE"
echo ""

echo "=== CHROMIUM DETAILED BREAKDOWN ==="
echo "--- Dashboard Chromium Processes ---"
# Find dashboard main PID
DASH_MAIN=$(ps aux | grep "chromium.*--kiosk" | grep -v "slideshow.html" | grep -v "screensaver.html" | grep -v grep | grep -v "type=" | head -1 | awk '{print $2}')
if [ -n "$DASH_MAIN" ]; then
    echo "Dashboard main PID: $DASH_MAIN"
    # Get all chromium processes and identify which belong to dashboard
    # Dashboard processes are those NOT part of slideshow/night
    ps aux | grep chromium | grep -v grep | while read line; do
        pid=$(echo "$line" | awk '{print $2}')
        cmdline=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')

        # Skip if this is part of slideshow or night mode
        if echo "$cmdline" | grep -q "slideshow.html\|screensaver.html\|chromium-slideshow\|chromium-screensaver-night"; then
            continue
        fi

        # This is a dashboard process
        mem=$(echo "$line" | awk '{printf "%d", $6/1024}')
        cpu=$(echo "$line" | awk '{printf "%.1f", $3}')
        if echo "$line" | grep -q "type=renderer"; then type="renderer"
        elif echo "$line" | grep -q "type=gpu-process"; then type="gpu"
        elif echo "$line" | grep -q "type=utility"; then type="utility"
        elif echo "$line" | grep -q "type=broker"; then type="broker"
        elif echo "$line" | grep -q "type=zygote"; then type="zygote"
        else type="main"; fi
        echo "PID $pid | Type: $type | MEM: ${mem}MB | CPU: ${cpu}%"
    done
else
    echo "Dashboard not running"
fi

echo ""
echo "--- Slideshow Chromium Processes ---"
# Find slideshow main PID
SLIDE_MAIN=$(ps aux | grep "chromium.*slideshow.html" | grep -v grep | grep -v "type=" | head -1 | awk '{print $2}')
if [ -n "$SLIDE_MAIN" ]; then
    # Get all chromium processes with slideshow profile or slideshow.html in cmdline
    ps aux | grep chromium | grep -v grep | while read line; do
        pid=$(echo "$line" | awk '{print $2}')

        # Check if this process belongs to slideshow
        if cat /proc/$pid/cmdline 2>/dev/null | tr '\0' '\n' | grep -q "slideshow.html\|chromium-slideshow"; then
            mem=$(echo "$line" | awk '{printf "%d", $6/1024}')
            cpu=$(echo "$line" | awk '{printf "%.1f", $3}')
            if echo "$line" | grep -q "type=renderer"; then type="renderer"
            elif echo "$line" | grep -q "type=gpu-process"; then type="gpu"
            elif echo "$line" | grep -q "type=utility"; then type="utility"
            elif echo "$line" | grep -q "type=broker"; then type="broker"
            elif echo "$line" | grep -q "type=zygote"; then type="zygote"
            else type="main"; fi
            echo "PID $pid | Type: $type | MEM: ${mem}MB | CPU: ${cpu}%"
        fi
    done
else
    echo "Slideshow not running"
fi

echo ""
echo "--- All Chromium Renderers (by memory) ---"
ps aux | grep chromium | grep "type=renderer" | grep -v grep | sort -k6 -rn | awk '{
    url = "unknown";
    if ($0 ~ /slideshow.html/) url = "slideshow";
    else if ($0 ~ /screensaver.html/) url = "screensaver";
    else if ($0 ~ /--kiosk/) url = "dashboard";
    printf "PID %s | %s renderer | MEM: %dMB | CPU: %.1f%%\n", $2, url, $6/1024, $3
}'

echo ""
echo "--- GPU Processes ---"
ps aux | grep chromium | grep "type=gpu-process" | grep -v grep | awk '{
    profile = "unknown";
    if ($0 ~ /chromium-slideshow/) profile = "slideshow";
    else if ($0 ~ /chromium-screensaver-night/) profile = "night";
    else profile = "dashboard";
    printf "PID %s | %s GPU | MEM: %dMB | CPU: %.1f%%\n", $2, profile, $6/1024, $3
}'

echo ""

echo "=== CHROMIUM MEMORY TOTALS ==="
# Dashboard memory - use exclusion method (all chromium NOT in slideshow/night)
DASHBOARD_TOTAL=$(ps aux | grep chromium | grep -v grep | while read line; do
    pid=$(echo "$line" | awk '{print $2}')
    cmdline=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')

    # Skip if this is part of slideshow or night mode
    if echo "$cmdline" | grep -q "slideshow.html\|screensaver.html\|chromium-slideshow\|chromium-screensaver-night"; then
        continue
    fi

    # This is a dashboard process - output memory
    echo "$line" | awk '{print $6}'
done | awk '{sum+=$1} END {printf "%d", sum/1024}')

DASHBOARD_RENDERER=$(ps aux | grep chromium | grep -v grep | grep "type=renderer" | while read line; do
    pid=$(echo "$line" | awk '{print $2}')
    cmdline=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')

    # Skip if this is part of slideshow or night mode
    if echo "$cmdline" | grep -q "slideshow.html\|screensaver.html\|chromium-slideshow\|chromium-screensaver-night"; then
        continue
    fi

    # This is a dashboard renderer - output memory
    echo "$line" | awk '{print $6}'
done | awk '{sum+=$1} END {printf "%d", sum/1024}')

# Slideshow memory (all processes with slideshow.html or chromium-slideshow profile)
SLIDESHOW_TOTAL=$(ps aux | grep chromium | grep -v grep | while read line; do
    pid=$(echo "$line" | awk '{print $2}')

    # Check if this process belongs to slideshow
    if cat /proc/$pid/cmdline 2>/dev/null | tr '\0' '\n' | grep -q "slideshow.html\|chromium-slideshow"; then
        echo "$line" | awk '{print $6}'
    fi
done | awk '{sum+=$1} END {printf "%d", sum/1024}')

SLIDESHOW_RENDERER=$(ps aux | grep chromium | grep -v grep | grep "type=renderer" | while read line; do
    pid=$(echo "$line" | awk '{print $2}')

    # Check if this process belongs to slideshow
    if cat /proc/$pid/cmdline 2>/dev/null | tr '\0' '\n' | grep -q "slideshow.html\|chromium-slideshow"; then
        echo "$line" | awk '{print $6}'
    fi
done | awk '{sum+=$1} END {printf "%d", sum/1024}')

# Night mode memory
NIGHT_TOTAL=$(ps aux | grep chromium | grep -v grep | while read line; do
    pid=$(echo "$line" | awk '{print $2}')

    # Check if this process belongs to night mode
    if cat /proc/$pid/cmdline 2>/dev/null | tr '\0' '\n' | grep -q "screensaver.html\|chromium-screensaver-night"; then
        echo "$line" | awk '{print $6}'
    fi
done | awk '{sum+=$1} END {printf "%d", sum/1024}')

# Total chromium
TOTAL_CHROMIUM_MEM=$(ps aux | grep chromium | grep -v grep | awk '{sum+=$6} END {printf "%d", sum/1024}')

echo "Dashboard total: ${DASHBOARD_TOTAL:-0} MB (renderer: ${DASHBOARD_RENDERER:-0} MB)"
echo "Slideshow total: ${SLIDESHOW_TOTAL:-0} MB (renderer: ${SLIDESHOW_RENDERER:-0} MB)"
echo "Night mode total: ${NIGHT_TOTAL:-0} MB"
echo "Total Chromium: ${TOTAL_CHROMIUM_MEM} MB"
echo ""

echo "=== PYTHON PROCESSES DETAILED ==="
TOTAL_PYTHON_MEM=$(ps aux | grep python | grep -v grep | awk '{sum+=$6} END {printf "%d", sum/1024}')
echo "Total Python memory: ${TOTAL_PYTHON_MEM} MB"
echo "Breakdown:"
ps aux | grep python | grep -v grep | awk '{printf "  PID %s | %dMB | CPU: %.1f%% | %s\n", $2, $6/1024, $3, substr($0, index($0,$11))}'
echo ""

echo "=== SYSTEM MEMORY ==="
FREE_MEM=$(free -m | awk 'NR==2{printf "%dMB", $7}')
USED_MEM=$(free -m | awk 'NR==2{printf "%dMB", $3}')
TOTAL_MEM=$(free -m | awk 'NR==2{printf "%dMB", $2}')
CACHED_MEM=$(free -m | awk 'NR==2{printf "%dMB", $6}')
echo "Total: $TOTAL_MEM | Used: $USED_MEM | Cached: $CACHED_MEM | Available: $FREE_MEM"
echo ""

echo "=== HARDWARE ACCELERATION STATUS ==="
# Check each chromium instance for its GL backend
echo "Dashboard GL backend:"
DASH_PID=$(ps aux | grep "chromium.*--kiosk" | grep -v "slideshow.html" | grep -v "screensaver.html" | grep -v grep | grep -v "type=" | head -1 | awk '{print $2}')
if [ -n "$DASH_PID" ]; then
    cat /proc/$DASH_PID/cmdline 2>/dev/null | tr '\0' '\n' | grep -E "use-gl|use-angle" | head -2 | paste -sd ' '
fi

echo "Slideshow GL backend:"
SLIDE_PID=$(ps aux | grep "chromium.*slideshow.html" | grep -v grep | grep -v "type=" | head -1 | awk '{print $2}')
if [ -n "$SLIDE_PID" ]; then
    cat /proc/$SLIDE_PID/cmdline 2>/dev/null | tr '\0' '\n' | grep -E "use-gl|use-angle" | head -2 | paste -sd ' '
fi

echo ""
echo "SwiftShader check:"
if ps aux | grep chromium | grep -v grep | grep -q "use-angle=swiftshader"; then
    echo "  FOUND: SwiftShader in use (software rendering)"
    ps aux | grep chromium | grep "use-angle=swiftshader" | grep -v grep | awk '{printf "    PID %s\n", $2}'
else
    echo "  OK: No SwiftShader detected"
fi

echo ""
echo "VAAPI check:"
if ps aux | grep chromium | grep -v grep | grep -q "VaapiVideoDecoder"; then
    echo "  OK: VAAPI hardware video decode active"
else
    echo "  WARNING: VAAPI not detected"
fi

SCREENSAVER_PID=$(pgrep -f "python.*screensaver.main" | head -1)
if [ -n "$SCREENSAVER_PID" ]; then
    LIBVA=$(cat /proc/$SCREENSAVER_PID/environ 2>/dev/null | tr '\0' '\n' | grep LIBVA_DRIVER_NAME | cut -d= -f2)
    echo "  LIBVA_DRIVER_NAME: ${LIBVA:-not set}"
fi
echo ""

echo "=== SCREENSAVER STATUS ==="
if ps aux | grep "chromium.*slideshow.html" | grep -v grep > /dev/null; then
    echo "Mode: Slideshow active"
    # Show how long slideshow has been running
    SLIDE_PID=$(ps aux | grep "chromium.*slideshow.html" | grep -v grep | grep -v "type=" | head -1 | awk '{print $2}')
    if [ -n "$SLIDE_PID" ]; then
        SLIDE_START=$(ps -p $SLIDE_PID -o lstart= 2>/dev/null)
        echo "  Started: $SLIDE_START"
    fi
elif ps aux | grep "chromium.*screensaver.html" | grep -v grep > /dev/null; then
    echo "Mode: Night mode active"
else
    echo "Mode: Dashboard only (screensaver inactive)"
fi
echo ""

echo "=== PHOTO COUNT ==="
if [ -f ~/photo-list.json ]; then
    PHOTO_COUNT=$(python3 -c "import json; print(len(json.load(open('$HOME/photo-list.json'))['photos']))" 2>/dev/null)
    echo "Photos available: ${PHOTO_COUNT:-Error reading}"
else
    echo "Photo list: Not generated"
fi
echo ""

echo "=== HOME ASSISTANT ==="
if [ -f ~/.ha_token ]; then
    echo "HA token: Present"
else
    echo "HA token: Missing"
fi

# Extract HA URL from config if available
if [ -f ~/kiosk-screensaver/config.yaml ]; then
    HA_URL=$(grep "url:" ~/kiosk-screensaver/config.yaml | grep "https://" | head -1 | awk '{print $2}')
    if [ -n "$HA_URL" ]; then
        HA_HOST=$(echo "$HA_URL" | sed -E 's|https?://([^:/]+).*|\1|')
        ping -c 1 -W 1 "$HA_HOST" > /dev/null 2>&1 && echo "HA ping: Success" || echo "HA ping: Failed"
    else
        echo "HA ping: N/A (HA not configured)"
    fi
else
    echo "HA ping: N/A (config not found)"
fi
echo ""

echo "=== NETWORK ==="
WIFI_SIGNAL=$(iwconfig wlan0 2>/dev/null | grep -i "signal level" | awk '{print $4}' | cut -d= -f2)
echo "WiFi signal: ${WIFI_SIGNAL:-N/A} dBm"
echo ""

echo "=== LOAD AVERAGE ==="
cat /proc/loadavg
echo ""

echo "=========================================="
echo "CONDENSED SUMMARY"
echo "=========================================="
SCREENSAVER_RUNNING=$(ps aux | grep "chromium.*slideshow.html\|chromium.*screensaver.html" | grep -v grep > /dev/null && echo "YES" || echo "NO")

cat << EOF
Time: $TIMESTAMP | Uptime: $UPTIME_SHORT | Temp: $TEMP_SHORT
Chromium: ${TOTAL_CHROMIUM} processes, ${TOTAL_CHROMIUM_MEM}MB total (${RENDERER} renderers)
  Dashboard: ${DASHBOARD_TOTAL:-0}MB (renderer: ${DASHBOARD_RENDERER:-0}MB)
  Slideshow: ${SLIDESHOW_TOTAL:-0}MB (renderer: ${SLIDESHOW_RENDERER:-0}MB)
  Active: $SCREENSAVER_RUNNING
Python: ${TOTAL_PYTHON_MEM}MB | Free RAM: ${FREE_MEM}
Load: $(cat /proc/loadavg | awk '{print $1, $2, $3}')
EOF
echo "=========================================="
echo ""
