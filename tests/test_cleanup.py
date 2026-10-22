"""Task 15: small bugs and cleanup."""
import warnings

import pytest
from fastapi.testclient import TestClient

import clients.motion_client as mc
import servers.festo_server as fs
import servers.motion_server as ms
from tests.test_registry import _route_requests_to
from tests.test_server_startup import motion, MOTORS_YAML   # noqa: F401  (fixture)


# ---------- festo_server ----------

def test_festo_close_removes_only_the_actuators_of_that_controller(monkeypatch):
    monkeypatch.setattr(fs, 'nidaqmx', object())
    a, b = fs.FestoNiDaqController('cDAQ1'), fs.FestoNiDaqController('cDAQ2')
    monkeypatch.setattr(fs, 'controllers', {'ctrl_a': a, 'ctrl_b': b})
    monkeypatch.setattr(fs, 'default_controller_name', 'ctrl_a')
    monkeypatch.setattr(fs, 'actuators', {
        'a1': fs.FestoActuator('a1', a, 'Mod1', 'line0:1'),
        'b1': fs.FestoActuator('b1', b, 'Mod1', 'line0:1'),
    })
    client = TestClient(fs.app)
    assert client.post('/festo/close?name=ctrl_a').json()['status'] == 'closed'
    assert list(fs.actuators) == ['b1']
    assert fs.default_controller_name == 'ctrl_b'


def test_festo_connect_default_name_matches_the_yaml(monkeypatch):
    monkeypatch.setattr(fs, 'nidaqmx', object())
    monkeypatch.setattr(fs, 'controllers', {})
    monkeypatch.setattr(fs, 'default_controller_name', None)
    assert TestClient(fs.app).post('/festo/connect').json()['name'] == 'main_festo'


# ---------- motion_server ----------

def test_parameters_endpoint_returns_a_dict(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        params = client.get('/motors/parameters/sx').json()
    assert params['motor'] == 'sx' and params['axis'] == 2
    assert params['position_counter'] == '0' and params['status_code'] == 'R'


def test_failed_init_is_reported(motion):
    fake, state, configure = motion
    configure()
    fake.status[1] = 'O'                 # axis not ready: INIT will be sent
    with TestClient(ms.app) as client:
        original_write = fake.write

        def write(data):
            if data.startswith(b'INIT'):
                raise OSError('write failed')
            return original_write(data)
        fake.write = write
        r = client.post('/motors/init/sx')
    assert r.status_code == 500 and 'write failed' in r.json()['detail']
    assert ms.motors['sx'].state == ms.DeviceState.FAULT


def test_velocity_error_is_logged_and_reported(motion, tmp_path):
    fake, state, configure = motion
    configure()
    cfg = tmp_path / 'motors.yaml'
    cfg.write_text(cfg.read_text().replace('    controller_channel: 2\n', '    controller_channel: 2\n    velocity: 1000\n'))
    original_write = fake.write

    def write(data):
        if data.startswith(b'PVEL2'):
            raise OSError('write failed')
        return original_write(data)
    fake.write = write
    with TestClient(ms.app) as client:
        st = client.get('/status').json()
    assert 'sx' in ms.motors                                   # still registered
    assert 'PVEL2=1000' in st['motors']['errors']['sx'] and 'write failed' in st['motors']['errors']['sx']


def test_no_default_serial_port(motion, monkeypatch, tmp_path):
    monkeypatch.delenv('PS90_PORT', raising=False)
    cfg = tmp_path / 'motors.yaml'
    cfg.write_text(MOTORS_YAML.format(init='false').replace('    port: FAKE_COM\n', ''))
    monkeypatch.setenv('IRLAB_MOTORS_CONFIG', str(cfg))
    with TestClient(ms.app) as client:
        st = client.get('/status').json()
        assert 'No serial port configured' in st['controllers'][0]['error']
        assert client.post('/ps90/connect').status_code == 422     # port is required


def test_port_already_in_use_message(monkeypatch):
    def busy(*a, **kw):
        raise ms.serial.SerialException("could not open port 'COM25': PermissionError(13, 'Access is denied.', None, 5)")
    monkeypatch.setattr(ms.serial, 'Serial', busy)
    with pytest.raises(RuntimeError, match='COM25 is already in use.*another motion server'):
        ms.PS90('COM25')


# ---------- motion_client ----------

def test_deprecated_attribute_names_still_work():
    with pytest.warns(DeprecationWarning):
        m = mc.Motor('m', controler_type='PS90', controler_channel=3)
    assert m.controller_channel == 3 and m.controller_type == 'PS90'
    with pytest.warns(DeprecationWarning):
        assert m.controler_channel == 3
    with pytest.warns(DeprecationWarning):
        m.controler_channel = 4
    assert m.controller_channel == 4


def test_positions_are_always_in_the_motor_unit():
    steps_motor = mc.Motor('a', step_to_mm=1.0)
    mm_motor = mc.Motor('b', step_to_mm=0.00005, unit='mm')
    deg_motor = mc.Motor('c', step_to_mm=0.01, unit='deg')
    assert steps_motor.unit == 'steps' and mc.Motor('d', step_to_mm=0.5).unit == 'mm'
    assert steps_motor.to_steps(2) == steps_motor.to_steps(2.0) == 2
    assert mm_motor.to_steps(2) == mm_motor.to_steps(2.0) == 40000
    assert deg_motor.to_steps(90) == 9000 and deg_motor.from_steps(9000) == 90
    assert steps_motor.from_steps(7) == 7


def test_motor_position_in_user_unit(motion, monkeypatch):
    fake, state, configure = motion
    configure()
    fake.positions[1] = 40000
    with TestClient(ms.app) as client:
        _route_requests_to(monkeypatch, client)
        assert mc.Motor('sx', step_to_mm=0.00005, unit='mm').position() == pytest.approx(2.0)
        assert mc.Motor('sx').position() == 40000


def test_factored_actions(motion, monkeypatch):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        _route_requests_to(monkeypatch, client)
        sx = mc.Motor('sx')
        assert mc.init(sx) == [('sx', {'status': 'initialized', 'motor': 'sx'})]
        assert mc.free(sx) == [('sx', {'status': 'freed', 'motor': 'sx'})]
        assert [n for n, r in mc.control_all_motors()] == ['sx', 'sy']
        assert 'error' in mc.stop(mc.Motor('nope'))[0][1]
        with pytest.raises(ValueError):
            mc.free('sx')
