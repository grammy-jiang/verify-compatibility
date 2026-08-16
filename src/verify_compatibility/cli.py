"""Command-line interface for compatibility audits."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Literal, cast

from . import __version__
from .errors import AuditInputError
from .mcp_audit import audit_mcp
from .models import AuditReport, Severity
from .profiles import ProfileError, load_profiles
from .reporting import render_json, render_text
from .skill_audit import audit_skill

ArtifactKind = Literal["skill", "mcp"]


def build_parser() -> argparse.ArgumentParser:
    """Build the public argument parser."""

    parser = argparse.ArgumentParser(
        prog="verify-compatibility",
        description="Audit Agent Skills and MCP servers across reviewed agent profiles.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit",
        help="Audit one Agent Skill or MCP server.",
        description=("Run deterministic static checks. A passing result is not runtime verification."),
    )
    audit_parser.add_argument("path", type=Path, help="Artifact directory, SKILL.md, or manifest.")
    audit_parser.add_argument(
        "--kind",
        choices=("auto", "skill", "mcp"),
        default="auto",
        help="Artifact kind. Auto-detection is conservative (default: auto).",
    )
    audit_parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        metavar="TARGET",
        help="Target profile ID. Repeat to select multiple targets; default is all profiles.",
    )
    audit_parser.add_argument(
        "--manifest",
        type=Path,
        help="MCP requirements manifest. Valid only for an MCP audit.",
    )
    audit_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report format (default: text).",
    )
    audit_parser.add_argument(
        "--fail-on",
        choices=("error", "warning"),
        default="error",
        help="Minimum finding severity that causes exit status 1 (default: error).",
    )
    audit_parser.set_defaults(handler=_handle_audit)

    profiles_parser = subparsers.add_parser(
        "profiles",
        help="List bundled target profiles and their review dates.",
    )
    profiles_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    profiles_parser.set_defaults(handler=_handle_profiles)

    skill_path_parser = subparsers.add_parser(
        "skill-path",
        help="Print the bundled verify-compatibility Agent Skill directory.",
    )
    skill_path_parser.set_defaults(handler=_handle_skill_path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command and return a process exit status."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = cast(Callable[[argparse.Namespace], int], args.handler)
    try:
        return handler(args)
    except (AuditInputError, ProfileError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


def _handle_audit(args: argparse.Namespace) -> int:
    path = cast(Path, args.path)
    requested_kind = cast(str, args.kind)
    manifest = cast(Path | None, args.manifest)
    targets = cast(list[str] | None, args.targets)
    kind = _detect_kind(path) if requested_kind == "auto" else cast(ArtifactKind, requested_kind)

    if kind == "skill":
        if manifest is not None:
            raise AuditInputError("--manifest is valid only for an MCP audit")
        report = audit_skill(path, target_ids=targets)
    else:
        report = audit_mcp(path, manifest_path=manifest, target_ids=targets)

    output = render_json(report) if args.format == "json" else render_text(report)
    print(output)
    return _exit_code(report, fail_on=cast(str, args.fail_on))


def _handle_skill_path(_args: argparse.Namespace) -> int:
    resource = files("verify_compatibility").joinpath("skill").joinpath("verify-compatibility")
    if not resource.is_dir():
        raise AuditInputError("The bundled verify-compatibility Agent Skill is missing")
    print(resource)
    return 0


def _handle_profiles(args: argparse.Namespace) -> int:
    profiles = load_profiles()
    if args.format == "json":
        print(json.dumps([profile.summary() for profile in profiles], indent=2, sort_keys=True))
        return 0

    for profile in profiles:
        print(f"{profile.id}\t{profile.reviewed_at}\t{profile.label}")
    return 0


def _detect_kind(path: Path) -> ArtifactKind:
    absolute = path.expanduser().absolute()
    if absolute.is_file() and absolute.name == "SKILL.md":
        return "skill"
    if absolute.is_dir() and (absolute / "SKILL.md").is_file():
        return "skill"
    if absolute.is_file() and absolute.suffix == ".json":
        return "mcp"
    if absolute.is_dir() and (absolute / "compatibility" / "requirements.json").is_file():
        return "mcp"
    if not absolute.exists():
        raise AuditInputError(f"Artifact path does not exist: {absolute}")
    raise AuditInputError(
        "Cannot infer artifact kind. Pass --kind skill for an Agent Skill or --kind mcp for an MCP server."
    )


def _exit_code(report: AuditReport, *, fail_on: str) -> int:
    if report.exit_code:
        return report.exit_code
    if fail_on == "warning" and any(
        finding.severity in {Severity.ERROR, Severity.WARNING} for finding in report.findings
    ):
        return 1
    return 0
