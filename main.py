from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Any, Iterator, SupportsFloat, cast

if os.name != "nt":
    import termios
    import tty
else:
    import msvcrt


@contextmanager
def raw_stdin_mode() -> Iterator[None]:
    if os.name == "nt":
        # Windows key capture with msvcrt does not require raw mode switching.
        yield
        return

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_key() -> str:
    if os.name == "nt":
        c1 = msvcrt.getwch()
        if c1 in {"\x00", "\xe0"}:
            c2 = msvcrt.getwch()
            mapping = {
                "H": "UP",
                "P": "DOWN",
                "M": "RIGHT",
                "K": "LEFT",
            }
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


def _motor_name(motor: Any) -> str:
    return str(getattr(motor, "name", motor))


def _motor_get_position(motor: Any) -> float | None:
    for attr in ("position", "pos"):
        if hasattr(motor, attr):
            value = getattr(motor, attr)
            if callable(value):
                try:
                    value = value()
                except TypeError:
                    continue
            if isinstance(value, (int, float, str)):
                try:
                    return float(value)
                except ValueError:
                    return None
            if hasattr(value, "__float__"):
                try:
                    return float(cast(SupportsFloat, value))
                except (TypeError, ValueError):
                    return None
            return None
    return None


def _motor_move_relative(motor: Any, delta: float) -> bool:
    for method_name in ("move_relative", "mvr"):
        method = getattr(motor, method_name, None)
        if callable(method):
            method(delta)
            return True
    return False


def tweak(
    *motors: Any,
    step: float = 2.0,
    step_scale: float = 2.0,
    min_step: float = 0.1,
) -> dict[str, float]:
    """Interactive tweak mode to drive 1, 2, or 3 motors.

    - 1 motor: Up/Down have the same effect as Left/Right.
    - 2 motors: Left/Right -> axis X, Up/Down -> axis Y.
    - 3 motors: plus a/z keys for axis 3.
    """
    if step <= 0 or step_scale <= 1 or min_step <= 0:
        raise ValueError("step>0, step_scale>1, min_step>0")
    if len(motors) not in {1, 2, 3}:
        raise ValueError("tweak expects 1, 2, or 3 motors")

    names = [_motor_name(motor) for motor in motors]
    current_step = step

    # Fallback local positions for motors without readable hardware position.
    positions = {name: (_motor_get_position(motor) or 0.0) for name, motor in zip(names, motors)}

    def render_status() -> None:
        for name, motor in zip(names, motors):
            motor_pos = _motor_get_position(motor)
            if motor_pos is not None:
                positions[name] = motor_pos

        status_parts = [f"{name}={positions[name]:g}" for name in names]
        msg = f"\rstep={current_step:g} | " + " | ".join(status_parts) + "      "
        sys.stdout.write(msg)
        sys.stdout.flush()

    def move(index: int, delta: float) -> None:
        motor = motors[index]
        name = names[index]
        moved = _motor_move_relative(motor, delta)
        if not moved:
            positions[name] += delta

    print("\nJog mode: arrows to move, +/- to change step, q to quit")
    if len(motors) == 1:
        print("1-axis mode: Left/Right and Up/Down control the same motor")
    if len(motors) == 3:
        print("3-axis mode: a/z keys control axis 3")
    print(f"Initial step: {current_step:g}\n")
    render_status()

    with raw_stdin_mode():
        while True:
            key = read_key()
            if key == "QUIT":
                break
            if key == "STEP_UP":
                current_step *= step_scale
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
