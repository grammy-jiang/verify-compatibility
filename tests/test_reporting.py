from __future__ import annotations

from pathlib import Path

from verify_compatibility.models import (
    AuditReport,
    CompatibilityGrade,
    ConformanceStatus,
    Finding,
    RuntimeStatus,
    Severity,
    TargetAssessment,
    TargetStatus,
)
from verify_compatibility.reporting import render_json, render_text


def test_report_renderers_include_evidence_boundary_and_remediation() -> None:
    report = AuditReport(
        artifact_kind="agent-skill",
        artifact_path=Path("example"),
        conformance=ConformanceStatus.PASS,
        static_portability=CompatibilityGrade.UNVERIFIED,
        findings=[
            Finding(
                code="TEST001",
                severity=Severity.WARNING,
                message="Evidence is incomplete.",
                remediation="Collect runtime evidence.",
            )
        ],
        evidence_boundary="static test fixture",
    )

    text = render_text(report)
    structured = render_json(report)

    assert "Evidence boundary: static test fixture" in text
    assert "Collect runtime evidence" in text
    assert '"runtime_verification": "unverified"' in structured
    assert report.exit_code == 0


def test_text_renderer_handles_empty_sections_and_verified_runtime() -> None:
    report = AuditReport(
        artifact_kind="mcp-server",
        artifact_path=Path("server"),
        conformance=ConformanceStatus.PASS,
        static_portability=CompatibilityGrade.PORTABLE,
        runtime_verification=RuntimeStatus.VERIFIED,
    )

    text = render_text(report)

    assert text.count("  - none") == 2
    assert "A static pass is not runtime proof" not in text


def test_text_renderer_includes_locations_targets_and_reasons() -> None:
    report = AuditReport(
        artifact_kind="agent-skill",
        artifact_path=Path("skill"),
        conformance=ConformanceStatus.PASS,
        static_portability=CompatibilityGrade.DEGRADED,
        targets=[
            TargetAssessment(
                "target",
                "Target",
                "2026-08-16",
                TargetStatus.DEGRADED,
                ["A reason."],
            )
        ],
        findings=[
            Finding(
                code="TEST002",
                severity=Severity.INFO,
                message="Located finding.",
                path="SKILL.md",
                targets=("target",),
            )
        ],
    )

    text = render_text(report)

    assert "A reason." in text
    assert "[SKILL.md] (target)" in text
