from fastapi import FastAPI, HTTPException
import time
import os

try:
    import serial
except Exception:
    serial = None
try:
    import yaml
except Exception:
    yaml = None

app = FastAPI()

# Global controller instance (lazy-created)
# controllers registry and default name
controllers = {}
default_controller_name = None

# registry of named motor objects (create once via /ps90/register)
motors = {}

# default config path (relative to repo root)
DEFAULT_MOTOR_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'motors.yaml')


class PS90:
    def __init__(self, port='COM25', baudrate=9600):
        if serial is None:
            raise RuntimeError("pyserial is required but not installed")
        self.ser = serial.Serial(port, baudrate,
                    timeout=1,
                    stopbits=1,
                    parity='N',
                    bytesize=8)
        time.sleep(1)  # allow connection to settle

    def send(self, cmd):
        full_cmd = cmd + '\r'   # OWIS uses CR as end character
        self.ser.reset_input_buffer()
        self.ser.write(full_cmd.encode())
        time.sleep(0.05)
        response = self.ser.read_all().decode().strip()
        return response

    def read(self):
        return

    def get_status(self):
        response = self.send('?ASTAT')
        if response=='':
            return 'Problem getting status from PS90 unit.'
        else:
            return response

    def init_axis(self, axis):
        self.send(f'AXIS{axis}=1')
        self.send(f'INIT{axis}')
        return


    def close(self):
        self.ser.close()


class PS90_motor:
    def __init__(self, name, control_unit, control_axis_number, step_to_mm=1):
        self.control_unit = control_unit
        self.name = name
        self.control_axis_number = control_axis_number
        self.step_to_mm = step_to_mm
        self.current_position_step = None
        
    
    def initialize_axis(self):
        control_unit_status = self.control_unit.get_status()
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
    
    def read_parameters(self):
        print('------------------------------------------')
        print(f'Parameters for {self.name}, PS90 motor axis {self.control_axis_number}')
        control_unit_status = self.control_unit.get_status()
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
        self.control_unit.send(f'AXIS{self.control_axis_number}=1')
        self.control_unit.send(f'INIT{self.control_axis_number}')
    
    def set_absolute_mode(self):
        self.control_unit.send(f'ABSOL{self.control_axis_number}')
        
    def set_relative_mode(self):
        self.control_unit.send(f'RELAT{self.control_axis_number}')
        
    def read_current_position(self):
        self.current_position_step = int(self.control_unit.send(f'?CNT{self.control_axis_number}'))
        return self.current_position_step
        
    def move_absolute(self, target_position:int):
        print(f"Moving {self.name} to {target_position}")
        try:
            self.control_unit.send(f'PSET{self.control_axis_number}={target_position}')
            self.control_unit.send(f'PGO{self.control_axis_number}')
        except:
            print(f'Error sending movement command to axis {self.control_axis_number}.')
            raise
            
        while self.control_unit.send(f'?ASTAT')[self.control_axis_number-1]=='T':
                time.sleep(0.05)
        actual_pos = self.read_current_position()
        if int(actual_pos)==target_position:
            return 'Move OK'
        else:
            print('Wrong final position')
    
    def move_relative(self, displacement_step:int):
        # Ensure reference position is known before computing relative target.
        if self.current_position_step is None:
            self.read_current_position()
        target_position = self.current_position_step + displacement_step
        self.move_absolute(target_position)


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

    try:
        controllers[name].close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error closing controller: {e}')

    # remove from registry and update default if needed
    del controllers[name]
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


@app.get("/ps90/register/{name}/{axis}")
def ps90_register(name: str, axis: int, step_to_mm: float = 1.0, controller_name: str = None):
    """Register a named motor backed by an existing controller instance.
    If `controller_name` is omitted the default controller is used.
    Example: /ps90/register/sx/1?controller_name=main&step_to_mm=0.01
    """
    if name in motors:
        return {"status": "already_registered", "name": name}
    try:
        ctrl = get_controller(controller_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    motor = PS90_motor(name=name, control_unit=ctrl, control_axis_number=axis, step_to_mm=step_to_mm)
    motors[name] = motor
    return {"status": "registered", "name": name, "axis": axis, "controller": controller_name}


def get_motor(name: str) -> PS90_motor:
    if name not in motors:
        raise HTTPException(status_code=404, detail=f'Motor "{name}" not registered. Call /ps90/register/{{name}}/{{axis}}')
    return motors[name]


@app.get("/ps90/list")
def ps90_list():
    """List registered motors."""
    return {"motors": [{"name": n, "axis": m.control_axis_number, "step_to_mm": m.step_to_mm} for n, m in motors.items()]}


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
                try:
                    controllers[cname] = PS90(port=port, baudrate=baud)
                    if default_controller_name is None:
                        default_controller_name = cname
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f'Failed to create controller "{cname}": {e}')
            else:
                # unknown controller type: skip (could add hooks for other types)
                continue

    if 'motors' not in cfg:
        raise ValueError('Config missing top-level "motors" key')

    for entry in cfg['motors']:
        name = entry.get('name')
        if not name:
            continue
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

        if controller_name not in controllers:
            raise ValueError(f'Controller "{controller_name}" not found for motor {name}')

        axis = int(entry.get('controller_channel') or entry.get('controler_channel') or entry.get('axis'))
        step = float(entry.get('step_to_mm', 1.0))
        velocity = entry.get('velocity')
        acceleration = entry.get('acceleration')

        if name in motors:
            continue
        ctrl = controllers[controller_name]
        motor = PS90_motor(name=name, control_unit=ctrl, control_axis_number=axis, step_to_mm=step)
        motors[name] = motor
        created.append(name)
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
            except Exception:
                # continue registering others even if one fails
                pass

    return created


