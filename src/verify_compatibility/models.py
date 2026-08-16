"""Shared report and finding model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    """Finding severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ConformanceStatus(str, Enum):
    """Static format-conformance status."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not-applicable"


class CompatibilityGrade(str, Enum):
    """Static portability grade."""

    PORTABLE = "portable"
    PORTABLE_WITH_ADAPTERS = "portable-with-adapters"
    DEGRADED = "degraded"
    INCOMPATIBLE = "incompatible"
    UNVERIFIED = "unverified"


class RuntimeStatus(str, Enum):
    """Runtime-evidence status."""

    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    UNVERIFIED = "unverified"


class TargetStatus(str, Enum):
    """Static status for one target surface."""

    SUPPORTED = "supported"
    DEGRADED = "degraded"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class Finding:
    """One stable, actionable audit result."""

    code: str
    severity: Severity
    message: str
    path: str | None = None
    targets: tuple[str, ...] = ()
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "targets": list(self.targets),
        }
        if self.path is not None:
            result["path"] = self.path
        if self.remediation is not None:
            result["remediation"] = self.remediation
        return result


@dataclass
class TargetAssessment:
    """Static assessment for one product surface."""

    target_id: str
    label: str
    reviewed_at: str
    status: TargetStatus
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "id": self.target_id,
            "label": self.label,
            "reviewed_at": self.reviewed_at,
            "status": self.status.value,
            "reasons": list(self.reasons),
        }


@dataclass
class AuditReport:
    """Complete deterministic audit result."""

    artifact_kind: str
    artifact_path: Path
    conformance: ConformanceStatus
    static_portability: CompatibilityGrade
    runtime_verification: RuntimeStatus = RuntimeStatus.UNVERIFIED
    targets: list[TargetAssessment] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    evidence_boundary: str = "static analysis only"

    @property
    def has_errors(self) -> bool:
        """Whether the report contains a blocking static error."""

        return any(finding.severity is Severity.ERROR for finding in self.findings)

    @property
    def exit_code(self) -> int:
        """Default CLI exit code.

        Warnings and missing runtime evidence do not fail the command. Static
        conformance failures and documented incompatibilities do.
        """

        if self.has_errors or self.static_portability is CompatibilityGrade.INCOMPATIBLE:
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "artifact": {
                "kind": self.artifact_kind,
                "path": str(self.artifact_path),
            },
            "conformance": self.conformance.value,
            "static_portability": self.static_portability.value,
            "runtime_verification": self.runtime_verification.value,
            "evidence_boundary": self.evidence_boundary,
            "targets": [target.to_dict() for target in self.targets],
            "findings": [finding.to_dict() for finding in self.findings],
        }
