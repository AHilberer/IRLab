import os
import sys
import tempfile
from pathlib import Path

# make `servers`, `common`, ... importable when running pytest from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# server logs written by the tests go to a temporary directory, not to logs/
os.environ.setdefault('IRLAB_LOG_DIR', tempfile.mkdtemp(prefix='irlab_test_logs_'))


import pytest  # noqa: E402  (after the path and log directory setup above)

import servers.motion_server as ms  # noqa: E402
from tests.fake_serial import FakePS90Serial  # noqa: E402
from tests.test_server_startup import MOTORS_YAML  # noqa: E402


@pytest.fixture
def motion(monkeypatch, tmp_path):
    for name, value in [('controllers', {}), ('motors', {}), ('controller_errors', {}),
                        ('motor_errors', {}), ('default_controller_name', None),
                        ('config_error', None), ('config_path', None)]:
        monkeypatch.setattr(ms, name, value)
    fake = FakePS90Serial(move_polls=2)
    state = {'plugged': True}

    def open_serial(*a, **kw):
        if not state['plugged']:
            raise OSError('could not open port FAKE_COM')
        return fake
    monkeypatch.setattr(ms.serial, 'Serial', open_serial)

    def configure(init=False):
        cfg = tmp_path / 'motors.yaml'
        cfg.write_text(MOTORS_YAML.format(init=str(init).lower()))
        monkeypatch.setenv('IRLAB_MOTORS_CONFIG', str(cfg))
    return fake, state, configure
