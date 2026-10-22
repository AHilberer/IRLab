# IRLab_shell.py
# startup with 'python IRLab_shell.py'

import builtins
import keyword

import IPython
from clients.motion_client import load_motors_from_server, mv, wm, mvr, free, control, free_all_motors, control_all_motors, stop, stop_all, init, init_all, Motor
from common.errors import MotionError
from clients.spectro_client import Spectrometer
from clients.festo_client import load_actuators_from_server, PneumaticActuator, on, off, toggle, state
from common.http_client import safe_get, DEFAULT_TIMEOUT
from common.servers import get_server_url
from scripts.base_scripts import ascan, dscan, tweak

print("""
 █████ ███████████   █████                 █████    
▒▒███ ▒▒███▒▒▒▒▒███ ▒▒███                 ▒▒███     
 ▒███  ▒███    ▒███  ▒███         ██████   ▒███████ 
 ▒███  ▒██████████   ▒███        ▒▒▒▒▒███  ▒███▒▒███
 ▒███  ▒███▒▒▒▒▒███  ▒███         ███████  ▒███ ▒███
 ▒███  ▒███    ▒███  ▒███      █ ███▒▒███  ▒███ ▒███
 █████ █████   █████ ███████████▒▒████████ ████████ 
▒▒▒▒▒ ▒▒▒▒▒   ▒▒▒▒▒ ▒▒▒▒▒▒▒▒▒▒▒  ▒▒▒▒▒▒▒▒ ▒▒▒▒▒▒▒▒  
                                                    
                                                    
 """)

spec = Spectrometer()


# Note: client functions `mv` and `wm` are imported directly and available in the shell.
# `ascan` is imported from `scripts/base_scripts.py`.
print("-----------------------------------------------------")
print("Checking connections...")
print("-----------------------------------------------------")

# prefer a short timeout at startup so the shell doesn't block
STARTUP_TIMEOUT = 2


def _describe_status(data):
    """One-line summary of a server's /status JSON, followed by its errors if any."""
    if not isinstance(data, dict):
        return str(data)
    lines = [f"{data.get('status', '?')} (version {data.get('version', '?')})"]
    if data.get('config_error'):
        lines.append(f"  [ERROR] {data['config_error']}")
    for c in data.get('controllers', []):
        if c.get('state') == 'error':
            lines.append(f"  [ERROR] controller {c.get('name')}: {c.get('error')}")
    for group in ('motors', 'actuators'):
        for name, err in (data.get(group) or {}).get('errors', {}).items():
            lines.append(f"  [ERROR] {name}: {err}")
    return "\n".join(lines)

# Check motion server status
try:
    motion_url = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
    r = safe_get(f"{motion_url}/status", timeout=STARTUP_TIMEOUT)
    motion_status = r.json()
    print(f"Motor server running: {_describe_status(motion_status)}")
    motor_server_ok = True
except Exception:
    print("Motor server NOT reachable")
    motor_server_ok = False
# Check spectro server status
try:
    s_status = spec.status(timeout=STARTUP_TIMEOUT)
    if s_status is None:
        print("Spectro server NOT reachable")
        spectro_server_ok = False
    else:
        print(f"Spectro server running: {s_status}")
        spectro_server_ok = True
        # ask the server to load its config and connect the hardware (non-fatal)
        try:
            spectro_url = get_server_url('spectro_server', env_var='SPECTRO_SERVER', default='http://127.0.0.1:8002')
            safe_get(f"{spectro_url}/spectro/load_config", timeout=5)
        except Exception as e:
            print(f"  [WARN] Failed to load/connect spectrometer from config: {e}")
except Exception:
    print("Spectro server NOT reachable")
    spectro_server_ok = False

# Check FESTO server status
try:
    festo_url = get_server_url('festo_server', env_var='FESTO_SERVER', default='http://127.0.0.1:8003')
    r = safe_get(f"{festo_url}/status", timeout=STARTUP_TIMEOUT)
    print(f"FESTO server running: {_describe_status(r.json())}")
    festo_server_ok = True
except Exception:
    print("FESTO server NOT reachable")
    festo_server_ok = False

print("-----------------------------------------------------")
print("Checked connections to servers.")
print("-----------------------------------------------------")
print("-----------------------------------------------------")
print("Building controlers and motor objects...")
print("-----------------------------------------------------")

def _expose(name, obj):
    """Make a motor / actuator available by its name in the shell, unless the name is not
    a valid Python identifier or would overwrite something else (mv, wm, spec, a builtin...).
    It is always available as motors[name] / actuators[name]."""
    if not name.isidentifier() or keyword.iskeyword(name):
        print(f"  [WARN] '{name}' is not a valid Python name: use motors['{name}'] / actuators['{name}']")
        return False
    existing = globals().get(name, getattr(builtins, name, None))
    # replacing an object of the same kind (e.g. after reconnecting) is fine
    if existing is not None and type(existing) is not type(obj):
        print(f"  [WARN] '{name}' would overwrite the existing '{name}' ({type(existing).__name__}): "
              f"not exposed, use motors['{name}'] / actuators['{name}']")
        return False
    globals()[name] = obj
    return True


# The motion server is the single source of truth: it loads config/motors.yaml at startup.
motors = {}
if motor_server_ok:
    try:
        motors = load_motors_from_server(timeout=5)
    except Exception as e:
        print(f"  [WARN] Failed to get the motors from the motion server: {e}")
    for name, m in motors.items():
        _expose(name, m)
        print(f"  [OK] Motor '{name}'  (axis {m.controler_channel}, controller: {m.controller_name}, "
              f"step_to_mm: {m.step_to_mm}, unit: {m.unit})")
    if not motors:
        print("  (no motors registered on server)")
    not_initialized = (motion_status.get('motors') or {}).get('not_initialized', [])
    if not_initialized:
        print(f"  [INFO] Not initialized yet: {', '.join(not_initialized)}")
        print("         Run init_all() (or init(motor)) before moving them. INIT can move the axes.")
else:
    raise Exception(f"Motion server not reachable, cannot load motors from server")

print("-----------------------------------------------------")
print("Building FESTO actuator objects...")
print("-----------------------------------------------------")

# The FESTO server is the single source of truth: it loads config/festo.yaml at startup.
actuators = {}
if festo_server_ok:
    try:
        actuators = load_actuators_from_server(timeout=5)
    except Exception as e:
        print(f"  [WARN] Failed to get the actuators from the FESTO server: {e}")
    for name, a in actuators.items():
        _expose(name, a)
        print(f"  [OK] Actuator '{name}'  ({a.controller_name}/{a.module}/port0/{a.lines})")
    if not actuators:
        print("  (no actuators registered on server)")

STATE_CHECK_TIMEOUT = 2


def check_all():
    """Query GET /state on all three device servers and print their reported state.

    Prints UNREACHABLE for a server if the request fails or times out.
    """
    servers = [
        ("motion_server", get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')),
        ("spectro_server", get_server_url('spectro_server', env_var='SPECTRO_SERVER', default='http://127.0.0.1:8002')),
        ("festo_server", get_server_url('festo_server', env_var='FESTO_SERVER', default='http://127.0.0.1:8003')),
    ]
    for name, url in servers:
        try:
            r = safe_get(f"{url}/state", timeout=STATE_CHECK_TIMEOUT)
            print(f"{name}: {r.json().get('state', 'UNKNOWN')}")
        except Exception:
            print(f"{name}: UNREACHABLE")


print("-----------------------------------------------------")
print("Starting custom shell interface.")
print("-----------------------------------------------------")

IPython.start_ipython(argv=[], user_ns=globals(), display_banner=False)
