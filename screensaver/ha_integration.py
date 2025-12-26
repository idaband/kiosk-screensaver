"""Home Assistant integration for screensaver control."""
import logging
import os
import requests
from typing import Optional


logger = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for Home Assistant API."""

    def __init__(self, config):
        """Initialize Home Assistant client.

        Args:
            config: Config instance
        """
        self.config = config
        self.enabled = config.get('network', 'home_assistant', 'enabled', default=False)
        self.url = config.get('network', 'home_assistant', 'url')
        self.entity = config.get('network', 'home_assistant', 'entity')

        # Get token file path with default fallback and expansion
        token_file_path = config.get('network', 'home_assistant', 'token_file', default='~/.ha_token')
        if not token_file_path:
            token_file_path = '~/.ha_token'
        self.token_file = os.path.expanduser(token_file_path)

        self.timeout = config.get('network', 'home_assistant', 'api_timeout', default=5)
        self.fail_safe_enable = config.get('network', 'home_assistant', 'fail_safe_enable', default=True)
        self.token = None

        if self.enabled:
            self._load_token()

    def _load_token(self) -> None:
        """Load authentication token from file."""
        try:
            if self.token_file and os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    self.token = f.read().strip()
                logger.info(f"Loaded HA token from {self.token_file}")
            else:
                logger.warning(f"HA token file not found: {self.token_file}")
        except Exception as e:
            logger.error(f"Failed to load HA token: {e}")

    def is_screensaver_disabled(self) -> bool:
        """Check if screensaver is disabled via Home Assistant.

        Returns:
            True if screensaver should be disabled, False if it should activate
        """
        if not self.enabled:
            logger.debug("HA integration disabled, screensaver will activate")
            return False

        if not self.token:
            logger.warning("No HA token available, using fail-safe mode")
            return not self.fail_safe_enable

        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            api_url = f"{self.url}/api/states/{self.entity}"

            response = requests.get(
                api_url,
                headers=headers,
                timeout=self.timeout,
                verify=False  # Allow self-signed certs
            )

            if response.status_code == 200:
                data = response.json()
                state = data.get('state', '')
                logger.debug(f"HA entity {self.entity} state: {state}")

                # Only disable screensaver if state is explicitly "on"
                if state == 'on':
                    logger.info("Screensaver disabled via HA helper")
                    return True
                else:
                    logger.debug("HA helper not 'on', screensaver will activate")
                    return False
            else:
                logger.warning(f"HA API returned status {response.status_code}")
                return not self.fail_safe_enable

        except requests.exceptions.Timeout:
            logger.warning("HA API timeout, using fail-safe mode")
            return not self.fail_safe_enable
        except Exception as e:
            logger.error(f"HA API error: {e}, using fail-safe mode")
            return not self.fail_safe_enable

    def get_entity_state(self) -> Optional[dict]:
        """Get full entity state from Home Assistant.

        Returns:
            Entity state dict or None if error
        """
        if not self.enabled or not self.token:
            return None

        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            api_url = f"{self.url}/api/states/{self.entity}"

            response = requests.get(
                api_url,
                headers=headers,
                timeout=self.timeout,
                verify=False
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get entity state: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Failed to get entity state: {e}")
            return None

    def test_connection(self) -> tuple:
        """Test Home Assistant connection.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.enabled:
            return False, "HA integration disabled in config"

        if not self.token:
            return False, f"Token file not found: {self.token_file}"

        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            api_url = f"{self.url}/api/"

            response = requests.get(
                api_url,
                headers=headers,
                timeout=self.timeout,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                message = data.get('message', 'Connected')
                return True, f"Connected to Home Assistant: {message}"
            else:
                return False, f"HTTP {response.status_code}: {response.text}"

        except requests.exceptions.Timeout:
            return False, f"Connection timeout after {self.timeout}s"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
