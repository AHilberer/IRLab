from common.http_client import safe_get, safe_post, DEFAULT_TIMEOUT
from common.servers import get_server_url
from common.errors import ServerError, MotionError, MotorBusyError
import os
try:
    import yaml
except Exception:
    yaml = None

BASE_URL = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
# Default max duration of a move, used until the motor's own value (from the
# server's /motors/list) is known. Same default as the motion server.
DEFAULT_MAX_MOVE_DURATION = 120.0
# Extra time (s) the client waits beyond the server's max move duration, so the
# server reports its own timeout/stop before the HTTP request gives up.
MOTION_TIMEOUT_MARGIN = 30.0
# timeout='auto' (default of mv/mvr): max_move_duration of the motor + MOTION_TIMEOUT_MARGIN
DEFAULT_MOTION_TIMEOUT = 'auto'


def build_motor_list_from_config(path: str = None, register_on_server: bool = True):
    """Load local motor definitions from a YAML file and optionally register them on the motion server.

    Returns a dict mapping motor name -> Motor instance.
    """
    if path is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'config', 'motors.yaml')
        path = os.path.normpath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Motor config not found: {path}")
    if yaml is None:
        raise RuntimeError('pyyaml is required to load motor config')
    with open(path, 'r') as fh:
        cfg = yaml.safe_load(fh)

    motors = {}
    for entry in cfg.get('motors', []):
        name = entry.get('name')
        controller = entry.get('controller') or entry.get('controller_name')
        axis = int(entry.get('controller_channel') or entry.get('controler_channel') or entry.get('axis'))
        step = float(entry.get('step_to_mm', 1.0))
        velocity = entry.get('velocity')
        acceleration = entry.get('acceleration')
        m = Motor(name=name,
                  controler_type='PS90',
                  controler_channel=axis,
                  velocity=velocity or 1.0,
                  acceleration=acceleration or 1.0,
                  step_to_mm=step,
                  controller_name=controller,
                  max_move_duration=float(entry.get('max_move_duration', DEFAULT_MAX_MOVE_DURATION)))
        motors[name] = m
        if register_on_server:
            # register on server using generic motors/register endpoint
            params = []
            params.append(f"name={name}")
            params.append(f"axis={axis}")
            params.append(f"step_to_mm={step}")
            if controller:
                params.append(f"controller_name={controller}")
            controller_type = entry.get('controller_type') or entry.get('controler_type')
            if controller_type:
                # include controller_type only if no controller name specified (simple behavior: server expects controller_name)
                params.append(f"controller_type={controller_type}")
            url = f"{BASE_URL}/motors/register?{'&'.join(params)}"
            safe_get(url, timeout=DEFAULT_TIMEOUT)
    return motors


def _read_motor_position(motor):
    r = safe_get(f"{BASE_URL}/motors/read/{motor.name}", timeout=DEFAULT_TIMEOUT)
    data = r.json()
    steps = data.get('position')
    if steps is None:
        return None
    try:
        mm = float(steps) * float(motor.step_to_mm)
    except Exception:
        mm = None
    if mm is None:
        return {'steps': steps}
    return {'steps': steps, 'mm': mm}


def _move_timeout(motor, timeout):
    """HTTP timeout for a move request of `motor`."""
    if timeout == 'auto':
        return float(getattr(motor, 'max_move_duration', DEFAULT_MAX_MOVE_DURATION)) + MOTION_TIMEOUT_MARGIN
    return timeout


def _motion_error(motor, exc):
    """Convert a failed move request into a MotionError with a readable message."""
    if isinstance(exc, ServerError):
        if exc.status_code == 409:
            return MotorBusyError(str(exc.detail))
        return MotionError(str(exc.detail))
    return MotionError(f"Motor {motor.name}: {exc}")


def _stop_on_interrupt(motors):
    print(f"\nInterrupted: stopping {', '.join(m.name for m in motors)}")
    stop(*motors)


def _collect_positions(motors):
    positions = {}
    for motor in motors:
        try:
            positions[motor.name] = _read_motor_position(motor)
        except Exception:
            positions[motor.name] = None
    return positions


