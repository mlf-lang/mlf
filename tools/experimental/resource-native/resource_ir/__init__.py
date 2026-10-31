"""Independent explicit resource-IR checker and executable semantics prototype."""
from .checker import CheckError, CheckedProgram, check, loads
from .runtime import RuntimeFault, run

__all__ = ["CheckError", "CheckedProgram", "RuntimeFault", "check", "loads", "run"]
