"""Base scripts that are expected to be reused often.

This module centralizes common scan helpers (for example `ascan`) and related
utilities so operational scripts are in one place.
"""

from typing import Any

import h5py
import numpy as np

from clients.motion_client import mv, wm


def ascan(motor: Any, start: float, stop: float, npts: int):
    """Move `motor` through `npts` linearly spaced positions from start to stop.
    
    Returns the motor to its initial position after the scan completes.
    """
    # Read initial position
    initial_pos = wm(motor)
    initial_value = initial_pos[motor.name]
    if isinstance(initial_value, dict):
        initial_value = initial_value['mm'] if 'mm' in initial_value else initial_value['steps']
    
    # Perform scan
    for x in np.linspace(start, stop, npts):
        mv(motor, float(x))
    
    # Return to initial position
    mv(motor, initial_value)

def dscan(motor: Any, start_delta: float, stop_delta: float, npts: int):
    """Move `motor` through `npts` linearly spaced positions relative to the current position.
    
    `start_delta` and `stop_delta` are relative offsets from the current position.
    Returns the motor to its initial position after the scan completes.
    """
    # Read initial position
    initial_pos = wm(motor)
    initial_value = initial_pos[motor.name]
    if isinstance(initial_value, dict):
        initial_value = initial_value['mm'] if 'mm' in initial_value else initial_value['steps']
    
    # Calculate absolute positions
    start_abs = initial_value + start_delta
    stop_abs = initial_value + stop_delta
    
    # Perform scan with absolute positions
    for x in np.linspace(start_abs, stop_abs, npts):
        mv(motor, float(x))
    
    # Return to initial position
    mv(motor, initial_value)

def save_hdf5(data, filename: str = "scan.h5"):
    """Save scan output in a simple HDF5 layout."""
    with h5py.File(filename, "w") as f:
        for i, point in enumerate(data):
            grp = f.create_group(f"point_{i}")
            grp["x"] = point["x"]
            grp["wavelength"] = point["spectrum"]["wavelength"]
            grp["intensity"] = point["spectrum"]["intensity"]



