"""Tasks 3 and 4, client side: mv/mvr raise MotionError, scans stop, Ctrl+C sends stop."""
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import clients.motion_client as mc
import common.http_client as hc
import scripts.base_scripts as bs
import servers.motion_server as ms
from common.errors import MotionError, MotorBusyError
from tests.fake_serial import FakePS90Serial


@pytest.fixture
def bench(monkeypatch):
    """Motion server with a fake PS90, reached by the real client code."""
    fake = FakePS90Serial(move_polls=2)
    monkeypatch.setattr(ms.serial, 'Serial', lambda *a, **kw: fake)
    ctrl = ms.PS90(port='FAKE', command_delay=0)
    monkeypatch.setattr(ms, 'controllers', {'main': ctrl})
    monkeypatch.setattr(ms, 'motors', {'m1': ms.PS90_motor('m1', ctrl, 1)})
    ms.motors['m1'].state = ms.DeviceState.ON   # as after init()
    tc = TestClient(ms.app)
    requests_seen = []

    def fake_request(method, url, timeout=None, **kwargs):
        parts = urlsplit(url)
        path = parts.path + (f'?{parts.query}' if parts.query else '')
        requests_seen.append((method, parts.path))
        if parts.path.startswith('/motors/move_abs'):
            moves.append(kwargs['json']['position'])
        if 'before' in bench_hooks:
            bench_hooks['before'](method, parts.path, kwargs.get('json'))
        resp = tc.request(method, path, **kwargs)
        resp.ok = resp.is_success
        return resp

    bench_hooks = {}
    moves = []          # targets of the absolute moves sent, in steps
    monkeypatch.setattr(hc.requests, 'request', fake_request)
    motor = mc.Motor('m1', controller_channel=1, step_to_mm=1.0)
    bench_hooks['moves'] = moves
    return fake, motor, requests_seen, bench_hooks


def test_mv_returns_final_position(bench):
    fake, motor, seen, hooks = bench
    res = mc.mv(motor, 50, show_positions=False)
    assert res == [('m1', {'result': 'ok', 'motor': 'm1', 'position': 50})]


def test_mv_raises_motion_error_with_server_detail(bench):
    fake, motor, seen, hooks = bench
    fake.blocked[0] = (30, 'L')
    with pytest.raises(MotionError, match='reached 30'):
        mc.mv(motor, 50, show_positions=False)
    with pytest.raises(MotionError, match='reached 30'):
        mc.mvr(motor, 20, show_positions=False)


def test_mv_raise_on_error_false_keeps_old_behaviour(bench):
    fake, motor, seen, hooks = bench
    fake.blocked[0] = (30, 'L')
    res = mc.mv(motor, 50, show_positions=False, raise_on_error=False)
    assert 'reached 30' in res[0][1]['error']


def test_busy_motor_raises_motor_busy_error(bench):
    fake, motor, seen, hooks = bench
    assert ms.motors['m1'].motion_lock.acquire()
    try:
        with pytest.raises(MotorBusyError):
            mc.mv(motor, 50, show_positions=False)
    finally:
        ms.motors['m1'].motion_lock.release()


def test_ctrl_c_during_mv_sends_stop(bench):
    fake, motor, seen, hooks = bench

    def interrupt(method, path, body):
        if path.startswith('/motors/move_abs'):
            raise KeyboardInterrupt
    hooks['before'] = interrupt
    with pytest.raises(KeyboardInterrupt):
        mc.mv(motor, 50, show_positions=False)
    assert ('POST', '/motors/stop/m1') in seen
    assert 'STOP1' in fake.commands


def test_ascan_stops_at_first_error_without_returning(bench, capsys):
    fake, motor, seen, hooks = bench
    fake.positions[0] = 5
    # 3rd point fails
    hooks['before'] = lambda method, path, body: fake.blocked.update({0: (25, 'L')}) if body == {'position': 30} else None
    with pytest.raises(MotionError):
        bs.ascan(motor, 10, 50, 5)
    assert hooks['moves'] == [10, 20, 30]
    out = capsys.readouterr().out
    assert 'point 3/5' in out and 'NOT returned' in out


def test_ascan_returns_to_start_on_success(bench):
    fake, motor, seen, hooks = bench
    fake.positions[0] = 5
    bs.ascan(motor, 10, 30, 3)
    assert hooks['moves'] == [10, 20, 30, 5]


def test_stop_all_client(bench):
    fake, motor, seen, hooks = bench
    assert mc.stop_all() == {'status': 'stopped', 'motors': ['m1']}
