"""Core screensaver manager with idle detection."""
import json
import logging
import os
import signal
import sys
import time
from inotify_simple import INotify, flags


logger = logging.getLogger(__name__)


class ScreensaverManager:
    """Main screensaver manager with idle detection."""

    def __init__(self, config, ha_client, mode_handler, photo_manager):
        """Initialize screensaver manager.

        Args:
            config: Config instance
            ha_client: HomeAssistantClient instance
            mode_handler: ModeHandler instance
            photo_manager: PhotoManager instance
        """
        self.config = config
        self.ha_client = ha_client
        self.mode_handler = mode_handler
        self.photo_manager = photo_manager
        self.screensaver_active = False
        self.running = False
        self.inotify = None
        self.current_mode = None  # Track current mode: 'day' or 'night'
        self.startup_time = time.time()  # Track when screensaver process started

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down")
        self.stop()
        sys.exit(0)

    def start(self) -> None:
        """Start the screensaver manager."""
        logger.info("Starting screensaver manager")
        self.running = True

        # Write slideshow config file for static HTTP server
        self._write_slideshow_config()

        # Generate initial photo list if it doesn't exist
        photo_list_path = self.config.get('paths', 'photo_list_json')
        if not os.path.exists(photo_list_path):
            logger.info("Generating initial photo list")
            self.photo_manager.generate_photo_list()

        # Start auto-regeneration scheduler
        self.photo_manager.start_auto_regeneration()

        # Setup inotify for input device monitoring
        self._setup_inotify()

        # Main event loop
        self._event_loop()

    def _setup_inotify(self) -> None:
        """Setup inotify to watch input devices."""
        try:
            self.inotify = INotify()
            input_devices = []

            # Find all input event devices
            for device in os.listdir('/dev/input'):
                if device.startswith('event'):
                    device_path = f'/dev/input/{device}'
                    try:
                        # Try to watch the device
                        wd = self.inotify.add_watch(device_path, flags.ACCESS)
                        input_devices.append(device_path)
                        logger.debug(f"Watching input device: {device_path}")
                    except PermissionError:
                        logger.warning(f"No permission to watch {device_path}")
                    except Exception as e:
                        logger.debug(f"Cannot watch {device_path}: {e}")

            if not input_devices:
                logger.error("No input devices found to monitor")
                raise RuntimeError("Cannot monitor input devices")

            logger.info(f"Monitoring {len(input_devices)} input devices")

        except Exception as e:
            logger.error(f"Failed to setup inotify: {e}")
            raise

    def _event_loop(self) -> None:
        """Main event loop for idle detection."""
        timeout = self.config.get('timing', 'idle_timeout', default=20)
        timeout_ms = timeout * 1000  # Convert to milliseconds

        # Check time boundary every minute (use shorter timeout)
        check_interval_ms = min(timeout_ms, 60000)  # Check at least every minute

        logger.info(f"Starting idle detection loop (timeout: {timeout}s)")
        self.last_activity_time = time.time()  # Make accessible to methods
        last_ha_poll_time = time.time()

        while self.running:
            # Wait for input events with shorter timeout for time checking
            events = self.inotify.read(timeout=check_interval_ms)

            if events:
                # Input detected
                self.last_activity_time = time.time()
                self._on_input_detected()
            else:
                # Check if enough time has passed since last activity
                elapsed = time.time() - self.last_activity_time

                if elapsed >= timeout:
                    # Idle timeout reached - ONLY activation path
                    self._on_idle_timeout()
                    # Reset timer after handling timeout
                    self.last_activity_time = time.time()

                # Poll HA state every 60 seconds for remote control (deactivation only)
                ha_poll_elapsed = time.time() - last_ha_poll_time
                if ha_poll_elapsed >= 60:
                    self._check_ha_state()
                    last_ha_poll_time = time.time()

                # Check for time-based mode transitions
                self._check_time_boundary()

    def _on_input_detected(self) -> None:
        """Handle input detection."""
        if self.screensaver_active:
            logger.info("Input detected, waking screensaver")
            if self.mode_handler.wake():
                self.screensaver_active = False
                self.current_mode = None
            else:
                logger.error("Failed to wake screensaver")

    def _on_idle_timeout(self) -> None:
        """Handle idle timeout - ONLY activation path for screensaver.

        This is the single code path that activates the screensaver.
        Checks HA state as go/no-go gate.
        If HA says disabled, resets idle timer and tries again next cycle.
        """
        if self.screensaver_active:
            # Already active, nothing to do
            # Screensaver stays active until user input, regardless of time
            return

        logger.info("Idle timeout detected")

        # Boot grace period: Don't activate screensaver during first 90 seconds after startup
        # This gives Wayland compositor time to fully initialize and prevents half-screen bug
        boot_grace_period = self.config.get('timing', 'boot_grace_period', default=90)
        time_since_startup = time.time() - self.startup_time
        if time_since_startup < boot_grace_period:
            logger.info(f"Within boot grace period ({int(time_since_startup)}s/{boot_grace_period}s) - resetting idle timer")
            self.last_activity_time = time.time()
            return

        # Check Home Assistant state as go/no-go gate
        # If HA says disabled, reset idle timer and try again next cycle
        if self.ha_client.is_screensaver_disabled():
            logger.info("Screensaver disabled via Home Assistant - resetting idle timer")
            self.last_activity_time = time.time()  # Reset timer like user input does
            return

        # HA says enabled (or not configured) - activate screensaver
        # Activate appropriate mode based on CURRENT time
        # Once activated, mode stays active until user touches screen or time boundary
        if self.mode_handler.is_day_mode():
            logger.info("Activating day mode (currently in day hours)")
            if self.mode_handler.activate_day_mode():
                self.screensaver_active = True
                self.current_mode = 'day'
            else:
                logger.error("Failed to activate day mode")
        else:
            logger.info("Activating night mode (currently in night hours)")
            if self.mode_handler.activate_night_mode():
                self.screensaver_active = True
                self.current_mode = 'night'
            else:
                logger.error("Failed to activate night mode")

    def _check_ha_state(self) -> None:
        """Poll Home Assistant state for remote deactivation.

        This allows remote control to DISABLE the screensaver via HA automation.
        Activation is handled exclusively by idle timeout (_on_idle_timeout).
        Polls every 60 seconds to detect when entity is turned ON remotely.
        """
        if not self.ha_client.enabled:
            return

        # Only check for deactivation - activation happens via idle timeout
        if self.ha_client.is_screensaver_disabled() and self.screensaver_active:
            # HA says disable screensaver, but it's currently active - wake it
            logger.info("HA entity turned ON remotely, deactivating screensaver")
            if self.mode_handler.wake():
                self.screensaver_active = False
                self.current_mode = None
            else:
                logger.error("Failed to wake screensaver")

    def _check_time_boundary(self) -> None:
        """Check if we've crossed day/night boundary and switch modes if needed.

        Only switches from day mode to night mode at the boundary.
        Does NOT auto-wake from night mode to day mode.
        """
        if not self.screensaver_active:
            # Not in screensaver, nothing to do
            return

        is_day_mode = self.mode_handler.is_day_mode()

        # Only auto-switch when crossing from day to night
        if self.current_mode == 'day' and not is_day_mode:
            logger.info("Day mode end time reached, switching to night mode")
            # Stop current slideshow and activate night mode
            if self.mode_handler.wake():  # Wake to stop slideshow
                time.sleep(0.5)
                if self.mode_handler.activate_night_mode():
                    self.current_mode = 'night'
                    logger.info("Successfully switched to night mode")
                else:
                    logger.error("Failed to activate night mode")
                    self.screensaver_active = False
                    self.current_mode = None
            else:
                logger.error("Failed to stop day mode")

        # Do NOT auto-switch from night to day - user must wake manually

    def _write_slideshow_config(self) -> None:
        """Write slideshow configuration to JSON file for static HTTP server."""
        try:
            # Get the static directory
            config_path = self.config.config_path
            if config_path:
                config_dir = os.path.dirname(os.path.abspath(config_path))
                static_dir = os.path.join(config_dir, 'static')
            else:
                static_dir = self.config.get('paths', 'static_dir', default=os.path.expanduser('~/kiosk-screensaver/static'))

            # Create slideshow config
            slideshow_config = {
                'slideshow_interval': self.config.get('timing', 'slideshow_interval', default=300)
            }

            # Write to static directory
            config_file = os.path.join(static_dir, 'slideshow-config.json')
            os.makedirs(static_dir, exist_ok=True)

            with open(config_file, 'w') as f:
                json.dump(slideshow_config, f)

            logger.info(f"Wrote slideshow config to {config_file}")

        except Exception as e:
            logger.warning(f"Failed to write slideshow config: {e}")

    def stop(self) -> None:
        """Stop the screensaver manager."""
        logger.info("Stopping screensaver manager")
        self.running = False

        # Wake if currently active
        if self.screensaver_active:
            self.mode_handler.wake()

        # Stop photo regeneration
        self.photo_manager.stop_auto_regeneration()

        # Cleanup inotify
        if self.inotify:
            self.inotify.close()

        logger.info("Screensaver manager stopped")

    def get_status(self) -> dict:
        """Get current status.

        Returns:
            Dict with status information
        """
        return {
            'running': self.running,
            'screensaver_active': self.screensaver_active,
            'is_day_mode': self.mode_handler.is_day_mode(),
            'photo_count': self.photo_manager.get_photo_count(),
            'ha_enabled': self.ha_client.enabled,
            'ha_connected': self.ha_client.test_connection()[0] if self.ha_client.enabled else None
        }
