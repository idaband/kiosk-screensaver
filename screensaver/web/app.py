"""Flask web admin panel."""
import json
import logging
import os
import subprocess
from flask import Flask, render_template, request, jsonify, redirect, url_for
from functools import wraps

from screensaver.config import load_config
from screensaver.ha_integration import HomeAssistantClient
from screensaver.photo_manager import PhotoManager


logger = logging.getLogger(__name__)


def update_reboot_cron(enabled, frequency, day_of_week, reboot_time):
    """Update crontab with scheduled reboot.

    Args:
        enabled: Whether scheduled reboot is enabled
        frequency: 'daily' or 'weekly'
        day_of_week: 0-6 (0=Monday, 6=Sunday) for weekly reboots
        reboot_time: HHMM format string (e.g., '0300')
    """
    try:
        # Parse time from HHMM to hour and minute
        hour = int(reboot_time[:2])
        minute = int(reboot_time[2:])

        # Get current crontab
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        current_cron = result.stdout if result.returncode == 0 else ''

        # Remove any existing kiosk-screensaver reboot entries
        cron_lines = [
            line for line in current_cron.split('\n')
            if '# kiosk-screensaver reboot' not in line
        ]

        # Add new entry if enabled
        if enabled:
            if frequency == 'daily':
                # Daily reboot: minute hour * * * sudo /sbin/reboot
                cron_entry = f"{minute} {hour} * * * sudo /sbin/reboot # kiosk-screensaver reboot"
            else:  # weekly
                # Weekly reboot: minute hour * * day_of_week sudo /sbin/reboot
                cron_entry = f"{minute} {hour} * * {day_of_week} sudo /sbin/reboot # kiosk-screensaver reboot"

            cron_lines.append(cron_entry)

        # Write back to crontab
        new_cron = '\n'.join(line for line in cron_lines if line.strip())
        if new_cron and not new_cron.endswith('\n'):
            new_cron += '\n'

        # Update crontab
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
        process.communicate(input=new_cron)

        if process.returncode == 0:
            if enabled:
                logger.info(f"Scheduled reboot configured: {frequency} at {reboot_time}")
            else:
                logger.info("Scheduled reboot disabled")
            return True, "Crontab updated successfully"
        else:
            logger.error("Failed to update crontab")
            return False, "Failed to update crontab"

    except Exception as e:
        logger.error(f"Error updating reboot cron: {e}")
        return False, str(e)


