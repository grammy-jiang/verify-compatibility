"""Deterministic static analysis for Agent Skills."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

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
from .profiles import TargetProfile, load_skill_standard, select_profiles

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def audit_skill(path: Path, *, target_ids: list[str] | None = None) -> AuditReport:
    """Audit one Agent Skill directory or its ``SKILL.md`` file."""

    skill_root, skill_file = _locate_skill(path)
    profiles = select_profiles(target_ids)
    findings: list[Finding] = []

    try:
        frontmatter, body, line_count = _parse_skill_file(skill_file)
    except AuditInputError as exc:
        findings.append(
            Finding(
                code="SKILL001",
                severity=Severity.ERROR,
                message=str(exc),
                path=str(skill_file),
                remediation="Provide a SKILL.md with YAML frontmatter followed by Markdown.",
            )
        )
        return _failed_report(skill_root, profiles, findings)

    standard = load_skill_standard()
    standard_frontmatter = cast(dict[str, Any], standard["frontmatter"])
    required = set(cast(list[str], standard_frontmatter["required"]))
    optional = set(cast(list[str], standard_frontmatter["optional"]))
    standard_fields = required | optional
    constraints = cast(dict[str, Any], standard_frontmatter["constraints"])

    _validate_required_fields(frontmatter, required, skill_file, findings)
    _validate_name(frontmatter.get("name"), skill_root, skill_file, constraints, findings)
    _validate_description(frontmatter.get("description"), skill_file, constraints, findings)
    _validate_optional_fields(frontmatter, skill_file, constraints, findings)

    unknown_fields = sorted(set(frontmatter) - standard_fields)
    if unknown_fields:
        fields = ", ".join(unknown_fields)
        findings.append(
            Finding(
                code="SKILL008",
                severity=Severity.WARNING,
                message=f"Non-standard frontmatter field(s): {fields}.",
                path=str(skill_file),
                remediation=(
                    "Move host-specific behavior into an explicit adapter, or confirm every "
                    "selected target accepts the field."
                ),
            )
        )

    file_line_limit = cast(int, constraints["recommended_file_max_lines"])
    if line_count > file_line_limit:
        findings.append(
            Finding(
                code="SKILL009",
                severity=Severity.WARNING,
                message=(f"SKILL.md has {line_count} lines, above the recommended {file_line_limit}-line limit."),
                path=str(skill_file),
                remediation="Move detailed material into focused files under references/.",
            )
        )
    if not body.strip():
        findings.append(
            Finding(
                code="SKILL010",
                severity=Severity.WARNING,
                message="SKILL.md has no instruction body.",
                path=str(skill_file),
                remediation="Add concise instructions, procedures, and relevant edge cases.",
            )
        )

    target_assessments, portability_findings, has_adapter = _assess_targets(
        profiles=profiles,
        frontmatter=frontmatter,
        standard_fields=standard_fields,
        body=body,
        skill_root=skill_root,
        skill_file=skill_file,
    )
    findings.extend(portability_findings)

    has_conformance_error = any(finding.severity is Severity.ERROR for finding in findings)
    conformance = ConformanceStatus.FAIL if has_conformance_error else ConformanceStatus.PASS
    static_portability = _skill_portability_grade(
        target_assessments,
        has_conformance_error=has_conformance_error,
        has_adapter=has_adapter,
    )

    return AuditReport(
        artifact_kind="agent-skill",
        artifact_path=skill_root,
        conformance=conformance,
        static_portability=static_portability,
        targets=target_assessments,
        findings=_sort_findings(findings),
        evidence_boundary=(
            "SKILL.md structure, reviewed capability profiles, and conservative literal "
            "host-extension detection; no host was executed"
        ),
    )


def _locate_skill(path: Path) -> tuple[Path, Path]:
    # ``absolute`` deliberately preserves a user-facing symlink name. Resolving
    # the symlink would compare ``name`` with the storage directory rather than
    # the directory through which an agent discovers the skill.
    absolute = path.expanduser().absolute()
    if absolute.is_file():
        if absolute.name != "SKILL.md":
            raise AuditInputError(f"Expected SKILL.md, got file: {absolute}")
        return absolute.parent, absolute
    if absolute.is_dir():
        candidate = absolute / "SKILL.md"
        if candidate.is_file():
            return absolute, candidate
        raise AuditInputError(f"No SKILL.md found directly under: {absolute}")
    raise AuditInputError(f"Artifact path does not exist: {absolute}")


def _parse_skill_file(path: Path) -> tuple[dict[str, Any], str, int]:
    try:
        text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    except (OSError, UnicodeError) as exc:
        raise AuditInputError(f"Cannot read SKILL.md: {exc}") from exc

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AuditInputError("SKILL.md must start with a YAML frontmatter delimiter (---)")

    end = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if end is None:
        raise AuditInputError("SKILL.md frontmatter has no closing delimiter (---)")

    raw_frontmatter = "\n".join(lines[1:end])
    try:
        syntax_tree = yaml.compose(raw_frontmatter)
        parsed: object = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError as exc:
        raise AuditInputError(f"SKILL.md frontmatter is invalid YAML: {exc}") from exc
    if not isinstance(syntax_tree, yaml.MappingNode) or not isinstance(parsed, Mapping):
        raise AuditInputError("SKILL.md frontmatter must be a YAML mapping")

    seen: set[str] = set()
    for key_node, _value_node in syntax_tree.value:
        if not isinstance(key_node, yaml.ScalarNode) or not isinstance(key_node.value, str):
            raise AuditInputError("SKILL.md frontmatter keys must be strings")
        if key_node.value in seen:
            raise AuditInputError(f"SKILL.md frontmatter contains duplicate key {key_node.value!r}")
        seen.add(key_node.value)

    if not all(isinstance(key, str) for key in parsed):
        raise AuditInputError("SKILL.md frontmatter keys must be strings")
    frontmatter = cast(dict[str, Any], dict(parsed))
    body = "\n".join(lines[end + 1 :])
    return frontmatter, body, len(lines)


def _validate_required_fields(
    frontmatter: dict[str, Any],
    required: set[str],
    path: Path,
    findings: list[Finding],
) -> None:
    for field_name in sorted(required):
        if field_name not in frontmatter:
            findings.append(
                Finding(
                    code="SKILL002",
                    severity=Severity.ERROR,
                    message=f"Required frontmatter field {field_name!r} is missing.",
                    path=str(path),
                    remediation=f"Add a non-empty {field_name!r} field.",
                )
            )


def _validate_name(
    value: object,
    skill_root: Path,
    path: Path,
    constraints: dict[str, Any],
    findings: list[Finding],
) -> None:
    if value is None:
        return
    maximum = cast(int, constraints["name_max_length"])
    if not isinstance(value, str) or not value:
        findings.append(
            Finding(
                code="SKILL003",
                severity=Severity.ERROR,
                message="The skill name must be a non-empty string.",
                path=str(path),
            )
        )
        return
    if len(value) > maximum or not _NAME_PATTERN.fullmatch(value):
        findings.append(
            Finding(
                code="SKILL004",
                severity=Severity.ERROR,
                message=(
                    f"Invalid skill name {value!r}; use 1-{maximum} lowercase letters, numbers, and single hyphens."
                ),
                path=str(path),
                remediation="Rename the skill and its directory to the same valid identifier.",
            )
        )
    if value != skill_root.name:
        findings.append(
            Finding(
                code="SKILL005",
                severity=Severity.ERROR,
                message=(f"Skill name {value!r} does not match parent directory {skill_root.name!r}."),
                path=str(path),
                remediation="Make the frontmatter name and skill-directory name identical.",
            )
        )


def _validate_description(
    value: object,
    path: Path,
    constraints: dict[str, Any],
    findings: list[Finding],
) -> None:
    if value is None:
        return
    maximum = cast(int, constraints["description_max_length"])
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        findings.append(
            Finding(
                code="SKILL006",
                severity=Severity.ERROR,
                message=(f"The description must be a non-empty string of at most {maximum} characters."),
                path=str(path),
                remediation="Describe what the skill does and when an agent should use it.",
            )
        )


def _validate_optional_fields(
    frontmatter: dict[str, Any],
    path: Path,
    constraints: dict[str, Any],
    findings: list[Finding],
) -> None:
    compatibility = frontmatter.get("compatibility")
    compatibility_max = cast(int, constraints["compatibility_max_length"])
    if compatibility is not None and (
        not isinstance(compatibility, str) or not compatibility.strip() or len(compatibility) > compatibility_max
    ):
        findings.append(
            Finding(
                code="SKILL007",
                severity=Severity.ERROR,
                message=(
                    f"The compatibility field must be a non-empty string of at most {compatibility_max} characters."
                ),
                path=str(path),
            )
        )

    metadata = frontmatter.get("metadata")
    if metadata is not None:
        valid = isinstance(metadata, Mapping) and all(
            isinstance(key, str) and isinstance(item, str) for key, item in metadata.items()
        )
        if not valid:
            findings.append(
                Finding(
                    code="SKILL007",
                    severity=Severity.ERROR,
                    message="The metadata field must map string keys to string values.",
                    path=str(path),
                )
            )

    allowed_tools = frontmatter.get("allowed-tools")
    if allowed_tools is not None and not isinstance(allowed_tools, str):
        findings.append(
            Finding(
                code="SKILL007",
                severity=Severity.ERROR,
                message="The open Agent Skills allowed-tools field must be a string.",
                path=str(path),
                remediation="Use a space-separated string, or move host syntax into an adapter.",
            )
        )

    license_value = frontmatter.get("license")
    if license_value is not None and (not isinstance(license_value, str) or not license_value.strip()):
        findings.append(
            Finding(
                code="SKILL007",
                severity=Severity.ERROR,
                message="The license field must be a non-empty string when provided.",
                path=str(path),
            )
        )


def _assess_targets(
    *,
    profiles: tuple[TargetProfile, ...],
    frontmatter: dict[str, Any],
    standard_fields: set[str],
    body: str,
    skill_root: Path,
    skill_file: Path,
) -> tuple[list[TargetAssessment], list[Finding], bool]:
    assessments: list[TargetAssessment] = []
    findings: list[Finding] = []

    marker_support: dict[str, tuple[str, set[str]]] = {}
    for profile in profiles:
        markers = cast(list[dict[str, str]], profile.skills.get("host_markers", []))
        for marker in markers:
            literal = marker["literal"]
            feature = marker["feature"]
            existing = marker_support.setdefault(literal, (feature, set()))
            existing[1].add(profile.id)

    matched_markers = {literal: details for literal, details in marker_support.items() if literal in body}
    for literal, (feature, supported_by) in matched_markers.items():
        unsupported_targets = tuple(profile.id for profile in profiles if profile.id not in supported_by)
        if unsupported_targets:
            findings.append(
                Finding(
                    code="PORT002",
                    severity=Severity.WARNING,
                    message=f"Body marker {literal!r} uses host-specific feature {feature!r}.",
                    path=str(skill_file),
                    targets=unsupported_targets,
                    remediation="Replace it with portable instructions or isolate it in an adapter.",
                )
            )

    has_adapter = False
    adapter_targets: dict[str, list[str]] = {}
    for profile in profiles:
        for adapter in cast(list[str], profile.skills.get("adapter_files", [])):
            adapter_targets.setdefault(adapter, []).append(profile.id)
    for adapter, targets in sorted(adapter_targets.items()):
        adapter_path = skill_root / adapter
        if adapter_path.is_file():
            has_adapter = True
            findings.append(
                Finding(
                    code="PORT003",
                    severity=Severity.INFO,
                    message=f"Host-specific adapter {adapter!r} detected.",
                    path=str(adapter_path),
                    targets=tuple(targets),
                )
            )

    allowed_tools_present = "allowed-tools" in frontmatter
    selected_allowed_tools = {
        profile.id: cast(dict[str, Any], profile.skills["frontmatter"])["allowed_tools"] for profile in profiles
    }
    dialects = {
        cast(str, cast(dict[str, Any], data)["dialect"])
        for data in selected_allowed_tools.values()
        if cast(dict[str, Any], data)["status"] == "supported"
    }
    uncertain_allowed_tools = any(
        cast(dict[str, Any], data)["status"] != "supported" for data in selected_allowed_tools.values()
    )
    if allowed_tools_present and (len(dialects) > 1 or uncertain_allowed_tools):
        findings.append(
            Finding(
                code="PORT001",
                severity=Severity.WARNING,
                message=(
                    "Selected targets do not document one equivalent allowed-tools contract; "
                    "tool names and permission semantics cannot be assumed portable."
                ),
                path=str(skill_file),
                targets=tuple(profile.id for profile in profiles),
                remediation=(
                    "Keep portable instructions independent of pre-approval, then generate "
                    "target-specific permission adapters."
                ),
            )
        )

    for profile in profiles:
        skill_data = profile.skills
        if not bool(skill_data.get("supported")):
            assessments.append(
                TargetAssessment(
                    target_id=profile.id,
                    label=profile.label,
                    reviewed_at=profile.reviewed_at,
                    status=TargetStatus.INCOMPATIBLE,
                    reasons=["Agent Skills are not supported on this target profile."],
                )
            )
            continue

        reasons: list[str] = []
        status = TargetStatus.SUPPORTED
        frontmatter_data = cast(dict[str, Any], skill_data["frontmatter"])
        additional_fields = set(cast(list[str], frontmatter_data["additional_fields"]))
        accepted_fields = standard_fields | additional_fields
        unaccepted = sorted(set(frontmatter) - accepted_fields)
        if unaccepted:
            behavior = cast(str, frontmatter_data["unknown_field_behavior"])
            candidate = {
                "rejected": TargetStatus.INCOMPATIBLE,
                "ignored": TargetStatus.DEGRADED,
                "undocumented": TargetStatus.UNKNOWN,
            }[behavior]
            status = _worse_status(status, candidate)
            reasons.append(f"Frontmatter field(s) {', '.join(unaccepted)} are {behavior} on this surface.")

        if allowed_tools_present:
            allowed_tools = cast(dict[str, Any], frontmatter_data["allowed_tools"])
            support_status = cast(str, allowed_tools["status"])
            dialect = cast(str, allowed_tools["dialect"])
            if support_status == "supported":
                if len(dialects) > 1:
                    status = _worse_status(status, TargetStatus.DEGRADED)
                reasons.append(f"allowed-tools is supported with the {dialect} permission dialect.")
            elif support_status == "unknown":
                status = _worse_status(status, TargetStatus.UNKNOWN)
                reasons.append("allowed-tools support is not established on this surface.")
            else:
                status = _worse_status(status, TargetStatus.DEGRADED)
                reasons.append(f"allowed-tools support is {support_status} on this surface.")

        for _literal, (feature, supported_by) in matched_markers.items():
            if profile.id not in supported_by:
                status = _worse_status(status, TargetStatus.DEGRADED)
                reasons.append(f"Host-specific body feature {feature!r} is not documented here.")

        if not reasons:
            reasons.append("No static gap was found against the reviewed Agent Skills profile.")
        assessments.append(
            TargetAssessment(
                target_id=profile.id,
                label=profile.label,
                reviewed_at=profile.reviewed_at,
                status=status,
                reasons=reasons,
            )
        )

    return assessments, findings, has_adapter


def _skill_portability_grade(
    assessments: list[TargetAssessment],
    *,
    has_conformance_error: bool,
    has_adapter: bool,
) -> CompatibilityGrade:
    if has_conformance_error:
        for assessment in assessments:
            assessment.status = TargetStatus.INCOMPATIBLE
            assessment.reasons.append("The Agent Skill does not conform to its base format.")
        return CompatibilityGrade.INCOMPATIBLE
    statuses = {assessment.status for assessment in assessments}
    if TargetStatus.INCOMPATIBLE in statuses:
        return CompatibilityGrade.INCOMPATIBLE
    if TargetStatus.DEGRADED in statuses:
        return CompatibilityGrade.DEGRADED
    if TargetStatus.UNKNOWN in statuses:
        return CompatibilityGrade.UNVERIFIED
    if has_adapter:
        return CompatibilityGrade.PORTABLE_WITH_ADAPTERS
    return CompatibilityGrade.PORTABLE


def _failed_report(
    skill_root: Path,
    profiles: tuple[TargetProfile, ...],
    findings: list[Finding],
) -> AuditReport:
    targets = [
        TargetAssessment(
            target_id=profile.id,
            label=profile.label,
            reviewed_at=profile.reviewed_at,
            status=TargetStatus.INCOMPATIBLE,
            reasons=["The Agent Skill could not be parsed."],
        )
        for profile in profiles
    ]
    return AuditReport(
        artifact_kind="agent-skill",
        artifact_path=skill_root,
        conformance=ConformanceStatus.FAIL,
        static_portability=CompatibilityGrade.INCOMPATIBLE,
        targets=targets,
        findings=findings,
        evidence_boundary="SKILL.md parsing failed; no runtime was attempted",
    )


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
    return sorted(
        findings,
        key=lambda item: (severity_order[item.severity], item.code, item.path or ""),
    )
