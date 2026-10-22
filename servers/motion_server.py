from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import time
import os
import threading

from common.states import DeviceState
from common.errors import MotionError, MotorBusyError, MotionStoppedError
from common.version import get_version

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


# Character ending each PS90 response.
# À VÉRIFIER dans le manuel OWIS PS90 (CR assumed, as for commands).
PS90_TERMINATOR = b'\r'
# Default serial read timeout (s): a query not answered within this delay fails.
PS90_DEFAULT_TIMEOUT = 1.0
# Pause after a command that returns no response, before the next command.
# À VÉRIFIER dans le manuel OWIS PS90 (minimal delay between commands, if any).
# Kept at the former fixed delay (0.05 s) until confirmed.
PS90_DEFAULT_COMMAND_DELAY = 0.05
# Command stopping one axis ({axis} is replaced by the axis number).
# À VÉRIFIER dans le manuel OWIS PS90 (axis stop command).
PS90_STOP_AXIS_CMD = 'STOP{axis}'
# Command stopping all axes of a controller, sent by /motors/stop_all before the
# per-axis stops. None: not used, only the per-axis stop of each registered motor
# is sent. À VÉRIFIER dans le manuel OWIS PS90 (general stop command).
PS90_STOP_ALL_CMD = None

# Per-motor defaults, overridable in config/motors.yaml
DEFAULT_MAX_MOVE_DURATION = 120.0     # s; beyond this the axis is stopped and the move fails
DEFAULT_POSITION_TOLERANCE_STEPS = 0  # accepted |final position - target|, in steps


