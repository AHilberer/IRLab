from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import os
import threading
import logging

from common.states import DeviceState
from common.errors import MotionError, MotorBusyError, MotionStoppedError
from common.version import get_version
from common.logging_setup import setup_logging, add_action_logging

logger = setup_logging('motion_server')
# every PS90 command and response, at DEBUG level; enabled by `log_serial: true` in motors.yaml
serial_logger = logging.getLogger('motion_server.serial')
serial_logger.setLevel(logging.WARNING)

try:
    import serial
except Exception:
    serial = None
try:
    import yaml
except Exception:
    yaml = None

@asynccontextmanager
async def lifespan(app):
    # startup: load the motor config (controllers + motors); never fails, errors
    # are reported by /status (degraded mode)
    load_config()
    yield
    # shutdown: stop moving axes, then close the controllers
    shutdown_close_controllers()


app = FastAPI(lifespan=lifespan)
add_action_logging(app, logger)

# Global controller instance (lazy-created)
# controllers registry and default name
controllers = {}
default_controller_name = None

# registry of named motor objects (created from the config file, see load_config)
motors = {}

# default config path (relative to repo root), overridable with $IRLAB_MOTORS_CONFIG
DEFAULT_MOTOR_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'config', 'motors.yaml')

# Result of the last config load, reported by /status
config_path = None
config_error = None        # config file missing / unreadable / invalid
controller_errors = {}     # controller name -> error message
motor_errors = {}          # motor name -> error message (registration or initialization)


# Protocol details below come from the PS 90+ user manual (command set, chap. 17 and
# attachment I); the older PS90 of the bench is assumed to behave the same.
# À VÉRIFIER sur le banc pour le PS90 (ancienne version).

# Character ending each PS90 response: CR with the default setting COMEND=0
# (COMEND=1: CR+LF, also handled; COMEND=2: LF, NOT handled).
PS90_TERMINATOR = b'\r'
# Default serial read timeout (s): a query not answered within this delay fails.
PS90_DEFAULT_TIMEOUT = 1.0
# Pause after a command that returns no response, before the next command: the
# manual gives a command processing time of about 20 to 40 ms between two commands.
PS90_DEFAULT_COMMAND_DELAY = 0.05
# In terminal mode TERM=2, each command without response is acknowledged by "OK":
# such a line read in place of a query response is skipped.
PS90_ACK = 'OK'
# Command stopping one axis ({axis} is replaced by the axis number): decelerates with
# the preset ramp and halts.
PS90_STOP_AXIS_CMD = 'STOP{axis}'
# Command stopping all axes of a controller, sent by /motors/stop_all before the
# per-axis stops. None: not used, only the per-axis stop of each registered motor is
# sent. The PS90 has MSTOP=<axis bit mask>, but the format of the mask depends on the
# terminal mode (decimal with TERM=0, string of 0/1 with TERM=1 or 2), so it is not used.
PS90_STOP_ALL_CMD = None

# ?ASTAT returns one character per axis. States in which the axis is moving:
PS90_MOVING_STATES = set('TSVPFWXYCN')
# Meaning of each state, used in error messages
PS90_AXIS_STATES = {
    'I': 'initialized',
    'O': 'disabled',
    'R': 'initialized and ready',
    'T': 'positioning in trapezoidal profile',
    'S': 'positioning in S-curve profile',
    'V': 'operating in velocity mode',
    'P': 'reference motion in progress',
    'F': 'releasing a limit switch',
    'J': 'operating in joystick mode',
    'L': 'disabled after approaching a hardware limit switch (MINSTOP/MAXSTOP)',
    'B': 'stopped after approaching a brake switch (MINDEC/MAXDEC)',
    'A': 'disabled after limit switch error',
    'M': 'disabled after motion controller error',
    'Z': 'disabled after timeout error',
    'H': 'phase initialization active',
    'U': 'not released',
    'E': 'disabled after motion error',
    'W': 'positioning in trapezoidal profile with WMS',
    'X': 'positioning in S-curve profile with WMS',
    'Y': 'operating in velocity mode with WMS',
    'C': 'operating in velocity mode with continuous-path control',
    'N': 'operating in piezo follow-up mode with WMS',
    '?': 'error, unknown state',
}

class MoveAbsRequest(BaseModel):
    position: int    # target position, in steps


class MoveRelRequest(BaseModel):
    delta: int       # displacement, in steps


