import os
from urllib.parse import urlsplit
try:
    import yaml
except Exception:
    yaml = None


DEFAULT_SERVERS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'config', 'servers.yaml')
)


def load_servers_config(path: str = None) -> dict:
    """Load config/servers.yaml and return a dict. Returns empty dict if file missing or PyYAML not installed."""
    if path is None:
        path = DEFAULT_SERVERS_PATH
    if not os.path.exists(path):
        return {}
    if yaml is None:
        return {}
    with open(path, 'r') as fh:
        return yaml.safe_load(fh) or {}


def get_server_url(key: str, env_var: str = None, default: str = None) -> str:
    """Resolve a server URL by checking (in order): environment variable, config/servers.yaml, then default.

    key should match the key used in config/servers.yaml (e.g. 'motion_server').
    env_var is optional and if provided will be checked in the environment first.
    """
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val
    cfg = load_servers_config()
    if key in cfg and cfg[key]:
        return cfg[key]
    return default



def get_server_port(key: str, env_var: str = None, default: int = None) -> int:
    """Return the port of a server, taken from its URL (see `get_server_url`).

    Used by the start_*.ps1 scripts so the port is defined in one place.
    """
    url = get_server_url(key, env_var=env_var)
    port = urlsplit(url).port if url else None
    if port is None:
        if default is None:
            raise ValueError(f'No port found for "{key}" in config/servers.yaml or ${env_var}')
        return default
    return port
