# Kiosk Screensaver System

> **Author's Note:** This project was created to solve a very specific need - a fast-responding slideshow screensaver for a Raspberry Pi 5 running a Home Assistant dashboard in kiosk mode. I developed this system using Visual Studio Code with significant assistance from the Claude Code extension. My personal coding ability is quite limited, and this project wouldn't have been possible without AI assistance. I'm sharing it publicly in case others have similar needs, but please be aware of its origins when using or contributing.

A comprehensive, configurable screensaver system for Raspberry Pi 5 kiosk displays with Home Assistant integration.

Perfect for creating a wall-mounted Home Assistant dashboard that automatically shows a photo slideshow when idle.

## Features

- **Automatic Idle Detection**: Monitors keyboard, mouse, and touchscreen input
- **Time-Based Modes**: Photo slideshow during day hours, blank screen + monitor off at night
- **Home Assistant Integration**: Remote enable/disable via HA entity (optional)
- **Web Admin Panel**: Browser-based configuration interface
- **Display Power Management**: DDC/CI brightness control, monitor power on/off
- **Auto Photo List Generation**: Scheduled regeneration of photo catalog
- **Privacy Mode**: Optional blank screen instead of photos
- **Scheduled Reboots**: Automatic system maintenance reboots
- **Movie Mode**: Quick script to force dark mode for watching movies

## System Requirements

### Hardware
- **Raspberry Pi 5** (8GB RAM recommended, 4GB works)
- **Monitor**: DDC/CI-compliant monitor recommended for brightness control (most modern monitors support this)
- **Storage**: 32GB+ microSD card
- **Input**: Touchscreen, mouse, or keyboard for interaction

### Software
- **Fresh Raspberry Pi OS (64-bit)** - Debian Trixie or newer
- **Desktop mode with auto-login** initially configured (installer will switch to CLI)
- Internet connection for downloading dependencies

## Installation

### 1. Prepare Your Raspberry Pi

1. Flash fresh **Raspberry Pi OS (64-bit)** to microSD card using Raspberry Pi Imager
2. During setup, configure:
   - Username and password
   - WiFi network
   - Enable SSH (optional, but recommended)
3. Boot into Desktop mode and complete initial setup
4. Configure auto-login in Desktop mode (System Settings → Users)

### 2. Transfer Files

Transfer this entire folder to your Raspberry Pi:

**Option A: Using WinSCP or similar (from Windows)**
```
Source: This folder
Destination: /home/[your-username]/kiosk-screensaver
```

**Option B: Using git (if available)**
```bash
cd ~
git clone [your-repo-url] kiosk-screensaver
```

**Option C: Using scp (from Linux/Mac)**
```bash
scp -r kiosk-screensaver pi@[pi-ip-address]:~/
```

### 3. Fix Line Endings (if transferring from Windows)

```bash
cd ~/kiosk-screensaver
find . -name "*.sh" -exec sed -i 's/\r$//' {} \;
```

### 4. Run Installer

```bash
cd ~/kiosk-screensaver
bash install.sh
```

The installer will:
1. Install all required dependencies (labwc, chromium, ddcutil, etc.)
2. Ask for your configuration:
   - Home Assistant URL (optional)
   - Dashboard URL (required)
   - Photos folder path
3. Switch boot mode from Desktop to CLI
4. Configure auto-start for labwc, Chromium, and screensaver
5. Set up web admin panel
6. Configure permissions

### 5. Reboot

```bash
sudo reboot
```