def mv(*args, show_positions: bool = True, timeout=DEFAULT_MOTION_TIMEOUT, raise_on_error: bool = True):
    """Move one or more motors. Usage: mv(motor1, pos1, motor2, pos2, ...)

    Each motor argument must be a `Motor` instance and each position a number.
    Positions are interpreted as millimetres if the Motor has a non-default step_to_mm; otherwise as steps.
    `timeout='auto'` (default) waits for the motor's max move duration plus
    MOTION_TIMEOUT_MARGIN; a number sets it in seconds; `timeout=None` waits
    indefinitely for the server response.
    A failed move raises MotionError (remaining motors are not moved); with
    `raise_on_error=False` errors are returned in the results list instead.
    Ctrl+C stops the motors and re-raises KeyboardInterrupt.
    """
    if len(args) % 2 != 0:
        raise ValueError("mv requires pairs of (Motor, position)")

    motors = []
    for i in range(0, len(args), 2):
        motor = args[i]
        pos = args[i+1]
        if not isinstance(motor, Motor) or not isinstance(pos, (int, float)):
            raise ValueError("Arguments must alternate Motor instance and numeric position")
        motors.append(motor)

    initial_positions = _collect_positions(motors)
    if show_positions:
        print(f"Initial positions: {initial_positions}")

    results = []
    for i in range(0, len(args), 2):
        motor = args[i]
        pos = args[i+1]

        # convert mm -> steps when appropriate
        if isinstance(pos, float) or motor.step_to_mm != 1.0:
            # interpret as mm; step_to_mm is mm per step
            try:
                steps = int(round(pos / motor.step_to_mm))
            except Exception:
                steps = int(pos)
        else:
            steps = int(pos)

        try:
            r = safe_get(f"{BASE_URL}/motors/move_abs/{motor.name}/{int(steps)}", timeout=_move_timeout(motor, timeout))
            results.append((motor.name, r.json()))
        except KeyboardInterrupt:
            _stop_on_interrupt(motors)
            raise
        except Exception as e:
            if raise_on_error:
                raise _motion_error(motor, e) from e
            results.append((motor.name, {'error': str(e)}))

    if show_positions:
        final_positions = _collect_positions(motors)
        print(f"Final positions: {final_positions}")

    return results

def mvr(*args, show_positions: bool = True, timeout=DEFAULT_MOTION_TIMEOUT, raise_on_error: bool = True):
    """Move one or more motors relative to current position. Usage: mvr(motor1, delta1, motor2, delta2, ...)

    Each motor argument must be a `Motor` instance and each delta a number.
    Deltas are interpreted as millimetres if the Motor has a non-default step_to_mm; otherwise as steps.
    `timeout='auto'` (default) waits for the motor's max move duration plus
    MOTION_TIMEOUT_MARGIN; a number sets it in seconds; `timeout=None` waits
    indefinitely for the server response.
    A failed move raises MotionError (remaining motors are not moved); with
    `raise_on_error=False` errors are returned in the results list instead.
    Ctrl+C stops the motors and re-raises KeyboardInterrupt.
    """
    if len(args) % 2 != 0:
        raise ValueError("mvr requires pairs of (Motor, delta)")

    motors = []
    for i in range(0, len(args), 2):
        motor = args[i]
        delta = args[i+1]
        if not isinstance(motor, Motor) or not isinstance(delta, (int, float)):
            raise ValueError("Arguments must alternate Motor instance and numeric delta")
        motors.append(motor)

    initial_positions = _collect_positions(motors)
    if show_positions:
        print(f"Initial positions: {initial_positions}")

    results = []
    for i in range(0, len(args), 2):
        motor = args[i]
        delta = args[i+1]

        # convert mm -> steps when appropriate
        if isinstance(delta, float) or motor.step_to_mm != 1.0:
            # interpret as mm; step_to_mm is mm per step
            try:
                steps = int(round(delta / motor.step_to_mm))
            except Exception:
                steps = int(delta)
        else:
            steps = int(delta)

        try:
            r = safe_get(f"{BASE_URL}/motors/move_rel/{motor.name}/{int(steps)}", timeout=_move_timeout(motor, timeout))
            results.append((motor.name, r.json()))
        except KeyboardInterrupt:
            _stop_on_interrupt(motors)
            raise
        except Exception as e:
            if raise_on_error:
                raise _motion_error(motor, e) from e
            results.append((motor.name, {'error': str(e)}))

    if show_positions:
        final_positions = _collect_positions(motors)
        print(f"Final positions: {final_positions}")

    return results

