"""HTTP server management for photo serving."""
import logging
import os
import signal
import subprocess
import time
import requests
from typing import Optional


logger = logging.getLogger(__name__)


class HTTPServerManager:
    """Manages rclone and Python HTTP servers."""

    def __init__(self, config):
        """Initialize server manager.

        Args:
            config: Config instance
        """
        self.config = config
        self.rclone_process = None
        self.python_process = None

    def is_rclone_running(self) -> bool:
        """Check if rclone server is running."""
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'rclone serve http'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_python_server_running(self) -> bool:
        """Check if Python HTTP server is running."""
        port = self.config.get('network', 'python_port', default=8091)
        try:
            result = subprocess.run(
                ['pgrep', '-f', f'python.*{port}'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_rclone(self) -> bool:
        """Start rclone HTTP server.

        Returns:
            True if started successfully
        """
        if self.is_rclone_running():
            logger.info("rclone server already running")
            return True

        try:
            photo_path = self.config.get('network', 'photo_source_path')
            host = self.config.get('network', 'rclone_host', default='127.0.0.1')
            port = self.config.get('network', 'rclone_port', default=8090)

            if not os.path.exists(photo_path):
                logger.error(f"Photo source path does not exist: {photo_path}")
                return False

            cmd = [
                'rclone', 'serve', 'http', photo_path,
                '--addr', f'{host}:{port}',
                '--read-only',
                '--no-modtime'
            ]

            logger.info(f"Starting rclone server: {' '.join(cmd)}")
            self.rclone_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait for server to be ready
            return self._wait_for_server(f'http://{host}:{port}', timeout=10)

        except Exception as e:
            logger.error(f"Failed to start rclone server: {e}")
            return False

    def start_python_server(self) -> bool:
        """Start Python HTTP server for slideshow HTML.

        Returns:
            True if started successfully
        """
        if self.is_python_server_running():
            logger.info("Python HTTP server already running")
            return True

        try:
            port = self.config.get('network', 'python_port', default=8091)

            # Serve from the static directory
            static_dir = os.path.dirname(self.config.get('paths', 'slideshow_html'))
            if not os.path.exists(static_dir):
                # Fall back to home directory
                static_dir = os.path.expanduser('~')

            logger.info(f"Starting Python HTTP server on port {port} from {static_dir}")
            self.python_process = subprocess.Popen(
                ['python3', '-m', 'http.server', str(port)],
                cwd=static_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait for server to be ready
            return self._wait_for_server(f'http://127.0.0.1:{port}', timeout=10)

        except Exception as e:
            logger.error(f"Failed to start Python server: {e}")
            return False

    def _wait_for_server(self, url: str, timeout: int = 10) -> bool:
        """Wait for HTTP server to become ready.

        Args:
            url: Server URL to check
            timeout: Maximum seconds to wait

        Returns:
            True if server responded within timeout
        """
        logger.info(f"Waiting for server at {url}")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=1)
                if response.status_code in [200, 404]:  # 404 is OK for directory listing
                    logger.info(f"Server ready at {url}")
                    return True
            except requests.exceptions.RequestException:
                pass

            time.sleep(0.5)

        logger.error(f"Server at {url} not ready after {timeout}s")
        return False

    def start_all(self) -> bool:
        """Start both rclone and Python servers.

        Returns:
            True if both started successfully
        """
        logger.info("Starting HTTP servers")

        rclone_ok = self.start_rclone()
        if not rclone_ok:
            logger.error("Failed to start rclone server")
            return False

        python_ok = self.start_python_server()
        if not python_ok:
            logger.error("Failed to start Python server")
            return False

        logger.info("All HTTP servers started successfully")
        return True

    def stop_rclone(self) -> None:
        """Stop rclone server."""
        if self.rclone_process:
            try:
                self.rclone_process.terminate()
                self.rclone_process.wait(timeout=5)
                logger.info("Stopped rclone server")
            except subprocess.TimeoutExpired:
                self.rclone_process.kill()
                logger.warning("Killed rclone server (timeout)")
            except Exception as e:
                logger.error(f"Error stopping rclone: {e}")
            finally:
                self.rclone_process = None

    def stop_python_server(self) -> None:
        """Stop Python HTTP server."""
        if self.python_process:
            try:
                self.python_process.terminate()
                self.python_process.wait(timeout=5)
                logger.info("Stopped Python HTTP server")
            except subprocess.TimeoutExpired:
                self.python_process.kill()
                logger.warning("Killed Python server (timeout)")
            except Exception as e:
                logger.error(f"Error stopping Python server: {e}")
            finally:
                self.python_process = None

    def stop_all(self) -> None:
        """Stop all HTTP servers."""
        logger.info("Stopping HTTP servers")
        self.stop_rclone()
        self.stop_python_server()

    def cleanup(self) -> None:
        """Cleanup on shutdown."""
        self.stop_all()
