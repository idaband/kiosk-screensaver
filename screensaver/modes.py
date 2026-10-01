"""Screensaver mode handlers (day, night, wake)."""
import logging
import os
import subprocess
import time
from datetime import datetime


logger = logging.getLogger(__name__)


class ModeHandler:
    """Handles different screensaver modes."""

    def __init__(self, config, server_manager):
        """Initialize mode handler.

        Args:
            config: Config instance
            server_manager: HTTPServerManager instance
        """
        self.config = config
        self.server_manager = server_manager
        self.chromium_process = None

    def activate_day_mode(self) -> bool:
        """Activate daytime screensaver (photo slideshow).

        Returns:
            True if activated successfully
        """
        logger.info("Activating day mode screensaver")

        privacy_mode = self.config.get('features', 'privacy_mode', default=False)

        # Start HTTP servers (with verification)
        if not privacy_mode:
            if not self.server_manager.start_all():
                logger.error("Failed to start HTTP servers")
                return False

        # Dim screen BEFORE launching chromium to hide white flash
        self._set_brightness(self.config.get('display', 'dimmed_brightness', default=0))
        time.sleep(1.3)  # Allow time for dim to complete

        # Launch chromium with slideshow or blank screen
        if privacy_mode:
            return self._launch_blank_screen('slideshow')
        else:
            return self._launch_slideshow()

    def refresh_day_slideshow(self) -> bool:
        """Relaunch the active day slideshow after its photo list changes."""
        logger.info("Refreshing daytime slideshow photo list")
        return self._launch_slideshow()

    def activate_night_mode(self) -> bool:
        """Activate nighttime screensaver (blank screen, monitor off).

        Returns:
            True if activated successfully
        """
        logger.info("Activating night mode screensaver")

        # Launch blank screen
        if not self._launch_blank_screen('night'):
            return False

        # Turn off monitor if configured
        if self.config.get('display', 'night_mode_monitor_off', default=True):
            time.sleep(0.5)
            self._set_monitor_power(False)

        return True

    def wake(self) -> bool:
        """Wake from screensaver and restore dashboard.

        Returns:
            True if woke successfully
        """
        logger.info("Waking from screensaver")

        # Turn on monitor first
        self._set_monitor_power(True)

        # Get PIDs before killing
        slideshow_pids = self._get_pids('slideshow.html')
        screensaver_pids = self._get_pids('screensaver.html')

        # Close windows gracefully
        self._pkill('screensaver.html')
        self._pkill('slideshow.html')

        time.sleep(0.5)

        # Force kill any remaining processes
        for pid in slideshow_pids + screensaver_pids:
            try:
                os.kill(int(pid), 9)
            except (ProcessLookupError, ValueError):
                pass

        # Restore brightness
        self._set_brightness(self.config.get('display', 'normal_brightness', default=80))

        logger.info("Wake complete")
        return True

    def _launch_slideshow(self) -> bool:
        """Launch photo slideshow in chromium as fullscreen window on top of dashboard.

        Returns:
            True if launched successfully
        """
        try:
            # CRITICAL: Kill existing slideshow/night instances to prevent memory leaks
            # Multiple Chromium instances cause severe memory leaks on Raspberry Pi
            # https://forums.raspberrypi.com/viewtopic.php?t=296598
            logger.info("Killing existing slideshow/night Chromium instances")
            subprocess.run(['pkill', '-f', 'chromium.*slideshow.html'], stderr=subprocess.DEVNULL)
            subprocess.run(['pkill', '-f', 'chromium.*screensaver.html'], stderr=subprocess.DEVNULL)
            time.sleep(1)  # Wait for processes to fully terminate

            # Clear slideshow profile cache to prevent memory buildup
            profile = self.config.get('paths', 'chromium_slideshow_profile')
            cache_dirs = ['Cache', 'Code Cache', 'GPUCache', 'Service Worker']
            for cache_dir in cache_dirs:
                cache_path = os.path.join(os.path.expanduser(profile), cache_dir)
                if os.path.exists(cache_path):
                    try:
                        subprocess.run(['rm', '-rf', cache_path], stderr=subprocess.DEVNULL)
                    except:
                        pass

            python_port = self.config.get('network', 'python_port', default=8091)
            hw_accel = self.config.get('chromium', 'hardware_acceleration', default=True)

            # Build chromium command - use --start-fullscreen NOT --kiosk
            # This allows the window to be on top of the dashboard kiosk without replacing it
            cmd = [
                'chromium',
                '--new-window',
                f'--user-data-dir={profile}',
                '--ozone-platform=wayland',  # CRITICAL: Force Wayland instead of X11
                '--start-fullscreen',  # Fullscreen window, NOT kiosk mode
                '--window-size=9999,9999',  # Force oversized window so Wayland corrects to fullscreen
                '--noerrdialogs',
                '--disable-infobars',
                '--no-first-run',
                '--kiosk-printing',  # Hide cursor on touchscreen
                '--password-store=basic',  # Use basic password store
                '--use-mock-keychain',  # Use mock keychain to prevent password prompts
                # Memory leak prevention flags
                '--disable-background-networking',  # Prevent background requests
                '--disable-extensions',  # Disable extensions to reduce memory
                '--disable-sync',  # Disable Google sync
                '--metrics-recording-only',  # Disable metrics upload
                '--disable-background-timer-throttling',  # Prevent timer accumulation
                '--disk-cache-size=1'  # Minimal disk cache to prevent buildup
            ]

            # Add hardware acceleration flags
            if hw_accel:
                extra_flags = self.config.get('chromium', 'extra_flags', default=[])
                cmd.extend(extra_flags)

            # Add dark mode flags
            dark_flags = self.config.get('chromium', 'dark_mode_flags', default=[])
            cmd.extend(dark_flags)

            # Slideshow URL with cache busting
            cache_buster = int(time.time())
            slideshow_url = f"http://127.0.0.1:{python_port}/slideshow.html?v={cache_buster}"
            cmd.append(f'--app={slideshow_url}')

            logger.info(f"Launching slideshow: {' '.join(cmd)}")

            # Set environment variables
            env = os.environ.copy()
            env['WAYLAND_DISPLAY'] = self.config.get('environment', 'wayland_display', default='wayland-0')
            env['LIBVA_DRIVER_NAME'] = self.config.get('environment', 'libva_driver', default='v3d_video')

            self.chromium_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            logger.info("Slideshow launched")
            return True

        except Exception as e:
            logger.error(f"Failed to launch slideshow: {e}")
            return False

    def _launch_blank_screen(self, profile_type: str) -> bool:
        """Launch blank screen in chromium as fullscreen window.

        Args:
            profile_type: 'slideshow' or 'night'

        Returns:
            True if launched successfully
        """
        try:
            # CRITICAL: Kill existing slideshow/night instances to prevent memory leaks
            logger.info("Killing existing slideshow/night Chromium instances")
            subprocess.run(['pkill', '-f', 'chromium.*slideshow.html'], stderr=subprocess.DEVNULL)
            subprocess.run(['pkill', '-f', 'chromium.*screensaver.html'], stderr=subprocess.DEVNULL)
            time.sleep(1)  # Wait for processes to fully terminate

            if profile_type == 'night':
                profile = self.config.get('paths', 'chromium_night_profile')
            else:
                profile = self.config.get('paths', 'chromium_slideshow_profile')

            # Clear profile cache to prevent memory buildup
            cache_dirs = ['Cache', 'Code Cache', 'GPUCache', 'Service Worker']
            for cache_dir in cache_dirs:
                cache_path = os.path.join(os.path.expanduser(profile), cache_dir)
                if os.path.exists(cache_path):
                    try:
                        subprocess.run(['rm', '-rf', cache_path], stderr=subprocess.DEVNULL)
                    except:
                        pass

            screensaver_html = self.config.get('paths', 'screensaver_html')
            hw_accel = self.config.get('chromium', 'hardware_acceleration', default=True)

            cmd = [
                'chromium',
                '--new-window',
                f'--user-data-dir={profile}',
                '--ozone-platform=wayland',  # CRITICAL: Force Wayland instead of X11
                '--start-fullscreen',  # Fullscreen window, NOT kiosk mode
                '--window-size=9999,9999',  # Force oversized window so Wayland corrects to fullscreen
                '--kiosk-printing',  # Hide cursor on touchscreen
                '--password-store=basic',  # Use basic password store
                '--use-mock-keychain',  # Use mock keychain to prevent password prompts
                # Memory leak prevention flags
                '--disable-background-networking',  # Prevent background requests
                '--disable-extensions',  # Disable extensions to reduce memory
                '--disable-sync',  # Disable Google sync
                '--metrics-recording-only',  # Disable metrics upload
                '--disable-background-timer-throttling',  # Prevent timer accumulation
                '--disk-cache-size=1'  # Minimal disk cache to prevent buildup
            ]

            if hw_accel:
                extra_flags = self.config.get('chromium', 'extra_flags', default=[])
                cmd.extend(extra_flags)

            dark_flags = self.config.get('chromium', 'dark_mode_flags', default=[])
            cmd.extend(dark_flags)

            cmd.append(f'--app=file://{screensaver_html}')

            logger.info(f"Launching blank screen: {' '.join(cmd)}")

            env = os.environ.copy()
            env['WAYLAND_DISPLAY'] = self.config.get('environment', 'wayland_display', default='wayland-0')

            self.chromium_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            logger.info("Blank screen launched")
            return True

        except Exception as e:
            logger.error(f"Failed to launch blank screen: {e}")
            return False

    def _set_brightness(self, level: int) -> None:
        """Set monitor brightness via ddcutil.

        Args:
            level: Brightness level 0-100
        """
        try:
            subprocess.run(['ddcutil', 'setvcp', '10', str(level)], timeout=5)
            logger.debug(f"Set brightness to {level}")
        except Exception as e:
            logger.warning(f"Failed to set brightness: {e}")

    def _set_monitor_power(self, on: bool) -> None:
        """Set monitor power via wlopm.

        Args:
            on: True to turn on, False to turn off
        """
        try:
            state = '--on' if on else '--off'
            subprocess.run(['wlopm', state, '*'], timeout=5)
            logger.debug(f"Set monitor power: {on}")
        except Exception as e:
            logger.warning(f"Failed to set monitor power: {e}")

    def _get_pids(self, process_name: str) -> list:
        """Get PIDs matching process name.

        Args:
            process_name: Process name to search for

        Returns:
            List of PIDs as strings
        """
        try:
            result = subprocess.run(
                ['pgrep', '-f', process_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')
            return []
        except Exception:
            return []

    def _pkill(self, process_name: str) -> None:
        """Kill processes matching name.

        Args:
            process_name: Process name to kill
        """
        try:
            subprocess.run(['pkill', '-f', process_name], timeout=5)
        except Exception as e:
            logger.warning(f"Failed to pkill {process_name}: {e}")

    def is_day_mode(self) -> bool:
        """Check if current time is within day mode hours.

        Returns:
            True if daytime, False if nighttime
        """
        now = datetime.now()
        current_time = now.hour * 100 + now.minute  # Convert to HHMM format (e.g., 1635)
        day_name = now.strftime('%A').lower()  # 'monday', 'tuesday', etc.

        # Day start time is the same every day
        start_str = self.config.get('timing', 'day_mode_start_time', default='0600')

        # Night start time can vary by day of week
        night_times = self.config.get('timing', 'night_mode_start_time', default='2200')

        # Handle both old format (string) and new format (dict)
        if isinstance(night_times, dict):
            night_str = night_times.get(day_name)
            if night_str is None:
                logger.warning(f"No night time configured for {day_name}, using default 2200")
                night_str = '2200'  # Default fallback
        else:
            night_str = night_times  # Old single-value format

        # Parse HHMM strings to integers
        try:
            start_time = int(start_str)  # e.g., "0615" -> 615
            night_time = int(night_str)  # e.g., "2300" -> 2300
        except (ValueError, TypeError):
            logger.error(f"Invalid time format in config: start={start_str}, night={night_str}")
            # Fallback to default times
            start_time = 600   # 6:00 AM
            night_time = 2200  # 10:00 PM

        # Day mode is active from start_time until night_time
        return start_time <= current_time < night_time
