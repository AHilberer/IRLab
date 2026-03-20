"""Common HTTP helper utilities for simple GET requests with timeouts.

This centralizes the small `_safe_get` helper used by multiple clients so
that behavior (default timeout, error handling) is consistent project-wide.
"""

import requests
from requests import exceptions as req_exceptions

# Default timeout for connection/response (seconds)
DEFAULT_TIMEOUT = 5


def safe_get(url, timeout=DEFAULT_TIMEOUT, **kwargs):
    """Perform a GET request with a timeout and wrap network errors.

    Returns the requests.Response on success. Raises RuntimeError for
    timeouts and other request-related exceptions so callers can handle
    them uniformly.
    """
    try:
        return requests.get(url, timeout=timeout, **kwargs)
    except req_exceptions.Timeout as e:
        raise RuntimeError(f"Timeout connecting to {url}: {e}")
    except req_exceptions.RequestException as e:
        raise RuntimeError(f"Connection error to {url}: {e}")


__all__ = ["safe_get", "DEFAULT_TIMEOUT"]
