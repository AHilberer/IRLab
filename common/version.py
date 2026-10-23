"""Version of the IRLab code, shown in the shell banner, in the servers' console and
log at startup, and reported by the servers' /status endpoint.

VERSION is set by hand for each release, and the release commit is tagged in git as
v<VERSION>.
"""

VERSION = '1.1'


def get_version() -> str:
    """Return the version string, e.g. 'v1.0'."""
    return f'v{VERSION}'
