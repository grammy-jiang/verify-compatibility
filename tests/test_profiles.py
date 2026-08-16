from __future__ import annotations

import copy
from importlib.resources import files
from typing import Any

import pytest

from verify_compatibility.profiles import (
    ProfileError,
    TargetProfile,
    _reject_unknown_keys,
    _require_non_empty_string,
    _require_unique_string_list,
    _validate_capability_status,
    _validate_mcp,
    _validate_review_date,
    _validate_skill_standard,
    _validate_skills,
    _validate_sources,
    _validate_status_map,
    load_profiles,
    load_skill_standard,
    select_profiles,
)


def _profile_data(profile_id: str = "claude-code") -> dict[str, Any]:
    profile = next(item for item in load_profiles() if item.id == profile_id)
    return copy.deepcopy(profile.data)


def _standard_data() -> dict[str, Any]:
    return copy.deepcopy(load_skill_standard())


def test_skill_standard_has_reviewed_open_fields() -> None:
    standard = load_skill_standard()

    assert standard["id"] == "agent-skills"
    assert standard["reviewed_at"] == "2026-08-16"
    assert standard["frontmatter"]["required"] == ["name", "description"]
    assert set(standard["frontmatter"]["optional"]) == {
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
    }


def test_bundled_profiles_are_surface_specific_and_sourced() -> None:
    profiles = load_profiles()

    assert [profile.id for profile in profiles] == [
        "claude-code",
        "codex-local",
        "github-copilot-cli",
        "github-copilot-cloud-agent",
    ]
    assert len({profile.surface for profile in profiles}) == len(profiles)
    for profile in profiles:
        assert profile.reviewed_at == "2026-08-16"
        assert profile.sources
        assert all(source["url"].startswith("https://") for source in profile.sources)


def test_profile_summary_is_stable_and_compact() -> None:
    profile = load_profiles()[0]

    assert profile.summary() == {
        "id": profile.id,
        "label": profile.label,
        "vendor": profile.data["vendor"],
        "surface": profile.surface,
        "reviewed_at": profile.reviewed_at,
        "sources": [source["url"] for source in profile.sources],
    }
    assert isinstance(profile.skills, dict)
    assert isinstance(profile.mcp, dict)


def test_select_profiles_preserves_requested_order() -> None:
    selected = select_profiles(["github-copilot-cli", "claude-code"])

    assert [profile.id for profile in selected] == [
        "github-copilot-cli",
        "claude-code",
    ]
    assert select_profiles(None) == load_profiles()


def test_select_profiles_rejects_unknown_and_duplicates() -> None:
    with pytest.raises(ProfileError, match="Unknown target"):
        select_profiles(["not-a-target"])
    with pytest.raises(ProfileError, match="selected more than once"):
        select_profiles(["claude-code", "claude-code"])


def test_bundled_skill_is_packaged_under_matching_directory() -> None:
    skill = files("verify_compatibility").joinpath("skill", "verify-compatibility")

    assert skill.is_dir()
    assert skill.joinpath("SKILL.md").is_file()


def test_common_profile_value_validators_reject_bad_values() -> None:
    with pytest.raises(ProfileError, match="non-empty string"):
        _require_non_empty_string({}, "name", context="test")
    with pytest.raises(ProfileError, match="array of strings"):
        _require_unique_string_list("bad", context="test")
    with pytest.raises(ProfileError, match="empty string"):
        _require_unique_string_list([""], context="test")
    with pytest.raises(ProfileError, match="duplicates"):
        _require_unique_string_list(["x", "x"], context="test")
    with pytest.raises(ProfileError, match="ISO date string"):
        _validate_review_date(1, context="test")
    with pytest.raises(ProfileError, match="not a valid ISO date"):
        _validate_review_date("not-a-date", context="test")
    with pytest.raises(ProfileError, match="invalid capability status"):
        _validate_capability_status("maybe", context="test")
    with pytest.raises(ProfileError, match="must be an object"):
        _validate_status_map([], context="test")
    with pytest.raises(ProfileError, match="non-empty strings"):
        _validate_status_map({"": "supported"}, context="test")
    with pytest.raises(ProfileError, match="unknown field"):
        _reject_unknown_keys({"unexpected": True}, set(), context="test")


