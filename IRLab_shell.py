# IRLab_shell.py
# startup with 'python IRLab_shell.py'

import IPython
from clients.motion_client import build_motor_list_from_config, mv, wm, mvr, free, control, free_all_motors, control_all_motors, stop, stop_all, init, init_all, Motor, DEFAULT_MAX_MOVE_DURATION
from common.errors import MotionError
from clients.spectro_client import Spectrometer
from clients.festo_client import build_actuator_list_from_config, PneumaticActuator, on, off, toggle, state
from common.http_client import safe_get, DEFAULT_TIMEOUT
from common.servers import get_server_url
from scripts.base_scripts import ascan, dscan, tweak
import os

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
    print(f"Motor server running: {_describe_status(r.json())}")
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

# Build or obtain motors. Prefer server-side single source-of-truth by asking the motion
# server to load its config and then using /motors/list to populate local Motor objects.
motors = {}
if motor_server_ok:
    try:
        motion_url = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
        # the server loads its config at startup; get the registered motors from it
        try:
            r = safe_get(f"{motion_url}/motors/list", timeout=5)
            data = r.json()
            for entry in data.get('motors', []):
                name = entry.get('name')
                step = float(entry.get('step_to_mm', 1.0))
                axis = entry.get('axis')
                controller_name = entry.get('controller')
                m = Motor(name=name, controler_channel=axis, step_to_mm=step, controller_name=controller_name,
                          max_move_duration=float(entry.get('max_move_duration', DEFAULT_MAX_MOVE_DURATION)))
                motors[name] = m
                globals()[name] = m
                print(f"  [OK] Motor '{name}'  (axis {axis}, controller: {controller_name}, step_to_mm: {step})")
            if not motors:
                print("  (no motors registered on server)")
            not_initialized = [e.get('name') for e in data.get('motors', []) if e.get('state') == 'off']
            if not_initialized:
                print(f"  [INFO] Not initialized yet: {', '.join(not_initialized)}")
                print("         Run init_all() (or init(motor)) before moving them. INIT can move the axes.")
        except Exception:
            # fallback: try local config and register on server (best-effort)
            try:
                motors = build_motor_list_from_config(register_on_server=True)
                for _name, _motor in motors.items():
                    globals()[_name] = _motor
                    print(f"  [OK] Motor '{_name}'  (axis {_motor.controler_channel}, step_to_mm: {_motor.step_to_mm})")
                if not motors:
                    print("  (no motors found in config)")
            except Exception as e:
                print(f"  [WARN] Failed to load/register motors from config: {e}")
                motors = {}
    except Exception:
        # completely offline: try local config without registering
        try:
            motors = build_motor_list_from_config(register_on_server=False)
            for _name, _motor in motors.items():
                globals()[_name] = _motor
                print(f"  [OK] Motor '{_name}'  (axis {_motor.controler_channel}, step_to_mm: {_motor.step_to_mm})")
            if not motors:
                print("  (no motors found in config)")
        except Exception as e:
            print(f"  [WARN] Failed to load local motors from config: {e}")
            motors = {}
else:
    raise Exception(f"Motion server not reachable, cannot load motors from server")

print("-----------------------------------------------------")
print("Building FESTO actuator objects...")
print("-----------------------------------------------------")

actuators = {}
if festo_server_ok:
    try:
        festo_url = get_server_url('festo_server', env_var='FESTO_SERVER', default='http://127.0.0.1:8003')
        # The server loads its config at startup. Retrieve the registered actuators and expose them as named objects in the shell.
        try:
            r = safe_get(f"{festo_url}/festo/actuators/list", timeout=5)
            data = r.json()
            for entry in data.get('actuators', []):
                name = entry.get('name')
                if not name:
                    continue
                a = PneumaticActuator(
                    name=name,
                    controller_name=entry.get('controller'),
                    module=entry.get('module'),
                    lines=entry.get('lines'),
                )
                actuators[name] = a
                globals()[name] = a
                print(f"  [OK] Actuator '{name}'  ({entry.get('controller')}/{entry.get('module')}/port0/{entry.get('lines')})")
            if not actuators:
                print("  (no actuators registered on server)")
        except Exception:
            try:
                actuators = build_actuator_list_from_config(register_on_server=True)
                for _name, _actuator in actuators.items():
                    globals()[_name] = _actuator
                    print(f"  [OK] Actuator '{_name}'  ({_actuator.module}/port0/{_actuator.lines})")
                if not actuators:
                    print("  (no actuators found in config)")
            except Exception as e:
                print(f"  [WARN] Failed to load/register FESTO actuators: {e}")
                actuators = {}
    except Exception as e:
        print(f"  [WARN] FESTO initialization failed: {e}")
        actuators = {}

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