class PS90:
    def __init__(self, port='COM25', baudrate=9600,
                 timeout=PS90_DEFAULT_TIMEOUT, command_delay=PS90_DEFAULT_COMMAND_DELAY):
        if serial is None:
            raise RuntimeError("pyserial is required but not installed")
        # FastAPI runs `def` routes in a thread pool: every exchange on the serial
        # port must hold this lock so concurrent requests cannot interleave.
        # Reentrant so multi-command sequences can hold it around several send().
        self.lock = threading.RLock()
        self.port = port
        self.command_delay = command_delay
        self.ser = serial.Serial(port, baudrate,
                    timeout=timeout,
                    stopbits=1,
                    parity='N',
                    bytesize=8)
        time.sleep(1)  # allow connection to settle

    def send(self, cmd):
        """Send a command. Queries (starting with '?') return the response string;
        other commands return None. Raises TimeoutError if a query gets no complete
        response within the serial timeout."""
        full_cmd = cmd + '\r'   # OWIS uses CR as end character
        with self.lock:
            self.ser.reset_input_buffer()
            self.ser.write(full_cmd.encode())
            if not cmd.startswith('?'):
                if self.command_delay:
                    time.sleep(self.command_delay)
                return None
            raw = self.ser.read_until(PS90_TERMINATOR)
        if not raw.endswith(PS90_TERMINATOR):
            raise TimeoutError(f'No complete response from PS90 to "{cmd}" '
                               f'within {self.ser.timeout} s (received: {raw!r})')
        return raw.decode(errors='replace').strip()

    def read(self):
        return

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
        # INIT can move the axis: refuse while a motion is in progress
        self._acquire_motion_lock()
        try:
            with self.control_unit.lock:
                control_unit_status = self.control_unit.get_status(self.control_axis_number)
                if control_unit_status[self.control_axis_number-1] != 'R':
                    try:
                        self.control_unit.init_axis(self.control_axis_number)
                        print(f'Initialized motor {self.name}')
                    except:
                        print(f'Failed to initilaize moto {self.name}')
                else:
                    print(f'Motor {self.name} already initialized')
                self.set_absolute_mode()
                self.read_current_position()
        except Exception:
            self.state = DeviceState.FAULT
            raise
        finally:
            self.motion_lock.release()
        self.state = DeviceState.ON
    
    def read_parameters(self):
        with self.control_unit.lock:
            self._read_parameters()

    def _read_parameters(self):
        print('------------------------------------------')
        print(f'Parameters for {self.name}, PS90 motor axis {self.control_axis_number}')
        control_unit_status = self.control_unit.get_status(self.control_axis_number)
        print('Motor status code from PS90 :', f'{control_unit_status[self.control_axis_number-1]}')
        print('Movement mode :', self.control_unit.send(f'?MODE{self.control_axis_number}')) # set with ABSOL<n> or RELAT<n>
        print('Motor velocity :', self.control_unit.send(f'?PVEL{self.control_axis_number}'))
        print('Motor acceleration :', self.control_unit.send(f'?ACC{self.control_axis_number}'))
        print('Motor deacceleration :', self.control_unit.send(f'?DACC{self.control_axis_number}'))
        print('Limit switch release speed :', self.control_unit.send(f'?FVEL{self.control_axis_number}'))
        print('Current motor setpoint :', self.control_unit.send(f'?PSET{self.control_axis_number}'))
        print('Current position counter :', self.control_unit.send(f'?CNT{self.control_axis_number}'))
        print('Current encoder position :', self.control_unit.send(f'?ENCPOS{self.control_axis_number}'))
        print('------------------------------------------')

    def free(self):
        self.control_unit.send(f'AXIS{self.control_axis_number}=0')

    def control(self):
        # INIT can move the axis: refuse while a motion is in progress
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

    def _axis_status(self):
        return self.control_unit.get_status(self.control_axis_number)[self.control_axis_number-1]

    def _motion_failure(self, reason, target_position):
        """Build a readable failure message with the reached position and axis status."""
        try:
            reached = self.read_current_position()
        except Exception as e:
            reached = f'unknown ({e})'
        try:
            axis_status = repr(self._axis_status())
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
        print(f"Moving {self.name} to {target_position}")
        self._stop_requested.clear()
        self.state = DeviceState.MOVING
        try:
            with self.control_unit.lock:
                self.control_unit.send(f'PSET{self.control_axis_number}={target_position}')
                self.control_unit.send(f'PGO{self.control_axis_number}')
            # the serial lock is taken and released at each ?ASTAT poll, so that
            # reads (wm), stop and other axes stay available during the motion
            deadline = time.monotonic() + self.max_move_duration
            while self._axis_status()=='T':
                if time.monotonic() > deadline:
                    self._send_stop()
                    raise MotionError(self._motion_failure(
                        f'move not finished after {self.max_move_duration} s, stop sent', target_position))
                time.sleep(0.05)
            actual_pos = self.read_current_position()
        except:
            self.state = DeviceState.FAULT
            print(f'Error during movement of axis {self.control_axis_number}.')
            raise

        if self._stop_requested.is_set():
            self.state = DeviceState.ON
            raise MotionStoppedError(f'Motor {self.name}: stopped by user '
                                     f'(target {target_position}, reached {actual_pos})')
        if abs(actual_pos - target_position) > self.position_tolerance_steps:
            self.state = DeviceState.FAULT
            message = self._motion_failure('wrong final position', target_position)
            print(message)
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
    global default_controller_name
    if name is None:
        if default_controller_name is None:
            raise RuntimeError('No controller connected. Call /ps90/connect first.')
        name = default_controller_name
    if name not in controllers:
        raise RuntimeError(f'Controller "{name}" not connected. Call /ps90/connect?name={name} first.')
    return controllers[name]


@app.get("/ps90/connect")
def ps90_connect(port: str = None, baud: int = 9600, name: str = 'ps90'):
    """Connect to a PS90 controller and store it under `name`.
    Example: /ps90/connect?name=main&port=/dev/ttyUSB0&baud=9600
    """
    global default_controller_name
    if serial is None:
        raise HTTPException(status_code=500, detail='pyserial is not installed in this environment')
    if name in controllers:
        return {"status": "already_connected", "name": name}
    if port is None:
        port = os.environ.get('PS90_PORT', '/dev/ttyUSB0')
    try:
        ctrl = PS90(port=port, baudrate=baud)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to open serial port: {e}')
    controllers[name] = ctrl
    if default_controller_name is None:
        default_controller_name = name
    return {"status": "connected", "name": name, "port": port, "baud": baud}


