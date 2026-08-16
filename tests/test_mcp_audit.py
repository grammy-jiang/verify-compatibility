from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from verify_compatibility.errors import AuditInputError
from verify_compatibility.mcp_audit import (
    _combine_alternative_category,
    _evaluate_required_capability,
    _load_manifest,
    _mcp_portability_grade,
    _resolve_manifest,
    _validate_manifest,
    audit_mcp,
)
from verify_compatibility.models import (
    CompatibilityGrade,
    ConformanceStatus,
    Finding,
    TargetAssessment,
    TargetStatus,
)
from verify_compatibility.profiles import TargetProfile, load_profiles


def _write_manifest(
    root: Path,
    *,
    features: list[str] | None = None,
    transports: list[str] | None = None,
    authentication: list[str] | None = None,
    extra: dict[str, object] | None = None,
) -> Path:
    manifest = {
        "schema_version": 1,
        "artifact": "mcp-server",
        "name": "test-server",
        "capabilities": {
            "features": features or [],
            "transports": transports or [],
            "authentication": authentication or [],
        },
    }
    if extra:
        manifest.update(extra)
    path = root / "compatibility" / "requirements.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_missing_manifest_is_unverified(tmp_path: Path) -> None:
    report = audit_mcp(tmp_path)

    assert report.conformance is ConformanceStatus.UNKNOWN
    assert report.static_portability is CompatibilityGrade.UNVERIFIED
    assert report.findings[0].code == "MCP001"
    assert all(target.status is TargetStatus.UNKNOWN for target in report.targets)


def test_portable_tools_stdio_server(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        features=["tools"],
        transports=["stdio"],
        authentication=["none"],
    )

    report = audit_mcp(tmp_path)

    assert report.conformance is ConformanceStatus.PASS
    assert report.static_portability is CompatibilityGrade.PORTABLE
    assert not report.findings
    assert all(target.status is TargetStatus.SUPPORTED for target in report.targets)


def test_required_resources_retain_incompatible_result_after_supported_tool(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        features=["tools", "resources"],
        transports=["stdio"],
        authentication=["none"],
    )

    report = audit_mcp(tmp_path)
    by_target = {target.target_id: target for target in report.targets}

    assert report.static_portability is CompatibilityGrade.INCOMPATIBLE
    assert by_target["github-copilot-cloud-agent"].status is TargetStatus.INCOMPATIBLE
    assert by_target["codex-local"].status is TargetStatus.UNKNOWN
    assert any(
        finding.code == "MCP003"
        and finding.targets == ("github-copilot-cloud-agent",)
        for finding in report.findings
    )


def test_oauth_only_is_incompatible_with_copilot_cloud_agent(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        features=["tools"],
        transports=["streamable-http"],
        authentication=["oauth"],
    )

    report = audit_mcp(tmp_path)

    assert report.static_portability is CompatibilityGrade.INCOMPATIBLE
    cloud = next(
        target for target in report.targets if target.target_id == "github-copilot-cloud-agent"
    )
    assert cloud.status is TargetStatus.INCOMPATIBLE
    assert any(finding.code == "MCP008" for finding in report.findings)


def test_supported_alternative_avoids_deprecated_transport_penalty(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        features=["tools"],
        transports=["sse", "streamable-http"],
        authentication=["none"],
    )

    report = audit_mcp(tmp_path)

    assert report.static_portability is CompatibilityGrade.PORTABLE
    assert not any(finding.code == "MCP005" for finding in report.findings)


def test_only_sse_is_not_portable(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        features=["tools"],
        transports=["sse"],
        authentication=["none"],
    )

    report = audit_mcp(tmp_path)
    by_target = {target.target_id: target for target in report.targets}

    assert report.static_portability is CompatibilityGrade.INCOMPATIBLE
    assert by_target["claude-code"].status is TargetStatus.DEGRADED
    assert by_target["codex-local"].status is TargetStatus.INCOMPATIBLE


def test_unknown_manifest_field_fails_conformance(tmp_path: Path) -> None:
    _write_manifest(tmp_path, features=["tools"], extra={"unexpected": True})

    report = audit_mcp(tmp_path)

    assert report.conformance is ConformanceStatus.FAIL
    assert report.static_portability is CompatibilityGrade.INCOMPATIBLE
    assert report.findings[0].code == "MCP002"
    assert "Unknown top-level" in report.findings[0].message


def test_explicit_manifest_path_is_supported(tmp_path: Path) -> None:
    server = tmp_path / "server"
    server.mkdir()
    manifest = _write_manifest(tmp_path / "declaration", features=["tools"])

    report = audit_mcp(server, manifest_path=manifest, target_ids=["claude-code"])

    assert report.static_portability is CompatibilityGrade.PORTABLE
    assert [target.target_id for target in report.targets] == ["claude-code"]


def _profile_with_status(
    *,
    category: str,
    capability: str,
    status: str,
) -> TargetProfile:
    data = copy.deepcopy(load_profiles()[0].data)
    data["id"] = "fixture-target"
    data["label"] = "Fixture target"
    data["mcp"][category][capability] = status
    return TargetProfile(data)


def test_missing_artifact_and_explicit_manifest_are_input_errors(tmp_path: Path) -> None:
    with pytest.raises(AuditInputError, match="Artifact path does not exist"):
        audit_mcp(tmp_path / "missing")

    server = tmp_path / "server"
    server.mkdir()
    with pytest.raises(AuditInputError, match="Manifest file does not exist"):
        _resolve_manifest(server, tmp_path / "missing.json")


