"""One module per diagnostic rule.

Milestone 3 of ``docs/UPGRADE_ROADMAP.md`` asks for the rule engine to be
broken into per-subsystem modules such that no rule change requires editing a
file longer than 200 lines. Every ``check_*`` function therefore lives in its
own module, and ``rule_engine.py`` stays a thin orchestrator.
"""

from .compass import check_compass
from .crash_unknown import check_events
from .ekf import check_ekf
from .gps import check_gps
from .mechanical_failure import check_mechanical_failure
from .motors import check_motors
from .pid_tuning import check_pid_tuning
from .power import check_power
from .rc_failsafe import check_rc_failsafe
from .setup_error import check_setup_error
from .system import check_system
from .thrust_loss import check_thrust_loss
from .vibration import check_vibration

__all__ = [
    "check_mechanical_failure",
    "check_vibration",
    "check_thrust_loss",
    "check_setup_error",
    "check_compass",
    "check_power",
    "check_gps",
    "check_motors",
    "check_pid_tuning",
    "check_ekf",
    "check_system",
    "check_rc_failsafe",
    "check_events",
]