@app.get("/ps90/close")
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
                port = ctrl.get('port') or os.environ.get('PS90_PORT', 'COM25')
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
        try:
            if _register_motor_from_entry(entry, initialize):
                created.append(name)
                motor_errors.pop(name, None)
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
                try:
                    controllers[controller_name] = PS90(port=os.environ.get('PS90_PORT', 'COM25'), baudrate=9600)
                    if default_controller_name is None:
                        default_controller_name = controller_name
                except Exception:
                    raise ValueError(f'Failed to create controller for motor {name}')
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
    # apply motion parameters if provided
    try:
        if velocity is not None:
            ctrl.send(f'PVEL{axis}={velocity}')
        if acceleration is not None:
            ctrl.send(f'ACC{axis}={acceleration}')
    except Exception:
        # non-fatal
        pass

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
    INIT can move the axes).
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
        created = _load_motor_config_from_dict(cfg, initialize=initialize)
    except Exception as e:
        config_error = f'Failed to load config {path}: {e}'
        print(config_error)
        return []
    config_error = None
    for name, err in controller_errors.items():
        print(f'Controller {name}: {err}')
    for name, err in motor_errors.items():
        print(f'Motor {name}: {err}')
    return created


@app.post("/admin/reload_config")
def admin_reload_config():
    """Retry loading the config: reconnect controllers and register motors that
    failed (e.g. PS90 unplugged at startup). Existing controllers and motors are kept;
    restart the server to apply other changes of the config file."""
    created = load_config()
    return {"created": created, **status()}


@app.get("/motors/move_abs/{motor}/{position}")
def motors_move_abs(motor: str, position: int):
    """Generic endpoint to move a registered motor by name (controller-agnostic)."""
    m = get_motor(motor)
    try:
        res = m.move_absolute(position)
    except MotorBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": "ok", "motor": motor, "position": res}


@app.get("/motors/move_rel/{motor}/{delta}")
def motors_move_rel(motor: str, delta: int):
    m = get_motor(motor)
    try:
        res = m.move_relative(delta)
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
    if PS90_STOP_ALL_CMD:
        for cname, ctrl in controllers.items():
            try:
                ctrl.send(PS90_STOP_ALL_CMD)
            except Exception as e:
                errors[cname] = str(e)
    stopped = []
    for name, m in motors.items():
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


@app.get("/motors/init/{motor}")
def motors_init(motor: str):
    m = get_motor(motor)
    try:
        m.initialize_axis()
    except MotorBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "initialized", "motor": motor}


@app.get("/motors/free/{motor}")
def motors_free(motor: str):
    """Release control on a registered motor axis."""
    m = get_motor(motor)
    try:
        m.free()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "freed", "motor": motor}


@app.get("/motors/control/{motor}")
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
    for name, m in motors.items():
        if m.state == DeviceState.MOVING:
            try:
                m.stop()
                print(f"Shutdown: stopped moving motor {name}")
            except Exception as e:
                print(f"Shutdown: failed to stop motor {name}: {e}")
    if not controllers:
        print("Shutdown: no controllers to close")
        return
    print(f"Shutdown: closing {len(controllers)} controller(s)")
    for name, inst in list(controllers.items()):
        try:
            inst.close()
            print(f"Closed controller: {name}")
        except Exception as e:
            print(f"Error closing controller {name}: {e}")
        # remove from registry
        try:
            del controllers[name]
        except Exception:
            pass
    # reset default name
    global default_controller_name
    default_controller_name = None
    print("Shutdown: controller registry cleared")