def create_app(config_path=None):
    """Create Flask application.

    Args:
        config_path: Path to config file

    Returns:
        Flask app instance
    """
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    # Load config
    try:
        app.config['SCREENSAVER_CONFIG'] = load_config(config_path)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise

    config = app.config['SCREENSAVER_CONFIG']

    # Check if auth required
    auth_enabled = config.get('features', 'web_admin_auth', default=False)
    admin_password = config.get('features', 'web_admin_password', default='')

    def check_auth(password):
        """Check if password is valid."""
        return password == admin_password

    def requires_auth(f):
        """Decorator for routes requiring authentication."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not auth_enabled:
                return f(*args, **kwargs)

            auth = request.authorization
            if not auth or not check_auth(auth.password):
                return jsonify({'error': 'Authentication required'}), 401

            return f(*args, **kwargs)
        return decorated

    @app.route('/')
    @requires_auth
    def index():
        """Main admin page."""
        return render_template('index.html', config=config.data)

    @app.route('/api/config', methods=['GET'])
    @requires_auth
    def get_config():
        """Get current configuration."""
        return jsonify(config.data)

    @app.route('/api/config/slideshow', methods=['GET'])
    def get_slideshow_config():
        """Get slideshow configuration (no auth required for slideshow.html)."""
        return jsonify({
            'slideshow_interval': config.get('timing', 'slideshow_interval', default=300)
        })

    @app.route('/api/config', methods=['POST'])
    @requires_auth
    def update_config():
        """Update configuration."""
        try:
            updates = request.json
            if not updates:
                return jsonify({'error': 'No data provided'}), 400

            # Handle HA token separately if provided
            ha_token = updates.pop('ha_token', None)
            if ha_token:
                # Save token to file
                token_file = os.path.expanduser(config.get('network', 'home_assistant.token_file'))
                try:
                    os.makedirs(os.path.dirname(token_file), exist_ok=True)
                    with open(token_file, 'w') as f:
                        f.write(ha_token)
                    os.chmod(token_file, 0o600)  # Secure permissions
                    logger.info(f"Saved HA token to {token_file}")
                except Exception as e:
                    logger.error(f"Failed to save HA token: {e}")
                    return jsonify({'error': f'Failed to save token: {e}'}), 500

            # Update config
            for section, values in updates.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        config.set(section, key, value=value)
                else:
                    config.data[section] = values

            # Validate
            errors = config.validate()
            if errors:
                return jsonify({'error': 'Validation failed', 'details': errors}), 400

            # Save
            config.save()

            # Update scheduled reboot cron if config changed
            if 'features' in updates and 'scheduled_reboot' in updates['features']:
                reboot_config = updates['features']['scheduled_reboot']
                success, message = update_reboot_cron(
                    enabled=reboot_config.get('enabled', False),
                    frequency=reboot_config.get('frequency', 'weekly'),
                    day_of_week=reboot_config.get('day_of_week', 1),
                    reboot_time=reboot_config.get('reboot_time', '0300')
                )
                if not success:
                    logger.warning(f"Failed to update reboot cron: {message}")

            # Update labwc autostart if dashboard URL changed
            if 'display' in updates and 'dashboard_url' in updates['display']:
                new_url = updates['display']['dashboard_url'].strip()
                autostart_file = os.path.expanduser('~/.config/labwc/autostart')
                if os.path.exists(autostart_file):
                    try:
                        with open(autostart_file, 'r') as f:
                            content = f.read()

                        # Replace the dashboard URL in the chromium command
                        # Pattern matches any URL (valid or malformed) after --ignore-certificate-errors
                        import re
                        pattern = r'(chromium.*--ignore-certificate-errors\s+)([^\s&]+)(\s+&)'
                        replacement = r'\1' + new_url + r'\3'
                        new_content = re.sub(pattern, replacement, content)

                        with open(autostart_file, 'w') as f:
                            f.write(new_content)

                        logger.info(f"Updated dashboard URL in autostart to: {new_url}")
                    except Exception as e:
                        logger.error(f"Failed to update autostart file: {e}")

            # Write slideshow config for static HTTP server
            try:
                config_path = config.config_path
                if config_path:
                    config_dir = os.path.dirname(os.path.abspath(config_path))
                    static_dir = os.path.join(config_dir, 'static')
                else:
                    static_dir = os.path.expanduser('~/kiosk-screensaver/static')

                slideshow_config = {
                    'slideshow_interval': config.get('timing', 'slideshow_interval', default=300)
                }

                config_file = os.path.join(static_dir, 'slideshow-config.json')
                os.makedirs(static_dir, exist_ok=True)

                with open(config_file, 'w') as f:
                    json.dump(slideshow_config, f)

                logger.info(f"Wrote slideshow config to {config_file}")
            except Exception as e:
                logger.warning(f"Failed to write slideshow config: {e}")

            # Restart screensaver to apply changes
            try:
                # Kill existing screensaver processes
                subprocess.run(['pkill', '-f', 'screensaver.main'], check=False)
                logger.info("Screensaver process terminated for restart")
            except Exception as e:
                logger.warning(f"Failed to restart screensaver: {e}")

            return jsonify({'success': True, 'message': 'Configuration updated and screensaver will restart'})

        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/status', methods=['GET'])
    @requires_auth
    def get_status():
        """Get system status."""
        try:
            # Initialize components for status check
            ha_client = HomeAssistantClient(config)
            photo_manager = PhotoManager(config)

            photo_count = photo_manager.get_photo_count()
            ha_success, ha_message = ha_client.test_connection()

            status = {
                'photo_count': photo_count,
                'photo_list_exists': os.path.exists(config.get('paths', 'photo_list_json')),
                'ha_enabled': ha_client.enabled,
                'ha_connected': ha_success,
                'ha_message': ha_message,
                'config_path': config.config_path
            }

            return jsonify(status)

        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/photos/generate', methods=['POST'])
    @requires_auth
    def generate_photos():
        """Trigger photo list generation."""
        try:
            photo_manager = PhotoManager(config)
            if photo_manager.generate_photo_list():
                count = photo_manager.get_photo_count()
                return jsonify({
                    'success': True,
                    'message': f'Generated list with {count} photos'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to generate photo list'
                }), 500

        except Exception as e:
            logger.error(f"Failed to generate photos: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ha/test', methods=['GET'])
    @requires_auth
    def test_ha():
        """Test Home Assistant connection."""
        try:
            ha_client = HomeAssistantClient(config)
            success, message = ha_client.test_connection()

            return jsonify({
                'success': success,
                'message': message
            })

        except Exception as e:
            logger.error(f"Failed to test HA: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/validate', methods=['POST'])
    @requires_auth
    def validate_config():
        """Validate current configuration."""
        try:
            errors = config.validate()

            return jsonify({
                'valid': len(errors) == 0,
                'errors': errors
            })

        except Exception as e:
            logger.error(f"Failed to validate config: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/reboot', methods=['POST'])
    @requires_auth
    def reboot_system():
        """Reboot the system."""
        try:
            logger.info("Reboot requested via web interface")
            # Use subprocess to trigger reboot in background
            subprocess.Popen(['sudo', 'reboot'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return jsonify({'success': True, 'message': 'System rebooting'})

        except Exception as e:
            logger.error(f"Failed to reboot: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ha/token', methods=['POST'])
    @requires_auth
    def save_ha_token():
        """Save Home Assistant token to file."""
        try:
            data = request.json
            token = data.get('token')

            if not token:
                return jsonify({'error': 'No token provided'}), 400

            # Get token file path from config, with default fallback
            token_file_path = config.get('network', 'home_assistant.token_file', default='~/.ha_token')

            if not token_file_path:
                token_file_path = '~/.ha_token'

            token_file = os.path.expanduser(token_file_path)

            # Save token to file
            try:
                # Create parent directory if needed
                token_dir = os.path.dirname(token_file)
                if token_dir:
                    os.makedirs(token_dir, exist_ok=True)

                with open(token_file, 'w') as f:
                    f.write(token)
                os.chmod(token_file, 0o600)  # Secure permissions
                logger.info(f"Saved HA token to {token_file}")

                return jsonify({'success': True, 'message': 'Token saved successfully'})

            except Exception as e:
                logger.error(f"Failed to save HA token: {e}")
                return jsonify({'error': f'Failed to save token: {e}'}), 500

        except Exception as e:
            logger.error(f"Failed to process token save: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ha/entity-status', methods=['GET'])
    @requires_auth
    def get_entity_status():
        """Get current state of Home Assistant entity."""
        try:
            ha_client = HomeAssistantClient(config)

            if not ha_client.enabled:
                return jsonify({'success': False, 'message': 'Home Assistant not enabled'})

            # Get entity state
            entity_id = config.get('network', 'home_assistant.entity')
            state = ha_client.get_entity_state()

            if state is not None:
                return jsonify({
                    'success': True,
                    'entity_id': entity_id,
                    'state': state
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Unable to get entity state'
                })

        except Exception as e:
            logger.error(f"Failed to get entity status: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    return app


def run_web_admin(config_path=None, host='0.0.0.0', port=5000):
    """Run web admin server.

    Args:
        config_path: Path to config file
        host: Host to bind to
        port: Port to listen on
    """
    app = create_app(config_path)
    logger.info(f"Starting web admin on {host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_web_admin(config_path)
