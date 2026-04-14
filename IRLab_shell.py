# IRLab_shell.py
# startup with 'python IRLab_shell.py'

import IPython
from clients.motion_client import build_motor_list_from_config, mv, wm, mvr, free, control, free_all_motors, control_all_motors, Motor
from clients.spectro_client import Spectrometer
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

# Check motion server status
try:
    motion_url = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
    r = safe_get(f"{motion_url}/status", timeout=STARTUP_TIMEOUT)
    print(f"Motor server running: {r.text}")
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
except Exception:
    print("Spectro server NOT reachable")
    spectro_server_ok = False

# Build or obtain motors. Prefer server-side single source-of-truth by asking the motion
# server to load its config and then using /motors/list to populate local Motor objects.
motors = {}
if motor_server_ok:
    try:
        motion_url = get_server_url('motion_server', env_var='MOTION_SERVER', default='http://127.0.0.1:8001')
        # ask the server to load its config and initialize axes (non-fatal)
        try:
            safe_get(f"{motion_url}/ps90/load_config?initialize=true", timeout=5)
        except Exception:
            # server may not be up or may not allow load; continue and try to read list
            pass

        # try to get the registered motors from the server
        try:
            r = safe_get(f"{motion_url}/motors/list", timeout=5)
            data = r.json()
            for entry in data.get('motors', []):
                name = entry.get('name')
                step = float(entry.get('step_to_mm', 1.0))
                axis = entry.get('axis')
                controller_name = entry.get('controller')
                m = Motor(name=name, controler_channel=axis, step_to_mm=step, controller_name=controller_name)
                motors[name] = m
                globals()[name] = m
        except Exception:
            # fallback: try local config and register on server (best-effort)
            try:
                motors = build_motor_list_from_config(register_on_server=True)
                for _name, _motor in motors.items():
                    globals()[_name] = _motor
            except Exception as e:
                print(f"Warning: failed to load/register motors from config: {e}")
                motors = {}
    except Exception:
        # completely offline: try local config without registering
        try:
            motors = build_motor_list_from_config(register_on_server=False)
            for _name, _motor in motors.items():
                globals()[_name] = _motor
        except Exception as e:
            print(f"Warning: failed to load local motors from config: {e}")
            motors = {}
else:
    raise Exception(f"Motion server not reachable, cannot load motors from server")

print("-----------------------------------------------------")
print("Starting custom shell interface")
print("-----------------------------------------------------")

IPython.start_ipython(argv=[], user_ns=globals(), display_banner=False)
