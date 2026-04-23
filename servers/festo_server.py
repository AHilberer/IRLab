from fastapi import FastAPI, HTTPException
import os

try:
    import nidaqmx
    from nidaqmx.constants import LineGrouping
except Exception:
    nidaqmx = None
    LineGrouping = None

try:
    import yaml
except Exception:
    yaml = None

app = FastAPI()

# Registry of NI-DAQ controller instances (keyed by name)
controllers = {}
default_controller_name = None

# Registry of actuator instances (keyed by logical name)
actuators = {}

DEFAULT_FESTO_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'config', 'festo.yaml')


class FestoNiDaqController:
    """NI-DAQmx controller for FESTO pneumatic on/off actuators.

    Each actuator uses a pair of complementary digital output lines:
      - line A (first)  = logical state (True = actuated, False = retracted)
      - line B (second) = inverted logical state

    This mirrors the move_festo() pattern from the test notebook:
        data = [boolean, not boolean]
    """

    def __init__(self, chassis: str = 'cDAQ1'):
        if nidaqmx is None:
            raise RuntimeError('nidaqmx is required but not installed')
        self.chassis = chassis

    def _channel(self, module: str, lines: str) -> str:
        return f"{self.chassis}{module}/port0/{lines}"

    def write(self, module: str, lines: str, state: bool):
        channel = self._channel(module, lines)
        data = [state, not state]
        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(channel, line_grouping=LineGrouping.CHAN_PER_LINE)
            task.start()
            task.write(data)
            task.stop()

    def read(self, module: str, lines: str) -> bool:
        """Read back the current state of a DO channel pair.

        Returns True when the first (active) line is high.
        """
        channel = self._channel(module, lines)
        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(channel, line_grouping=LineGrouping.CHAN_PER_LINE)
            result = task.read(number_of_samples_per_channel=1)

        # With number_of_samples_per_channel=1 and CHAN_PER_LINE, nidaqmx returns
        # a flat list [ch0_value, ch1_value] when there are exactly 2 channels.
        if isinstance(result, list) and len(result) >= 1:
            first = result[0]
            # In some versions / multi-sample mode it is a nested list
            if isinstance(first, list):
                return bool(first[0])
            return bool(first)
        return bool(result)

    def close(self):
        # Tasks are context-managed; nothing persistent to release.
        pass


class FestoActuator:
    def __init__(self, name: str, controller: FestoNiDaqController, module: str, lines: str):
        self.name = name
        self.controller = controller
        self.module = module
        self.lines = lines
        self.last_state = None  # cached last commanded state

    def set_on(self):
        self.controller.write(self.module, self.lines, True)
        self.last_state = True

    def set_off(self):
        self.controller.write(self.module, self.lines, False)
        self.last_state = False

    def read_state(self) -> bool:
        state = self.controller.read(self.module, self.lines)
        self.last_state = state
        return state

    def toggle(self) -> bool:
        state = self.read_state()
        if state:
            self.set_off()
            return False
        self.set_on()
        return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def get_controller(name: str = None) -> FestoNiDaqController:
    global default_controller_name
    if name is None:
        if default_controller_name is None:
            raise RuntimeError('No FESTO controller connected. Call /festo/connect first.')
        name = default_controller_name
    if name not in controllers:
        raise RuntimeError(f'Controller "{name}" not found')
    return controllers[name]


def get_actuator(name: str) -> FestoActuator:
    if name not in actuators:
        raise HTTPException(status_code=404, detail=f'Actuator "{name}" not registered')
    return actuators[name]


def _register_actuator_from_entry(entry: dict):
    name = str(entry.get('name', ''))
    if not name:
        return None
    if name in actuators:
        return name

    controller_name = entry.get('controller') or entry.get('controller_name') or default_controller_name
    if controller_name is None:
        raise ValueError(f'No controller specified for actuator "{name}"')
    if controller_name not in controllers:
        raise ValueError(f'Controller "{controller_name}" not found for actuator "{name}"')

    module = entry.get('module')
    lines = entry.get('lines')
    if not module or not lines:
        raise ValueError(f'Actuator "{name}" requires "module" and "lines"')

    actuators[name] = FestoActuator(
        name=name,
        controller=controllers[controller_name],
        module=module,
        lines=str(lines),
    )
    return name


def _load_config_from_dict(cfg: dict):
    global default_controller_name
    created_controllers = []
    created_actuators = []

    for ctrl in cfg.get('controllers', []):
        name = ctrl.get('name')
        if not name or name in controllers:
            continue

        ctrl_type = (ctrl.get('type') or 'nidaqmx').lower()
        if ctrl_type != 'nidaqmx':
            raise ValueError(f'Unsupported FESTO controller type "{ctrl_type}". Only "nidaqmx" is supported.')

        chassis = ctrl.get('chassis') or os.environ.get('FESTO_CHASSIS', 'cDAQ1')

        try:
            controllers[name] = FestoNiDaqController(chassis=chassis)
        except Exception as e:
            raise ValueError(f'Failed to create NI-DAQ controller "{name}": {e}')

        created_controllers.append(name)
        if default_controller_name is None:
            default_controller_name = name

    for entry in cfg.get('actuators', []):
        try:
            registered = _register_actuator_from_entry(entry)
        except ValueError as e:
            raise ValueError(str(e))
        if registered:
            created_actuators.append(registered)

    return created_controllers, created_actuators


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get('/festo/connect')
def festo_connect(name: str = 'festo', chassis: str = None):
    """Instantiate a NI-DAQ controller for the given chassis (default: cDAQ1).

    Example: /festo/connect?name=main&chassis=cDAQ1
    """
    global default_controller_name

    if name in controllers:
        return {'status': 'already_connected', 'name': name}

    if chassis is None:
        chassis = os.environ.get('FESTO_CHASSIS', 'cDAQ1')

    try:
        controllers[name] = FestoNiDaqController(chassis=chassis)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to create controller: {e}')

    if default_controller_name is None:
        default_controller_name = name

    return {'status': 'connected', 'name': name, 'chassis': chassis}


