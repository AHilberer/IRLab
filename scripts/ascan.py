"""ascan helper moved out of IRLab_shell for better organization.

Provides a simple linear scan helper that uses the motion client's `mv` function.
This module is importable from `IRLab_shell.py` and can also be used standalone.
"""
from typing import Any


def ascan(motor: Any, start: float, stop: float, npts: int):
    """Move `motor` through `npts` positions linearly spaced between start and stop.

    motor: a Motor instance from clients.motion_client
    start/stop: numeric positions (interpreted by mv as mm when Motor.step_to_mm != 1.0)
    npts: number of points (inclusive)
    """
    # import locally to avoid importing client heavy modules at package import time
    import numpy as np
    from clients.motion_client import mv

    for x in np.linspace(start, stop, npts):
        mv(motor, float(x))


if __name__ == "__main__":
    print("ascan module: import from IRLab_shell or call ascan(motor, start, stop, npts) from scripts.ascan")
