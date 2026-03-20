from common.http_client import safe_get, DEFAULT_TIMEOUT

BASE_URL = "http://192.168.1.2:8002"


class Spectrometer:
    def acquire(self, exposure=0.1, timeout=DEFAULT_TIMEOUT):
        r = safe_get(f"{BASE_URL}/acquire", params={"exposure": exposure}, timeout=timeout)
        return r.json()

    def status(self, timeout=DEFAULT_TIMEOUT):
        try:
            r = safe_get(f"{BASE_URL}/status", timeout=timeout)
            return r.text
        except RuntimeError:
            return None