def test_manifest_loader_rejects_invalid_json_and_non_object(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(AuditInputError, match="invalid JSON"):
        _load_manifest(malformed)

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(AuditInputError, match="must be a JSON object"):
        _load_manifest(array)


def test_manifest_validator_rejects_every_contract_violation(tmp_path: Path) -> None:
    path = tmp_path / "requirements.json"
    base = {
        "schema_version": 1,
        "artifact": "mcp-server",
        "name": "server",
        "capabilities": {"features": ["tools"]},
    }

    cases: list[tuple[dict[str, Any], str]] = [
        ({**base, "schema_version": 2}, "schema_version"),
        ({**base, "artifact": "other"}, "artifact must"),
        ({**base, "name": ""}, "non-empty string"),
        ({**base, "capabilities": []}, "must be an object"),
        (
            {
                **base,
                "capabilities": {"features": ["tools"], "invented": []},
            },
            "Unknown capabilities field",
        ),
        (
            {**base, "capabilities": {"features": "tools"}},
            "must be an array of strings",
        ),
        (
            {**base, "capabilities": {"features": ["tools", "tools"]}},
            "duplicate values",
        ),
        (
            {**base, "capabilities": {"features": ["invented"]}},
            "Unknown capabilities.features",
        ),
        ({**base, "capabilities": {}}, "at least one capability"),
        ({**base, "unexpected": True}, "Unknown top-level"),
    ]
    for data, match in cases:
        with pytest.raises(AuditInputError, match=match):
            _validate_manifest(data, path)


def test_invalid_manifest_is_returned_as_a_failed_report(tmp_path: Path) -> None:
    path = tmp_path / "requirements.json"
    path.write_text("[]", encoding="utf-8")

    report = audit_mcp(path)

    assert report.conformance is ConformanceStatus.FAIL
    assert report.findings[0].code == "MCP002"
    assert all(target.status is TargetStatus.INCOMPATIBLE for target in report.targets)


def test_required_capability_partial_deprecated_unknown_and_invalid(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.json"
    for status, expected, code in [
        ("partial", TargetStatus.DEGRADED, "MCP004"),
        ("deprecated", TargetStatus.DEGRADED, "MCP005"),
        ("unknown", TargetStatus.UNKNOWN, "MCP004"),
        ("unsupported", TargetStatus.INCOMPATIBLE, "MCP003"),
    ]:
        profile = _profile_with_status(category="features", capability="tools", status=status)
        target_status, reason, finding = _evaluate_required_capability(
            target=profile,
            category="feature",
            capability="tools",
            capability_status=status,
            manifest=manifest,
        )
        assert target_status is expected
        assert status in reason or "unknown" in reason
        assert finding is not None
        assert finding.code == code

    profile = _profile_with_status(category="features", capability="tools", status="supported")
    target_status, _reason, finding = _evaluate_required_capability(
        target=profile,
        category="feature",
        capability="tools",
        capability_status="supported",
        manifest=manifest,
    )
    assert target_status is TargetStatus.SUPPORTED
    assert finding is None

    with pytest.raises(AuditInputError, match="invalid MCP status"):
        _evaluate_required_capability(
            target=profile,
            category="feature",
            capability="tools",
            capability_status="invented",
            manifest=manifest,
        )


def test_alternative_category_partial_unknown_and_empty(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.json"
    reasons: list[str] = []
    findings: list[Finding] = []

    profile = _profile_with_status(category="transports", capability="stdio", status="partial")
    status = _combine_alternative_category(
        current=TargetStatus.SUPPORTED,
        profile=profile,
        category="transports",
        offered=["stdio"],
        reasons=reasons,
        findings=findings,
        manifest=manifest,
    )
    assert status is TargetStatus.DEGRADED
    assert findings[-1].code == "MCP006"

    reasons.clear()
    findings.clear()
    profile = _profile_with_status(category="transports", capability="stdio", status="unknown")
    status = _combine_alternative_category(
        current=TargetStatus.SUPPORTED,
        profile=profile,
        category="transports",
        offered=["stdio"],
        reasons=reasons,
        findings=findings,
        manifest=manifest,
    )
    assert status is TargetStatus.UNKNOWN
    assert findings[-1].code == "MCP007"

    assert (
        _combine_alternative_category(
            current=TargetStatus.DEGRADED,
            profile=profile,
            category="transports",
            offered=[],
            reasons=reasons,
            findings=findings,
            manifest=manifest,
        )
        is TargetStatus.DEGRADED
    )


def test_portability_grade_covers_all_target_states() -> None:
    def assessment(status: TargetStatus) -> TargetAssessment:
        return TargetAssessment("target", "Target", "2026-08-16", status)

    assert _mcp_portability_grade([assessment(TargetStatus.SUPPORTED)]) is CompatibilityGrade.PORTABLE
    assert _mcp_portability_grade([assessment(TargetStatus.UNKNOWN)]) is CompatibilityGrade.UNVERIFIED
    assert _mcp_portability_grade([assessment(TargetStatus.DEGRADED)]) is CompatibilityGrade.DEGRADED
    assert (
        _mcp_portability_grade([assessment(TargetStatus.INCOMPATIBLE)])
        is CompatibilityGrade.INCOMPATIBLE
    )
