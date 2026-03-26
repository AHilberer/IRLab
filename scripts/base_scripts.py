"""Base scripts that are expected to be reused often.

This module centralizes common scan helpers (for example `ascan`) and related
utilities so operational scripts are in one place.
"""

from typing import Any

import h5py
import numpy as np


def ascan(motor: Any, start: float, stop: float, npts: int):
    """Move `motor` through `npts` linearly spaced positions from start to stop."""
    from clients.motion_client import mv

    for x in np.linspace(start, stop, npts):
        mv(motor, float(x))


def save_hdf5(data, filename: str = "scan.h5"):
    """Save scan output in a simple HDF5 layout."""
    with h5py.File(filename, "w") as f:
        for i, point in enumerate(data):
            grp = f.create_group(f"point_{i}")
            grp["x"] = point["x"]
            grp["wavelength"] = point["spectrum"]["wavelength"]
            grp["intensity"] = point["spectrum"]["intensity"]



