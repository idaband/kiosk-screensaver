"""Configuration management for kiosk screensaver."""
import os
import yaml
from pathlib import Path
from typing import Any, Dict


class Config:
    """Manages configuration loading and validation."""

    def __init__(self, config_path: str = None):
        """Initialize configuration.

        Args:
            config_path: Path to YAML config file. If None, uses default locations.
        """
        if config_path is None:
            # Try default locations
            possible_paths = [
                Path.home() / "kiosk-screensaver" / "config.yaml",
                "/etc/kiosk-screensaver/config.yaml",
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = str(path)
                    break

            if config_path is None:
                raise FileNotFoundError("No config file found. Checked: " + ", ".join(map(str, possible_paths)))

        self.config_path = config_path
        self.data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate YAML configuration."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Expand user paths
            self._expand_paths(config)

            return config
        except Exception as e:
            raise ValueError(f"Failed to load config from {self.config_path}: {e}")

    def _expand_paths(self, config: Dict[str, Any]) -> None:
        """Expand ~ and environment variables in path configurations."""
        if 'paths' in config:
            for key, value in config['paths'].items():
                if isinstance(value, str):
                    config['paths'][key] = os.path.expanduser(value)

        if 'network' in config and 'photo_source_path' in config['network']:
            config['network']['photo_source_path'] = os.path.expanduser(
                config['network']['photo_source_path']
            )

        if 'network' in config and 'home_assistant' in config['network']:
            ha = config['network']['home_assistant']
            if 'token_file' in ha:
                ha['token_file'] = os.path.expanduser(ha['token_file'])

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get nested configuration value.

        Args:
            *keys: Nested keys to traverse (e.g., 'network', 'rclone_port')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        value = self.data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, *keys: str, value: Any) -> None:
        """Set nested configuration value.

        Args:
            *keys: Nested keys to traverse
            value: Value to set
        """
        data = self.data
        for key in keys[:-1]:
            if key not in data:
                data[key] = {}
            data = data[key]
        data[keys[-1]] = value

    def save(self) -> None:
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise IOError(f"Failed to save config to {self.config_path}: {e}")

    def reload(self) -> None:
        """Reload configuration from file."""
        self.data = self._load_config()

    def validate(self) -> list:
        """Validate configuration and return list of errors.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check required sections
        required_sections = ['timing', 'network', 'display', 'paths', 'features', 'photos', 'logging']
        for section in required_sections:
            if section not in self.data:
                errors.append(f"Missing required section: {section}")

        # Validate timing values
        timing = self.data.get('timing', {})
        if timing.get('idle_timeout', 0) <= 0:
            errors.append("timing.idle_timeout must be positive")
        if timing.get('slideshow_interval', 0) <= 0:
            errors.append("timing.slideshow_interval must be positive")

        # Validate time format (HHMM) if using new format, or hour format if using old
        start_time = timing.get('day_mode_start_time')
        night_time = timing.get('night_mode_start_time')

        if start_time:
            # New HHMM format
            try:
                time_val = int(start_time)
                if not (0 <= time_val <= 2359):
                    errors.append("timing.day_mode_start_time must be 0000-2359")
            except (ValueError, TypeError):
                errors.append("timing.day_mode_start_time must be valid HHMM format")

        if night_time:
            # Handle both old (string) and new (dict) formats
            if isinstance(night_time, dict):
                # New per-day format - validate each day
                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                for day in days:
                    day_time = night_time.get(day)
                    if day_time:
                        try:
                            time_val = int(day_time)
                            if not (0 <= time_val <= 2359):
                                errors.append(f"timing.night_mode_start_time.{day} must be 0000-2359")
                        except (ValueError, TypeError):
                            errors.append(f"timing.night_mode_start_time.{day} must be valid HHMM format")
            else:
                # Old single-value HHMM format
                try:
                    time_val = int(night_time)
                    if not (0 <= time_val <= 2359):
                        errors.append("timing.night_mode_start_time must be 0000-2359")
                except (ValueError, TypeError):
                    errors.append("timing.night_mode_start_time must be valid HHMM format")

        # Validate network ports
        network = self.data.get('network', {})
        for port_key in ['rclone_port', 'python_port', 'web_admin_port']:
            port = network.get(port_key, 0)
            if not (1 <= port <= 65535):
                errors.append(f"network.{port_key} must be 1-65535")

        # Note: We don't validate photo source path during install
        # The path might not be mounted yet, or might be configured later
        # The photo manager will handle missing paths gracefully at runtime

        # Note: We don't validate HA token file existence during install
        # The token can be set via the web interface after installation
        # The HA integration will gracefully handle missing token at runtime

        # Validate display brightness
        display = self.data.get('display', {})
        for brightness_key in ['dimmed_brightness', 'normal_brightness']:
            brightness = display.get(brightness_key, -1)
            if not (0 <= brightness <= 100):
                errors.append(f"display.{brightness_key} must be 0-100")

        # Validate photo parameters
        photos = self.data.get('photos', {})
        if photos.get('max_size_mb', 0) <= 0:
            errors.append("photos.max_size_mb must be positive")
        if not photos.get('extensions'):
            errors.append("photos.extensions cannot be empty")

        return errors


def load_config(config_path: str = None) -> Config:
    """Load configuration from file.

    Args:
        config_path: Path to config file (optional)

    Returns:
        Config instance
    """
    return Config(config_path)
