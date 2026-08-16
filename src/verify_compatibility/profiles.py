"""Load and validate bundled standards and target capability profiles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any, cast
from urllib.parse import urlparse

_CAPABILITY_STATUSES = {
    "supported",
    "unsupported",
    "deprecated",
    "partial",
    "unknown",
    "not-applicable",
}
_PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProfileError(ValueError):
    """A bundled profile is malformed or unsupported."""


@dataclass(frozen=True)
class TargetProfile:
    """One concrete AI-agent surface."""

    data: dict[str, Any]

    @property
    def id(self) -> str:
        return cast(str, self.data["id"])

    @property
    def label(self) -> str:
        return cast(str, self.data["label"])

    @property
    def reviewed_at(self) -> str:
        return cast(str, self.data["reviewed_at"])

    @property
    def surface(self) -> str:
        return cast(str, self.data["surface"])

    @property
    def sources(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.data["sources"])

    @property
    def skills(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.data["skills"])

    @property
    def mcp(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.data["mcp"])

    def summary(self) -> dict[str, Any]:
        """Return stable profile metadata without duplicating the capability matrix."""

        return {
            "id": self.id,
            "label": self.label,
            "vendor": self.data["vendor"],
            "surface": self.surface,
            "reviewed_at": self.reviewed_at,
            "sources": [source["url"] for source in self.sources],
        }


def _load_json_resource(group: str, name: str) -> dict[str, Any]:
    resource = files("verify_compatibility").joinpath("data", group, name)
    try:
        raw = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        raise ProfileError(f"Bundled {group} resource cannot be read: {name}: {exc}") from exc

    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Bundled {group} resource is invalid JSON: {name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProfileError(f"Bundled {group} resource must be a JSON object: {name}")
    return cast(dict[str, Any], parsed)


def load_skill_standard() -> dict[str, Any]:
    """Load the reviewed Agent Skills format constraints."""

    data = _load_json_resource("standards", "agent-skills.json")
    _validate_skill_standard(data, source="agent-skills.json")
    return data


def load_profiles() -> tuple[TargetProfile, ...]:
    """Load every bundled target profile in deterministic order."""

    directory = files("verify_compatibility").joinpath("data", "profiles")
    result: list[TargetProfile] = []
    seen: set[str] = set()
    for resource in sorted(directory.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".json"):
            continue
        try:
            parsed: object = json.loads(resource.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProfileError(f"Cannot load profile {resource.name}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ProfileError(f"Profile must be a JSON object: {resource.name}")
        data = cast(dict[str, Any], parsed)
        _validate_target_profile(data, source=resource.name)
        target_id = cast(str, data["id"])
        if target_id in seen:
            raise ProfileError(f"Duplicate target profile id: {target_id}")
        seen.add(target_id)
        result.append(TargetProfile(data))
    if not result:
        raise ProfileError("No bundled target profiles were found")
    return tuple(result)


def select_profiles(target_ids: list[str] | None) -> tuple[TargetProfile, ...]:
    """Return all profiles or the requested subset in request order."""

    profiles = load_profiles()
    if not target_ids:
        return profiles

    duplicates = sorted({item for item in target_ids if target_ids.count(item) > 1})
    if duplicates:
        raise ProfileError(f"Target(s) selected more than once: {', '.join(duplicates)}")

    by_id = {profile.id: profile for profile in profiles}
    unknown = [target_id for target_id in target_ids if target_id not in by_id]
    if unknown:
        available = ", ".join(sorted(by_id))
        names = ", ".join(unknown)
        raise ProfileError(f"Unknown target(s): {names}. Available targets: {available}")
    return tuple(by_id[target_id] for target_id in target_ids)


def _validate_skill_standard(data: dict[str, Any], *, source: str) -> None:
    allowed = {"schema_version", "id", "label", "reviewed_at", "sources", "frontmatter"}
    _reject_unknown_keys(data, allowed, context=source)
    _require_schema_version(data, source=source)
    if data.get("id") != "agent-skills":
        raise ProfileError("Agent Skills standard has an unexpected id")
    _require_non_empty_string(data, "label", context=source)
    _validate_review_date(data.get("reviewed_at"), context=source)
    _validate_sources(data.get("sources"), context=source)

    frontmatter = data.get("frontmatter")
    if not isinstance(frontmatter, dict):
        raise ProfileError(f"{source} requires object 'frontmatter'")
    _reject_unknown_keys(
        frontmatter,
        {"required", "optional", "constraints"},
        context=f"{source}.frontmatter",
    )
    required = _require_unique_string_list(frontmatter.get("required"), context=f"{source}.frontmatter.required")
    optional = _require_unique_string_list(frontmatter.get("optional"), context=f"{source}.frontmatter.optional")
    overlap = sorted(set(required) & set(optional))
    if overlap:
        raise ProfileError(f"Required and optional fields overlap: {', '.join(overlap)}")
    if set(required) != {"name", "description"}:
        raise ProfileError("Agent Skills required fields must be name and description")

    constraints = frontmatter.get("constraints")
    if not isinstance(constraints, dict):
        raise ProfileError(f"{source}.frontmatter requires object 'constraints'")
    required_constraints = {
        "name_max_length",
        "description_max_length",
        "compatibility_max_length",
        "recommended_file_max_lines",
    }
    _reject_unknown_keys(
        constraints,
        required_constraints,
        context=f"{source}.frontmatter.constraints",
    )
    missing = sorted(required_constraints - set(constraints))
    if missing:
        raise ProfileError(f"Missing standard constraint(s): {', '.join(missing)}")
    for name, value in constraints.items():
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ProfileError(f"Constraint {name!r} must be a positive integer")


def _require_schema_version(data: dict[str, Any], *, source: str) -> None:
    version = data.get("schema_version")
    if version != 1:
        raise ProfileError(f"Unsupported schema_version in {source}: {version!r}")


def _validate_target_profile(data: dict[str, Any], *, source: str) -> None:
    allowed = {
        "schema_version",
        "id",
        "label",
        "vendor",
        "surface",
        "reviewed_at",
        "sources",
        "skills",
        "mcp",
    }
    _reject_unknown_keys(data, allowed, context=source)
    _require_schema_version(data, source=source)
    for key in ("id", "label", "vendor", "surface"):
        _require_non_empty_string(data, key, context=source)
    target_id = cast(str, data["id"])
    if not _PROFILE_ID_PATTERN.fullmatch(target_id):
        raise ProfileError(f"Profile {source} has invalid id {target_id!r}")
    _validate_review_date(data.get("reviewed_at"), context=source)
    _validate_sources(data.get("sources"), context=source)
    _validate_skills(data.get("skills"), context=f"{source}.skills")
    _validate_mcp(data.get("mcp"), context=f"{source}.mcp")


def _validate_sources(value: object, *, context: str) -> None:
    if not isinstance(value, list) or not value:
        raise ProfileError(f"{context} requires at least one source")
    seen_ids: set[str] = set()
    for index, source in enumerate(value):
        item_context = f"{context}.sources[{index}]"
        if not isinstance(source, dict):
            raise ProfileError(f"{item_context} must be an object")
        _reject_unknown_keys(source, {"id", "title", "url", "covers"}, context=item_context)
        for key in ("id", "title", "url"):
            _require_non_empty_string(source, key, context=item_context)
        source_id = cast(str, source["id"])
        if source_id in seen_ids:
            raise ProfileError(f"Duplicate source id {source_id!r} in {context}")
        seen_ids.add(source_id)
        url = cast(str, source["url"])
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProfileError(f"{item_context}.url must be an absolute HTTPS URL")
        _require_unique_string_list(source.get("covers"), context=f"{item_context}.covers")


def _validate_skills(value: object, *, context: str) -> None:
    if not isinstance(value, dict):
        raise ProfileError(f"{context} must be an object")
    allowed = {
        "supported",
        "discovery",
        "frontmatter",
        "features",
        "host_markers",
        "adapter_files",
    }
    _reject_unknown_keys(value, allowed, context=context)
    if not isinstance(value.get("supported"), bool):
        raise ProfileError(f"{context}.supported must be a boolean")

    discovery = value.get("discovery")
    if not isinstance(discovery, dict):
        raise ProfileError(f"{context}.discovery must be an object")
    _reject_unknown_keys(discovery, {"project", "user"}, context=f"{context}.discovery")
    for scope in ("project", "user"):
        paths = _require_unique_string_list(discovery.get(scope), context=f"{context}.discovery.{scope}")
        for path in paths:
            if not path.strip():
                raise ProfileError(f"{context}.discovery.{scope} contains an empty path")

    frontmatter = value.get("frontmatter")
    if not isinstance(frontmatter, dict):
        raise ProfileError(f"{context}.frontmatter must be an object")
    _reject_unknown_keys(
        frontmatter,
        {"additional_fields", "unknown_field_behavior", "allowed_tools"},
        context=f"{context}.frontmatter",
    )
    _require_unique_string_list(
        frontmatter.get("additional_fields"),
        context=f"{context}.frontmatter.additional_fields",
    )
    behavior = frontmatter.get("unknown_field_behavior")
    if behavior not in {"rejected", "ignored", "undocumented"}:
        raise ProfileError(f"{context}.frontmatter.unknown_field_behavior has invalid value {behavior!r}")
    allowed_tools = frontmatter.get("allowed_tools")
    if not isinstance(allowed_tools, dict):
        raise ProfileError(f"{context}.frontmatter.allowed_tools must be an object")
    _reject_unknown_keys(
        allowed_tools,
        {"status", "dialect"},
        context=f"{context}.frontmatter.allowed_tools",
    )
    _validate_capability_status(allowed_tools.get("status"), context=f"{context}.frontmatter.allowed_tools.status")
    _require_non_empty_string(allowed_tools, "dialect", context=f"{context}.frontmatter.allowed_tools")

    _validate_status_map(value.get("features"), context=f"{context}.features")

    markers = value.get("host_markers")
    if not isinstance(markers, list):
        raise ProfileError(f"{context}.host_markers must be an array")
    seen_literals: set[str] = set()
    for index, marker in enumerate(markers):
        marker_context = f"{context}.host_markers[{index}]"
        if not isinstance(marker, dict):
            raise ProfileError(f"{marker_context} must be an object")
        _reject_unknown_keys(marker, {"literal", "feature"}, context=marker_context)
        for key in ("literal", "feature"):
            _require_non_empty_string(marker, key, context=marker_context)
        literal = cast(str, marker["literal"])
        if literal in seen_literals:
            raise ProfileError(f"Duplicate host marker {literal!r} in {context}")
        seen_literals.add(literal)

    adapters = _require_unique_string_list(value.get("adapter_files"), context=f"{context}.adapter_files")
    for adapter in adapters:
        path = PurePosixPath(adapter)
        if path.is_absolute() or ".." in path.parts or adapter.endswith("/"):
            raise ProfileError(f"{context}.adapter_files contains unsafe path {adapter!r}")


def _validate_mcp(value: object, *, context: str) -> None:
    if not isinstance(value, dict):
        raise ProfileError(f"{context} must be an object")
    categories = {
        "features": {"tools", "resources", "prompts", "server-instructions", "elicitation"},
        "transports": {"stdio", "streamable-http", "sse", "websocket"},
        "authentication": {"none", "headers", "bearer", "oauth", "oidc"},
    }
    _reject_unknown_keys(value, set(categories), context=context)
    missing_categories = sorted(set(categories) - set(value))
    if missing_categories:
        raise ProfileError(f"{context} is missing categories: {', '.join(missing_categories)}")
    for category, expected_keys in categories.items():
        mapping = value.get(category)
        _validate_status_map(mapping, context=f"{context}.{category}")
        assert isinstance(mapping, dict)
        missing = sorted(expected_keys - set(mapping))
        extra = sorted(set(mapping) - expected_keys)
        if missing:
            raise ProfileError(f"{context}.{category} is missing: {', '.join(missing)}")
        if extra:
            raise ProfileError(f"{context}.{category} has unknown entries: {', '.join(extra)}")


def _validate_status_map(value: object, *, context: str) -> None:
    if not isinstance(value, dict):
        raise ProfileError(f"{context} must be an object")
    for name, status in value.items():
        if not isinstance(name, str) or not name:
            raise ProfileError(f"{context} keys must be non-empty strings")
        _validate_capability_status(status, context=f"{context}.{name}")


def _validate_capability_status(value: object, *, context: str) -> None:
    if not isinstance(value, str) or value not in _CAPABILITY_STATUSES:
        raise ProfileError(f"{context} has invalid capability status {value!r}")


def _validate_review_date(value: object, *, context: str) -> None:
    if not isinstance(value, str):
        raise ProfileError(f"{context}.reviewed_at must be an ISO date string")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ProfileError(f"{context}.reviewed_at is not a valid ISO date: {value!r}") from exc


def _require_non_empty_string(data: dict[str, Any], key: str, *, context: str) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{context} requires non-empty string {key!r}")


def _require_unique_string_list(value: object, *, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProfileError(f"{context} must be an array of strings")
    result = cast(list[str], value)
    if any(not item.strip() for item in result):
        raise ProfileError(f"{context} contains an empty string")
    duplicates = sorted({item for item in result if result.count(item) > 1})
    if duplicates:
        raise ProfileError(f"{context} contains duplicates: {', '.join(duplicates)}")
    return result


def _reject_unknown_keys(data: dict[str, Any], allowed: set[str], *, context: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProfileError(f"{context} has unknown field(s): {', '.join(unknown)}")
