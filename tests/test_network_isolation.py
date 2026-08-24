from __future__ import annotations

from types import SimpleNamespace

import pytest

from synthetic_data import network_isolation


def test_execute_reexecs_inside_fresh_user_network_namespace(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(network_isolation.platform, "system", lambda: "Linux")
    monkeypatch.delenv(network_isolation.CHILD_ENV, raising=False)
    monkeypatch.setattr(
        network_isolation, "_unshare_binary", lambda: "/usr/bin/unshare"
    )
    monkeypatch.setattr(
        network_isolation, "_namespace_link", lambda _pid="self": "net:[100]"
    )
    monkeypatch.setattr(network_isolation, "_sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(network_isolation, "_interface_names", lambda: ["lo"])
    monkeypatch.setattr(network_isolation, "_loopback_is_up", lambda: True)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(network_isolation.subprocess, "run", fake_run)

    result = network_isolation.maybe_reexec_isolated(
        ["execute", "--output-dir", "/experiment"]
    )

    assert result == 7
    assert captured["command"][:5] == [
        "/usr/bin/unshare",
        "--user",
        "--map-root-user",
        "--net",
        "--",
    ]
    assert captured["command"][-3:] == [
        "execute",
        "--output-dir",
        "/experiment",
    ]
    environment = captured["kwargs"]["env"]
    assert environment[network_isolation.CHILD_ENV] == "1"
    assert environment[network_isolation.PARENT_NAMESPACE_ENV] == "net:[100]"
    assert environment[network_isolation.UNSHARE_SHA256_ENV] == "a" * 64
    assert captured["kwargs"]["shell"] is False


def test_live_child_namespace_proof_is_bound_to_actual_parent(monkeypatch) -> None:
    monkeypatch.setattr(network_isolation.platform, "system", lambda: "Linux")
    monkeypatch.setenv(network_isolation.CHILD_ENV, "1")
    monkeypatch.setenv(network_isolation.PARENT_NAMESPACE_ENV, "net:[100]")
    monkeypatch.setenv(network_isolation.UNSHARE_SHA256_ENV, "a" * 64)
    monkeypatch.setattr(network_isolation.os, "getppid", lambda: 4321)
    monkeypatch.setattr(
        network_isolation,
        "_namespace_link",
        lambda pid="self": "net:[101]" if pid == "self" else "net:[100]",
    )
    monkeypatch.setattr(
        network_isolation, "_unshare_binary", lambda: "/usr/bin/unshare"
    )
    monkeypatch.setattr(network_isolation, "_sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(network_isolation, "_interface_names", lambda: ["lo"])
    monkeypatch.setattr(network_isolation, "_loopback_is_up", lambda: True)

    proof = network_isolation.require_isolated_network_namespace()

    assert proof["current_namespace"] == "net:[101]"
    assert proof["parent_namespace"] == "net:[100]"
    assert proof["external_interfaces_present"] is False
    assert proof["loopback_interface_up"] is True
    assert proof["interfaces"] == ["lo"]


def test_same_or_spoofed_parent_namespace_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(network_isolation.platform, "system", lambda: "Linux")
    monkeypatch.setenv(network_isolation.CHILD_ENV, "1")
    monkeypatch.setenv(network_isolation.PARENT_NAMESPACE_ENV, "net:[100]")
    monkeypatch.setattr(network_isolation.os, "getppid", lambda: 4321)
    monkeypatch.setattr(
        network_isolation, "_namespace_link", lambda _pid="self": "net:[100]"
    )

    with pytest.raises(RuntimeError, match="not isolated"):
        network_isolation.require_isolated_network_namespace()


@pytest.mark.parametrize(
    "interfaces,loopback_up", [(["eth0", "lo"], True), (["lo"], False)]
)
def test_child_rejects_external_interface_or_down_loopback(
    monkeypatch, interfaces, loopback_up
) -> None:
    monkeypatch.setattr(network_isolation.platform, "system", lambda: "Linux")
    monkeypatch.setenv(network_isolation.CHILD_ENV, "1")
    monkeypatch.setenv(network_isolation.PARENT_NAMESPACE_ENV, "net:[100]")
    monkeypatch.setenv(network_isolation.UNSHARE_SHA256_ENV, "a" * 64)
    monkeypatch.setattr(network_isolation.os, "getppid", lambda: 4321)
    monkeypatch.setattr(
        network_isolation,
        "_namespace_link",
        lambda pid="self": "net:[101]" if pid == "self" else "net:[100]",
    )
    monkeypatch.setattr(
        network_isolation, "_unshare_binary", lambda: "/usr/bin/unshare"
    )
    monkeypatch.setattr(network_isolation, "_sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(network_isolation, "_interface_names", lambda: interfaces)
    monkeypatch.setattr(network_isolation, "_loopback_is_up", lambda: loopback_up)

    with pytest.raises(RuntimeError, match="not loopback-only"):
        network_isolation.require_isolated_network_namespace()


def test_active_execution_refuses_non_linux_hosts(monkeypatch) -> None:
    monkeypatch.setattr(network_isolation.platform, "system", lambda: "Windows")

    with pytest.raises(RuntimeError, match="Linux/WSL"):
        network_isolation.maybe_reexec_isolated(["execute"])
