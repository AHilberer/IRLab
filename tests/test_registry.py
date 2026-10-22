"""Task 9: the servers are the single source of truth for motors and actuators."""
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import clients.festo_client as fc
import clients.motion_client as mc
import common.http_client as hc
import servers.festo_server as fs
import servers.motion_server as ms
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
    assert (sx.controler_channel, sx.controller_name, sx.max_move_duration, sx.unit) == (2, 'main_ps90', 300, 'steps')


def test_close_controller_then_reload_recreates_motors(motion):
    fake, state, configure = motion
    configure()
    with TestClient(ms.app) as client:
        old_ctrl = ms.controllers['main_ps90']
        assert client.get('/ps90/close?name=main_ps90').json()['status'] == 'closed'
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
