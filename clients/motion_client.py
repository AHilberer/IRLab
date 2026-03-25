from common.http_client import safe_get, DEFAULT_TIMEOUT

BASE_URL = "http://192.168.1.2:8001"


def mv(*kwargs):
    """Function to send a motor to a new position. Usage: mv(sx, 10.0)"""
    if len(kwargs)//2 != 0:
        raise ValueError("mv() requires exactly 2 arguments: motor name and position")
    else:
        for i in range(0, len(kwargs), 2):
            motor = kwargs[i]
            pos = kwargs[i+1]
            # fire-and-forget move request
            safe_get(f"{BASE_URL}/mv/{motor}/{pos}", timeout=DEFAULT_TIMEOUT)

def umv(*kwargs):
    """Function to move a motor but shows continuously updated positions of motors. Usage: umv(sx, 10.0)"""
    if len(kwargs)//2 != 0:
        raise ValueError("umv() requires exactly 2 arguments: motor name and position")
    else:
        for i in range(0, len(kwargs), 2):
            motor = kwargs[i]
            pos = kwargs[i+1]

def wm(*kwargs):
    """Function to check the position of a motor. Usage: wm(sx) returns the position of motor sx."""
    for motor in kwargs:
        r = safe_get(f"{BASE_URL}/read/{motor}", timeout=DEFAULT_TIMEOUT)
        print(f"{motor} position: {r.json()['position']}")



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