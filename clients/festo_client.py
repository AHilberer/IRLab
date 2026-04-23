import os

from common.http_client import safe_get, DEFAULT_TIMEOUT
from common.servers import get_server_url

try:
    import yaml
except Exception:
    yaml = None

BASE_URL = get_server_url('festo_server', env_var='FESTO_SERVER', default='http://127.0.0.1:8003')


def _as_name(actuator):
    return actuator.name if hasattr(actuator, 'name') else str(actuator)


class PneumaticActuator:
    """Client-side handle for a FESTO pneumatic on/off actuator.

    Delegates all hardware operations to the FESTO server via HTTP.
    """

    def __init__(self, name: str, controller_name: str = None,
                 module: str = None, lines: str = None):
        self.name = name
        self.controller_name = controller_name
        self.module = module
        self.lines = lines

    def on(self, timeout=DEFAULT_TIMEOUT):
        r = safe_get(f"{BASE_URL}/festo/actuators/on/{self.name}", timeout=timeout)
        return r.json()

    def off(self, timeout=DEFAULT_TIMEOUT):
        r = safe_get(f"{BASE_URL}/festo/actuators/off/{self.name}", timeout=timeout)
        return r.json()

    def toggle(self, timeout=DEFAULT_TIMEOUT):
        r = safe_get(f"{BASE_URL}/festo/actuators/toggle/{self.name}", timeout=timeout)
        return r.json()

    def state(self, timeout=DEFAULT_TIMEOUT):
        r = safe_get(f"{BASE_URL}/festo/actuators/state/{self.name}", timeout=timeout)
        return r.json()

    def __repr__(self):
        return f"PneumaticActuator(name={self.name!r})"


# Alias kept short for interactive shell use.
Actuator = PneumaticActuator


def build_actuator_list_from_config(path: str = None, register_on_server: bool = True):
    """Load actuator definitions from config/festo.yaml.

    Returns a dict mapping actuator name -> PneumaticActuator instance.
    If register_on_server=True, each actuator is also registered on the FESTO server.
    """
    if path is None:
        path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config', 'festo.yaml'))

    if not os.path.exists(path):
        raise FileNotFoundError(f'FESTO config not found: {path}')

    if yaml is None:
        raise RuntimeError('pyyaml is required to load FESTO config')

    with open(path, 'r') as fh:
        cfg = yaml.safe_load(fh) or {}

    result = {}
    for entry in cfg.get('actuators', []):
        name = str(entry.get('name', ''))
        if not name:
            continue

        module = entry.get('module')
        lines = str(entry.get('lines', ''))
        controller_name = entry.get('controller') or entry.get('controller_name')

        actuator = PneumaticActuator(
            name=name,
            controller_name=controller_name,
            module=module,
            lines=lines,
        )
        result[name] = actuator

        if register_on_server:
            params = {'name': name}
            if controller_name:
                params['controller_name'] = controller_name
            if module:
                params['module'] = module
            if lines:
                params['lines'] = lines
            try:
                safe_get(f"{BASE_URL}/festo/actuators/register", params=params, timeout=DEFAULT_TIMEOUT)
            except Exception:
                pass

    return result


# ---------------------------------------------------------------------------
# Multi-actuator helper functions (mirror the motion_client.py style)
# ---------------------------------------------------------------------------

def on(*actuators, timeout=DEFAULT_TIMEOUT):
    """Activate one or more actuators. Usage: on(a1, a2, ...)"""
    results = []
    for actuator in actuators:
        name = _as_name(actuator)
        try:
            r = safe_get(f"{BASE_URL}/festo/actuators/on/{name}", timeout=timeout)
            results.append((name, r.json()))
        except Exception as e:
            results.append((name, {'error': str(e)}))
    return results


def off(*actuators, timeout=DEFAULT_TIMEOUT):
    """Deactivate one or more actuators. Usage: off(a1, a2, ...)"""
    results = []
    for actuator in actuators:
        name = _as_name(actuator)
        try:
            r = safe_get(f"{BASE_URL}/festo/actuators/off/{name}", timeout=timeout)
            results.append((name, r.json()))
        except Exception as e:
            results.append((name, {'error': str(e)}))
    return results


def toggle(*actuators, timeout=DEFAULT_TIMEOUT):
    """Toggle one or more actuators. Usage: toggle(a1, a2, ...)"""
    results = []
    for actuator in actuators:
        name = _as_name(actuator)
        try:
            r = safe_get(f"{BASE_URL}/festo/actuators/toggle/{name}", timeout=timeout)
            results.append((name, r.json()))
        except Exception as e:
            results.append((name, {'error': str(e)}))
    return results


def state(*actuators, timeout=DEFAULT_TIMEOUT):
    """Read on/off state for one or more actuators. Usage: state(a1, a2, ...)"""
    results = {}
    for actuator in actuators:
        name = _as_name(actuator)
        try:
            r = safe_get(f"{BASE_URL}/festo/actuators/state/{name}", timeout=timeout)
            results[name] = r.json().get('state')
        except Exception:
            results[name] = None
    return results
