#!/bin/bash
# Diagnostic script to capture system state when Pi appears offline
# Run this immediately when you notice the offline issue (before power cycle)

echo "=== System Diagnostic for Offline Issue ==="
echo "Time: $(date)"
echo ""

echo "=== Network Interfaces ==="
ip addr show
echo ""

echo "=== HTTP Server Status ==="
echo "Python HTTP server (8091):"
pgrep -fa "python.*8091" || echo "NOT RUNNING"
echo ""
echo "rclone server (8090):"
pgrep -fa "rclone serve http" || echo "NOT RUNNING"
echo ""

echo "=== Port Listeners ==="
netstat -tuln | grep -E "8090|8091"
echo ""

echo "=== Chromium Processes ==="
pgrep -fa chromium | head -20
echo ""

echo "=== Recent Screensaver Logs (last 50 lines) ==="
tail -50 /tmp/kiosk-screensaver.log
echo ""

echo "=== Network Connectivity ==="
echo "Can reach localhost HTTP server:"
curl -v --max-time 2 http://127.0.0.1:8091/ 2>&1 | head -20
echo ""

echo "=== System Load ==="
uptime
echo ""

echo "=== Memory Status ==="
free -h
echo ""

echo "=== Disk Space ==="
df -h /
echo ""

echo "=== Diagnostic complete ==="
