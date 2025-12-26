"""Main entry point for kiosk screensaver."""
import argparse
import logging
import logging.handlers
import os
import sys

from screensaver.config import load_config
from screensaver.ha_integration import HomeAssistantClient
from screensaver.manager import ScreensaverManager
from screensaver.modes import ModeHandler
from screensaver.photo_manager import PhotoManager
from screensaver.servers import HTTPServerManager


def setup_logging(config):
    """Setup logging configuration.

    Args:
        config: Config instance
    """
    log_file = config.get('paths', 'log_file', default='/tmp/kiosk-screensaver.log')
    log_level = config.get('logging', 'level', default='INFO')
    log_format = config.get('logging', 'format', default='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    max_size_mb = config.get('logging', 'max_size_mb', default=10)
    backup_count = config.get('logging', 'backup_count', default=3)

    # Create log directory if needed
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # File handler with rotation
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not setup file logging: {e}", file=sys.stderr)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)

    return logger


def validate_environment():
    """Validate required environment and permissions."""
    errors = []

    # Check if running on Wayland
    if not os.environ.get('WAYLAND_DISPLAY'):
        errors.append("WAYLAND_DISPLAY not set. Must run in Wayland session.")

    # Check for required commands
    required_commands = ['chromium', 'ddcutil', 'wlopm', 'rclone', 'pgrep', 'pkill']
    for cmd in required_commands:
        if os.system(f'which {cmd} > /dev/null 2>&1') != 0:
            errors.append(f"Required command not found: {cmd}")

    # Check input device permissions
    input_devices = [f'/dev/input/{d}' for d in os.listdir('/dev/input') if d.startswith('event')]
    if not input_devices:
        errors.append("No input devices found in /dev/input")
    else:
        # Check if at least one device is readable
        readable = any(os.access(device, os.R_OK) for device in input_devices)
        if not readable:
            errors.append("No permission to read input devices. Run as root or add user to 'input' group.")

    return errors


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Kiosk Screensaver Manager')
    parser.add_argument('-c', '--config', help='Path to config file', default=None)
    parser.add_argument('--validate', action='store_true', help='Validate config and exit')
    parser.add_argument('--generate-photos', action='store_true', help='Generate photo list and exit')
    parser.add_argument('--test-ha', action='store_true', help='Test Home Assistant connection and exit')
    parser.add_argument('--status', action='store_true', help='Show status and exit')

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config(args.config)
        print(f"Loaded config from: {config.config_path}")

        # Setup logging
        logger = setup_logging(config)
        logger.info("Kiosk Screensaver starting")
        logger.info(f"Config loaded from: {config.config_path}")

        # Validate configuration
        config_errors = config.validate()
        if config_errors:
            logger.error("Configuration validation failed:")
            for error in config_errors:
                logger.error(f"  - {error}")
            if not args.validate:
                sys.exit(1)

        if args.validate:
            if config_errors:
                print("Configuration validation FAILED:")
                for error in config_errors:
                    print(f"  ✗ {error}")
                sys.exit(1)
            else:
                print("✓ Configuration valid")
                sys.exit(0)

        # Validate environment
        env_errors = validate_environment()
        if env_errors:
            logger.error("Environment validation failed:")
            for error in env_errors:
                logger.error(f"  - {error}")
            if not (args.generate_photos or args.test_ha):
                sys.exit(1)

        # Initialize components
        ha_client = HomeAssistantClient(config)
        server_manager = HTTPServerManager(config)
        photo_manager = PhotoManager(config)
        mode_handler = ModeHandler(config, server_manager)

        # Handle special commands
        if args.test_ha:
            print("Testing Home Assistant connection...")
            success, message = ha_client.test_connection()
            if success:
                print(f"✓ {message}")
                sys.exit(0)
            else:
                print(f"✗ {message}")
                sys.exit(1)

        if args.generate_photos:
            print("Generating photo list...")
            if photo_manager.generate_photo_list():
                count = photo_manager.get_photo_count()
                print(f"✓ Generated list with {count} photos")
                sys.exit(0)
            else:
                print("✗ Failed to generate photo list")
                sys.exit(1)

        if args.status:
            manager = ScreensaverManager(config, ha_client, mode_handler, photo_manager)
            status = manager.get_status()
            print("Screensaver Status:")
            print(f"  Running: {status['running']}")
            print(f"  Screensaver Active: {status['screensaver_active']}")
            print(f"  Day Mode: {status['is_day_mode']}")
            print(f"  Photo Count: {status['photo_count']}")
            print(f"  HA Enabled: {status['ha_enabled']}")
            print(f"  HA Connected: {status['ha_connected']}")
            sys.exit(0)

        # Start screensaver manager
        manager = ScreensaverManager(config, ha_client, mode_handler, photo_manager)

        try:
            manager.start()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            manager.stop()
            server_manager.cleanup()

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
