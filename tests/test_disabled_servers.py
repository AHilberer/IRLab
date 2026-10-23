"""Servers listed in `disabled_servers` of config/servers.yaml are not contacted."""
import pytest

import clients.spectro_client as sc
import common.servers as cs


def test_disabled_servers(tmp_path, monkeypatch):
    path = tmp_path / 'servers.yaml'
    path.write_text('spectro_server: "http://pc-spectro:8002"\ndisabled_servers:\n  - spectro_server\n')
    monkeypatch.setattr(cs, 'DEFAULT_SERVERS_PATH', str(path))
    assert cs.is_server_disabled('spectro_server')
    assert not cs.is_server_disabled('motion_server')
    with pytest.raises(RuntimeError, match='disabled'):
        sc.Spectrometer().acquire(0.1)

    path.write_text('spectro_server: "http://pc-spectro:8002"\n')
    assert not cs.is_server_disabled('spectro_server')