@app.get('/festo/close')
def festo_close(name: str = None):
    global default_controller_name

    if name is None:
        name = default_controller_name
    if not name or name not in controllers:
        return {'status': 'not_connected'}

    try:
        controllers[name].close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to close controller: {e}')

    del controllers[name]

    # Remove actuators that referenced this controller.
    for aname in [n for n, a in actuators.items() if a.controller is not controllers.get(name)]:
        if actuators[aname].controller not in controllers.values():
            del actuators[aname]

    if default_controller_name == name:
        default_controller_name = next(iter(controllers.keys()), None)

    return {'status': 'closed', 'name': name}


@app.get('/festo/load_config')
def festo_load_config(path: str = None):
    """Load controller and actuator definitions from config/festo.yaml.

    Example: /festo/load_config
    """
    if yaml is None:
        raise HTTPException(status_code=500, detail='pyyaml is not installed')

    if path is None:
        path = os.path.normpath(DEFAULT_FESTO_CONFIG)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f'Config not found: {path}')

    try:
        with open(path, 'r') as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to read config: {e}')

    try:
        created_controllers, created_actuators = _load_config_from_dict(cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        'status': 'loaded',
        'controllers_created': created_controllers,
        'actuators_created': created_actuators,
    }


@app.get('/festo/actuators/register')
def festo_register_actuator(name: str,
                            controller_name: str = None,
                            module: str = None,
                            lines: str = None):
    """Register a single actuator by NI-DAQ channel.

    Example: /festo/actuators/register?name=valve_1&module=Mod1&lines=line0:1
    """
    if name in actuators:
        return {'status': 'already_registered', 'name': name}

    if not module or not lines:
        raise HTTPException(status_code=400, detail='"module" and "lines" are required')

    if controller_name is None:
        controller_name = default_controller_name
    if controller_name is None:
        raise HTTPException(status_code=400, detail='No default controller; provide controller_name')
    if controller_name not in controllers:
        raise HTTPException(status_code=400, detail=f'Controller "{controller_name}" not found')

    actuators[name] = FestoActuator(
        name=name,
        controller=controllers[controller_name],
        module=module,
        lines=lines,
    )
    return {'status': 'registered', 'name': name, 'module': module, 'lines': lines, 'controller': controller_name}


@app.get('/festo/actuators/list')
def festo_list_actuators():
    out = []
    for name, a in actuators.items():
        ctrl_name = next((cn for cn, ci in controllers.items() if ci is a.controller), None)
        out.append({'name': name, 'module': a.module, 'lines': a.lines, 'controller': ctrl_name})
    return {'actuators': out}


@app.get('/festo/controllers/list')
def festo_list_controllers():
    out = [{'name': n, 'chassis': c.chassis} for n, c in controllers.items()]
    return {'controllers': out}


@app.get('/festo/actuators/on/{actuator_name}')
def festo_set_on(actuator_name: str):
    a = get_actuator(actuator_name)
    try:
        a.set_on()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {'actuator': actuator_name, 'state': 'on'}


@app.get('/festo/actuators/off/{actuator_name}')
def festo_set_off(actuator_name: str):
    a = get_actuator(actuator_name)
    try:
        a.set_off()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {'actuator': actuator_name, 'state': 'off'}


@app.get('/festo/actuators/toggle/{actuator_name}')
def festo_toggle(actuator_name: str):
    a = get_actuator(actuator_name)
    try:
        new_state = a.toggle()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {'actuator': actuator_name, 'state': 'on' if new_state else 'off'}


@app.get('/festo/actuators/state/{actuator_name}')
def festo_state(actuator_name: str):
    a = get_actuator(actuator_name)
    try:
        st = a.read_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {'actuator': actuator_name, 'state': 'on' if st else 'off'}


@app.get('/status')
def status():
    return 'This confirms connection to the FESTO NI-DAQmx server. Use /festo/actuators/* endpoints.'


@app.on_event('shutdown')
def shutdown_close_controllers():
    global default_controller_name
    for name in list(controllers.keys()):
        try:
            controllers[name].close()
        except Exception:
            pass
        try:
            del controllers[name]
        except Exception:
            pass
    actuators.clear()
    default_controller_name = None


## launch with: uvicorn servers.festo_server:app --host 0.0.0.0 --port 8003
