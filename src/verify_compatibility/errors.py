"""Domain-specific exceptions."""

from __future__ import annotations


class AuditInputError(ValueError):
    """The requested artifact cannot be audited as supplied."""
