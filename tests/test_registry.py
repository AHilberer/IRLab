"""Task 9: the servers are the single source of truth for motors and actuators."""
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import clients.festo_client as fc
import clients.motion_client as mc
import common.http_client as hc
import servers.festo_server as fs
import servers.motion_server as ms
import servers.spectro_server as ss
from tests.fake_serial import FakePS90Serial
from tests.test_server_startup import motion, FESTO_YAML   # noqa: F401  (fixture)


def _route_requests_to(monkeypatch, client):
    def fake_request(method, url, timeout=None, **kwargs):
        parts = urlsplit(url)
        resp = client.request(method, parts.path + (f'?{parts.query}' if parts.query else ''), **kwargs)
        resp.ok = resp.is_success
        return resp
    monkeypatch.setattr(hc.requests, 'request', fake_request)


def test_removed_registration_endpoints(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        for path in ('/ps90/register/x/1', '/ps90/list', '/ps90/load_config', '/motors/register?name=x&axis=1'):
            assert client.get(path).status_code == 404, path


def test_load_motors_from_server(motion, monkeypatch):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        _route_requests_to(monkeypatch, client)
        motors = mc.load_motors_from_server()
    assert sorted(motors) == ['sx', 'sy']
    sx = motors['sx']
    assert isinstance(sx, mc.Motor)
    assert (sx.controller_channel, sx.controller_name, sx.max_move_duration, sx.unit) == (2, 'main_ps90', 300, 'steps')


def test_close_controller_then_reload_recreates_motors(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        old_ctrl = ms.controllers['main_ps90']
        assert client.post('/ps90/close?name=main_ps90').json()['status'] == 'closed'
        assert client.get('/motors/list').json()['motors'] == []
        r = client.post('/admin/reload_config')
        assert sorted(r.json()['created']) == ['sx', 'sy']
        assert ms.motors['sx'].control_unit is ms.controllers['main_ps90'] is not old_ctrl


def test_load_actuators_from_server(monkeypatch, tmp_path):
    for name, value in [('controllers', {}), ('actuators', {}), ('controller_errors', {}),
                        ('actuator_errors', {}), ('default_controller_name', None)]:
        monkeypatch.setattr(fs, name, value)
    cfg = tmp_path / 'festo.yaml'
    cfg.write_text(FESTO_YAML)
    monkeypatch.setenv('IRLAB_FESTO_CONFIG', str(cfg))
    monkeypatch.setattr(fs, 'nidaqmx', object())
    with TestClient(fs.app) as client:
        assert client.get('/festo/actuators/register?name=x&module=M&lines=l').status_code == 404
        assert client.get('/festo/load_config').status_code == 404
        _route_requests_to(monkeypatch, client)
        actuators = fc.load_actuators_from_server()
    a = actuators['festo_1']
    assert (a.controller_name, a.module, a.lines) == ('main_festo', 'Mod1', 'line0:1')


def test_actions_refuse_get(motion):
    """Task 11: a GET (browser prefetch, link crawler...) never changes the bench state."""
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        client.post('/motors/init/sx')
        for path in ('/motors/move_abs/sx', '/motors/move_rel/sx', '/motors/init/sx', '/motors/free/sx',
                     '/motors/control/sx', '/ps90/connect', '/ps90/close'):
            assert client.get(path).status_code == 405, path
        # the old URL form does not match any route either
        assert client.get('/motors/move_abs/sx/100').status_code == 404
        assert not any(c.startswith('PSET') for c in fake.commands)
        # body validation
        assert client.post('/motors/move_abs/sx', json={'position': 'abc'}).status_code == 422
        assert client.post('/motors/move_abs/sx', json={'position': 42}).json()['position'] == 42


def test_festo_and_spectro_actions_refuse_get():
    for app, paths in ((fs.app, ('/festo/connect', '/festo/close', '/festo/actuators/on/a',
                                 '/festo/actuators/off/a', '/festo/actuators/toggle/a')),
                       (ss.app, ('/spectro/connect', '/spectro/close', '/spectro/load_config', '/acquire'))):
        client = TestClient(app)
        for path in paths:
            assert client.get(path).status_code == 405, path
