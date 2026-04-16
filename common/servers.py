import os
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
