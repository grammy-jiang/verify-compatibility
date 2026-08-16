# Capability Profile Schema

## Purpose

A capability profile records reviewed facts about one concrete AI-agent
surface. Profiles are the static evidence base used by the compatibility
engine.

They are intentionally narrow. `github-copilot` is not a valid profile identity
when Copilot CLI and Copilot cloud agent have different MCP contracts.

## Storage

Bundled profiles live under:

```text
src/verify_compatibility/data/profiles/
```

The current representation is JSON so the runtime can load it without an
additional profile-parser dependency. The package still uses PyYAML to parse
Agent Skills frontmatter.

## Top-level shape

```json
{
  "schema_version": 1,
  "id": "target-id",
  "label": "Human-readable target",
  "vendor": "Vendor",
  "surface": "Concrete surface",
  "reviewed_at": "2026-08-16",
  "sources": [],
  "skills": {},
  "mcp": {}
}
```

### `schema_version`

Integer version of this repository's profile format. A reader must reject a
newer unsupported schema rather than silently ignore fields.

### `id`

Stable lowercase identifier used by CLI `--target` options and JSON reports.
Changing an ID is a breaking change.

### `label`

Human-readable target name.

### `vendor`

The organization responsible for the target.

### `surface`

A concrete runtime or distribution surface. Examples include `local-cli` and
`cloud-agent`.

### `reviewed_at`

ISO date on which the profile claims were checked against the listed official
sources.

### `sources`

A non-empty array of official sources:

```json
{
  "id": "stable-source-id",
  "title": "Official documentation title",
  "url": "https://example.invalid/official-docs",
  "covers": ["skills", "mcp.transports"]
}
```

`id` is a stable local identifier. `covers` gives reviewers a compact trace
from capability groups to sources. It does not replace more granular evidence
when a future schema adds it.

## Agent Skills section

```json
{
  "supported": true,
  "discovery": {
    "project": [".agents/skills"],
    "user": ["~/.agents/skills"]
  },
  "frontmatter": {
    "additional_fields": [],
    "unknown_field_behavior": "undocumented",
    "allowed_tools": {
      "status": "unknown",
      "dialect": "agent-skills-experimental"
    }
  },
  "features": {
    "explicit-invocation": "supported",
    "implicit-invocation": "supported"
  },
  "host_markers": [],
  "adapter_files": []
}
```

### `additional_fields`

Fields accepted beyond the open Agent Skills standard. Their presence is
host-specific even when valid on this target.

### `unknown_field_behavior`

Current values:

- `rejected` — official evidence says unknown fields fail;
- `ignored` — official evidence says unknown fields are ignored;
- `undocumented` — behavior is not established.

The verifier must not translate `undocumented` into `ignored`.

### `allowed_tools`

Records both the target's support status for the open `allowed-tools` field and
the target-specific tool-name or permission dialect. Equal field support does
not imply equivalent tool expressions or approval behavior.

### `features`

Map of named skill behavior to a capability status.

### `host_markers`

Literal body markers whose meaning is documented only on this target:

```json
{
  "literal": "${CLAUDE_SKILL_DIR}",
  "feature": "skill-directory-variable"
}
```

Literal matching is intentionally conservative. More advanced parsing can be
added when it has deterministic semantics.

### `adapter_files`

Relative paths for target-specific metadata files that can augment the portable
skill without changing its canonical `SKILL.md`. The presence of an adapter is
reported separately; it does not make proprietary fields part of the portable
core.

## MCP section

```json
{
  "features": {
    "tools": "supported",
    "resources": "unknown",
    "prompts": "unknown",
    "server-instructions": "supported"
  },
  "transports": {
    "stdio": "supported",
    "streamable-http": "supported",
    "sse": "unsupported",
    "websocket": "unsupported"
  },
  "authentication": {
    "none": "supported",
    "headers": "supported",
    "bearer": "supported",
    "oauth": "supported",
    "oidc": "unknown"
  }
}
```

## Capability statuses

Every capability value uses one of:

- `supported` — officially documented as supported;
- `unsupported` — officially documented as unavailable;
- `deprecated` — accepted but discouraged and expected to be removed;
- `partial` — only a documented subset or constrained form is supported;
- `unknown` — official evidence is silent or ambiguous;
- `not-applicable` — the capability does not apply to the surface.

A deprecated capability counts as usable for basic intersection checks but
produces a finding. Partial support requires a more specific rule or remains
unverified.

## MCP requirements manifest

The optional server-side declaration is separate from target profiles and lives
in the artifact repository:

```text
compatibility/requirements.json
```

Shape:

```json
{
  "schema_version": 1,
  "artifact": "mcp-server",
  "name": "server-name",
  "capabilities": {
    "features": ["tools"],
    "transports": ["stdio"],
    "authentication": ["none"]
  }
}
```

Semantics:

- every listed feature is required to preserve the server's intended behavior;
- transports are alternatives offered by the server;
- authentication methods are alternatives offered by the server;
- a target needs at least one supported transport and one supported
  authentication method when those lists are non-empty;
- the declaration does not prove what the running server negotiates.

Unknown vocabulary is rejected. Expanding the vocabulary requires a profile and
rule change with tests.

## Review checklist

Before merging a profile update, verify:

1. The profile names one surface.
2. `reviewed_at` reflects the actual review date.
3. Every source is official and relevant.
4. No claim was copied from another surface without direct evidence.
5. Silence is represented as `unknown`.
6. Changed claims have tests.
7. Runtime evidence, when available, is not confused with documentation.
8. No credentials or private URLs are present.
