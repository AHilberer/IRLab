"""Task 1: serial port lock and per-motor motion lock."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

import servers.motion_server as ms
from tests.fake_serial import FakePS90Serial


@pytest.fixture
def setup(monkeypatch):
    fake = FakePS90Serial(move_polls=20)
    monkeypatch.setattr(ms.serial, 'Serial', lambda *a, **kw: fake)
    ctrl = ms.PS90(port='FAKE')
    monkeypatch.setattr(ms, 'controllers', {'main': ctrl})
    motors = {
        'm1': ms.PS90_motor('m1', ctrl, 1),
        'm2': ms.PS90_motor('m2', ctrl, 2),
    }
    for m in motors.values():
        m.state = ms.DeviceState.ON   # as after init()
    monkeypatch.setattr(ms, 'motors', motors)
    fake.positions[0] = 111
    fake.positions[1] = 222
    return fake, ctrl, motors


def test_concurrent_reads_do_not_interleave(setup):
    fake, ctrl, motors = setup
    errors = []

    def worker(name, expected):
        try:
            for _ in range(10):
                assert motors[name].read_current_position() == expected
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n, v))
               for n, v in [('m1', 111), ('m2', 222)] * 4]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert fake.collisions == 0


def test_reads_allowed_during_move_and_second_move_is_busy(setup):
    fake, ctrl, motors = setup
    client = TestClient(ms.app)
    result = {}
    t = threading.Thread(target=lambda: result.update(r=client.get('/motors/move_abs/m1/500')))
    t.start()
    # wait until the axis is actually moving
    while fake.status[0] != 'T':
        pass

    # position reads go through during the move (serial lock not held between polls)
    r = client.get('/motors/read/m2')
    assert r.status_code == 200 and r.json()['position'] == 222

    # a second move (absolute, relative) or an init on the same motor is refused
    assert client.get('/motors/move_abs/m1/0').status_code == 409
    r = client.get('/motors/move_rel/m1/10')
    assert r.status_code == 409 and 'busy' in r.json()['detail']
    assert client.get('/motors/control/m1').status_code == 409

    t.join()
    assert result['r'].status_code == 200
    assert fake.positions[0] == 500
    assert fake.collisions == 0
    assert 'PSET1=0' not in fake.commands

    # the lock is released after the move
    assert client.get('/motors/move_rel/m1/10').status_code == 200
    assert fake.positions[0] == 510


def test_pset_pgo_sequence_is_atomic(setup):
    fake, ctrl, motors = setup
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            motors['m2'].read_current_position()
            time.sleep(0.01)   # like real HTTP clients, leave gaps between requests

    t = threading.Thread(target=reader)
    t.start()
    try:
        for target in (10, 20, 30):
            motors['m1'].move_absolute(target)
    finally:
        stop.set()
        t.join()
    for i, cmd in enumerate(fake.commands):
        if cmd.startswith('PSET1='):
            assert fake.commands[i + 1] == 'PGO1'
    assert fake.collisions == 0
