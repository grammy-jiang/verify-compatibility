from __future__ import annotations

from pathlib import Path

import pytest

from verify_compatibility.errors import AuditInputError
from verify_compatibility.models import (
    CompatibilityGrade,
    ConformanceStatus,
    Finding,
    Severity,
    TargetAssessment,
    TargetStatus,
)
from verify_compatibility.profiles import TargetProfile, load_profiles, load_skill_standard
from verify_compatibility.skill_audit import (
    _assess_targets,
    _locate_skill,
    _parse_skill_file,
    _skill_portability_grade,
    audit_skill,
)


def _write_skill(
    root: Path,
    *,
    name: str | None = None,
    description: str = "Checks something. Use when a check is requested.",
    extra_frontmatter: str = "",
    body: str = "Follow the requested procedure.",
) -> Path:
    root.mkdir(parents=True)
    declared_name = root.name if name is None else name
    root.joinpath("SKILL.md").write_text(
        f"---\nname: {declared_name}\ndescription: {description}\n{extra_frontmatter}---\n\n{body}\n",
        encoding="utf-8",
    )
    return root


def test_bundled_skill_is_statically_portable() -> None:
    skill = Path(__file__).parents[1] / "src" / "verify_compatibility" / "skill" / "verify-compatibility"

    report = audit_skill(skill)

    assert report.conformance is ConformanceStatus.PASS
    assert report.static_portability is CompatibilityGrade.PORTABLE
    assert not report.findings
    assert all(target.status is TargetStatus.SUPPORTED for target in report.targets)


def test_invalid_name_and_directory_are_conformance_errors(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "actual-name", name="Wrong_Name")

    report = audit_skill(skill)

    assert report.conformance is ConformanceStatus.FAIL
    assert report.static_portability is CompatibilityGrade.INCOMPATIBLE
    assert {finding.code for finding in report.findings} >= {"SKILL004", "SKILL005"}
    assert report.exit_code == 1


def test_duplicate_frontmatter_key_fails_parse(tmp_path: Path) -> None:
    skill = tmp_path / "duplicate"
    skill.mkdir()
    skill.joinpath("SKILL.md").write_text(
        "---\nname: duplicate\nname: again\ndescription: Test.\n---\nBody.\n",
        encoding="utf-8",
    )

    report = audit_skill(skill)

    assert report.conformance is ConformanceStatus.FAIL
    assert report.findings[0].code == "SKILL001"
    assert "duplicate key" in report.findings[0].message


def test_claude_frontmatter_extension_is_not_assumed_portable(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "forked", extra_frontmatter="context: fork\n")

    report = audit_skill(skill)
    by_target = {target.target_id: target for target in report.targets}

    assert report.conformance is ConformanceStatus.PASS
    assert report.static_portability is CompatibilityGrade.UNVERIFIED
    assert by_target["claude-code"].status is TargetStatus.SUPPORTED
    assert by_target["codex-local"].status is TargetStatus.UNKNOWN
    assert any(finding.code == "SKILL008" for finding in report.findings)


def test_allowed_tools_dialects_are_not_treated_as_equivalent(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path / "tool-limited",
        extra_frontmatter="allowed-tools: Read Bash(git:*)\n",
    )

    report = audit_skill(skill)
    by_target = {target.target_id: target for target in report.targets}

    assert report.conformance is ConformanceStatus.PASS
    assert report.static_portability is CompatibilityGrade.DEGRADED
    assert by_target["codex-local"].status is TargetStatus.UNKNOWN
    assert by_target["claude-code"].status is TargetStatus.DEGRADED
    assert any(finding.code == "PORT001" for finding in report.findings)


def test_host_marker_is_reported_for_other_targets(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path / "claude-path",
        body="Read ${CLAUDE_SKILL_DIR}/references/details.md.",
    )

    report = audit_skill(skill)

    finding = next(item for item in report.findings if item.code == "PORT002")
    assert "claude-code" not in finding.targets
    assert "codex-local" in finding.targets
    assert report.static_portability is CompatibilityGrade.DEGRADED