@app.get("/ps90/load_config")
def ps90_load_config(path: str = None, initialize: bool = False):
    """Load motor definitions from a YAML file and register them. If `initialize=true`, call initialize on each.
    By default the server will look for `motors.yaml` next to the repository root.
    """
    if yaml is None:
        raise HTTPException(status_code=500, detail='pyyaml is not installed in this environment')
    if path is None:
        # normalize default path
        path = os.path.normpath(DEFAULT_MOTOR_CONFIG)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f'Config file not found: {path}')
    try:
        with open(path, 'r') as fh:
            cfg = yaml.safe_load(fh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to read config: {e}')
    try:
        created = _load_motor_config_from_dict(cfg, initialize=initialize)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "loaded", "created": created}


@app.get("/motors/move_abs/{motor}/{position}")
def motors_move_abs(motor: str, position: int):
    """Generic endpoint to move a registered motor by name (controller-agnostic)."""
    m = get_motor(motor)
    try:
        res = m.move_absolute(position)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": res}


@app.get("/motors/move_rel/{motor}/{delta}")
def motors_move_rel(motor: str, delta: int):
    m = get_motor(motor)
    try:
        m.move_relative(delta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": "move_command_sent", "motor": motor}


@app.get("/motors/read/{motor}")
def motors_read(motor: str):
    m = get_motor(motor)
    try:
        pos = m.read_current_position()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"motor": motor, "position": pos}


@app.get("/motors/init/{motor}")
def motors_init(motor: str):
    m = get_motor(motor)
    try:
        m.initialize_axis()
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "controlled", "motor": motor}


@app.get("/motors/register")
def motors_register(name: str,
                   controller_type: str = None,
                   controller_name: str = None,
                   controller_port: str = None,
                   controller_baud: int = 9600,
                   axis: int = None,
                   step_to_mm: float = 1.0,
                   velocity: float = None,
                   acceleration: float = None):
    """Generic motor registration endpoint.

    Examples:
      /motors/register?name=sx&controller_name=main_ps90&axis=2
      /motors/register?name=mx&controller_type=ps90&controller_port=COM25&axis=1
    """
    if not name or axis is None:
        raise HTTPException(status_code=400, detail='name and axis are required')
    if name in motors:
        return {"status": "already_registered", "name": name}

    # Resolve controller
    ctrl = None
    if controller_name:
        if controller_name in controllers:
            ctrl = controllers[controller_name]
        else:
            # no controller with that name exists -> error (simple behavior)
            raise HTTPException(status_code=400, detail=f'Controller "{controller_name}" not found')
    else:
        # no controller name provided, try to use controller_type
        # require explicit controller_name; do not auto-create based on controller_type in simple mode
        raise HTTPException(status_code=400, detail='controller_name is required for registration in simple mode')

    # create motor object
    try:
        motor = PS90_motor(name=name, control_unit=ctrl, control_axis_number=axis, step_to_mm=step_to_mm)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    motors[name] = motor

    # apply motion parameters if provided
    try:
        if velocity is not None:
            ctrl.send(f'PVEL{axis}={velocity}')
        if acceleration is not None:
            ctrl.send(f'ACC{axis}={acceleration}')
    except Exception:
        pass

    return {"status": "registered", "name": name, "axis": axis, "controller": controller_name or controller_type}


@app.get("/motors/list")
def motors_list():
    """Return registered motors and their controller mappings."""
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
            "controller": ctrl_name,
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
    return "This confirms connection to the motion server. Use /motors/* endpoints to control hardware."


## launch with 'uvicorn servers.motion_server:app --host 0.0.0.0 --port 8001'


@app.on_event("shutdown")
def shutdown_close_controllers():
    """Gracefully close all connected controller instances when the FastAPI app is shutting down.

    This will attempt to call `.close()` on each controller and clear the registry so serial
    ports are released when the server process exits (for example on Ctrl+C from uvicorn).
    """
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