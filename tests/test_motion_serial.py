"""Task 2: robust serial reads (queries vs commands, timeouts, response validation)."""
import time

import pytest

import servers.motion_server as ms
from tests.fake_serial import FakePS90Serial


@pytest.fixture
def fake_ctrl(monkeypatch):
    fake = FakePS90Serial()
    monkeypatch.setattr(ms.serial, 'Serial', lambda *a, **kw: fake)
    ctrl = ms.PS90(port='FAKE', command_delay=0)
    return fake, ctrl


def test_query_returns_response_and_command_returns_none(fake_ctrl):
    fake, ctrl = fake_ctrl
    fake.positions[2] = -42
    assert ctrl.send('?CNT3') == '-42'
    assert ctrl.send('PSET3=10') is None


def test_query_without_response_raises_timeout(fake_ctrl):
    fake, ctrl = fake_ctrl
    fake.disconnected = True
    m = ms.PS90_motor('m3', ctrl, 3)
    with pytest.raises(TimeoutError, match=r'\?CNT3'):
        m.read_current_position()


def test_truncated_response_raises_timeout(fake_ctrl):
    fake, ctrl = fake_ctrl
    # response without terminator: read_until returns only what it got
    fake.read_until = lambda expected=b'\r': b'12'
    with pytest.raises(TimeoutError, match='12'):
        ctrl.send('?CNT1')


def test_non_integer_position_raises_value_error(fake_ctrl):
    fake, ctrl = fake_ctrl
    fake.overrides['?CNT1'] = 'ERR'
    m = ms.PS90_motor('m1', ctrl, 1)
    with pytest.raises(ValueError, match="m1.*'ERR'"):
        m.read_current_position()


@pytest.mark.parametrize('status', ['', 'RR'])
def test_bad_status_raises(fake_ctrl, status):
    fake, ctrl = fake_ctrl
    fake.overrides['?ASTAT'] = status
    m = ms.PS90_motor('m5', ctrl, 5)
    with pytest.raises((RuntimeError, TimeoutError)):
        m.initialize_axis()
    assert m.state == ms.DeviceState.FAULT


def test_command_delay_applies_only_to_commands(monkeypatch):
    fake = FakePS90Serial()
    monkeypatch.setattr(ms.serial, 'Serial', lambda *a, **kw: fake)
    ctrl = ms.PS90(port='FAKE', command_delay=0.2)
    t0 = time.monotonic()
    ctrl.send('?CNT1')
    assert time.monotonic() - t0 < 0.1
    t0 = time.monotonic()
    ctrl.send('ABSOL1')
    assert time.monotonic() - t0 >= 0.2


def test_late_ok_acknowledgement_is_skipped(monkeypatch):
    """Manual: with TERM=2 each command without response is acknowledged by "OK"."""
    fake = FakePS90Serial(late_ack=True)
    monkeypatch.setattr(ms.serial, 'Serial', lambda *a, **kw: fake)
    ctrl = ms.PS90(port='FAKE', command_delay=0)
    fake.positions[0] = 42
    ctrl.send('ABSOL1')
    assert ctrl.send('?CNT1') == '42'


def test_port_reopened_after_cable_unplugged(monkeypatch):
    """USB-serial cable unplugged then plugged back: clear error meanwhile, then the
    port is reopened by the next command, without restarting the server."""
    old, new = FakePS90Serial(), FakePS90Serial()
    new.positions[2] = 7
    ports = iter([old])
    plugged = {'yes': True}

    def open_serial(*a, **kw):
        if not plugged['yes']:
            raise OSError('could not open port FAKE')
        return next(ports)
    monkeypatch.setattr(ms.serial, 'Serial', open_serial)
    monkeypatch.setattr(ms.time, 'sleep', lambda s: None)
    ctrl = ms.PS90(port='FAKE', command_delay=0)

    old.broken, plugged['yes'] = True, False          # cable unplugged
    with pytest.raises(RuntimeError, match='lost'):
        ctrl.send('?CNT3')

    plugged['yes'], ports = True, iter([new])        # plugged back
    assert ctrl.send('?CNT3') == '7'
