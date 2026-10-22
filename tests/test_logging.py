"""Task 12: persistent logs of the actions on the bench."""
import logging

from fastapi.testclient import TestClient

import servers.motion_server as ms
from common.logging_setup import get_log_dir


def _log_text():
    for h in ms.logger.handlers:
        h.flush()
    return (get_log_dir() / 'motion_server.log').read_text(encoding='utf-8')


def test_actions_are_logged_with_client_ip_and_result(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        client.post('/motors/init/sx')
        client.post('/motors/move_abs/sx', json={'position': 1234})
        client.post('/motors/move_abs/sy', json={'position': 5})     # not initialized: error
        client.get('/motors/read/sx')
    log = _log_text()
    ok = [l for l in log.splitlines() if 'POST /motors/move_abs/sx {"position":1234} from testclient: HTTP 200' in l]
    assert ok and "'position': 1234" in ok[-1]
    err = [l for l in log.splitlines() if 'POST /motors/move_abs/sy' in l and 'HTTP 500' in l]
    assert err and 'ERROR' in err[-1] and 'not initialized' in err[-1]
    assert 'GET /motors/read' not in log          # reads are not logged


def test_serial_debug_log_is_off_by_default_and_can_be_enabled(motion, tmp_path, monkeypatch):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        client.get('/motors/read/sx')
    assert ms.serial_logger.level == logging.WARNING
    assert '>> ?CNT2' not in _log_text()

    cfg = tmp_path / 'motors.yaml'
    cfg.write_text(cfg.read_text() + '\nlog_serial: true\n')
    with TestClient(ms.app) as client:
        client.get('/motors/read/sx')
    assert 'FAKE_COM >> ?CNT2' in _log_text()
    assert "FAKE_COM << b'0\\r'" in _log_text()
    ms.serial_logger.setLevel(logging.WARNING)


def test_start_line_logged_with_and_without_body(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        client.post('/motors/init/sy')
        client.post('/motors/move_rel/sy', json={'delta': 7})
    log = _log_text()
    assert 'POST /motors/init/sy from testclient: started' in log
    assert 'POST /motors/move_rel/sy {"delta":7} from testclient: started' in log