# Max time (s) to wait for an axis to come to rest after a stop sent on timeout
STOP_SETTLE_TIMEOUT = 10.0

# Per-motor defaults, overridable in config/motors.yaml
DEFAULT_MAX_MOVE_DURATION = 120.0     # s; beyond this the axis is stopped and the move fails
DEFAULT_POSITION_TOLERANCE_STEPS = 0  # accepted |final position - target|, in steps


def _port_in_use(exc) -> bool:
    """True if a pyserial open error means the port is already opened by another process."""
    text = str(exc).lower()
    return any(k in text for k in ('permissionerror', 'access is denied', 'accès refusé',
                                   'resource busy', 'errno 16'))


class PS90:
    def __init__(self, port, baudrate=9600,
                 timeout=PS90_DEFAULT_TIMEOUT, command_delay=PS90_DEFAULT_COMMAND_DELAY):
        if serial is None:
            raise RuntimeError("pyserial is required but not installed")
        # FastAPI runs `def` routes in a thread pool: every exchange on the serial
        # port must hold this lock so concurrent requests cannot interleave.
        # Reentrant so multi-command sequences can hold it around several send().
        self.lock = threading.RLock()
        self.port = port
        self.command_delay = command_delay
        try:
            self.ser = serial.Serial(port, baudrate,
                        timeout=timeout,
                        stopbits=1,
                        parity='N',
                        bytesize=8)
        except serial.SerialException as e:
            if _port_in_use(e):
                raise RuntimeError(f'Serial port {port} is already in use by another program '
                                   f'(is another motion server already running?): {e}') from e
            raise
        time.sleep(1)  # allow connection to settle

    def send(self, cmd):
        """Send a command. Queries (starting with '?') return the response string;
        other commands return None. Raises TimeoutError if a query gets no complete
        response within the serial timeout."""
        full_cmd = cmd + '\r'   # OWIS uses CR as end character
        with self.lock:
            self.ser.reset_input_buffer()
            serial_logger.debug('%s >> %s', self.port, cmd)
            self.ser.write(full_cmd.encode())
            if not cmd.startswith('?'):
                if self.command_delay:
                    time.sleep(self.command_delay)
                return None
            raw = self.ser.read_until(PS90_TERMINATOR)
            serial_logger.debug('%s << %r', self.port, raw)
            if raw.strip() == PS90_ACK.encode():
                # late "OK" acknowledging a previous command (TERM=2): read the real response
                raw = self.ser.read_until(PS90_TERMINATOR)
                serial_logger.debug('%s << %r', self.port, raw)
        if not raw.endswith(PS90_TERMINATOR):
            raise TimeoutError(f'No complete response from PS90 to "{cmd}" '
                               f'within {self.ser.timeout} s (received: {raw!r})')
        return raw.decode(errors='replace').strip()

    def get_status(self, axis=None):
        """Return the ?ASTAT string (one character per axis). If `axis` is given,
        check that the response covers that axis."""
        response = self.send('?ASTAT')
        if response == '':
            raise RuntimeError('Empty status response from PS90 to "?ASTAT"')
        if axis is not None and len(response) < axis:
            raise RuntimeError(f'Status response from PS90 too short for axis {axis}: {response!r}')
        return response

    def init_axis(self, axis):
        with self.lock:
            self.send(f'AXIS{axis}=1')
            self.send(f'INIT{axis}')
        return


    def close(self):
        self.ser.close()


