from common.http_client import safe_get, DEFAULT_TIMEOUT

BASE_URL = "http://192.168.1.2:8001"


class Motor:
    def __init__(self, name):
        self.name = name

    def move(self, pos, timeout=DEFAULT_TIMEOUT):
        """Request the server to move the motor. Raises RuntimeError on failure."""
        safe_get(f"{BASE_URL}/move/{self.name}/{pos}", timeout=timeout)

    def read(self, timeout=DEFAULT_TIMEOUT):
        """Read the motor position. Raises RuntimeError on failure."""
        r = safe_get(f"{BASE_URL}/read/{self.name}", timeout=timeout)
        return r.json()["position"]

    def status(self, timeout=DEFAULT_TIMEOUT):
        """Check server status. Returns the response text or None if unreachable.

        This method catches network errors and returns None for a non-blocking
        availability check.
        """
        try:
            r = safe_get(f"{BASE_URL}/status", timeout=timeout)
            return r.text
        except RuntimeError:
            return None