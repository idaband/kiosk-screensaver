# Raspberry Pi 10" Touchscreen Rotation Guide

Comprehensive guide for rotating a Raspberry Pi 10" Touch Display 2 with correct display and touchscreen calibration.

---

## Official Method (Recommended) ⭐

This is the **official Raspberry Pi approach** for Touch Display 2 rotation, configured at the kernel/firmware level for maximum reliability.

**Source:** [Raspberry Pi Touch Display 2 Documentation](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html#customise-touchscreen-settings)

### Step 1: Identify Your Hardware

**For Official 10" Raspberry Pi Touch Display 2:**
- Device Tree overlay name: `vc4-kms-dsi-ili79600-10-1inch`
- Configured in: `/boot/firmware/config.txt`

**For Other 10" DSI Displays:**
- May use different overlay names (e.g., `vc4-kms-dsi-ili9881-7inch`, `vc4-kms-dsi-ili79600`)
- Check your display documentation or run:
  ```bash
  cat /proc/device-tree/chosen/bootargs | grep -i overlay
  ```

### Step 2: Edit Configuration

Open `/boot/firmware/config.txt`:

```bash
sudo nano /boot/firmware/config.txt
```

**Find or add the dtoverlay line for your display:**

```ini
dtoverlay=vc4-kms-dsi-ili79600-10-1inch
```

### Step 3: Apply Rotation

This is the touch layer only. It fixes how the touchscreen maps coordinates.

Add rotation parameters to the `dtoverlay` line. Common options:

| Option | Purpose | Effect |
|--------|---------|--------|
| `swapxy` | Swap X and Y axes | Rotates touch 90° |
| `invx` | Invert X-axis | Flips left/right |
| `invy` | Invert Y-axis | Flips top/bottom |
| `sizex=<value>` | Set touch X resolution | Default: 1200 for 10" |
| `sizey=<value>` | Set touch Y resolution | Default: 1920 for 10" |

**Examples:**


**This kiosk’s working configuration (counter-clockwise 90°):**
```ini
dtoverlay=vc4-kms-dsi-ili79600-10-1inch,swapxy,invy,invx
```

This config fixes the touchscreen mapping. It does not rotate the browser output by itself.

For the actual screen image, you must also apply a compositor output transform in the Wayland startup as shown below.

### Step 4: Save and Reboot

```bash
sudo reboot
```

The rotation will take effect immediately after boot. Both display and touchscreen will rotate together automatically.



---

## Display-Only Rotation (Without Touchscreen Changes)

If you only want to rotate the video display for console output:

### Method A: Desktop Environment

1. Open **Preferences → Control Centre → Screens**
2. Right-click the display (labeled `DSI-1`)
3. Select **Orientation** → Choose **Normal**, **Left**, **Inverted**, or **Right**
4. Click **Apply**

This persists across reboots in desktop mode.

### Method B: Kernel Command Line (Console/CLI Only)

Edit `/boot/firmware/cmdline.txt`:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Add to the end of the **single line** (important - must be one line):

```
video=DSI-1:1200x1920@60,rotate=90
```

**Rotation values:** `0`, `90`, `180`, `270` (degrees clockwise)

**Example full cmdline.txt:**
```
console=tty1 root=PARTUUID=... rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait video=DSI-1:1200x1920@60,rotate=90
```

⚠️ **Note:** This only rotates the text console. GUI applications (like Chromium in your kiosk) will ignore this. Use the Device Tree method (above) for full rotation.

---

## Wayland / labwc Kiosk Configuration

This is the display layer. It rotates the actual framebuffer and browser output.

For this project, the actual screen orientation was set in the compositor startup instead of relying on the console-only `video=...rotate=` method.

```bash
# Rotate the actual DSI output for the browser and kiosk UI
wlr-randr --output DSI-1 --transform 90
```

This is the method used in the kiosk launcher for the rotated Touch Display 2.

A real example from this project looks like this:

```bash
chromium \
  --ozone-platform=wayland \
  --touch-events=enabled \
  --force-device-scale-factor=1.5 \
  --default-zoom-level=1.5 \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --disable-features=WakeLockSensor,IdleDetection,MediaSession \
  --use-gl=egl \
  --enable-features=VaapiVideoDecoder,VaapiVideoEncoder \
  --ignore-gpu-blocklist \
  --enable-gpu-rasterization \
  --enable-zero-copy \
  --ignore-certificate-errors \
  http://URL.com &

# Kiosk Screensaver (Python version)
cd /home/skylight/kiosk-screensaver-1.0.0 && \
PYTHONPATH=/home/skylight/kiosk-screensaver-1.0.0 \
python3 -m screensaver.main -c /home/skylight/kiosk-screensaver-1.0.0/config.yaml \
>> /home/skylight/screensaver-startup.log 2>&1 &

wlr-randr --output DSI-1 --transform 90
```

This is the relevant Wayland rotation for the browser and kiosk UI and matches the actual working setup used here.

Important: both pieces are required together:
- the `dtoverlay=...` line adjusts touch coordinates
- `wlr-randr --output DSI-1 --transform 90` rotates the display output

Without both, the screen or the touch input will be wrong.

---

## Troubleshooting

### Issue: Display rotates but touchscreen doesn't

**Cause:** Only display rotation applied, not Device Tree overlay configuration.

**Solution:** Use Device Tree method (official method, above) which handles both simultaneously.

### Issue: Touchscreen not responding after rotation

**Cause:** Device Tree overlay not loaded or wrong device name used.

**Solution:**
1. Verify overlay syntax in config.txt:
   ```bash
   cat /boot/firmware/config.txt | grep dtoverlay
   ```

2. Check if overlay loaded:
   ```bash
   cat /proc/device-tree/chosen/bootargs
   ```

3. Check system logs:
   ```bash
   journalctl -b | grep -i overlay
   ```

### Issue: Partial touch responsiveness

**Cause:** Calibration parameters don't match your orientation or display resolution.

**Solution:**
1. Verify display resolution:
   ```bash
   wlr-randr
   ```

2. Test touch input:
   ```bash
   evtest /dev/input/event10  # adjust event number
   ```

3. Ensure `sizex` and `sizey` match your rotated display dimensions

### Issue: Changes lost after system update

**Cause:** Update overwrites `/boot/firmware/config.txt`.

**Solution:** 
- Keep your changes in a separate commented section
- Document in `/etc/motd` which custom overlays are in use
- Version control your `/boot/firmware/config.txt` if possible

---

## Testing Your Configuration

1. **Verify display rotation:**
   ```bash
   wlr-randr
   ```

2. **Verify touch responsiveness:**
   ```bash
   evtest /dev/input/event10
   # Physically touch screen and watch coordinates
   ```

3. **Test in application:**
   - Open a drawing app (e.g., GIMP, simple paint)
   - Draw on screen to verify coordinates match touch points
   - Touch corners and edges to confirm mapping

4. **Monitor logs:**
   ```bash
   journalctl -b | grep -i overlay
   ```

---

## Technical Reference: Device Tree Parameters

| Parameter | Type | Default (10") | Description |
|-----------|------|----------------|-------------|
| `sizex` | integer | 1200 | Touch input horizontal resolution |
| `sizey` | integer | 1920 | Touch input vertical resolution |
| `invx` | boolean | false | Invert X-axis (left↔right) |
| `invy` | boolean | false | Invert Y-axis (up↔down) |
| `swapxy` | boolean | false | Swap X and Y (rotate 90°) |
| `disable_touch` | boolean | false | Disable touchscreen entirely |

**Boolean parameters:**
- Present without value = enabled (true)
- `=0` suffix = disabled (false)

**Example with all parameters:**
```ini
dtoverlay=vc4-kms-dsi-ili79600-10-1inch,invx=0,invy=1,swapxy=1,sizex=1200,sizey=1920
```

---

## Kiosk System Integration

This was the exact configuration used for the rotating Touch Display 2 in the kiosk project. Both settings were required together for correct operation:

```ini
# /boot/firmware/config.txt
# counter-clockwise 90° rotation for the Touch Display 2 panel and touch input
# NOTE: this is the working project configuration

dtoverlay=vc4-kms-dsi-ili79600-10-1inch,swapxy,invy,invx
```

And the actual display rotation for the browser UI was applied in the Wayland compositor startup:

```bash
# ~/.config/labwc/autostart
wlr-randr --output DSI-1 --transform 90
```

This combination is what made the screen and touchscreen rotate correctly in the kiosk environment.

In short: the DSI overlay config fixes touch alignment, and the `wlr-randr` transform fixes the display orientation. Neither alone is sufficient.

---

## Additional Resources

- **Official Raspberry Pi Docs:** https://www.raspberrypi.com/documentation/accessories/touch-display-2.html
- **Device Tree Overlays:** https://github.com/raspberrypi/linux/tree/rpi-6.1.y/arch/arm/boot/dts/overlays
- **Wayland Display:** https://wayland.freedesktop.org/
- **labwc Configuration:** https://github.com/labwc/labwc