After reboot:
- System starts in CLI mode (you'll see text briefly)
- labwc Wayland compositor starts automatically
- Chromium opens your dashboard in kiosk mode
- Screensaver runs in the background

## Configuration

### Web Admin Panel

Access at `http://[pi-ip-address]:5000`

Configure:
- Idle timeout (seconds before screensaver activates)
- Slideshow interval (seconds between photos)
- Day/night mode times
- Scheduled reboots
- Photo list regeneration

### Home Assistant Integration (Optional)

If enabled during install:

**IMPORTANT:** Use your Home Assistant's **local network IP address** (e.g., `https://192.168.1.100:8123`), NOT your DuckDNS or external URL. The screensaver runs on the same local network as Home Assistant and should communicate locally for best performance and reliability.

1. Create an `input_boolean` in Home Assistant:
   ```yaml
   input_boolean:
     disable_screensaver:
       name: Disable Screensaver
       icon: mdi:monitor-off
   ```

2. Get a Long-Lived Access Token:
   - In HA, go to your Profile → Security → Long-Lived Access Tokens
   - Create new token
   - Copy the token

3. Save token on Pi:
   ```bash
   echo "your-token-here" > ~/.ha_token
   ```

4. Test connection in web admin panel

**How it works:**
- When `input_boolean.disable_screensaver` is **OFF**: Screensaver works normally
- When **ON**: Screensaver is disabled (dashboard always visible)

### Photo Source

Configure your photo source path during installation or edit later in `config.yaml`.

**Important:** If using network shares or external drives, you are responsible for mounting them properly on your Raspberry Pi. The examples below show the basic commands, but configuring persistent mounts, credentials, and network stability is outside the scope of this project. Refer to Raspberry Pi and Linux documentation for mounting network shares.

**Local photos:**
```bash
photo_source_path: /home/username/Pictures
```

**Network share (Windows/Samba) - Example:**
```bash
# First, mount the share (add to /etc/fstab for auto-mount on boot)
sudo mkdir /mnt/photos
sudo mount -t cifs //192.168.1.100/Pictures /mnt/photos -o username=user,password=pass

# Then configure:
photo_source_path: /mnt/photos
```

**NFS share - Example:**
```bash
sudo mkdir /mnt/photos
sudo mount -t nfs 192.168.1.100:/photos /mnt/photos

photo_source_path: /mnt/photos
```

**Note:** Network share mounting configuration, credentials management, and ensuring mounts persist across reboots are the user's responsibility. Search for "Raspberry Pi mount network share" or "Linux fstab configuration" for detailed guides.

## Usage

### Normal Operation

- **Boot**: After system startup, screensaver waits 90 seconds before it can activate (boot grace period)
  - This ensures the Wayland compositor is fully initialized
  - Prevents display issues on fresh boot
- **Idle**: After configured timeout (default 20 seconds), slideshow starts
- **Wake**: Tap screen or move mouse to return to dashboard
- **Day mode** (6:15 AM - 11:00 PM): Photo slideshow
- **Night mode** (11:00 PM - 6:15 AM): Blank screen + monitor off

### Movie Mode

Quick script to force dark screen while watching movies.

**Requirements:**
- SSH access to the Raspberry Pi
- Terminal session (or SSH client like PuTTY)

**Note:** This feature requires a persistent SSH connection. You'll need to set up SSH access to your Pi and keep a terminal session open. Configuration of SSH is outside the scope of this installation - refer to Raspberry Pi documentation for SSH setup.

**Usage:**
```bash
# SSH into your Pi, then run:
bash ~/kiosk-screensaver/force-night-screensaver.sh
```

**What it does:**
- Immediately activates night mode (blank screen, monitor off)
- Waits for input (tap screen or press any key)
- Exits and returns to normal operation
- Perfect for watching movies without the slideshow activating

**Automation Alternative:**
Instead of using this script, you can use the Home Assistant integration to disable the screensaver remotely via an HA automation or dashboard button.

## Troubleshooting

### Screensaver not activating

```bash
# Check if screensaver process is running
pgrep -f screensaver.main

# View logs
journalctl -u screensaver-web -f

# Check input device permissions
ls -la /dev/input/event*

# Ensure you're in input group
groups | grep input
```

### Monitor brightness not working

```bash
# Test DDC/CI detection
ddcutil detect

# If not detected, your monitor may not support DDC/CI
# Screensaver will still work, just without brightness control
```

### Dashboard not loading

```bash
# Check if Chromium is running
pgrep chromium

# Check autostart file
cat ~/.config/labwc/autostart

# Restart labwc
pkill labwc
```

### Web admin not accessible

```bash
# Check if service is running
sudo systemctl status screensaver-web

# Restart service
sudo systemctl restart screensaver-web

# Check logs
sudo journalctl -u screensaver-web -f
```

## Advanced Configuration

### Manual Configuration File

Edit `~/kiosk-screensaver/config.yaml` for advanced settings:

```bash
nano ~/kiosk-screensaver/config.yaml
```

After editing, restart services:
```bash
sudo systemctl restart screensaver-web
pkill -f screensaver.main  # Will auto-restart from autostart
```

### Boot Grace Period

The `boot_grace_period` setting (default: 90 seconds) prevents the screensaver from activating immediately after system boot. This is critical for proper operation:

- Wayland compositor (labwc) needs time to fully initialize after boot
- Without this delay, the screensaver may launch Chromium windows before the compositor is ready
- This can cause display issues like half-screen rendering
- **Recommended minimum: 60 seconds** for Raspberry Pi 5
- Do not disable this setting (set to 0) unless you're using systemd service startup with proper dependencies

### Scheduled Reboots

Configure in web admin panel or config.yaml:
```yaml
features:
  scheduled_reboot:
    enabled: true
    frequency: "weekly"  # or "daily"
    day_of_week: 1  # 0=Monday, 6=Sunday
    reboot_time: "0300"  # 3:00 AM
```

### Privacy Mode

Disable photo slideshow, use blank screen instead:
```yaml
features:
  privacy_mode: true
```

## Architecture

### Components

1. **Python Screensaver Manager** (`screensaver/manager.py`)
   - Monitors input devices using inotify
   - Handles idle timeout and mode switching
   - Integrates with Home Assistant

2. **Web Admin Panel** (`screensaver/web/`)
   - Flask-based web interface
   - Real-time configuration updates
   - System status monitoring

3. **Photo Manager** (`screensaver/photos.py`)
   - Generates photo list from source directory
   - Scheduled auto-regeneration
   - Excludes large files, caches metadata

4. **Mode Handler** (`screensaver/modes.py`)
   - Day mode: Launches Chromium with slideshow
   - Night mode: Blank screen + monitor power off
   - Handles mode transitions

### File Structure

```
~/kiosk-screensaver/
├── install.sh              # Installation script
├── config.yaml             # Main configuration (generated by installer)
├── config.yaml.template    # Template used by installer
├── requirements.txt        # Python dependencies
├── screensaver/            # Python package
│   ├── main.py            # Entry point
│   ├── manager.py         # Core screensaver logic
│   ├── modes.py           # Day/night mode handling
│   ├── photos.py          # Photo list generation
│   ├── config.py          # Configuration loader
│   ├── ha_client.py       # Home Assistant integration
│   └── web/               # Web admin panel
├── static/                 # HTML/JS for slideshow
└── force-night-screensaver.sh  # Movie mode script

Note: Systemd service files and sudoers configuration are generated
automatically by the installer with your specific user and paths.
```

## Credits

Built for Raspberry Pi 5 kiosk installations with Home Assistant integration.

## License

[Your chosen license]

## Support

For issues and questions, please open an issue on GitHub or refer to the troubleshooting section above.
