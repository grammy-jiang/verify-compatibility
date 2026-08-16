# Verify Compatibility

Verify Compatibility audits Agent Skills and Model Context Protocol (MCP)
servers across Claude Code, GitHub Copilot, and Codex.

The project is intentionally evidence-driven. It does not treat “the file
loads” as proof of compatibility, and it does not collapse distinct product
surfaces into a single vendor-level answer.

## Current scope

The bootstrap implementation provides:

- deterministic Agent Skills frontmatter and structure validation;
- static detection of host-specific skill features;
- manifest-driven MCP capability comparison;
- versioned, surface-specific capability profiles;
- machine-readable and human-readable reports;
- a portable `verify-compatibility` Agent Skill;
- explicit separation between static assessment and runtime verification.

Runtime probes, automatic adapter generation, profile refresh automation, and
safe `--fix` support are planned but are not yet implemented.

## Compatibility model

Each report keeps these questions separate:

1. **Conformance** — does the artifact satisfy its governing format or
   requirements schema?
2. **Static portability** — can every selected target represent the requested
   features, transports, authentication methods, and host extensions?
3. **Runtime verification** — has equivalent behavior actually been exercised
   on every target surface?

A clean static result is not reported as runtime-verified. This prevents a
successful parse from being mistaken for behavioral parity.

Static portability grades are:

- `portable` — no static portability gap was found;
- `portable-with-adapters` — a common core exists and explicit host adapters are
  present or required;
- `degraded` — at least one target loses behavior;
- `incompatible` — at least one required capability is unsupported;
- `unverified` — the available evidence is insufficient.

## Target surfaces

The initial profiles are deliberately surface-specific:

- Claude Code;
- GitHub Copilot CLI;
- GitHub Copilot cloud agent and Copilot code review;
- Codex local host, covering the shared configuration used by Codex CLI, the
  Codex IDE extension, and the ChatGPT desktop app.

Additional surfaces can be added without changing the report model.

## Quick start

Install the development environment:

```bash
python -m pip install -e '.[dev]'
```

Audit an Agent Skill:

```bash
verify-compatibility audit path/to/my-skill
```

Emit JSON:

```bash
verify-compatibility audit path/to/my-skill --format json
```

List bundled target profiles:

```bash
verify-compatibility profiles
```

## MCP requirements manifest

There is no portable static MCP-server manifest that fully describes what a
server exposes. Until runtime introspection is implemented, the MCP auditor uses
an explicit requirements manifest at `compatibility/requirements.json`:

```json
{
  "schema_version": 1,
  "artifact": "mcp-server",
  "name": "example-server",
  "capabilities": {
    "features": ["tools"],
    "transports": ["stdio", "streamable-http"],
    "authentication": ["none", "oauth"]
  }
}
```

Feature entries are capabilities whose behavior must be preserved. Transport
and authentication entries are alternatives offered by the server; a target
needs at least one supported option from each non-empty list.

Run the audit with automatic manifest discovery:

```bash
verify-compatibility audit path/to/server --kind mcp
```

Or pass a manifest explicitly:

```bash
verify-compatibility audit path/to/server \
  --kind mcp \
  --manifest path/to/requirements.json
```

The manifest is a declaration, not runtime evidence. A passing result still
shows runtime verification as `unverified`.

## Repository layout

```text
src/verify_compatibility/
├── data/
│   ├── profiles/       # Surface-specific capability profiles
│   └── standards/      # Open-format constraints
├── skill/              # Canonical portable Agent Skill
├── cli.py              # Command-line entry point
├── mcp_audit.py        # MCP manifest comparison
├── models.py           # Report and finding model
├── profiles.py         # Profile loading and validation
├── reporting.py        # Text and JSON output
└── skill_audit.py      # Agent Skill static analysis
```

See [the design document](docs/design.md) for the governing architecture,
[the profile schema](docs/profile-schema.md) for evidence requirements, and
[the implementation roadmap](docs/roadmap.md) for planned delivery slices.

## Development principles

- Use official product documentation and protocol specifications as primary
  evidence.
- Pin every capability claim to a product surface and review date.
- Prefer `unknown` over an inferred claim.
- Treat host-specific extensions as adapters, not portable core behavior.
- Never claim behavioral parity without runtime evidence.
- Keep automatic changes opt-in, reviewable, and transactional.

## Status

This repository is at the foundation stage. Its public interfaces may change
before the first stable release.
