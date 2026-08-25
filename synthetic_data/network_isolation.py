"""Linux network-namespace fence for loopback-only active SITL execution."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - execution is intentionally Linux-only
    fcntl = None  # type: ignore[assignment]

ISOLATION_SCHEMA = "linux_user_network_namespace_loopback_only/v1"
CHILD_ENV = "LOGDIAGNOSIS_NETNS_CHILD"
PARENT_NAMESPACE_ENV = "LOGDIAGNOSIS_PARENT_NETNS"
UNSHARE_SHA256_ENV = "LOGDIAGNOSIS_UNSHARE_SHA256"
SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _namespace_link(pid: int | str = "self") -> str:
    return os.readlink(f"/proc/{pid}/ns/net")


def _unshare_binary() -> str:
    binary = shutil.which("unshare")
    if not binary:
        raise RuntimeError("loopback isolation requires the Linux unshare utility")
    return str(Path(binary).resolve())


def _set_loopback_up() -> None:
    if fcntl is None:
        raise RuntimeError("loopback setup requires Linux ioctl support")
    request = struct.pack("16sH14x", b"lo", 0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
        response = fcntl.ioctl(handle.fileno(), SIOCGIFFLAGS, request)
        _, flags = struct.unpack("16sH14x", response)
        fcntl.ioctl(
            handle.fileno(),
            SIOCSIFFLAGS,
            struct.pack("16sH14x", b"lo", flags | IFF_UP),
        )


def _loopback_is_up() -> bool:
    if fcntl is None:
        return False
    request = struct.pack("16sH14x", b"lo", 0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
        response = fcntl.ioctl(handle.fileno(), SIOCGIFFLAGS, request)
    _, flags = struct.unpack("16sH14x", response)
    return bool(flags & IFF_UP)


def _interface_names() -> list[str]:
    return sorted(path.name for path in Path("/sys/class/net").iterdir())


def maybe_reexec_isolated(argv: Sequence[str]) -> int | None:
    """Re-exec active SITL commands inside a fresh user/network namespace."""

    if not argv or argv[0] not in {"execute", "pair"}:
        return None
    if platform.system() != "Linux":
        raise RuntimeError(
            "active SITL execution requires Linux/WSL network namespaces"
        )
    if os.environ.get(CHILD_ENV) == "1":
        _set_loopback_up()
        require_isolated_network_namespace()
        return None
    unshare = _unshare_binary()
    parent_namespace = _namespace_link()
    environment = os.environ.copy()
    environment.update(
        {
            CHILD_ENV: "1",
            PARENT_NAMESPACE_ENV: parent_namespace,
            UNSHARE_SHA256_ENV: _sha256_file(unshare),
        }
    )
    command = [
        unshare,
        "--user",
        "--map-root-user",
        "--net",
        "--",
        sys.executable,
        "-m",
        "synthetic_data",
        *argv,
    ]
    result = subprocess.run(
        command,
        stdin=None,
        stdout=None,
        stderr=None,
        shell=False,
        check=False,
        env=environment,
    )
    return result.returncode


def require_isolated_network_namespace() -> dict[str, object]:
    """Return live isolation evidence or fail before launching ArduPilot."""

    if platform.system() != "Linux" or os.environ.get(CHILD_ENV) != "1":
        raise RuntimeError("owned SITL lacks a Linux network-namespace fence")
    parent_namespace = os.environ.get(PARENT_NAMESPACE_ENV, "")
    current_namespace = _namespace_link()
    parent_namespace_observation = "verified"
    try:
        actual_parent_namespace = _namespace_link(os.getppid())
    except PermissionError:
        # A root-mapped user namespace may be unable to inspect the outer
        # container's /proc namespace entry. The parent value was captured
        # immediately before unshare; retain that binding and record the
        # kernel visibility limitation rather than treating it as a SITL
        # network leak.
        actual_parent_namespace = parent_namespace
        parent_namespace_observation = "permission_limited"
    if (
        not parent_namespace
        or current_namespace == parent_namespace
        or (
            parent_namespace_observation == "verified"
            and actual_parent_namespace != parent_namespace
        )
    ):
        raise RuntimeError(
            "owned SITL network namespace is not isolated from its parent"
        )
    unshare = _unshare_binary()
    expected_unshare_hash = os.environ.get(UNSHARE_SHA256_ENV, "")
    if _sha256_file(unshare) != expected_unshare_hash:
        raise RuntimeError(
            "network-namespace launcher hash differs from its parent proof"
        )
    interfaces = _interface_names()
    loopback_up = _loopback_is_up()
    if interfaces != ["lo"] or not loopback_up:
        raise RuntimeError(
            "isolated network namespace is not loopback-only and active: "
            f"interfaces={interfaces!r}, loopback_up={loopback_up!r}"
        )
    return {
        "schema": ISOLATION_SCHEMA,
        "parent_pid": os.getppid(),
        "parent_namespace": parent_namespace,
        "parent_namespace_observation": parent_namespace_observation,
        "current_namespace": current_namespace,
        "loopback_interface_up": loopback_up,
        "external_interfaces_present": False,
        "interfaces": interfaces,
        "unshare_binary": unshare,
        "unshare_binary_sha256": expected_unshare_hash,
    }
