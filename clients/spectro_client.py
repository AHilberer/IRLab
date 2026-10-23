from common.http_client import safe_get, safe_post, DEFAULT_TIMEOUT
from common.servers import get_server_url, is_server_disabled

BASE_URL = get_server_url('spectro_server', env_var='SPECTRO_SERVER', default='http://127.0.0.1:8002')
# Extra time (s) allowed beyond the exposure for an acquisition request (readout, transfer)
ACQUIRE_TIMEOUT_MARGIN = 10.0


class Spectrometer:
    def __init__(self, timeout_margin=ACQUIRE_TIMEOUT_MARGIN):
        self.timeout_margin = timeout_margin

    def acquire(self, exposure=0.1, timeout=None):
        """Acquire a spectrum. `timeout=None` (default) waits for exposure + timeout_margin seconds."""
        if is_server_disabled('spectro_server'):
            raise RuntimeError('The spectrometer server is disabled (disabled_servers in config/servers.yaml)')
        if timeout is None:
            timeout = float(exposure) + self.timeout_margin
        r = safe_post(f"{BASE_URL}/acquire", json={"exposure": exposure}, timeout=timeout)
        return r.json()

    def status(self, timeout=DEFAULT_TIMEOUT):
        try:
            r = safe_get(f"{BASE_URL}/status", timeout=timeout)
            return r.text
        except RuntimeError:
            return None