import warnings

from common.http_client import safe_get, safe_post, DEFAULT_TIMEOUT
from common.servers import get_server_url
from common.errors import ServerError, MotionError, MotorBusyError

BASE_URL = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
# Default max duration of a move, used until the motor's own value (from the
# server's /motors/list) is known. Same default as the motion server.
DEFAULT_MAX_MOVE_DURATION = 120.0
# Extra time (s) the client waits beyond the server's max move duration, so the
# server reports its own timeout/stop before the HTTP request gives up.
MOTION_TIMEOUT_MARGIN = 30.0
# timeout='auto' (default of mv/mvr): max_move_duration of the motor + MOTION_TIMEOUT_MARGIN
DEFAULT_MOTION_TIMEOUT = 'auto'


def load_motors_from_server(timeout=DEFAULT_TIMEOUT):
    """Create the Motor objects from the motion server's /motors/list (the single
    source of truth). Returns a dict name -> Motor. Raises if the server is unreachable."""
    r = safe_get(f"{BASE_URL}/motors/list", timeout=timeout)
    motors = {}
    for entry in r.json().get('motors', []):
        name = entry.get('name')
        if not name:
            continue
        motors[name] = Motor(name=name,
                             controller_channel=entry.get('axis'),
                             step_to_mm=float(entry.get('step_to_mm', 1.0)),
                             controller_name=entry.get('controller'),
                             max_move_duration=float(entry.get('max_move_duration', DEFAULT_MAX_MOVE_DURATION)),
                             unit=entry.get('unit'))
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
    Positions are always in the motor's unit (`motor.unit`: mm, deg, steps...).
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

        steps = motor.to_steps(pos)   # value in the motor's unit -> steps

        try:
            r = safe_post(f"{BASE_URL}/motors/move_abs/{motor.name}", json={'position': int(steps)},
                          timeout=_move_timeout(motor, timeout))
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
    Deltas are always in the motor's unit (`motor.unit`: mm, deg, steps...).
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

        steps = motor.to_steps(delta)   # value in the motor's unit -> steps

        try:
            r = safe_post(f"{BASE_URL}/motors/move_rel/{motor.name}", json={'delta': int(steps)},
                          timeout=_move_timeout(motor, timeout))
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


def _motor_names(motors):
    for motor in motors:
        if not isinstance(motor, Motor):
            raise ValueError("Arguments must be Motor instances")
    return [motor.name for motor in motors]


def _post_to_motors(action, names, warn=None):
    """POST /motors/<action>/<name> for each motor name. Never raises on a server
    error: returns [(name, response JSON or {'error': ...})], and prints a warning
    "Failed to <warn> motor ..." if `warn` is given."""
    results = []
    for name in names:
        try:
            r = safe_post(f"{BASE_URL}/motors/{action}/{name}", timeout=DEFAULT_TIMEOUT)
            results.append((name, r.json()))
        except Exception as e:
            if warn:
                print(f"[WARN] Failed to {warn} motor {name}: {e}")
            results.append((name, {'error': str(e)}))
    return results


def _post_to_all_motors(action, warn=None):
    """Same as `_post_to_motors`, for all motors registered on the motion server."""
    try:
        r = safe_get(f"{BASE_URL}/motors/list", timeout=DEFAULT_TIMEOUT)
        names = [entry.get('name') for entry in r.json().get('motors', []) if entry.get('name')]
    except Exception as e:
        if warn:
            print(f"[WARN] Failed to list motors: {e}")
        return [('_list_motors', {'error': str(e)})]
    return _post_to_motors(action, names, warn)


def free(*motors):
    """Release one or more motors. Usage: free(motor1, motor2, ...)"""
    return _post_to_motors('free', _motor_names(motors))


def control(*motors):
    """Re-acquire control of one or more motors. Usage: control(motor1, motor2, ...)"""
    return _post_to_motors('control', _motor_names(motors))


def stop(*motors):
    """Stop one or more motors immediately. Usage: stop(motor1, motor2, ...)

    Never raises on a server error (it is used while handling Ctrl+C):
    failures are printed and returned in the results list.
    """
    return _post_to_motors('stop', _motor_names(motors), warn='stop')


