"""Base scripts that are expected to be reused often.

This module centralizes common scan helpers (for example `ascan`) and related
utilities so operational scripts are in one place.
"""

import os
import sys
from contextlib import contextmanager
from typing import Iterator
from typing import Any

import h5py
import numpy as np

from clients.motion_client import mv, mvr, wm

if os.name != "nt":
    import termios
    import tty
else:
    import msvcrt


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
        mv(motor, float(x), show_positions=False)
    
    # Return to initial position
    mv(motor, initial_value, show_positions=False)

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
        mv(motor, float(x), show_positions=False)
    
    # Return to initial position
    mv(motor, initial_value, show_positions=False)

def save_hdf5(data, filename: str = "scan.h5"):
    """Save scan output in a simple HDF5 layout."""
    with h5py.File(filename, "w") as f:
        for i, point in enumerate(data):
            grp = f.create_group(f"point_{i}")
            grp["x"] = point["x"]
            grp["wavelength"] = point["spectrum"]["wavelength"]
            grp["intensity"] = point["spectrum"]["intensity"]


# Functions necessary for the interactive tweak mode, but not expected to be used directly by users, are defined here but prefixed with an underscore to indicate they are "private" helpers.
@contextmanager
def _raw_stdin_mode() -> Iterator[None]:
    if os.name == "nt":
        yield
        return

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key() -> str:
    if os.name == "nt":
        c1 = msvcrt.getwch()
        if c1 in {"\x00", "\xe0"}:
            c2 = msvcrt.getwch()
            mapping = {"H": "UP", "P": "DOWN", "M": "RIGHT", "K": "LEFT"}
            return mapping.get(c2, "UNKNOWN")
        if c1 in {"q", "Q"}:
            return "QUIT"
        if c1 in {"+", "="}:
            return "STEP_UP"
        if c1 == "-":
            return "STEP_DOWN"
        if c1 in {"a", "A"}:
            return "AXIS3_UP"
        if c1 in {"z", "Z"}:
            return "AXIS3_DOWN"
        return c1

    c1 = sys.stdin.read(1)
    if c1 == "\x1b":
        c2 = sys.stdin.read(1)
        c3 = sys.stdin.read(1)
        if c2 == "[" and c3 in "ABCD":
            return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}[c3]
        return "ESC"
    if c1 in {"q", "Q"}:
        return "QUIT"
    if c1 in {"+", "="}:
        return "STEP_UP"
    if c1 == "-":
        return "STEP_DOWN"
    if c1 in {"a", "A"}:
        return "AXIS3_UP"
    if c1 in {"z", "Z"}:
        return "AXIS3_DOWN"
    return c1


def _extract_wm_value(readback: dict, motor_name: str):
    value = readback.get(motor_name)
    if isinstance(value, dict):
        if "mm" in value:
            return value["mm"]
        if "steps" in value:
            return value["steps"]
    return value


def _motor_uses_mm(motor: Any) -> bool:
    step_to_mm = getattr(motor, "step_to_mm", 1.0)
    try:
        return float(step_to_mm) != 1.0
    except Exception:
        return False


def _motor_position_unit(motor: Any) -> str:
    return "mm" if _motor_uses_mm(motor) else "steps"


def _movement_delta_for_motor(motor: Any, delta: float) -> float:
    if _motor_uses_mm(motor):
        return float(delta)
    sign = -1.0 if delta < 0 else 1.0
    return sign * max(1, int(round(abs(delta))))


def tweak(*motors: Any, step: float = 0.01, step_scale: float = 2.0, min_step: float = 0.0001):
    """Interactive jog mode for 1, 2, or 3 motors using relative moves.

    Step values are expressed in millimetres for calibrated motors. Motors
    without calibration fall back to whole-step jogs.

    Controls:
    - Left/Right: axis 1
    - Up/Down: axis 2 (or axis 1 in one-axis mode)
    - a/z: axis 3 in three-axis mode
    - +/-: change step
    - q: quit
    """
    if step_scale <= 1:
        raise ValueError("step_scale>1")
    if len(motors) not in {1, 2, 3}:
        raise ValueError("tweak expects 1, 2, or 3 motors")

    names = [str(getattr(motor, "name", motor)) for motor in motors]
    current_step = max(float(step), float(min_step))
    min_step = float(min_step)

    positions = {name: 0.0 for name in names}
    try:
        readback = wm(*motors)
        for name in names:
            value = _extract_wm_value(readback, name)
            if isinstance(value, (int, float)):
                positions[name] = float(value)
    except Exception:
        pass

    def refresh_positions() -> None:
        try:
            readback = wm(*motors)
            for name in names:
                value = _extract_wm_value(readback, name)
                if isinstance(value, (int, float)):
                    positions[name] = float(value)
        except Exception:
            pass

    def render_status() -> None:
        refresh_positions()
        status_parts = [
            f"{name}={positions[name]:g} {_motor_position_unit(motor)}"
            for motor, name in zip(motors, names)
        ]
        msg = f"\rstep={current_step:g} mm | " + " | ".join(status_parts) + "      "
        sys.stdout.write(msg)
        sys.stdout.flush()

    def move(index: int, delta: float) -> None:
        motor = motors[index]
        name = names[index]
        effective_delta = _movement_delta_for_motor(motor, delta)
        try:
            mvr(motor, effective_delta, show_positions=False)
            positions[name] += effective_delta
        except Exception as exc:
            sys.stdout.write(f"\nMove error on {name}: {exc}\n")
            sys.stdout.flush()

    print("\nJog mode: arrows to move, +/- to change step, q to quit")
    if len(motors) == 1:
        print("1-axis mode: Left/Right and Up/Down control the same motor")
    if len(motors) == 3:
        print("3-axis mode: a/z keys control axis 3")
    print("Step is expressed in mm for calibrated motors; non-calibrated motors use whole steps.")
    print(f"Initial step: {current_step:g} mm\n")
    render_status()

    with _raw_stdin_mode():
        while True:
            key = _read_key()
            if key == "QUIT":
                break
            if key == "STEP_UP":
                current_step = max(min_step, current_step * step_scale)
                render_status()
                continue
            if key == "STEP_DOWN":
                current_step = max(min_step, current_step / step_scale)
                render_status()
                continue
            if key == "LEFT":
                move(0, -current_step)
                render_status()
                continue
            if key == "RIGHT":
                move(0, current_step)
                render_status()
                continue
            if key == "UP":
                if len(motors) == 1:
                    move(0, current_step)
                else:
                    move(1, current_step)
                render_status()
                continue
            if key == "DOWN":
                if len(motors) == 1:
                    move(0, -current_step)
                else:
                    move(1, -current_step)
                render_status()
                continue
            if key == "AXIS3_UP" and len(motors) == 3:
                move(2, current_step)
                render_status()
                continue
            if key == "AXIS3_DOWN" and len(motors) == 3:
                move(2, -current_step)
                render_status()

    print("\n\nLeaving jog mode")
    print(f"Final positions: {positions}")
    return positions



