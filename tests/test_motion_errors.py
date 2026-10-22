"""Tasks 3 and 4: motion errors reported over HTTP, and stop endpoints (server side)."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

import servers.motion_server as ms
from tests.fake_serial import FakePS90Serial


@pytest.fixture
def setup(monkeypatch):
    fake = FakePS90Serial(move_polls=5)
    monkeypatch.setattr(ms.serial, 'Serial', lambda *a, **kw: fake)
    ctrl = ms.PS90(port='FAKE', command_delay=0)
    monkeypatch.setattr(ms, 'controllers', {'main': ctrl})
    motors = {
        'm1': ms.PS90_motor('m1', ctrl, 1),
        'm2': ms.PS90_motor('m2', ctrl, 2),
    }
    for m in motors.values():
        m.state = ms.DeviceState.ON   # as after init()
    monkeypatch.setattr(ms, 'motors', motors)
    return fake, motors, TestClient(ms.app)


def _wait_moving(fake, axis_index):
    t0 = time.monotonic()
    while fake.status[axis_index] != 'T':
        assert time.monotonic() - t0 < 5
        time.sleep(0.001)


def test_successful_move_returns_final_position(setup):
    fake, motors, client = setup
    r = client.get('/motors/move_abs/m1/1234')
    assert r.status_code == 200
    assert r.json()['position'] == 1234
    r = client.get('/motors/move_rel/m1/-34')
    assert r.status_code == 200 and r.json()['position'] == 1200


def test_wrong_final_position_is_an_http_error(setup):
    fake, motors, client = setup
    fake.blocked[0] = (700, 'L')     # stops early, e.g. on a limit switch
    r = client.get('/motors/move_abs/m1/1000')
    assert r.status_code == 500
    detail = r.json()['detail']
    for text in ('m1', 'wrong final position', 'target 1000', 'reached 700', "'L'"):
        assert text in detail
    assert motors['m1'].state == ms.DeviceState.FAULT


def test_position_tolerance(setup):
    fake, motors, client = setup
    motors['m1'].position_tolerance_steps = 2
    fake.blocked[0] = (998, 'R')
    assert client.get('/motors/move_abs/m1/1000').json()['position'] == 998
    fake.blocked[0] = (997, 'R')
    assert client.get('/motors/move_abs/m1/1000').status_code == 500


def test_max_move_duration_stops_the_axis(setup):
    fake, motors, client = setup
    fake.move_polls = 10**9
    motors['m1'].max_move_duration = 0.3
    t0 = time.monotonic()
    r = client.get('/motors/move_abs/m1/1000')
    assert time.monotonic() - t0 < 2
    assert r.status_code == 500
    assert 'not finished after 0.3 s' in r.json()['detail']
    assert 'STOP1' in fake.commands
    assert fake.status[0] == 'R'


def test_stop_interrupts_a_move(setup):
    fake, motors, client = setup
    fake.move_polls = 10**9
    result = {}
    t = threading.Thread(target=lambda: result.update(r=client.get('/motors/move_abs/m1/1000')))
    t.start()
    _wait_moving(fake, 0)
    t0 = time.monotonic()
    r = client.post('/motors/stop/m1')
    assert r.status_code == 200
    assert time.monotonic() - t0 < 0.5      # does not wait for the motion lock
    t.join(timeout=5)
    assert result['r'].status_code == 500
    assert 'stopped by user' in result['r'].json()['detail']
    assert motors['m1'].state == ms.DeviceState.ON
    # the motor accepts new moves afterwards
    fake.move_polls = 2
    assert client.get('/motors/move_abs/m1/10').status_code == 200


def test_stop_all_stops_every_motor(setup):
    fake, motors, client = setup
    fake.move_polls = 10**9
    threads = [threading.Thread(target=client.get, args=(f'/motors/move_abs/{n}/1000',))
               for n in ('m1', 'm2')]
    for t in threads:
        t.start()
    _wait_moving(fake, 0)
    _wait_moving(fake, 1)
    r = client.post('/motors/stop_all')
    assert r.status_code == 200 and sorted(r.json()['motors']) == ['m1', 'm2']
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert fake.status[:2] == ['R', 'R']


def test_stop_endpoints_reject_get(setup):
    fake, motors, client = setup
    assert client.get('/motors/stop/m1').status_code == 405
    assert client.get('/motors/stop_all').status_code == 405


def test_relative_move_uses_freshly_read_position(setup):
    """Task 5: the axis moved without the server knowing (by hand after free())."""
    fake, motors, client = setup
    assert client.get('/motors/move_abs/m1/100').json()['position'] == 100
    fake.positions[0] = 5000          # moved by hand
    r = client.get('/motors/move_rel/m1/10')
    assert r.status_code == 200 and r.json()['position'] == 5010
    assert 'PSET1=5010' in fake.commands
