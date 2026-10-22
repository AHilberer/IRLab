"""Task 8: config loaded at server startup (lifespan), degraded mode, /status, reload."""
import pytest
from fastapi.testclient import TestClient

import servers.festo_server as fs
import servers.motion_server as ms
import servers.spectro_server as ss
from tests.fake_serial import FakePS90Serial

MOTORS_YAML = """
initialize_on_startup: {init}
controllers:
  - name: main_ps90
    type: ps90
    port: FAKE_COM
motors:
  - name: sx
    controller: main_ps90
    controller_channel: 2
    max_move_duration: 300
  - name: sy
    controller: main_ps90
    controller_channel: 3
"""


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


def test_config_loaded_at_startup_and_moves_need_init(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        motors = {m['name']: m for m in client.get('/motors/list').json()['motors']}
        assert sorted(motors) == ['sx', 'sy']
        assert motors['sx']['state'] == 'off' and motors['sx']['max_move_duration'] == 300
        assert not any(c.startswith('INIT') for c in fake.commands)     # nothing moved

        r = client.post('/motors/move_abs/sx', json={'position': 100})
        assert r.status_code == 500 and 'not initialized' in r.json()['detail']

        assert client.post('/motors/init/sx').status_code == 200
        assert client.post('/motors/move_abs/sx', json={'position': 100}).json()['position'] == 100

        st = client.get('/status').json()
        assert st['server'] == 'motion_server' and st['status'] == 'ok'
        assert st['controllers'] == [{'name': 'main_ps90', 'port': 'FAKE_COM', 'state': 'connected'}]
        assert st['motors']['not_initialized'] == ['sy']


def test_initialize_on_startup(motion):
    fake, state, configure = motion
    configure(init=True)
    with TestClient(ms.app) as client:
        states = {m['name']: m['state'] for m in client.get('/motors/list').json()['motors']}
        assert states == {'sx': 'on', 'sy': 'on'}


def test_degraded_start_then_reload(motion):
    fake, state, configure = motion
    configure()
    state['plugged'] = False
    with TestClient(ms.app) as client:
        st = client.get('/status').json()
        assert st['status'] == 'degraded'
        assert st['controllers'][0]['state'] == 'error'
        assert 'could not open port' in st['controllers'][0]['error']
        assert client.get('/motors/list').json()['motors'] == []

        assert client.get('/admin/reload_config').status_code == 405
        state['plugged'] = True
        r = client.post('/admin/reload_config')
        assert r.status_code == 200 and sorted(r.json()['created']) == ['sx', 'sy']
        assert r.json()['status'] == 'ok'
        assert len(client.get('/motors/list').json()['motors']) == 2


def test_missing_config_file(motion, monkeypatch, tmp_path):
    monkeypatch.setenv('IRLAB_MOTORS_CONFIG', str(tmp_path / 'nope.yaml'))
    with TestClient(ms.app) as client:
        st = client.get('/status').json()
        assert st['status'] == 'degraded' and 'nope.yaml' in st['config_error']


def test_shutdown_stops_moving_axes(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        client.post('/motors/init/sx')
        ms.motors['sx'].state = ms.DeviceState.MOVING     # as during a move
    assert 'STOP2' in fake.commands


FESTO_YAML = """
controllers:
  - name: main_festo
    type: nidaqmx
    chassis: cDAQ1
actuators:
  - name: festo_1
    controller: main_festo
    module: Mod1
    lines: "line0:1"
"""


def test_festo_degraded_then_reload(monkeypatch, tmp_path):
    for name, value in [('controllers', {}), ('actuators', {}), ('controller_errors', {}),
                        ('actuator_errors', {}), ('default_controller_name', None),
                        ('config_error', None), ('config_path', None)]:
        monkeypatch.setattr(fs, name, value)
    cfg = tmp_path / 'festo.yaml'
    cfg.write_text(FESTO_YAML)
    monkeypatch.setenv('IRLAB_FESTO_CONFIG', str(cfg))
    monkeypatch.setattr(fs, 'nidaqmx', None)            # driver missing
    with TestClient(fs.app) as client:
        st = client.get('/status').json()
        assert st['server'] == 'festo_server' and st['status'] == 'degraded'
        assert 'nidaqmx' in st['controllers'][0]['error']
        assert 'festo_1' in st['actuators']['errors']

        monkeypatch.setattr(fs, 'nidaqmx', object())    # driver available
        r = client.post('/admin/reload_config')
        assert r.json()['actuators_created'] == ['festo_1'] and r.json()['status'] == 'ok'
        assert client.get('/festo/actuators/list').json()['actuators'][0]['name'] == 'festo_1'


def test_spectro_status_is_json():
    st = TestClient(ss.app).get('/status').json()
    assert st['server'] == 'spectro_server' and 'version' in st
