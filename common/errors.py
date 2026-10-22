"""Exceptions shared by servers and clients."""


class ServerError(RuntimeError):
    """A device server answered a request with an HTTP error status.

    `detail` is the readable message sent by the server (FastAPI `detail`).
    """

    def __init__(self, url, status_code, detail):
        self.url = url
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{detail} (HTTP {status_code} from {url})")


class MotionError(RuntimeError):
    """A motor motion failed: target not reached, timeout, stopped, server unreachable..."""


class MotorBusyError(MotionError):
    """A motion was requested on a motor that is already moving (HTTP 409)."""
