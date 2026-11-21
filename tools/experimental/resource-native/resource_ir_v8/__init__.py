"""Isolated IR8 declarations only; no executable IR or runtime entry point."""

from .declarations import (
    DeclarationError,
    DeclarationIndex,
    check_declarations,
    loads_declarations,
)

__all__ = (
    "DeclarationError",
    "DeclarationIndex",
    "check_declarations",
    "loads_declarations",
)
