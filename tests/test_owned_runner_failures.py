from __future__ import annotations

import signal
import subprocess
from pathlib import Path

import pytest

from synthetic_data import owned_runner
from synthetic_data.owned_runner import OwnedSITLProcess
from synthetic_data.runner import PymavlinkSITLSession


class _Process:
    def __init__(self, *, returncode=None):
        self.returncode = returncode
        self.pid = 8123

    def poll(self):
        return self.returncode


def _owner(tmp_path: Path, process: _Process) -> OwnedSITLProcess:
    owner = OwnedSITLProcess.__new__(OwnedSITLProcess)
    owner.run_dir = tmp_path
    owner.process = process
    owner.process_group_id = 8123
    owner.log_handle = None
    owner.shutdown_result = None
    owner.command = ["arducopter"]
    owner.source_attestation = {}
    owner.runtime_attestation = {}
    owner.parameter_file_sha256 = "a" * 64
    owner.started_at = "2026-08-23T00:00:00+00:00"
    return owner


def test_early_sitl_exit_blocks_log_finalization(tmp_path) -> None:
    log = tmp_path / "flight.BIN"
    log.write_bytes(b"partial-dataflash")
    owner = _owner(tmp_path, _Process(returncode=7))

    with pytest.raises(RuntimeError, match="did not stabilize while SITL was alive"):
        owner.finalize_log(1.0)

    assert owner.shutdown_result is None


def test_logger_that_keeps_changing_never_reaches_pre_shutdown_gate(
    tmp_path, monkeypatch
) -> None:
    log = tmp_path / "flight.BIN"
    log.write_bytes(b"0")
    owner = _owner(tmp_path, _Process())

    def logger_tick(_seconds: float) -> None:
        with log.open("ab") as handle:
            handle.write(b"1")

    monkeypatch.setattr(owned_runner.time, "sleep", logger_tick)

    with pytest.raises(RuntimeError, match="did not stabilize while SITL was alive"):
        owner.finalize_log(1.0)

    assert log.stat().st_size > 1


def test_posix_stop_records_sigkill_escalation_and_cannot_look_clean(
    tmp_path, monkeypatch
) -> None:
    class StubbornProcess(_Process):
        def __init__(self):
            super().__init__()
            self.wait_count = 0

        def wait(self, timeout):
            self.wait_count += 1
            if self.wait_count == 1:
                raise subprocess.TimeoutExpired("arducopter", timeout)
            self.returncode = -int(signal.SIGKILL)
            return self.returncode

    process = StubbornProcess()
    owner = _owner(tmp_path, process)
    signals: list[int] = []

    def fake_killpg(_group_id: int, requested_signal: int) -> None:
        signals.append(requested_signal)
        if requested_signal == 0:
            raise ProcessLookupError

    monkeypatch.setattr(owned_runner.os, "name", "posix")
    monkeypatch.setattr(owned_runner.os, "killpg", fake_killpg, raising=False)
    monkeypatch.setattr(owned_runner.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(owned_runner.time, "sleep", lambda _seconds: None)

    shutdown = owner._stop(1.0)

    assert signals[:2] == [signal.SIGTERM, signal.SIGKILL]
    assert shutdown["shutdown_method"] == "posix_process_group_sigkill"
    assert shutdown["shutdown_escalated"] is True
    assert shutdown["process_terminated"] is True
    assert shutdown["process_tree_terminated"] is True


def test_parameter_inventory_ignores_foreign_mavlink_source() -> None:
    class Message:
        def __init__(self, system: int, component: int, name: str, value: float):
            self._system = system
            self._component = component
            self.param_id = name
            self.param_value = value
            self.param_count = 1

        def get_srcSystem(self):
            return self._system

        def get_srcComponent(self):
            return self._component

    class Mav:
        def param_request_list_send(self, *_args):
            return None

    class Master:
        target_system = 1
        target_component = 1
        mav = Mav()

        def __init__(self):
            self.messages = [
                Message(42, 1, "FOREIGN", 99.0),
                Message(1, 1, "OWNED", 1.0),
            ]

        def recv_match(self, **_kwargs):
            return self.messages.pop(0)

    session = PymavlinkSITLSession.__new__(PymavlinkSITLSession)
    session.master = Master()
    session._source_system = 1
    session._source_component = 1

    assert session.fetch_parameters(1.0) == {"OWNED": 1.0}
