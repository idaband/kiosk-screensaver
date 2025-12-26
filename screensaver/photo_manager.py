"""Photo list generation and management."""
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import List
from urllib.parse import quote
import schedule
import threading
import time
import shutil


logger = logging.getLogger(__name__)


class PhotoManager:
    """Manages photo list generation and updates."""

    def __init__(self, config):
        """Initialize photo manager.

        Args:
            config: Config instance
        """
        self.config = config
        self.photo_list_path = config.get('paths', 'photo_list_json')
        self.auto_regenerate = config.get('features', 'auto_regenerate_photos', default=True)

        # Get schedule config (can be string or dict)
        schedule_config = config.get('features', 'regenerate_schedule', default={'day_of_week': '*', 'time': '02:00'})
        if isinstance(schedule_config, str):
            # Legacy cron format - convert to new format
            self.schedule_config = self._parse_cron(schedule_config)
        else:
            # New structured format
            self.schedule_config = schedule_config

        self.scheduler_thread = None
        self.scheduler_running = False

    def generate_photo_list(self) -> bool:
        """Generate photo list JSON file.

        Returns:
            True if successful
        """
        try:
            photo_path = self.config.get('network', 'photo_source_path')
            max_size_mb = self.config.get('photos', 'max_size_mb', default=10)
            extensions = self.config.get('photos', 'extensions', default=['jpg', 'jpeg', 'png', 'gif'])
            rclone_port = self.config.get('network', 'rclone_port', default=8090)

            if not os.path.exists(photo_path):
                logger.error(f"Photo source path does not exist: {photo_path}")
                return False

            logger.info(f"Generating photo list from {photo_path}")

            # Build find command for all extensions
            ext_args = []
            for i, ext in enumerate(extensions):
                if i > 0:
                    ext_args.extend(['-o', '-iname', f'*.{ext}'])
                else:
                    ext_args.extend(['-iname', f'*.{ext}'])

            # Find all photos under size limit
            cmd = ['find', photo_path, '-type', 'f'] + ext_args + ['-size', f'-{max_size_mb}M']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"find command failed: {result.stderr}")
                return False

            # Convert file paths to URLs
            photos = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                # Convert absolute path to relative path from photo_path
                rel_path = os.path.relpath(line, photo_path)
                # URL encode the path (handle spaces and special characters)
                encoded_path = quote(rel_path)
                url = f"http://127.0.0.1:{rclone_port}/{encoded_path}"
                photos.append(url)

            logger.info(f"Found {len(photos)} photos")

            # Write JSON file
            photo_data = {'photos': photos}
            temp_path = self.photo_list_path + '.tmp'

            with open(temp_path, 'w') as f:
                json.dump(photo_data, f)

            # Atomic rename
            os.replace(temp_path, self.photo_list_path)

            logger.info(f"Photo list written to {self.photo_list_path}")

            # Also copy to static folder for HTTP server access
            # Get static dir - use absolute path from config
            config_path = self.config.config_path
            if config_path:
                # Derive static dir from config path location
                config_dir = os.path.dirname(os.path.abspath(config_path))
                static_dir = os.path.join(config_dir, 'static')
            else:
                # Fallback to config value
                static_dir = self.config.get('paths', 'static_dir', default=os.path.expanduser('~/kiosk-screensaver/static'))

            static_photo_list = os.path.join(static_dir, 'photo-list.json')
            try:
                os.makedirs(static_dir, exist_ok=True)
                shutil.copy2(self.photo_list_path, static_photo_list)
                logger.info(f"Photo list also copied to {static_photo_list}")
            except Exception as e:
                logger.warning(f"Failed to copy photo list to static dir: {e}")

            return True

        except subprocess.TimeoutExpired:
            logger.error("Photo list generation timed out (>5 minutes)")
            return False
        except Exception as e:
            logger.error(f"Failed to generate photo list: {e}")
            return False

    def get_photo_count(self) -> int:
        """Get number of photos in current list.

        Returns:
            Number of photos or 0 if error
        """
        try:
            if not os.path.exists(self.photo_list_path):
                return 0

            with open(self.photo_list_path, 'r') as f:
                data = json.load(f)
                return len(data.get('photos', []))
        except Exception as e:
            logger.error(f"Failed to read photo count: {e}")
            return 0

    def _parse_cron(self, cron_str: str) -> dict:
        """Parse simple cron expression to schedule parameters.

        Args:
            cron_str: Cron expression (e.g., '0 2 * * *')

        Returns:
            Dict with schedule parameters {'day_of_week': str, 'time': str}
        """
        # Simple parser for common cron patterns
        parts = cron_str.split()
        if len(parts) != 5:
            logger.error(f"Invalid cron expression: {cron_str}")
            return {'day_of_week': '*', 'time': '02:00'}

        minute, hour, day, month, weekday = parts

        # Convert to new format
        time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"

        # Map weekday or use * for daily
        if weekday == '*':
            day_of_week = '*'
        else:
            # Cron uses 0=Sunday, we use 0=Monday, so convert
            day_of_week = str((int(weekday) + 6) % 7) if weekday.isdigit() else '*'

        return {'day_of_week': day_of_week, 'time': time_str}

    def start_auto_regeneration(self) -> None:
        """Start automatic photo list regeneration."""
        if not self.auto_regenerate:
            logger.info("Auto-regeneration disabled")
            return

        # Get schedule parameters
        day_of_week = self.schedule_config.get('day_of_week', '*')
        schedule_time = self.schedule_config.get('time', '02:00')

        # Schedule based on day_of_week
        if day_of_week == '*':
            # Daily schedule
            logger.info(f"Scheduling photo list regeneration daily at {schedule_time}")
            schedule.every().day.at(schedule_time).do(self.generate_photo_list)
        else:
            # Specific day of week (0=Monday, 6=Sunday)
            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_index = int(day_of_week)
            if 0 <= day_index <= 6:
                day_name = day_names[day_index]
                logger.info(f"Scheduling photo list regeneration every {day_name} at {schedule_time}")
                getattr(schedule.every(), day_name).at(schedule_time).do(self.generate_photo_list)
            else:
                logger.error(f"Invalid day_of_week: {day_of_week}, using daily schedule")
                schedule.every().day.at(schedule_time).do(self.generate_photo_list)

        # Start scheduler thread
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def _run_scheduler(self) -> None:
        """Run scheduler loop."""
        logger.info("Photo regeneration scheduler started")
        while self.scheduler_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    def stop_auto_regeneration(self) -> None:
        """Stop automatic regeneration."""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        schedule.clear()
        logger.info("Photo regeneration scheduler stopped")
