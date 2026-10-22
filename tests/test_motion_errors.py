"""Task 3: motion errors reported over HTTP (server side)."""
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
    monkeypatch.setattr(ms, 'motors', motors)
    return fake, motors, TestClient(ms.app)


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