def test_openai_adapter_is_reported_without_polluting_core(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "adapted")
    adapter = skill / "agents" / "openai.yaml"
    adapter.parent.mkdir()
    adapter.write_text("policy:\n  allow_implicit_invocation: false\n", encoding="utf-8")

    report = audit_skill(skill)

    assert report.static_portability is CompatibilityGrade.PORTABLE_WITH_ADAPTERS
    finding = next(item for item in report.findings if item.code == "PORT003")
    assert finding.targets == ("codex-local",)


def test_invalid_optional_fields_fail_conformance(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path / "invalid-metadata",
        extra_frontmatter="metadata:\n  version: 1\nallowed-tools:\n  - read\n",
    )

    report = audit_skill(skill)

    assert report.conformance is ConformanceStatus.FAIL
    assert [finding.code for finding in report.findings].count("SKILL007") == 2


def test_empty_body_is_warning_only(tmp_path: Path) -> None:
    report = audit_skill(_write_skill(tmp_path / "empty", body=""))

    assert report.conformance is ConformanceStatus.PASS
    assert report.exit_code == 0
    assert any(finding.code == "SKILL010" for finding in report.findings)


def test_symlink_discovery_name_is_preserved(tmp_path: Path) -> None:
    target = _write_skill(tmp_path / "storage", name="portable")
    link = tmp_path / "portable"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    report = audit_skill(link, target_ids=["claude-code"])

    assert report.conformance is ConformanceStatus.PASS
    assert not any(finding.code == "SKILL005" for finding in report.findings)


def test_skill_locator_rejects_wrong_paths(tmp_path: Path) -> None:
    wrong_file = tmp_path / "README.md"
    wrong_file.write_text("text", encoding="utf-8")
    with pytest.raises(AuditInputError, match="Expected SKILL.md"):
        _locate_skill(wrong_file)

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(AuditInputError, match="No SKILL.md"):
        _locate_skill(directory)

    with pytest.raises(AuditInputError, match="does not exist"):
        _locate_skill(tmp_path / "missing")