class PS90_motor:
    def __init__(self, name, control_unit, control_axis_number, step_to_mm=1,
                 max_move_duration=DEFAULT_MAX_MOVE_DURATION,
                 position_tolerance_steps=DEFAULT_POSITION_TOLERANCE_STEPS,
                 unit=None):
        self.control_unit = control_unit
        self.name = name
        self.control_axis_number = control_axis_number
        self.step_to_mm = step_to_mm
        # user unit, for display by the clients; by default the one implied by step_to_mm
        self.unit = unit or ('mm' if float(step_to_mm) != 1.0 else 'steps')
        self.max_move_duration = max_move_duration
        self.position_tolerance_steps = position_tolerance_steps
        # set by stop(); checked by the end-of-move loop
        self._stop_requested = threading.Event()
        # last position read, for information only: never used as a motion reference
        self.current_position_step = None
        self.state = DeviceState.OFF
        # Only one motion at a time per motor; a second request fails fast (HTTP 409).
        self.motion_lock = threading.Lock()

    def _acquire_motion_lock(self):
        if not self.motion_lock.acquire(blocking=False):
            raise MotorBusyError(f'Motor {self.name} is busy (a motion is already in progress)')


    def initialize_axis(self):
        # INIT enables the power stage and the position control loop (the axis does not
        # move: the reference run is REF). Refused while a motion is in progress.
        self._acquire_motion_lock()
        try:
            with self.control_unit.lock:
                control_unit_status = self.control_unit.get_status(self.control_axis_number)
                if control_unit_status[self.control_axis_number-1] != 'R':
                    self.control_unit.init_axis(self.control_axis_number)
                    logger.info('Initialized motor %s', self.name)
                else:
                    logger.info('Motor %s already initialized', self.name)
                self.set_absolute_mode()
                self.read_current_position()
        except Exception:
            self.state = DeviceState.FAULT
            logger.exception('Failed to initialize motor %s', self.name)
            raise
        finally:
            self.motion_lock.release()
        self.state = DeviceState.ON
    
    def read_parameters(self) -> dict:
        """Read the axis parameters from the PS90 (raw responses)."""
        axis = self.control_axis_number
        with self.control_unit.lock:
            control_unit_status = self.control_unit.get_status(axis)
            return {
                'motor': self.name,
                'axis': axis,
                'status_code': control_unit_status[axis-1],
                'mode': self.control_unit.send(f'?MODE{axis}'),          # set with ABSOL<n> or RELAT<n>
                'velocity': self.control_unit.send(f'?PVEL{axis}'),
                'acceleration': self.control_unit.send(f'?ACC{axis}'),
                'deceleration': self.control_unit.send(f'?DACC{axis}'),
                'limit_switch_release_speed': self.control_unit.send(f'?FVEL{axis}'),
                'setpoint': self.control_unit.send(f'?PSET{axis}'),
                'position_counter': self.control_unit.send(f'?CNT{axis}'),
                'encoder_position': self.control_unit.send(f'?ENCPOS{axis}'),
            }

    def free(self):
        self.control_unit.send(f'AXIS{self.control_axis_number}=0')

    def control(self):
        # re-enables the axis with INIT: refused while a motion is in progress
        self._acquire_motion_lock()
        try:
            self.control_unit.init_axis(self.control_axis_number)
        finally:
            self.motion_lock.release()
    
    def stop(self):
        """Stop this axis now. Does not wait for the motion lock: only the serial
        lock is taken, for a single command."""
        self._stop_requested.set()
        self._send_stop()

    def _send_stop(self):
        self.control_unit.send(PS90_STOP_AXIS_CMD.format(axis=self.control_axis_number))

    def _wait_stopped(self, timeout=STOP_SETTLE_TIMEOUT):
        """Wait until the axis is no longer moving (after a stop), at most `timeout` s."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self._axis_status() not in PS90_MOVING_STATES:
                    return
            except Exception:
                return
            time.sleep(0.05)

    def _axis_status(self):
        return self.control_unit.get_status(self.control_axis_number)[self.control_axis_number-1]

    def _motion_failure(self, reason, target_position):
        """Build a readable failure message with the reached position and axis status."""
        try:
            reached = self.read_current_position()
        except Exception as e:
            reached = f'unknown ({e})'
        try:
            code = self._axis_status()
            axis_status = f"'{code}' ({PS90_AXIS_STATES.get(code, 'unknown state code')})"
        except Exception as e:
            axis_status = f'unknown ({e})'
        return (f'Motor {self.name}: {reason} '
                f'(target {target_position}, reached {reached}, axis status {axis_status})')

    def set_absolute_mode(self):
        self.control_unit.send(f'ABSOL{self.control_axis_number}')
        
    def set_relative_mode(self):
        self.control_unit.send(f'RELAT{self.control_axis_number}')
        
    def read_current_position(self):
        response = self.control_unit.send(f'?CNT{self.control_axis_number}')
        try:
            position = int(response)
        except ValueError:
            raise ValueError(f'Invalid position from PS90 for motor {self.name} '
                             f'(?CNT{self.control_axis_number}): {response!r}') from None
        self.current_position_step = position
        return self.current_position_step
        
    def _check_initialized(self):
        # OFF: initialize_axis() never ran since the server started, so the axis mode
        # (absolute/relative) and enable state are unknown
        if self.state == DeviceState.OFF:
            raise MotionError(f'Motor {self.name} not initialized: run init({self.name}) or init_all()')

    def move_absolute(self, target_position:int):
        self._check_initialized()
        self._acquire_motion_lock()
        try:
            return self._move_absolute(target_position)
        finally:
            self.motion_lock.release()

    def _move_absolute(self, target_position:int):
        # caller must hold self.motion_lock
        # Returns the final position (steps); raises MotionError if the target is not reached.
        logger.info('Moving %s to %s', self.name, target_position)
        self._stop_requested.clear()
        self.state = DeviceState.MOVING
        try:
            with self.control_unit.lock:
                self.control_unit.send(f'PSET{self.control_axis_number}={target_position}')
                self.control_unit.send(f'PGO{self.control_axis_number}')
            # the serial lock is taken and released at each ?ASTAT poll, so that
            # reads (wm), stop and other axes stay available during the motion
            deadline = time.monotonic() + self.max_move_duration
            while self._axis_status() in PS90_MOVING_STATES:
                if time.monotonic() > deadline:
                    self._send_stop()
                    # keep the motion lock until the axis is at rest: no new move during deceleration
                    self._wait_stopped()
                    raise MotionError(self._motion_failure(
                        f'move not finished after {self.max_move_duration} s, stop sent', target_position))
                time.sleep(0.05)
            actual_pos = self.read_current_position()
        except Exception:
            self.state = DeviceState.FAULT
            logger.exception('Error during movement of %s (axis %d)', self.name, self.control_axis_number)
            raise

        if self._stop_requested.is_set():
            self.state = DeviceState.ON
            raise MotionStoppedError(f'Motor {self.name}: stopped by user '
                                     f'(target {target_position}, reached {actual_pos})')
        if abs(actual_pos - target_position) > self.position_tolerance_steps:
            self.state = DeviceState.FAULT
            message = self._motion_failure('wrong final position', target_position)
            logger.error(message)
            raise MotionError(message)
        self.state = DeviceState.ON
        return actual_pos
    
    def move_relative(self, displacement_step:int):
        self._check_initialized()
        self._acquire_motion_lock()
        try:
            # Always re-read the position: the cached current_position_step may be stale
            # (axis moved by hand after free(), interrupted move, other client...).
            target_position = self.read_current_position() + displacement_step
            return self._move_absolute(target_position)
        finally:
            self.motion_lock.release()


def get_controller(name: str = None):
    """Return a controller instance by name. If name is None, return the default controller if set."""
    if name is None:
        if default_controller_name is None:
            raise RuntimeError('No controller connected. Call /ps90/connect first.')
        name = default_controller_name
    if name not in controllers:
        raise RuntimeError(f'Controller "{name}" not connected. Call /ps90/connect?name={name} first.')
    return controllers[name]


@app.post("/ps90/connect")
def ps90_connect(port: str, baud: int = 9600, name: str = 'main_ps90'):
    """Connect to a PS90 controller and store it under `name` (debug / recovery: the
    controllers of config/motors.yaml are connected at startup).
    Example: /ps90/connect?name=main_ps90&port=COM25&baud=9600
    """
    global default_controller_name
    if serial is None:
        raise HTTPException(status_code=500, detail='pyserial is not installed in this environment')
    if name in controllers:
        return {"status": "already_connected", "name": name}
    try:
        ctrl = PS90(port=port, baudrate=baud)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to open serial port: {e}')
    controllers[name] = ctrl
    if default_controller_name is None:
        default_controller_name = name
    return {"status": "connected", "name": name, "port": port, "baud": baud}


@app.post("/ps90/close")
def ps90_close(name: str = None):
    """Close a named controller or the default when `name` is omitted.

    If no controller is connected, returns status 'not_connected'.
    """
    global default_controller_name
    # choose target controller name
    if name is None:
        if default_controller_name is None:
            return {"status": "not_connected"}
        name = default_controller_name

    if name not in controllers:
        return {"status": "not_connected"}

    closed = controllers[name]
    try:
        closed.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error closing controller: {e}')

    # remove from registry (and its motors, recreated by /admin/reload_config) and update default if needed
    del controllers[name]
    for mname in [n for n, m in motors.items() if m.control_unit is closed]:
        del motors[mname]
    if default_controller_name == name:
        default_controller_name = None
        # pick another default if available
        if controllers:
            default_controller_name = next(iter(controllers.keys()))

    return {"status": "closed", "name": name}


@app.get("/ps90/status")
def ps90_status():
    c = get_controller()
    return {"status": c.get_status()}


def get_motor(name: str) -> PS90_motor:
    if name not in motors:
        raise HTTPException(status_code=404, detail=f'Motor "{name}" not registered (see config/motors.yaml and /status)')
    return motors[name]


def _load_motor_config_from_dict(cfg: dict, initialize: bool = False):
    """Given a parsed YAML/JSON dict, register motors. Expected format:
    motors:
      - name: sx
        axis: 2
        step_to_mm: 0.01
    """
    global default_controller_name
    created = []
    # optional controllers section: create controller instances first
    if 'controllers' in cfg:
        if yaml is None:
            raise ValueError('pyyaml is required to load controllers from config')
        for ctrl in cfg['controllers']:
            cname = ctrl.get('name')
            ctype = ctrl.get('type', '').lower()
            if cname in controllers:
                continue
            if ctype == 'ps90':
                port = ctrl.get('port') or os.environ.get('PS90_PORT')
                if not port:
                    controller_errors[cname] = 'No serial port configured: set "port" in config/motors.yaml'
                    continue
                baud = int(ctrl.get('baud', 9600))
                timeout = float(ctrl.get('timeout', PS90_DEFAULT_TIMEOUT))
                command_delay = float(ctrl.get('command_delay', PS90_DEFAULT_COMMAND_DELAY))
                try:
                    controllers[cname] = PS90(port=port, baudrate=baud,
                                              timeout=timeout, command_delay=command_delay)
                    controller_errors.pop(cname, None)
                    if default_controller_name is None:
                        default_controller_name = cname
                except Exception as e:
                    # degraded mode: keep going, motors of this controller are skipped
                    controller_errors[cname] = f'Failed to open {port}: {e}'
            else:
                # unknown controller type: skip (could add hooks for other types)
                continue

    if 'motors' not in cfg:
        raise ValueError('Config missing top-level "motors" key')

    for entry in cfg['motors']:
        name = entry.get('name')
        if not name or name in motors:
            continue
        motor_errors.pop(name, None)
        try:
            if _register_motor_from_entry(entry, initialize):
                created.append(name)
        except Exception as e:
            motor_errors[name] = str(e)

    return created


def _register_motor_from_entry(entry: dict, initialize: bool = False):
    """Create one motor from its config entry. Returns True if created."""
    global default_controller_name
    name = entry.get('name')
    # controller selection: prefer explicit controller name, else controller_type triggers auto controller
    controller_name = entry.get('controller') or entry.get('controller_name')
    controller_type = entry.get('controller_type') or entry.get('controler_type')
    if controller_name is None and controller_type:
        # create or reuse an auto controller for this type
        controller_name = f'auto_{controller_type}'
        if controller_name not in controllers:
            if controller_type.lower() == 'ps90':
                port = os.environ.get('PS90_PORT')
                if not port:
                    raise ValueError(f'No serial port for the automatic controller of motor {name}: '
                                     f'declare it in the "controllers" section of config/motors.yaml')
                try:
                    controllers[controller_name] = PS90(port=port, baudrate=9600)
                    if default_controller_name is None:
                        default_controller_name = controller_name
                except Exception as e:
                    raise ValueError(f'Failed to create controller for motor {name}: {e}')
            else:
                raise ValueError(f'Unsupported controller type "{controller_type}" for motor {name}')

    if controller_name is None:
        # fallback to default controller
        if default_controller_name is None:
            raise ValueError('No controller specified for motor and no default controller connected')
        controller_name = default_controller_name

    if controller_name in controller_errors:
        raise ValueError(f'Controller "{controller_name}" unavailable (see its error)')
    if controller_name not in controllers:
        raise ValueError(f'Controller "{controller_name}" not found for motor {name}')

    axis = int(entry.get('controller_channel') or entry.get('controler_channel') or entry.get('axis'))
    step = float(entry.get('step_to_mm', 1.0))
    velocity = entry.get('velocity')
    acceleration = entry.get('acceleration')
    max_move_duration = float(entry.get('max_move_duration', DEFAULT_MAX_MOVE_DURATION))
    position_tolerance_steps = int(entry.get('position_tolerance_steps', DEFAULT_POSITION_TOLERANCE_STEPS))

    ctrl = controllers[controller_name]
    motor = PS90_motor(name=name, control_unit=ctrl, control_axis_number=axis, step_to_mm=step,
                       max_move_duration=max_move_duration,
                       position_tolerance_steps=position_tolerance_steps,
                       unit=entry.get('unit'))
    motors[name] = motor
    # apply motion parameters if provided (non-fatal: the motor stays registered)
    for command, value in (('PVEL', velocity), ('ACC', acceleration)):
        if value is None:
            continue
        try:
            ctrl.send(f'{command}{axis}={value}')
        except Exception as e:
            message = f'Failed to set {command}{axis}={value}: {e}'
            logger.error('Motor %s: %s', name, message)
            motor_errors[name] = message

    if initialize:
        try:
            motor.initialize_axis()
        except Exception as e:
            # the motor stays registered (state FAULT); continue with the others
            motor_errors[name] = f'Initialization failed: {e}'
    return True


def load_config(path: str = None, initialize: bool = None):
    """Load the motor config: open the controllers and register the motors.

    Never raises: errors are kept in config_error / controller_errors / motor_errors
    and reported by /status (degraded mode). Controllers already connected and motors
    already registered are left as they are, so calling it again retries only what
    failed. `initialize=None` uses `initialize_on_startup` from the YAML (default false:
    INIT powers the motors, which is done on purpose from the shell).
    """
    global config_path, config_error
    if path is None:
        path = os.environ.get('IRLAB_MOTORS_CONFIG') or os.path.normpath(DEFAULT_MOTOR_CONFIG)
    config_path = path
    try:
        if yaml is None:
            raise RuntimeError('pyyaml is not installed in this environment')
        with open(path, 'r') as fh:
            cfg = yaml.safe_load(fh) or {}
        if initialize is None:
            initialize = bool(cfg.get('initialize_on_startup', False))
        serial_logger.setLevel(logging.DEBUG if cfg.get('log_serial') else logging.WARNING)
        created = _load_motor_config_from_dict(cfg, initialize=initialize)
    except Exception as e:
        config_error = f'Failed to load config {path}: {e}'
        logger.error(config_error)
        return []
    config_error = None
    for name, err in controller_errors.items():
        logger.error('Controller %s: %s', name, err)
    for name, err in motor_errors.items():
        logger.error('Motor %s: %s', name, err)
    logger.info('Config %s loaded: %d controller(s), %d motor(s) (%s created now)',
                path, len(controllers), len(motors), ', '.join(created) or 'none')
    return created


@app.post("/admin/reload_config")
def admin_reload_config():
    """Retry loading the config: reconnect controllers and register motors that
    failed (e.g. PS90 unplugged at startup). Existing controllers and motors are kept;
    restart the server to apply other changes of the config file."""
    created = load_config()
    return {"created": created, **status()}


@app.post("/motors/move_abs/{motor}")
def motors_move_abs(motor: str, req: MoveAbsRequest):
    """Move a registered motor to an absolute position (body: {"position": steps}).
    Returns when the move is finished, with the final position."""
    m = get_motor(motor)
    try:
        res = m.move_absolute(req.position)
    except MotorBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": "ok", "motor": motor, "position": res}


@app.post("/motors/move_rel/{motor}")
def motors_move_rel(motor: str, req: MoveRelRequest):
    """Move a registered motor relative to its current position (body: {"delta": steps})."""
    m = get_motor(motor)
    try:
        res = m.move_relative(req.delta)
    except MotorBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": "ok", "motor": motor, "position": res}


@app.post("/motors/stop/{motor}")
def motors_stop(motor: str):
    """Stop a motor immediately (does not wait for a running move request)."""
    m = get_motor(motor)
    try:
        m.stop()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to stop motor {motor}: {e}')
    return {"status": "stopped", "motor": motor}


@app.post("/motors/stop_all")
def motors_stop_all():
    """Stop all axes of all controllers."""
    errors = {}
    # iterate over copies: /admin/reload_config may change the registries meanwhile
    if PS90_STOP_ALL_CMD:
        for cname, ctrl in list(controllers.items()):
            try:
                ctrl.send(PS90_STOP_ALL_CMD)
            except Exception as e:
                errors[cname] = str(e)
    stopped = []
    for name, m in list(motors.items()):
        try:
            m.stop()
            stopped.append(name)
        except Exception as e:
            errors[name] = str(e)
    if errors:
        raise HTTPException(status_code=500, detail=f'Stop failed for {errors} (stopped: {stopped})')
    return {"status": "stopped", "motors": stopped}


@app.get("/motors/read/{motor}")
def motors_read(motor: str):
    m = get_motor(motor)
    try:
        pos = m.read_current_position()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"motor": motor, "position": pos, "state": m.state.value}


@app.get("/motors/parameters/{motor}")
def motors_parameters(motor: str):
    """Axis parameters read from the PS90 (mode, velocity, acceleration, counters...)."""
    m = get_motor(motor)
    try:
        return m.read_parameters()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/motors/init/{motor}")
def motors_init(motor: str):
    m = get_motor(motor)
    try:
        m.initialize_axis()
    except MotorBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "initialized", "motor": motor}


@app.post("/motors/free/{motor}")
def motors_free(motor: str):
    """Release control on a registered motor axis."""
    m = get_motor(motor)
    try:
        m.free()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "freed", "motor": motor}


@app.post("/motors/control/{motor}")
def motors_control(motor: str):
    """Re-acquire control on a registered motor axis."""
    m = get_motor(motor)
    try:
        m.control()
    except MotorBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "controlled", "motor": motor}


@app.get("/motors/list")
def motors_list():
    """Return registered motors: controller mapping, unit, limits and state.
    This is the single source of truth used by the shell to create its Motor objects."""
    out = []
    for name, m in motors.items():
        # find controller name by identity
        ctrl_name = None
        for cname, cinst in controllers.items():
            if cinst is m.control_unit:
                ctrl_name = cname
                break
        out.append({
            "name": name,
            "axis": m.control_axis_number,
            "step_to_mm": m.step_to_mm,
            "unit": m.unit,
            "controller": ctrl_name,
            "max_move_duration": m.max_move_duration,
            "state": m.state.value,
        })
    return {"motors": out}


@app.get("/controllers/list")
def controllers_list():
    """Return the list of controller names and a brief status (if available)."""
    out = []
    for name, inst in controllers.items():
        status = None
        try:
            # try to ask the controller for a short status summary
            status = inst.get_status()
        except Exception:
            status = None
        out.append({"name": name, "status": status})
    return {"controllers": out}

@app.get("/status")
def status():
    """Server status: version, config, controllers (connected or in error) and motors."""
    ctrl = [{"name": n, "port": c.port, "state": "connected"} for n, c in controllers.items()]
    ctrl += [{"name": n, "state": "error", "error": e}
             for n, e in controller_errors.items() if n not in controllers]
    degraded = bool(config_error or controller_errors or motor_errors)
    return {
        "server": "motion_server",
        "version": get_version(),
        "status": "degraded" if degraded else "ok",
        "config": config_path,
        "config_error": config_error,
        "controllers": ctrl,
        "motors": {
            "registered": list(motors),
            "not_initialized": [n for n, m in motors.items() if m.state == DeviceState.OFF],
            "errors": dict(motor_errors),
        },
    }


@app.get("/state")
def get_state():
    """Server-wide state: FAULT if any motor is in FAULT, MOVING if any motor is moving, else ON."""
    states = [m.state for m in motors.values()]
    if DeviceState.FAULT in states:
        overall = DeviceState.FAULT
    elif DeviceState.MOVING in states:
        overall = DeviceState.MOVING
    else:
        overall = DeviceState.ON
    return {"state": overall.value}


## launch with 'uvicorn servers.motion_server:app --host 0.0.0.0 --port 8001'


def shutdown_close_controllers():
    """Gracefully close all connected controller instances when the FastAPI app is shutting down.

    Moving axes are stopped first. Then this will attempt to call `.close()` on each controller
    and clear the registry so serial ports are released when the server process exits (for
    example on Ctrl+C from uvicorn).
    """
    for name, m in list(motors.items()):
        if m.state == DeviceState.MOVING:
            try:
                m.stop()
                logger.warning('Shutdown: stopped moving motor %s', name)
            except Exception as e:
                logger.error('Shutdown: failed to stop motor %s: %s', name, e)
    if not controllers:
        logger.info('Shutdown: no controllers to close')
        return
    logger.info('Shutdown: closing %d controller(s)', len(controllers))
    for name, inst in list(controllers.items()):
        try:
            inst.close()
            logger.info('Closed controller: %s', name)
        except Exception as e:
            logger.error('Error closing controller %s: %s', name, e)
        # remove from registry
        try:
            del controllers[name]
        except Exception:
            pass
    # reset default name
    global default_controller_name
    default_controller_name = None
    logger.info('Shutdown: controller registry cleared')