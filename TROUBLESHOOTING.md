# Troubleshooting Guide

## Issue: Dashboard Non-Functional on Wake (Network Appears Down)

**Symptoms:**
- Tap screen to wake from screensaver
- Dashboard UI appears visually
- Camera streams dead (no video)
- Weather radar dead (no external HTTP content)
- All buttons non-functional, may show "couldn't send event" error
- **Key observation:** Second wake attempt works fine - dashboard fully functional

**Root Cause:** HTTP servers (Python http.server on port 8091, rclone on port 8090) may not be running OR network is briefly down when the dashboard loads after first wake.

### Why This Happens:

**NEW DISCOVERY (Jan 11, 2026):** Second wake always works! This points to a **timing/race condition** rather than a permanent failure.

**CONFIRMED ROOT CAUSE - WiFi Network Dropout:**

**Log Evidence (Jan 11, 2026 15:15:09):**
```
HA API error: HTTPSConnectionPool(host='192.168.20.2', port=8123):
Max retries exceeded with url: /api/states/input_boolean.disable_screensaver
(Caused by NewConnectionError ... Failed to establish a new connection:
[Errno 113] No route to host')
```

**What Actually Happens:**
1. First wake (15:14:27) - HTTP servers already running, wake completes
2. ~40 seconds later - Network drops: "No route to host" error trying to reach HA
3. Dashboard is stuck - can't reach HA (192.168.20.2) OR external services
4. Slideshow activates again after idle timeout (~20 seconds)
5. Second wake (15:15:36) - Network has recovered, everything works

**Why Second Wake Works:**
- WiFi connection has re-established by the time of second wake
- HTTP servers were never the problem - they stayed running throughout
- Network dropout was temporary (lasted ~30-40 seconds)
- Dashboard gets fresh connection attempt when it reloads

**Contributing Factors:**

1. **WiFi Power Save Mode ENABLED** (confirmed in dmesg):
   ```
   brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled
   ```
   This is the PRIMARY CULPRIT. WiFi power save can cause brief disconnections during:
   - Wake from screensaver (system coming out of idle)
   - High CPU/GPU load (photo transitions with hardware decode)
   - Periodic power save cycling by the WiFi chip

2. **CPU/GPU Spike During Photo Transitions:**
   - Full resolution JPEG decode (12-24MP images)
   - GPU compositing (1-second opacity fade between two full layers)
   - VAAPI hardware decoder activation
   - During spike, WiFi may drop packets or enter power save
   - Broadcom WiFi chip (BCM4345/6) shares resources with system

3. **Timing:** Network drops ~40 seconds AFTER wake (not during)
   - Suggests power save re-engages after brief wake activity
   - Or WiFi attempting to reconnect after brief dropout

### The Fix (APPLIED - Jan 11, 2026):

**1. WiFi Power Save Disabled (PRIMARY FIX):**
- Installed `iw` package
- Created systemd service: `/etc/systemd/system/disable-wifi-powersave.service`
- Service runs on boot to disable WiFi power management
- Verified in dmesg: `brcmfmac: brcmf_cfg80211_set_power_mgmt: power save disabled`
- Status: `iw dev wlan0 get power_save` shows "Power save: off"

**2. HTTP Server Verification (SECONDARY FIX):**
- Modified `screensaver/modes.py` wake() method
- Added verification that HTTP servers are running after wake
- Restart servers if they stopped during night mode
- This ensures dashboard has working servers when it loads

**Expected Result:**
- Network should remain stable during wake
- No more "No route to host" errors
- Dashboard should work on first wake attempt
- If issue persists, it's likely a different root cause (check logs)

### Code Changes:

**File:** `screensaver/modes.py` (lines 99-108)

```python
# Ensure HTTP servers are running (critical for dashboard to work)
# Servers may have stopped during night mode or crashed during wake
privacy_mode = self.config.get('features', 'privacy_mode', default=False)
if not privacy_mode:
    logger.info("Verifying HTTP servers are running after wake")
    if not self.server_manager.start_all():
        logger.error("Failed to ensure HTTP servers are running after wake")
        # Don't fail wake - dashboard will work in degraded mode
    else:
        logger.info("HTTP servers verified/restarted successfully")
```

**File:** `screensaver/servers.py` (lines 138, 147, 152)

Enhanced error logging to capture what went wrong if server verification fails.

### Diagnostic Script:

If this issue happens again **before power cycling**, run:

```bash
/home/admin/kiosk-screensaver/scripts/diagnose-offline.sh > /tmp/offline-diagnostic.txt
```

This will capture:
- HTTP server process status
- Network port listeners
- Recent screensaver logs
- Network connectivity tests
- System resource usage

Then you can review the diagnostic output to see exactly what state the system was in.

### Deployment:

To deploy this fix:

1. Copy updated files to Pi
2. Restart screensaver service:
   ```bash
   systemctl --user restart kiosk-screensaver
   ```

### Prevention:

The fix should prevent this issue by ensuring HTTP servers are always running after wake. However, if you want to minimize the chance of hitting this during photo transitions:

- The 15-minute slideshow interval means photos change every 15 minutes
- Avoid tapping exactly on 15-minute marks (e.g., 10:00, 10:15, 10:30)
- If you notice a photo starting to fade out, wait 1-2 seconds for the transition to complete

### Monitoring:

Check logs after waking to verify servers are being restarted:

```bash
tail -20 /tmp/kiosk-screensaver.log | grep -i "verifying\|http server"
```

Expected output after wake:
```
Verifying HTTP servers are running after wake
rclone server already running
Python HTTP server already running
HTTP servers verified/restarted successfully
```

Or if servers needed restart:
```
Verifying HTTP servers are running after wake
Starting HTTP servers
Starting rclone server...
Starting Python HTTP server on port 8091...
All HTTP servers started successfully
HTTP servers verified/restarted successfully
```

### If Issue Persists:

If you still see the offline issue after deploying this fix:

1. Run the diagnostic script immediately (don't power cycle yet)
2. Save the output
3. Check if it's a different root cause (network configuration, DNS, firewall, etc.)
4. Review `/tmp/kiosk-screensaver.log` for any errors during wake sequence