def test_parser_rejects_frontmatter_shape_errors(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    cases = [
        ("Body only.\n", "must start"),
        ("---\nname: skill\n", "no closing delimiter"),
        ("---\n[broken\n---\nBody\n", "invalid YAML"),
        ("---\n- name\n---\nBody\n", "must be a YAML mapping"),
        ("---\n1: value\n---\nBody\n", "keys must be strings"),
    ]
    for content, match in cases:
        skill.write_text(content, encoding="utf-8")
        with pytest.raises(AuditInputError, match=match):
            _parse_skill_file(skill)


def test_missing_and_invalid_required_fields_are_reported(tmp_path: Path) -> None:
    skill = tmp_path / "missing-fields"
    skill.mkdir()
    skill.joinpath("SKILL.md").write_text("---\nlicense: MIT\n---\nBody.\n", encoding="utf-8")

    report = audit_skill(skill)
    assert [finding.code for finding in report.findings].count("SKILL002") == 2

    invalid = tmp_path / "invalid-values"
    invalid.mkdir()
    invalid.joinpath("SKILL.md").write_text(
        "---\nname: []\ndescription: []\n---\nBody.\n",
        encoding="utf-8",
    )
    report = audit_skill(invalid)
    assert {finding.code for finding in report.findings} >= {"SKILL003", "SKILL006"}


def test_optional_field_and_length_validation(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path / "invalid-optionals",
        description="x" * 1025,
        extra_frontmatter=(f"compatibility: {'x' * 501}\nlicense: []\nmetadata:\n  key: value\n"),
    )

    report = audit_skill(skill)

    assert report.conformance is ConformanceStatus.FAIL
    assert any(finding.code == "SKILL006" for finding in report.findings)
    assert [finding.code for finding in report.findings].count("SKILL007") == 2


def test_large_skill_file_produces_recommendation(tmp_path: Path) -> None:
    body = "\n".join(f"Line {index}" for index in range(510))
    report = audit_skill(_write_skill(tmp_path / "large", body=body))

    assert report.conformance is ConformanceStatus.PASS
    assert any(finding.code == "SKILL009" for finding in report.findings)


def test_skill_file_path_is_accepted(tmp_path: Path) -> None:
    root = _write_skill(tmp_path / "portable")
    skill_file = root / "SKILL.md"

    report = audit_skill(skill_file, target_ids=["claude-code"])

    assert report.artifact_path == root
    assert report.static_portability is CompatibilityGrade.PORTABLE


def test_target_assessment_handles_unsupported_and_known_unknown_fields(tmp_path: Path) -> None:
    root = _write_skill(tmp_path / "custom", extra_frontmatter="custom-field: true\n")
    frontmatter, body, _line_count = _parse_skill_file(root / "SKILL.md")
    standard = load_skill_standard()["frontmatter"]
    standard_fields = set(standard["required"]) | set(standard["optional"])

    unsupported_data = load_profiles()[0].data.copy()
    unsupported_data["skills"] = dict(unsupported_data["skills"])
    unsupported_data["skills"]["supported"] = False
    unsupported_data["id"] = "unsupported-target"
    unsupported_data["label"] = "Unsupported target"

    ignored_data = load_profiles()[0].data.copy()
    ignored_data["skills"] = dict(ignored_data["skills"])
    ignored_data["skills"]["frontmatter"] = dict(ignored_data["skills"]["frontmatter"])
    ignored_data["skills"]["frontmatter"]["unknown_field_behavior"] = "ignored"
    ignored_data["id"] = "ignored-target"
    ignored_data["label"] = "Ignored target"

    assessments, _findings, _has_adapter = _assess_targets(
        profiles=(TargetProfile(unsupported_data), TargetProfile(ignored_data)),
        frontmatter=frontmatter,
        standard_fields=standard_fields,
        body=body,
        skill_root=root,
        skill_file=root / "SKILL.md",
    )

    assert assessments[0].status is TargetStatus.INCOMPATIBLE
    assert assessments[1].status is TargetStatus.DEGRADED


def test_skill_portability_grade_covers_all_states() -> None:
    def assessment(status: TargetStatus) -> TargetAssessment:
        return TargetAssessment("target", "Target", "2026-08-16", status)

    conformance = [assessment(TargetStatus.SUPPORTED)]
    assert (
        _skill_portability_grade(conformance, has_conformance_error=True, has_adapter=False)
        is CompatibilityGrade.INCOMPATIBLE
    )
    assert conformance[0].status is TargetStatus.INCOMPATIBLE
    assert (
        _skill_portability_grade(
            [assessment(TargetStatus.INCOMPATIBLE)],
            has_conformance_error=False,
            has_adapter=False,
        )
        is CompatibilityGrade.INCOMPATIBLE
    )
    assert (
        _skill_portability_grade(
            [assessment(TargetStatus.DEGRADED)],
            has_conformance_error=False,
            has_adapter=False,
        )
        is CompatibilityGrade.DEGRADED
    )
    assert (
        _skill_portability_grade(
            [assessment(TargetStatus.UNKNOWN)],
            has_conformance_error=False,
            has_adapter=False,
        )
        is CompatibilityGrade.UNVERIFIED
    )
    assert (
        _skill_portability_grade(
            [assessment(TargetStatus.SUPPORTED)],
            has_conformance_error=False,
            has_adapter=True,
        )
        is CompatibilityGrade.PORTABLE_WITH_ADAPTERS
    )


def test_finding_serialization_omits_optional_fields() -> None:
    assert Finding("TEST", Severity.INFO, "message").to_dict() == {
        "code": "TEST",
        "severity": "info",
        "message": "message",
        "targets": [],
    }
