"""Host preflight and topology recommendation tests (all monkeypatched)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from synthetic_data.cluster.topology import (
    _unshare_support,
    probe_host,
    recommend_topology,
)


def test_unshare_success_hashes_the_binary(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "unshare"
    fake.write_bytes(b"\x7fELF-fake")
    calls = []

    def run(*args, **kwargs):
        calls.append(args[0])
        return subprocess.CompletedProcess(args[0], 0, b"", b"")

    monkeypatch.setattr("synthetic_data.cluster.topology.subprocess.run", run)
    support = _unshare_support(str(fake))
    assert support["user_network_namespace_ok"] is True
    assert support["unshare_binary"] == str(fake)
    assert len(support["unshare_sha256"]) == 64
    assert calls == [[str(fake), "-Urn", "true"]]


def test_unshare_failure_reports_kernel_reason(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "unshare"
    fake.write_bytes(b"x")

    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, b"", b"Operation not permitted")

    monkeypatch.setattr("synthetic_data.cluster.topology.subprocess.run", run)
    support = _unshare_support(str(fake))
    assert support["user_network_namespace_ok"] is False
    assert "exited 1" in support["reason"]
    assert "Operation not permitted" in support["reason"]


def test_missing_unshare_is_an_explicit_reason() -> None:
    support = _unshare_support(None)
    assert support["user_network_namespace_ok"] is False
    assert "not found" in support["reason"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific branch")
def test_windows_probe_demands_linux_substrate() -> None:
    probe = probe_host(check_namespaces=True)
    assert probe["user_network_namespace_ok"] is False
    assert "WSL2" in probe["reason"] or "container" in probe["reason"]
    assert probe["system"] == "Windows"


def test_topology_profiles_and_validation() -> None:
    dgx_probe = {"cpu_count": 64, "user_network_namespace_ok": True}
    dgx = recommend_topology(dgx_probe, profile="dgx")
    assert dgx["recommended_max_concurrent"] == 32
    assert dgx["requires_container"] is True
    assert "@sha256:" in dgx["container_image"]

    laptop_probe = {"cpu_count": 8, "user_network_namespace_ok": False}
    laptop = recommend_topology(laptop_probe, profile="laptop")
    assert laptop["recommended_max_concurrent"] <= 4
    assert laptop["sequential_fallback_lanes"] == 1

    with pytest.raises(ValueError, match="unknown profile"):
        recommend_topology(laptop_probe, profile="supercomputer")


def test_capacity_floor_is_reported_not_assumed() -> None:
    probe = probe_host(min_cpu=9999, min_mem_gb=99999.0)
    assert probe["capacity_ok"] is False
    assert "requires" in probe["capacity_reason"]
