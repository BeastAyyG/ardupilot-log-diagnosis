"""Cluster runtime for the verified synthetic-data laboratory."""

from __future__ import annotations

from .coordinator import ClusterCoordinator, SSHTransport
from .scheduler import (
    BatchEntry,
    BatchReport,
    SlotAllocation,
    TerminalRunError,
    assign_nodes,
    build_batch_plan,
    execute_batch,
    fence_stale,
    reconcile,
    recover_pending,
    write_assignment_ledger,
    write_batch_receipt,
)

__all__ = [
    "BatchEntry",
    "BatchReport",
    "SlotAllocation",
    "ClusterCoordinator",
    "SSHTransport",
    "TerminalRunError",
    "assign_nodes",
    "build_batch_plan",
    "execute_batch",
    "fence_stale",
    "reconcile",
    "recover_pending",
    "write_assignment_ledger",
    "write_batch_receipt",
]
