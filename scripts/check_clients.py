"""Manual demo script to check client timeouts.

Usage:
    python3 scripts/check_clients.py

This is not a unit test — it only demonstrates how clients behave with
short timeouts and how to handle errors.
"""

from clients.motion_client import Motor
from clients.spectro_client import Spectrometer


def demo():
    print("Client demo with short timeouts")

    motor = Motor('sx')
    spectro = Spectrometer()

    # Test 1: status() — non-blocking, returns None if unreachable
    print('\n-- Checking status (timeout=0.5s)')
    m_status = motor.status(timeout=0.5)
    s_status = spectro.status(timeout=0.5)
    print(f"Motor status: {m_status}")
    print(f"Spectro status: {s_status}")

    # Test 2: read() and acquire() — should raise RuntimeError on timeout
    print('\n-- Trying read() and acquire() (timeout=0.001s to force timeout)')
    try:
        pos = motor.read(timeout=0.001)
        print(f"Position: {pos}")
    except RuntimeError as e:
        print(f"motor.read() failed as expected: {e}")

    try:
        data = spectro.acquire(exposure=0.1, timeout=0.001)
        print(f"Spectrum received (length): {len(data.get('intensity', []))}")
    except RuntimeError as e:
        print(f"spectro.acquire() failed as expected: {e}")


if __name__ == '__main__':
    demo()
