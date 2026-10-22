"""Common HTTP helper utilities for simple GET requests with timeouts.

This centralizes the small `safe_get` helper used by multiple
clients so that behavior (default timeout, error handling) is consistent
project-wide.
"""

import requests
from requests import exceptions as req_exceptions

from common.errors import ServerError

# Default timeout for connection/response (seconds)
DEFAULT_TIMEOUT = 5


def _request(method, url, timeout, **kwargs):
    try:
        r = requests.request(method, url, timeout=timeout, **kwargs)
    except req_exceptions.Timeout as e:
        raise RuntimeError(f"Timeout connecting to {url}: {e}")
    except req_exceptions.RequestException as e:
        raise RuntimeError(f"Connection error to {url}: {e}")
    if not r.ok:
        try:
            detail = r.json().get('detail', r.text)
        except Exception:
            detail = r.text
        raise ServerError(url, r.status_code, detail)
    return r


def safe_get(url, timeout=DEFAULT_TIMEOUT, **kwargs):
    """Perform a GET request with a timeout and wrap errors.

    Returns the requests.Response on success. Raises RuntimeError for
    timeouts and other request-related exceptions, and ServerError (a
    RuntimeError carrying the server's `detail`) for HTTP error statuses,
    so callers can handle them uniformly.
    """
    return _request('GET', url, timeout, **kwargs)


__all__ = ["safe_get", "DEFAULT_TIMEOUT"]