def wm(*motors):
    """Query positions for the provided Motor instances.

    Returns a dict name -> {'steps': int, 'mm': float} when step_to_mm is known, otherwise name->steps.
    """
    positions = {}
    for motor in motors:
        if not isinstance(motor, Motor):
            raise ValueError("Arguments must be Motor instances")
        try:
            positions[motor.name] = _read_motor_position(motor)
        except Exception:
            positions[motor.name] = None
    return positions


def free(*motors):
    """Release one or more motors. Usage: free(motor1, motor2, ...)"""
    results = []
    for motor in motors:
        if not isinstance(motor, Motor):
            raise ValueError("Arguments must be Motor instances")
        try:
            r = safe_get(f"{BASE_URL}/motors/free/{motor.name}", timeout=DEFAULT_TIMEOUT)
            results.append((motor.name, r.json()))
        except Exception as e:
            results.append((motor.name, {'error': str(e)}))
    return results


def control(*motors):
    """Re-acquire control of one or more motors. Usage: control(motor1, motor2, ...)"""
    results = []
    for motor in motors:
        if not isinstance(motor, Motor):
            raise ValueError("Arguments must be Motor instances")
        try:
            r = safe_get(f"{BASE_URL}/motors/control/{motor.name}", timeout=DEFAULT_TIMEOUT)
            results.append((motor.name, r.json()))
        except Exception as e:
            results.append((motor.name, {'error': str(e)}))
    return results


def stop(*motors):
    """Stop one or more motors immediately. Usage: stop(motor1, motor2, ...)

    Never raises on a server error (it is used while handling Ctrl+C):
    failures are printed and returned in the results list.
    """
    results = []
    for motor in motors:
        if not isinstance(motor, Motor):
            raise ValueError("Arguments must be Motor instances")
        try:
            r = safe_post(f"{BASE_URL}/motors/stop/{motor.name}", timeout=DEFAULT_TIMEOUT)
            results.append((motor.name, r.json()))
        except Exception as e:
            print(f"[WARN] Failed to stop motor {motor.name}: {e}")
            results.append((motor.name, {'error': str(e)}))
    return results


def stop_all():
    """Stop all axes of all controllers of the motion server."""
    try:
        r = safe_post(f"{BASE_URL}/motors/stop_all", timeout=DEFAULT_TIMEOUT)
        return r.json()
    except Exception as e:
        print(f"[WARN] stop_all failed: {e}")
        return {'error': str(e)}


def free_all_motors():
    """Release all motors currently registered on the motion server."""
    try:
        r = safe_get(f"{BASE_URL}/motors/list", timeout=DEFAULT_TIMEOUT)
        data = r.json()
        motor_names = [entry.get('name') for entry in data.get('motors', []) if entry.get('name')]
    except Exception as e:
        return [('_list_motors', {'error': str(e)})]

    results = []
    for motor_name in motor_names:
        try:
            resp = safe_get(f"{BASE_URL}/motors/free/{motor_name}", timeout=DEFAULT_TIMEOUT)
            results.append((motor_name, resp.json()))
        except Exception as e:
            results.append((motor_name, {'error': str(e)}))

    return results


def control_all_motors():
    """Re-acquire control of all motors currently registered on the motion server."""
    try:
        r = safe_get(f"{BASE_URL}/motors/list", timeout=DEFAULT_TIMEOUT)
        data = r.json()
        motor_names = [entry.get('name') for entry in data.get('motors', []) if entry.get('name')]
    except Exception as e:
        return [('_list_motors', {'error': str(e)})]

    results = []
    for motor_name in motor_names:
        try:
            resp = safe_get(f"{BASE_URL}/motors/control/{motor_name}", timeout=DEFAULT_TIMEOUT)
            results.append((motor_name, resp.json()))
        except Exception as e:
            results.append((motor_name, {'error': str(e)}))

    return results


class Motor:
    def __init__(self,
                 name,
                 controler_type="PS90",
                 controler_channel=1,
                 velocity=1.0,
                 acceleration=1.0,
                 step_to_mm=1.0,
                 controller_name: str = None,
                 max_move_duration=DEFAULT_MAX_MOVE_DURATION):
        self.name = name
        self.controler_type = controler_type
        self.controler_channel = controler_channel
        self.velocity = velocity
        self.acceleration = acceleration
        # mm per step (so steps -> mm = steps * step_to_mm). Default 1.0 preserves old behaviour.
        self.step_to_mm = step_to_mm
        # optional controller name (for registration or reference)
        self.controller_name = controller_name
        # server-side max duration of a move (s), used for the client HTTP timeout
        self.max_move_duration = max_move_duration