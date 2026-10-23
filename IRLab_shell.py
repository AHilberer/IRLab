# IRLab_shell.py
# startup with 'python IRLab_shell.py'

import builtins
import keyword

import IPython
from clients.motion_client import load_motors_from_server, mv, wm, mvr, free, control, free_all_motors, control_all_motors, stop, stop_all, init, init_all, Motor
from common.errors import MotionError, ServerError
from clients.spectro_client import Spectrometer
from clients.festo_client import load_actuators_from_server, PneumaticActuator, on, off, toggle, state
from common.http_client import safe_get, safe_post, DEFAULT_TIMEOUT
from common.servers import get_server_url, is_server_disabled
from common.version import VERSION, get_version
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
print(f"IRLab shell {get_version()}")
print()

spec = Spectrometer()

# prefer a short timeout at startup so the shell doesn't block
STARTUP_TIMEOUT = 2

MOTION_URL = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
SPECTRO_URL = get_server_url('spectro_server', env_var='SPECTRO_SERVER', default='http://127.0.0.1:8002')
FESTO_URL = get_server_url('festo_server', env_var='FESTO_SERVER', default='http://127.0.0.1:8003')

# reachability of each server, updated by reconnect()
servers_ok = {'motion': False, 'spectro': False, 'festo': False}
# servers listed in `disabled_servers` of config/servers.yaml: never contacted
disabled = {key for key in servers_ok if is_server_disabled(f'{key}_server')}
# objects created from the servers, also exposed by name in the shell (see _expose)
motors = {}
actuators = {}


def _describe_status(data):
    """One-line summary of a server's /status JSON, followed by its errors if any."""
    if not isinstance(data, dict):
        return str(data)
    version = data.get('version', '?')
    lines = [f"{data.get('status', '?')} (v{version})"]
    if version != VERSION:
        lines.append(f"  [WARN] the server runs v{version} but this shell is v{VERSION}: "
                     "update the code on that PC (or on this one)")
    if data.get('config_error'):
        lines.append(f"  [ERROR] {data['config_error']}")
    for c in data.get('controllers', []):
        if c.get('state') == 'error':
            lines.append(f"  [ERROR] controller {c.get('name')}: {c.get('error')}")
    for group in ('motors', 'actuators'):
        for name, err in (data.get(group) or {}).get('errors', {}).items():
            lines.append(f"  [ERROR] {name}: {err}")
    return "\n".join(lines)


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


def _server_status(label, url):
    """Return the server's /status JSON, or None (with a warning) if it is not reachable."""
    try:
        status = safe_get(f"{url}/status", timeout=STARTUP_TIMEOUT).json()
    except ServerError as e:
        print(f"[WARN] {label} server at {url} answered with an error: {e}")
        return None
    except Exception:
        print(f"[WARN] {label} server NOT reachable at {url}")
        return None
    print(f"{label} server running: {_describe_status(status)}")
    return status


def _connect_motion():
    """Connect to the motion server and create the Motor objects (the server is the
    single source of truth: it loads config/motors.yaml at startup)."""
    status = _server_status("Motion", MOTION_URL)
    if status is None:
        return False
    try:
        loaded = load_motors_from_server(timeout=5)
    except Exception as e:
        print(f"  [WARN] Failed to get the motors from the motion server: {e}")
        return False
    for name, m in loaded.items():
        motors[name] = m
        _expose(name, m)
        print(f"  [OK] Motor '{name}'  (axis {m.controller_channel}, controller: {m.controller_name}, "
              f"step_to_mm: {m.step_to_mm}, unit: {m.unit})")
    if not loaded:
        print("  (no motors registered on server)")
    not_initialized = (status.get('motors') or {}).get('not_initialized', [])
    if not_initialized:
        print(f"  [INFO] Not initialized yet: {', '.join(not_initialized)}")
        print("         Run init_all() (or init(motor)) before moving them: it powers the motors.")
    return True


def _connect_festo():
    """Connect to the FESTO server and create the PneumaticActuator objects (the server
    is the single source of truth: it loads config/festo.yaml at startup)."""
    if _server_status("FESTO", FESTO_URL) is None:
        return False
    try:
        loaded = load_actuators_from_server(timeout=5)
    except Exception as e:
        print(f"  [WARN] Failed to get the actuators from the FESTO server: {e}")
        return False
    for name, a in loaded.items():
        actuators[name] = a
        _expose(name, a)
        print(f"  [OK] Actuator '{name}'  ({a.controller_name}/{a.module}/port0/{a.lines})")
    if not loaded:
        print("  (no actuators registered on server)")
    return True


def _connect_spectro():
    """Connect to the spectro server and ask it to load its config (connect the hardware)."""
    if _server_status("Spectro", SPECTRO_URL) is None:
        return False
    try:
        safe_post(f"{SPECTRO_URL}/spectro/load_config", timeout=5)
    except Exception as e:
        print(f"  [WARN] Failed to load/connect spectrometer from config: {e}")
    return True


def _print_summary():
    print("-----------------------------------------------------")
    print("Summary:")
    for key, label, url in (('motion', 'Motion server', MOTION_URL),
                            ('spectro', 'Spectro server', SPECTRO_URL),
                            ('festo', 'FESTO server', FESTO_URL)):
        if key in disabled:
            print(f"  {label:<15} {'DISABLED':<14} (disabled_servers in config/servers.yaml)")
        else:
            print(f"  {label:<15} {'OK' if servers_ok[key] else 'NOT REACHABLE':<14} {url}")
    print(f"  {len(motors)} motor(s), {len(actuators)} actuator(s) loaded")
    if not all(ok for key, ok in servers_ok.items() if key not in disabled):
        print("  Start the missing server(s), then run reconnect().")
    print("-----------------------------------------------------")


def reconnect():
    """Retry the connection to all servers and create the missing motor / actuator
    objects (e.g. after starting a server, or after /admin/reload_config on a server)."""
    print("-----------------------------------------------------")
    print("Connecting to servers...")
    print("-----------------------------------------------------")
    for key, connect in (('motion', _connect_motion), ('spectro', _connect_spectro),
                         ('festo', _connect_festo)):
        servers_ok[key] = key not in disabled and connect()
    _print_summary()


STATE_CHECK_TIMEOUT = 2


def check_all():
    """Query GET /state on all three device servers and print their reported state.

    Prints UNREACHABLE for a server if the request fails or times out.
    """
    servers = [
        ("motion_server", MOTION_URL),
        ("spectro_server", SPECTRO_URL),
        ("festo_server", FESTO_URL),
    ]
    for name, url in servers:
        if is_server_disabled(name):
            print(f"{name}: DISABLED")
            continue
        try:
            r = safe_get(f"{url}/state", timeout=STATE_CHECK_TIMEOUT)
            print(f"{name}: {r.json().get('state', 'UNKNOWN')}")
        except Exception:
            print(f"{name}: UNREACHABLE")


# A missing server only produces a warning: the shell starts with what is available.
reconnect()

print("Starting custom shell interface.")
print("-----------------------------------------------------")

IPython.start_ipython(argv=[], user_ns=globals(), display_banner=False)
