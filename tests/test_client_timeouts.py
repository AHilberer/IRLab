"""Task 7: client-side HTTP timeouts adapted to move duration and exposure."""
import pytest

import clients.motion_client as mc
import clients.spectro_client as sc
import common.http_client as hc


class _Resp:
    ok = True
    status_code = 200

    def json(self):
        return {}


@pytest.fixture
def timeouts(monkeypatch):
    seen = []

    def fake_request(method, url, timeout=None, **kwargs):
        seen.append((url, timeout))
        return _Resp()
    monkeypatch.setattr(hc.requests, 'request', fake_request)
    return seen


def test_move_timeout_follows_motor_max_move_duration(timeouts):
    m = mc.Motor('m1', max_move_duration=300)
    mc.mv(m, 10, show_positions=False)
    mc.mvr(m, 10, show_positions=False)
    assert [t for u, t in timeouts if '/move_' in u] == [300 + mc.MOTION_TIMEOUT_MARGIN] * 2


def test_move_timeout_default_and_explicit(timeouts):
    m = mc.Motor('m1')
    mc.mv(m, 10, show_positions=False)
    mc.mv(m, 10, show_positions=False, timeout=5)
    mc.mv(m, 10, show_positions=False, timeout=None)
    assert [t for u, t in timeouts if '/move_' in u] == [mc.DEFAULT_MAX_MOVE_DURATION + mc.MOTION_TIMEOUT_MARGIN, 5, None]
    assert mc.DEFAULT_MAX_MOVE_DURATION + mc.MOTION_TIMEOUT_MARGIN > 120


def test_acquire_timeout_follows_exposure(timeouts, monkeypatch):
    monkeypatch.setattr(sc, 'is_server_disabled', lambda key: False)
    spec = sc.Spectrometer()
    spec.acquire(exposure=8)
    spec.acquire(exposure=8, timeout=3)
    sc.Spectrometer(timeout_margin=2).acquire(exposure=1)
    assert [t for u, t in timeouts] == [18.0, 3, 3.0]
