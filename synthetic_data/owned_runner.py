"""Owned sim_vehicle lifecycle and automatic DataFlash artifact discovery."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .execution_integrity import (
    attest_clean_source,
    command_sha256,
    direct_sitl_command,
    runtime_identity,
)
from .network_isolation import require_isolated_network_namespace

FRAME_MODELS = {"quad": "+", "hexa": "hexa", "octa": "octa"}


def _safe_under(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path escapes its owned root: {resolved}")
    return resolved


class OwnedSITLProcess:
    """Launch and stop one fixed-argument sim_vehicle process in a fresh directory."""

    def __init__(
        self,
        *,
        experiment_dir: str | Path,
        plan: Mapping[str, Any],
        ardupilot_root: str | Path,
        binary_path: str | Path,
        endpoint: str,
        instance: int,
    ):
        self.experiment_dir = Path(experiment_dir).resolve()
        self.plan = dict(plan)
        self.ardupilot_root = Path(ardupilot_root).resolve()
        self.binary_path = Path(binary_path).resolve()
        self.endpoint = str(endpoint)
        self.instance = int(instance)
        if self.instance != 0:
            raise ValueError(
                "release-grade direct SITL currently supports only sequential instance 0"
            )
        endpoint_parts = self.endpoint.split(":")
        if len(endpoint_parts) != 3 or endpoint_parts[0].lower() != "tcpin":
            raise ValueError("direct SITL execution requires tcpin:LOOPBACK:PORT")
        try:
            endpoint_ip = ipaddress.ip_address(endpoint_parts[1])
            self.mavlink_port = int(endpoint_parts[2])
        except ValueError as exc:
            raise ValueError("invalid direct SITL loopback endpoint") from exc
        expected_port = 14550 + 10 * self.instance
        if (
            endpoint_ip.version != 4
            or endpoint_ip.compressed != "127.0.0.1"
            or self.mavlink_port != expected_port
        ):
            raise ValueError(
                f"instance {self.instance} requires tcpin:127.0.0.1:{expected_port}"
            )
        self.run_dir = _safe_under(
            self.experiment_dir,
            self.experiment_dir / "owned_runs" / str(self.plan["run_id"]),
        )
        self.parameter_file = _safe_under(
            self.experiment_dir,
            self.experiment_dir / "params" / f"{self.plan['run_id']}.parm",
        )
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.started_at = ""
        self.command: list[str] = []
        self.process_group_id: int | None = None
        self.source_attestation: dict[str, Any] = {}
        self.runtime_attestation: dict[str, str] = {}
        self.network_attestation: dict[str, object] = {}
        self.parameter_file_sha256 = ""
        self.shutdown_result: dict[str, Any] | None = None

    def _validate_parameter_file(self) -> None:
        expected_lines = [
            f"{name}={float(value):.12g}"
            for name, value in self.plan["startup_parameters"].items()
        ]
        expected = "\n".join(expected_lines) + ("\n" if expected_lines else "")
        actual = self.parameter_file.read_text(encoding="utf-8")
        if actual != expected:
            raise RuntimeError(
                "planned parameter file bytes differ from the immutable startup mapping"
            )
        self.parameter_file_sha256 = hashlib.sha256(
            self.parameter_file.read_bytes()
        ).hexdigest()

    def _validate_source_and_model(self, model: str) -> None:
        binary_digest = hashlib.sha256(self.binary_path.read_bytes()).hexdigest()
        if binary_digest != self.plan.get("binary_sha256"):
            raise RuntimeError("SITL binary hash differs from the immutable run plan")
        self.source_attestation = attest_clean_source(
            self.ardupilot_root, str(self.plan["ardupilot_revision"])
        )
        model_output = subprocess.run(
            [str(self.binary_path), "--list-models"],
            cwd=self.experiment_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            timeout=30.0,
            check=True,
            text=True,
        ).stdout
        try:
            vehicle_info = json.loads(model_output)
            frame_info = vehicle_info["ArduCopter"]["frames"][self.plan["frame"]]
            listed_model = frame_info.get("model", self.plan["frame"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "pinned SITL --list-models output lacks the planned frame"
            ) from exc
        if listed_model != model:
            raise RuntimeError(
                f"pinned SITL frame maps to {listed_model!r}, expected {model!r}"
            )

    def start(self) -> None:
        if self.run_dir.exists():
            raise FileExistsError("owned SITL run directory already exists")
        for path, description in (
            (self.binary_path, "pinned SITL binary"),
            (self.parameter_file, "planned parameter file"),
        ):
            if not path.is_file():
                raise FileNotFoundError(f"{description} is missing: {path}")
        self._validate_parameter_file()
        model = FRAME_MODELS.get(str(self.plan.get("frame", "")))
        if model is None:
            raise ValueError("run plan has an unsupported direct SITL frame")
        self._validate_source_and_model(model)
        self.runtime_attestation = runtime_identity(enforce_supported_pymavlink=True)
        self.network_attestation = require_isolated_network_namespace()
        self.run_dir.mkdir(parents=True)
        self.command = direct_sitl_command(
            binary_path=self.binary_path,
            parameter_file=self.parameter_file,
            plan=self.plan,
            instance=self.instance,
            endpoint_ip="127.0.0.1",
            mavlink_port=self.mavlink_port,
        )
        output_path = self.run_dir / "sim_vehicle.output.log"
        self.log_handle = output_path.open("wb")
        creationflags = 0
        if os.name == "nt":
            creationflags = int(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        self.started_at = datetime.now(timezone.utc).isoformat()
        try:
            self.process = subprocess.Popen(
                self.command,
                cwd=self.run_dir,
                stdin=subprocess.DEVNULL,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
        except Exception as exc:
            if self.log_handle is not None:
                self.log_handle.close()
                self.log_handle = None
            (self.run_dir / "launch_failure.json").write_text(
                json.dumps(
                    {
                        "schema": "logdiagnosis.sitl-launch-failure/v1",
                        "run_id": self.plan["run_id"],
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            raise
        if os.name != "nt":
            self.process_group_id = os.getpgid(self.process.pid)

    def _stop(self, timeout: float) -> dict[str, Any]:
        if self.shutdown_result is not None:
            return dict(self.shutdown_result)
        if self.process is None:
            if self.log_handle is not None:
                self.log_handle.close()
                self.log_handle = None
            self.shutdown_result = {
                "process_exit_code": None,
                "process_terminated": True,
                "process_tree_terminated": False,
                "shutdown_method": "not_started",
                "alive_before_shutdown": False,
                "shutdown_escalated": False,
            }
            return dict(self.shutdown_result)
        deadline = time.monotonic() + min(max(timeout, 1.0), 30.0)
        method = ""
        tree_terminated = False
        alive_before_shutdown = self.process.poll() is None
        shutdown_escalated = False
        if os.name == "nt":
            if self.process.poll() is None:
                try:
                    result = subprocess.run(
                        [
                            "taskkill.exe",
                            "/PID",
                            str(self.process.pid),
                            "/T",
                            "/F",
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        shell=False,
                        timeout=max(1.0, deadline - time.monotonic()),
                        check=False,
                    )
                    method = "windows_taskkill_tree"
                    tree_terminated = result.returncode == 0
                except (OSError, subprocess.SubprocessError):
                    method = "windows_tree_termination_failed"
            else:
                method = "parent_exited_before_tree_fence"
        else:
            group_id = self.process_group_id
            if alive_before_shutdown and group_id is not None:
                try:
                    os.killpg(group_id, signal.SIGTERM)
                    method = "posix_process_group_sigterm"
                except ProcessLookupError:
                    method = "posix_process_group_already_gone"
                    tree_terminated = True
                except OSError:
                    method = "posix_process_group_sigterm_failed"
        try:
            self.process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            shutdown_escalated = True
            if os.name != "nt" and self.process_group_id is not None:
                os.killpg(self.process_group_id, signal.SIGKILL)
                method = "posix_process_group_sigkill"
            else:
                self.process.kill()
                method = method or "parent_kill_only"
            try:
                self.process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                pass
        if os.name != "nt" and self.process_group_id is not None:
            while time.monotonic() < deadline:
                try:
                    os.killpg(self.process_group_id, 0)
                except ProcessLookupError:
                    tree_terminated = True
                    break
                time.sleep(0.05)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        self.shutdown_result = {
            "process_exit_code": self.process.returncode,
            "process_terminated": self.process.poll() is not None,
            "process_tree_terminated": tree_terminated,
            "shutdown_method": method,
            "alive_before_shutdown": alive_before_shutdown,
            "shutdown_escalated": shutdown_escalated,
        }
        return dict(self.shutdown_result)

    def _stable(self, path: Path, *, require_alive: bool) -> tuple[bool, int]:
        sizes: list[int] = []
        for _ in range(4):
            if require_alive and (
                self.process is None or self.process.poll() is not None
            ):
                return False, sizes[-1] if sizes else 0
            sizes.append(path.stat().st_size)
            time.sleep(0.75)
        return len(set(sizes)) == 1 and sizes[0] > 0, sizes[-1]

    def finalize_log(self, timeout: float) -> tuple[Path, dict[str, Any]]:
        logs = sorted(
            path
            for path in self.run_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".bin"
        )
        if len(logs) != 1:
            raise RuntimeError(
                f"owned SITL run produced {len(logs)} BIN logs; exactly one is required"
            )
        # LOG_FILE_DSRMROT is serviced asynchronously. Keep SITL alive for more
        # than two logger ticks and require a stable file before fencing it.
        stable_before_shutdown, _ = self._stable(logs[0], require_alive=True)
        if not stable_before_shutdown:
            raise RuntimeError("DataFlash log did not stabilize while SITL was alive")
        shutdown = self._stop(timeout)
        if not (
            shutdown["alive_before_shutdown"]
            and not shutdown["shutdown_escalated"]
            and shutdown["process_tree_terminated"]
        ):
            raise RuntimeError("owned SITL process tree did not close cleanly")
        stable, size = self._stable(logs[0], require_alive=False)
        if not stable:
            raise RuntimeError("owned DataFlash log did not reach a stable closed size")
        attestation = {
            "owned_process": True,
            "pid": int(self.process.pid) if self.process is not None else None,
            **shutdown,
            "shutdown_reason": "controlled_after_disarm_and_logger_flush",
            "command": self.command,
            "command_sha256": command_sha256(self.command),
            "working_directory": str(self.run_dir),
            **self.source_attestation,
            "runtime": self.runtime_attestation,
            "network_isolation": self.network_attestation,
            "parameter_file_sha256": self.parameter_file_sha256,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "new_log_count": len(logs),
            "pre_shutdown_log_stable": stable_before_shutdown,
            "log_stable": stable,
            "source_log_path": str(logs[0]),
            "source_log_size": size,
        }
        return logs[0], attestation

    def abort(self, timeout: float) -> dict[str, Any]:
        shutdown = self._stop(timeout)
        return {
            "owned_process": True,
            **shutdown,
            "working_directory": str(self.run_dir),
        }
