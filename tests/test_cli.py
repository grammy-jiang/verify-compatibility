from __future__ import annotations

import json
from pathlib import Path

import pytest

from verify_compatibility.cli import main


def _write_minimal_skill(root: Path, *, body: str = "Run the check.") -> Path:
    root.mkdir()
    root.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {root.name}\n"
        "description: Run a check. Use when checking behavior.\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return root


def test_profiles_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profiles", "--format", "json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert {item["id"] for item in data} == {
        "claude-code",
        "codex-local",
        "github-copilot-cli",
        "github-copilot-cloud-agent",
    }


def test_audit_json_auto_detects_skill(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_minimal_skill(tmp_path / "portable")

    assert main(["audit", str(skill), "--format", "json"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["artifact"]["kind"] == "agent-skill"
    assert report["static_portability"] == "portable"
    assert report["runtime_verification"] == "unverified"


def test_fail_on_warning_is_opt_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_minimal_skill(tmp_path / "empty", body="")

    assert main(["audit", str(skill)]) == 0
    capsys.readouterr()
    assert main(["audit", str(skill), "--fail-on", "warning"]) == 1


def test_unknown_kind_returns_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", str(tmp_path)]) == 2
    captured = capsys.readouterr()

    assert "Cannot infer artifact kind" in captured.err


def test_manifest_is_rejected_for_skill(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_minimal_skill(tmp_path / "portable")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    assert main(["audit", str(skill), "--manifest", str(manifest)]) == 2
    captured = capsys.readouterr()
    assert "valid only for an MCP audit" in captured.err


def test_skill_path_points_to_bundled_skill(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skill-path"]) == 0
    captured = capsys.readouterr()

    path = Path(captured.out.strip())
    assert path.name == "verify-compatibility"
    assert path.joinpath("SKILL.md").is_file()


def test_profiles_text_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profiles"]) == 0
    captured = capsys.readouterr()
    assert "claude-code\t2026-08-16\tClaude Code" in captured.out

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_audit_json_auto_detects_mcp_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "requirements.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": "mcp-server",
                "name": "server",
                "capabilities": {
                    "features": ["tools"],
                    "transports": ["stdio"],
                    "authentication": ["none"],
                },
            }
        ),
        encoding="utf-8",
    )

    assert main(["audit", str(manifest), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["artifact"]["kind"] == "mcp-server"


def test_explicit_kind_reports_invalid_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wrong = tmp_path / "README.md"
    wrong.write_text("text", encoding="utf-8")

    assert main(["audit", str(wrong), "--kind", "skill"]) == 2
    assert "Expected SKILL.md" in capsys.readouterr().err


def test_missing_path_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["audit", str(tmp_path / "missing")]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_broken_pipe_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import verify_compatibility.cli as cli

    def broken(_args: object) -> int:
        raise BrokenPipeError

    monkeypatch.setattr(cli, "_handle_profiles", broken)
    assert cli.main(["profiles"]) == 0


def test_main_module_imports() -> None:
    import verify_compatibility.__main__ as entrypoint

    assert entrypoint.main is main