def init(*motors):
    """Initialize one or more motors (enable the axis, INIT if not ready, absolute mode).
    Needed once after the motion server starts, before moving them. INIT can move the axis.
    Usage: init(motor1, motor2, ...)"""
    return _post_to_motors('init', _motor_names(motors), warn='initialize')


def init_all():
    """Initialize all motors registered on the motion server (see `init`)."""
    return _post_to_all_motors('init', warn='initialize')


def free_all_motors():
    """Release all motors currently registered on the motion server."""
    return _post_to_all_motors('free')


def control_all_motors():
    """Re-acquire control of all motors currently registered on the motion server."""
    return _post_to_all_motors('control')


def stop_all():
    """Stop all axes of all controllers of the motion server."""
    try:
        r = safe_post(f"{BASE_URL}/motors/stop_all", timeout=DEFAULT_TIMEOUT)
        return r.json()
    except Exception as e:
        print(f"[WARN] stop_all failed: {e}")
        return {'error': str(e)}


class Motor:
    """Client-side handle for a motor of the motion server.

    Positions passed to mv / mvr and returned by `position()` are always in the
    motor's unit (`unit`: mm, deg, steps..., from config/motors.yaml).
    `step_to_mm` is the size of one step in that unit (despite its historical name,
    it is in deg per step for a motor in deg, and 1 for a motor in steps):
    steps = value / step_to_mm.
    """

    def __init__(self,
                 name,
                 controller_type="PS90",
                 controller_channel=1,
                 velocity=1.0,
                 acceleration=1.0,
                 step_to_mm=1.0,
                 controller_name: str = None,
                 max_move_duration=DEFAULT_MAX_MOVE_DURATION,
                 unit: str = None,
                 controler_type=None,
                 controler_channel=None):
        # former misspelled keyword arguments, still accepted
        if controler_type is not None:
            warnings.warn("Motor(controler_type=...) is deprecated, use controller_type", DeprecationWarning, stacklevel=2)
            controller_type = controler_type
        if controler_channel is not None:
            warnings.warn("Motor(controler_channel=...) is deprecated, use controller_channel", DeprecationWarning, stacklevel=2)
            controller_channel = controler_channel
        self.name = name
        self.controller_type = controller_type
        self.controller_channel = controller_channel
        self.velocity = velocity
        self.acceleration = acceleration
        # size of one step in the motor's unit (steps -> unit = steps * step_to_mm)
        self.step_to_mm = step_to_mm
        # optional controller name (for registration or reference)
        self.controller_name = controller_name
        # server-side max duration of a move (s), used for the client HTTP timeout
        self.max_move_duration = max_move_duration
        # user unit of positions; by default the one implied by step_to_mm
        self.unit = unit or ('mm' if float(step_to_mm) != 1.0 else 'steps')

    # Former misspelled attribute names, kept so that existing scripts keep working.
    @property
    def controler_type(self):
        warnings.warn("Motor.controler_type is deprecated, use controller_type", DeprecationWarning, stacklevel=2)
        return self.controller_type

    @controler_type.setter
    def controler_type(self, value):
        warnings.warn("Motor.controler_type is deprecated, use controller_type", DeprecationWarning, stacklevel=2)
        self.controller_type = value

    @property
    def controler_channel(self):
        warnings.warn("Motor.controler_channel is deprecated, use controller_channel", DeprecationWarning, stacklevel=2)
        return self.controller_channel

    @controler_channel.setter
    def controler_channel(self, value):
        warnings.warn("Motor.controler_channel is deprecated, use controller_channel", DeprecationWarning, stacklevel=2)
        self.controller_channel = value

    def to_steps(self, value) -> int:
        """Convert a position or displacement in the motor's unit to steps."""
        return int(round(float(value) / float(self.step_to_mm)))

    def from_steps(self, steps):
        """Convert a number of steps to the motor's unit."""
        if self.unit == 'steps':
            return steps
        return steps * float(self.step_to_mm)

    def position(self):
        """Current position, read from the server, in the motor's unit."""
        r = safe_get(f"{BASE_URL}/motors/read/{self.name}", timeout=DEFAULT_TIMEOUT)
        return self.from_steps(r.json()['position'])

    def __repr__(self):
        return f"Motor(name={self.name!r})"
