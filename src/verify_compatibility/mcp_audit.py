"""Manifest-driven static compatibility analysis for MCP servers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .errors import AuditInputError
from .models import (
    AuditReport,
    CompatibilityGrade,
    ConformanceStatus,
    Finding,
    Severity,
    TargetAssessment,
    TargetStatus,
)
from .profiles import TargetProfile, select_profiles

_DEFAULT_MANIFEST = Path("compatibility/requirements.json")
_SUPPORTED_CAPABILITY_STATUSES = {"supported"}
_DEGRADED_CAPABILITY_STATUSES = {"deprecated", "partial"}
_UNCERTAIN_CAPABILITY_STATUSES = {"unknown"}
_UNAVAILABLE_CAPABILITY_STATUSES = {"unsupported", "not-applicable"}


def audit_mcp(
    path: Path,
    *,
    manifest_path: Path | None = None,
    target_ids: list[str] | None = None,
) -> AuditReport:
    """Audit declared MCP requirements against selected target profiles."""

    artifact_path = path.expanduser().resolve()
    if not artifact_path.exists():
        raise AuditInputError(f"Artifact path does not exist: {artifact_path}")
    profiles = select_profiles(target_ids)
    manifest = _resolve_manifest(artifact_path, manifest_path)
    if manifest is None:
        finding = Finding(
            code="MCP001",
            severity=Severity.WARNING,
            message="No MCP requirements manifest was found.",
            path=str(artifact_path),
            remediation=(
                "Add compatibility/requirements.json, pass --manifest, or wait for the "
                "runtime-introspection phase."
            ),
        )
        targets = [
            TargetAssessment(
                target_id=profile.id,
                label=profile.label,
                reviewed_at=profile.reviewed_at,
                status=TargetStatus.UNKNOWN,
                reasons=["The server's required capabilities were not declared or probed."],
            )
            for profile in profiles
        ]
        return AuditReport(
            artifact_kind="mcp-server",
            artifact_path=artifact_path,
            conformance=ConformanceStatus.UNKNOWN,
            static_portability=CompatibilityGrade.UNVERIFIED,
            targets=targets,
            findings=[finding],
            evidence_boundary="no requirements declaration and no runtime initialization",
        )

    try:
        data = _load_manifest(manifest)
        capabilities = _validate_manifest(data, manifest)
    except AuditInputError as exc:
        finding = Finding(
            code="MCP002",
            severity=Severity.ERROR,
            message=str(exc),
            path=str(manifest),
            remediation="Correct the manifest structure and supported capability vocabulary.",
        )
        targets = [
            TargetAssessment(
                target_id=profile.id,
                label=profile.label,
                reviewed_at=profile.reviewed_at,
                status=TargetStatus.INCOMPATIBLE,
                reasons=["The MCP requirements declaration is invalid."],
            )
            for profile in profiles
        ]
        return AuditReport(
            artifact_kind="mcp-server",
            artifact_path=artifact_path,
            conformance=ConformanceStatus.FAIL,
            static_portability=CompatibilityGrade.INCOMPATIBLE,
            targets=targets,
            findings=[finding],
            evidence_boundary="requirements-manifest validation failed; no runtime was attempted",
        )

    targets, findings = _assess_mcp_targets(profiles, capabilities, manifest)
    return AuditReport(
        artifact_kind="mcp-server",
        artifact_path=artifact_path,
        conformance=ConformanceStatus.PASS,
        static_portability=_mcp_portability_grade(targets),
        targets=targets,
        findings=findings,
        evidence_boundary=(
            "declared compatibility/requirements.json compared with reviewed target profiles; "
            "the running server was not initialized"
        ),
    )


def _resolve_manifest(artifact_path: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        resolved = explicit.expanduser().resolve()
        if not resolved.is_file():
            raise AuditInputError(f"Manifest file does not exist: {resolved}")
        return resolved
    if artifact_path.is_file() and artifact_path.suffix == ".json":
        return artifact_path
    if artifact_path.is_dir():
        candidate = artifact_path / _DEFAULT_MANIFEST
        if candidate.is_file():
            return candidate
    return None


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise AuditInputError(f"Cannot read MCP requirements manifest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AuditInputError(f"MCP requirements manifest is invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AuditInputError("MCP requirements manifest must be a JSON object")
    return cast(dict[str, Any], parsed)


def _validate_manifest(data: dict[str, Any], path: Path) -> dict[str, list[str]]:
    allowed_top_level = {"schema_version", "artifact", "name", "capabilities"}
    unknown_top_level = sorted(set(data) - allowed_top_level)
    if unknown_top_level:
        raise AuditInputError(
            f"Unknown top-level field(s) in {path}: {', '.join(unknown_top_level)}"
        )
    if data.get("schema_version") != 1:
        raise AuditInputError(
            f"Unsupported or missing schema_version in {path}; expected integer 1"
        )
    if data.get("artifact") != "mcp-server":
        raise AuditInputError("Manifest artifact must be the string 'mcp-server'")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AuditInputError("Manifest name must be a non-empty string")
    raw_capabilities = data.get("capabilities")
    if not isinstance(raw_capabilities, dict):
        raise AuditInputError("Manifest capabilities must be an object")

    vocabulary = {
        "features": {"tools", "resources", "prompts", "server-instructions", "elicitation"},
        "transports": {"stdio", "streamable-http", "sse", "websocket"},
        "authentication": {"none", "headers", "bearer", "oauth", "oidc"},
    }
    unknown_categories = sorted(set(raw_capabilities) - set(vocabulary))
    if unknown_categories:
        raise AuditInputError(
            f"Unknown capabilities field(s): {', '.join(unknown_categories)}"
        )

    result: dict[str, list[str]] = {}
    for category, allowed in vocabulary.items():
        value = raw_capabilities.get(category, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise AuditInputError(f"capabilities.{category} must be an array of strings")
        entries = cast(list[str], value)
        duplicates = sorted({item for item in entries if entries.count(item) > 1})
        if duplicates:
            raise AuditInputError(
                f"capabilities.{category} contains duplicate values: {', '.join(duplicates)}"
            )
        unknown = sorted(set(entries) - allowed)
        if unknown:
            raise AuditInputError(
                f"Unknown capabilities.{category} value(s): {', '.join(unknown)}"
            )
        result[category] = entries
    if not any(result.values()):
        raise AuditInputError("Manifest must declare at least one capability")
    return result


def _assess_mcp_targets(
    profiles: tuple[TargetProfile, ...],
    capabilities: dict[str, list[str]],
    manifest: Path,
) -> tuple[list[TargetAssessment], list[Finding]]:
    assessments: list[TargetAssessment] = []
    findings: list[Finding] = []

    for profile in profiles:
        reasons: list[str] = []
        overall = TargetStatus.SUPPORTED
        feature_map = cast(dict[str, str], profile.mcp["features"])

        for feature in capabilities["features"]:
            capability_status = feature_map.get(feature, "unknown")
            feature_status, reason, finding = _evaluate_required_capability(
                target=profile,
                category="feature",
                capability=feature,
                capability_status=capability_status,
                manifest=manifest,
            )
            overall = _worse_status(overall, feature_status)
            reasons.append(reason)
            if finding is not None:
                findings.append(finding)

        overall = _combine_alternative_category(
            current=overall,
            profile=profile,
            category="transports",
            offered=capabilities["transports"],
            reasons=reasons,
            findings=findings,
            manifest=manifest,
        )
        overall = _combine_alternative_category(
            current=overall,
            profile=profile,
            category="authentication",
            offered=capabilities["authentication"],
            reasons=reasons,
            findings=findings,
            manifest=manifest,
        )

        assessments.append(
            TargetAssessment(
                target_id=profile.id,
                label=profile.label,
                reviewed_at=profile.reviewed_at,
                status=overall,
                reasons=reasons,
            )
        )

    return assessments, _sort_findings(findings)


def _evaluate_required_capability(
    *,
    target: TargetProfile,
    category: str,
    capability: str,
    capability_status: str,
    manifest: Path,
) -> tuple[TargetStatus, str, Finding | None]:
    if capability_status in _SUPPORTED_CAPABILITY_STATUSES:
        return (
            TargetStatus.SUPPORTED,
            f"Required {category} {capability!r} is supported.",
            None,
        )
    if capability_status in _DEGRADED_CAPABILITY_STATUSES:
        return (
            TargetStatus.DEGRADED,
            f"Required {category} {capability!r} is {capability_status}.",
            Finding(
                code="MCP005" if capability_status == "deprecated" else "MCP004",
                severity=Severity.WARNING,
                message=(
                    f"{target.label} marks required {category} {capability!r} as "
                    f"{capability_status}."
                ),
                path=str(manifest),
                targets=(target.id,),
                remediation=(
                    "Prefer a fully supported capability, or define and test the accepted "
                    "degraded behavior."
                ),
            ),
        )
    if capability_status in _UNAVAILABLE_CAPABILITY_STATUSES:
        return (
            TargetStatus.INCOMPATIBLE,
            f"Required {category} {capability!r} is {capability_status}.",
            Finding(
                code="MCP003",
                severity=Severity.ERROR,
                message=(
                    f"{target.label} cannot provide required {category} {capability!r} "
                    f"({capability_status})."
                ),
                path=str(manifest),
                targets=(target.id,),
                remediation="Remove the requirement, provide a degraded mode, or exclude the target.",
            ),
        )
    if capability_status in _UNCERTAIN_CAPABILITY_STATUSES:
        return (
            TargetStatus.UNKNOWN,
            f"Required {category} {capability!r} has unknown support.",
            Finding(
                code="MCP004",
                severity=Severity.WARNING,
                message=(
                    f"Support for required {category} {capability!r} is unknown on "
                    f"{target.label}."
                ),
                path=str(manifest),
                targets=(target.id,),
                remediation="Refresh the official profile or collect target-specific runtime evidence.",
            ),
        )
    raise AuditInputError(
        f"Profile {target.id} has invalid MCP status {capability_status!r} "
        f"for {category} {capability}"
    )


def _combine_alternative_category(
    *,
    current: TargetStatus,
    profile: TargetProfile,
    category: str,
    offered: list[str],
    reasons: list[str],
    findings: list[Finding],
    manifest: Path,
) -> TargetStatus:
    if not offered:
        return current

    support_map = cast(dict[str, str], profile.mcp[category])
    observed = {option: support_map.get(option, "unknown") for option in offered}
    supported = sorted(
        option for option, capability_status in observed.items() if capability_status == "supported"
    )
    deprecated = sorted(
        option for option, capability_status in observed.items() if capability_status == "deprecated"
    )
    partial = sorted(
        option for option, capability_status in observed.items() if capability_status == "partial"
    )
    unknown = sorted(
        option for option, capability_status in observed.items() if capability_status == "unknown"
    )

    if supported:
        reasons.append(f"Offered {category} have a supported option: {', '.join(supported)}.")
        return current
    if deprecated:
        reasons.append(
            f"Only deprecated {category} options are usable: {', '.join(deprecated)}."
        )
        findings.append(
            Finding(
                code="MCP005",
                severity=Severity.WARNING,
                message=f"{profile.label} only supports deprecated offered {category}.",
                path=str(manifest),
                targets=(profile.id,),
                remediation=f"Add a non-deprecated {category} option supported by this target.",
            )
        )
        return _worse_status(current, TargetStatus.DEGRADED)
    if partial:
        reasons.append(f"Only partial {category} options are available: {', '.join(partial)}.")
        findings.append(
            Finding(
                code="MCP006",
                severity=Severity.WARNING,
                message=f"{profile.label} only partially supports offered {category}.",
                path=str(manifest),
                targets=(profile.id,),
                remediation=(
                    "Declare a fully supported alternative or define and test the accepted "
                    "partial behavior."
                ),
            )
        )
        return _worse_status(current, TargetStatus.DEGRADED)
    if unknown:
        reasons.append(f"Support is unknown for offered {category}: {', '.join(unknown)}.")
        findings.append(
            Finding(
                code="MCP007",
                severity=Severity.WARNING,
                message=f"{profile.label} has no established support for offered {category}.",
                path=str(manifest),
                targets=(profile.id,),
                remediation="Refresh the profile or collect runtime evidence.",
            )
        )
        return _worse_status(current, TargetStatus.UNKNOWN)

    reasons.append(f"No offered {category} option is supported.")
    findings.append(
        Finding(
            code="MCP008",
            severity=Severity.ERROR,
            message=f"{profile.label} supports none of the offered {category} options.",
            path=str(manifest),
            targets=(profile.id,),
            remediation=f"Add a {category} option supported by this target or exclude the target.",
        )
    )
    return TargetStatus.INCOMPATIBLE


def _mcp_portability_grade(assessments: list[TargetAssessment]) -> CompatibilityGrade:
    statuses = {assessment.status for assessment in assessments}
    if TargetStatus.INCOMPATIBLE in statuses:
        return CompatibilityGrade.INCOMPATIBLE
    if TargetStatus.DEGRADED in statuses:
        return CompatibilityGrade.DEGRADED
    if TargetStatus.UNKNOWN in statuses:
        return CompatibilityGrade.UNVERIFIED
    return CompatibilityGrade.PORTABLE


def _worse_status(current: TargetStatus, candidate: TargetStatus) -> TargetStatus:
    order = {
        TargetStatus.SUPPORTED: 0,
        TargetStatus.NOT_APPLICABLE: 0,
        TargetStatus.UNKNOWN: 1,
        TargetStatus.DEGRADED: 2,
        TargetStatus.INCOMPATIBLE: 3,
    }
    return candidate if order[candidate] > order[current] else current


def _sort_findings(findings: list[Finding]) -> list[Finding]:
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(findings, key=lambda item: (severity_order[item.severity], item.code, item.targets))