def test_sources_validation_rejects_invalid_entries() -> None:
    with pytest.raises(ProfileError, match="at least one source"):
        _validate_sources([], context="test")
    with pytest.raises(ProfileError, match="must be an object"):
        _validate_sources(["bad"], context="test")

    bad_url = {
        "id": "source",
        "title": "Source",
        "url": "http://example.com",
        "covers": ["skills"],
    }
    with pytest.raises(ProfileError, match="absolute HTTPS"):
        _validate_sources([bad_url], context="test")

    duplicate = {
        "id": "source",
        "title": "Source",
        "url": "https://example.com",
        "covers": ["skills"],
    }
    with pytest.raises(ProfileError, match="Duplicate source id"):
        _validate_sources([duplicate, copy.deepcopy(duplicate)], context="test")


def test_standard_validation_rejects_contract_drift() -> None:
    data = _standard_data()
    data["id"] = "other"
    with pytest.raises(ProfileError, match="unexpected id"):
        _validate_skill_standard(data, source="standard")

    data = _standard_data()
    data["frontmatter"] = []
    with pytest.raises(ProfileError, match="requires object 'frontmatter'"):
        _validate_skill_standard(data, source="standard")

    data = _standard_data()
    data["frontmatter"]["optional"].append("name")
    with pytest.raises(ProfileError, match="overlap"):
        _validate_skill_standard(data, source="standard")

    data = _standard_data()
    data["frontmatter"]["required"] = ["name"]
    with pytest.raises(ProfileError, match="must be name and description"):
        _validate_skill_standard(data, source="standard")

    data = _standard_data()
    data["frontmatter"]["constraints"] = []
    with pytest.raises(ProfileError, match="requires object 'constraints'"):
        _validate_skill_standard(data, source="standard")

    data = _standard_data()
    del data["frontmatter"]["constraints"]["name_max_length"]
    with pytest.raises(ProfileError, match="Missing standard constraint"):
        _validate_skill_standard(data, source="standard")

    data = _standard_data()
    data["frontmatter"]["constraints"]["name_max_length"] = 0
    with pytest.raises(ProfileError, match="positive integer"):
        _validate_skill_standard(data, source="standard")


def test_skill_profile_validation_rejects_invalid_structures() -> None:
    data = _profile_data()["skills"]
    with pytest.raises(ProfileError, match="must be an object"):
        _validate_skills([], context="skills")

    bad = copy.deepcopy(data)
    bad["supported"] = "yes"
    with pytest.raises(ProfileError, match="must be a boolean"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    bad["discovery"] = []
    with pytest.raises(ProfileError, match="discovery must be an object"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    bad["frontmatter"] = []
    with pytest.raises(ProfileError, match="frontmatter must be an object"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    bad["frontmatter"]["unknown_field_behavior"] = "guess"
    with pytest.raises(ProfileError, match="invalid value"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    bad["frontmatter"]["allowed_tools"] = []
    with pytest.raises(ProfileError, match="allowed_tools must be an object"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    bad["host_markers"] = ["bad"]
    with pytest.raises(ProfileError, match=r"host_markers\[0\] must be an object"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    marker = {"literal": "$X", "feature": "x"}
    bad["host_markers"] = [marker, copy.deepcopy(marker)]
    with pytest.raises(ProfileError, match="Duplicate host marker"):
        _validate_skills(bad, context="skills")

    bad = copy.deepcopy(data)
    bad["adapter_files"] = ["../unsafe.yaml"]
    with pytest.raises(ProfileError, match="unsafe path"):
        _validate_skills(bad, context="skills")


def test_mcp_profile_validation_rejects_missing_and_unknown_capabilities() -> None:
    data = _profile_data()["mcp"]
    with pytest.raises(ProfileError, match="must be an object"):
        _validate_mcp([], context="mcp")

    bad = copy.deepcopy(data)
    del bad["features"]
    with pytest.raises(ProfileError, match="missing categories"):
        _validate_mcp(bad, context="mcp")

    bad = copy.deepcopy(data)
    del bad["features"]["tools"]
    with pytest.raises(ProfileError, match="features is missing"):
        _validate_mcp(bad, context="mcp")

    bad = copy.deepcopy(data)
    bad["features"]["invented"] = "supported"
    with pytest.raises(ProfileError, match="unknown entries"):
        _validate_mcp(bad, context="mcp")


def test_target_profile_wrapper_accepts_valid_data() -> None:
    profile = TargetProfile(_profile_data())
    assert profile.id == "claude-code"
