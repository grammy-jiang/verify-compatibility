"""Render audit reports for humans and automation."""

from __future__ import annotations

import json

from .models import AuditReport


def render_json(report: AuditReport) -> str:
    """Render stable, pretty JSON."""

    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def render_text(report: AuditReport) -> str:
    """Render a compact human-readable report."""

    lines = [
        f"Artifact: {report.artifact_kind} ({report.artifact_path})",
        f"Conformance: {report.conformance.value}",
        f"Static portability: {report.static_portability.value}",
        f"Runtime verification: {report.runtime_verification.value}",
        f"Evidence boundary: {report.evidence_boundary}",
        "",
        "Targets:",
    ]
    if report.targets:
        for target in report.targets:
            lines.append(
                f"  - {target.target_id}: {target.status.value} "
                f"(profile reviewed {target.reviewed_at})"
            )
            for reason in target.reasons:
                lines.append(f"      {reason}")
    else:
        lines.append("  - none")

    lines.extend(("", "Findings:"))
    if report.findings:
        for finding in report.findings:
            location = f" [{finding.path}]" if finding.path else ""
            targets = f" ({', '.join(finding.targets)})" if finding.targets else ""
            lines.append(
                f"  - {finding.severity.value.upper()} {finding.code}{location}{targets}: "
                f"{finding.message}"
            )
            if finding.remediation:
                lines.append(f"      Remediation: {finding.remediation}")
    else:
        lines.append("  - none")

    if report.runtime_verification.value == "unverified":
        lines.extend(
            (
                "",
                "A static pass is not runtime proof. Run target-specific probes before claiming",
                "behavioral parity.",
            )
        )
    return "\n".join(lines)
