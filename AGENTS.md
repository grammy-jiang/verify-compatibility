# Repository Instructions

## Mission

Build a deterministic, evidence-backed compatibility verifier for Agent Skills
and MCP servers across Claude Code, GitHub Copilot, Codex, and future agent
hosts.

## Non-negotiable rules

1. Do not make a vendor-level compatibility claim when support differs by
   surface. Identify the product, surface, and relevant version or review date.
2. Use official product documentation, protocol specifications, or executable
   runtime evidence as the primary source for capability claims.
3. Record every profile claim with a source and `reviewed_at` date. When support
   is not documented, use `unknown`; do not infer support from a similar client.
4. Keep format conformance, static portability, and runtime verification
   separate in code and reports.
5. Do not report `portable` behavior from static parsing alone. Runtime parity
   requires target-specific evidence.
6. Treat host-specific features as explicit adapters. Do not silently place
   proprietary fields in the portable core.
7. Do not mutate a reviewed artifact unless the user explicitly requests a fix.
   Future fixes must be transactional, reviewable, and reversible.
8. Never place secrets, access tokens, or expanded credential values in reports,
   fixtures, profiles, logs, or tests.

## Engineering workflow

- Develop substantive changes on a feature branch and through a pull request.
- Add or update tests for every rule and profile-model change.
- Run `pytest`, `ruff check .`, `ruff format --check .`, and `mypy` before merge.
- Keep runtime dependencies small and justified.
- Prefer dataclasses and standard-library mechanisms over framework-heavy
  abstractions.
- Preserve stable finding codes once released; consumers may use them in CI.
- Update documentation and profile evidence in the same change as behavior.

## Capability profiles

Profiles are source data, not prose notes. A profile must:

- identify one concrete surface;
- state when it was reviewed;
- cite official sources;
- distinguish `supported`, `unsupported`, `deprecated`, `partial`, and
  `unknown`;
- avoid copying capability assumptions from another surface;
- remain machine-readable and schema-valid.

A documentation change does not automatically prove runtime behavior. Where
practical, add a runtime probe and retain its evidence separately.

## Agent Skill rules

The canonical skill must remain valid against the open Agent Skills
specification. Keep proprietary frontmatter out of its portable `SKILL.md`.
Host-specific metadata belongs in optional adapter files or generated
installation output.

## MCP rules

Static MCP analysis must be explicit about its evidence boundary. Repository
code inspection and a declared requirements manifest are not equivalent to an
MCP initialization handshake. Runtime verification should eventually exercise
initialization, capability negotiation, listing, representative invocation,
and failure behavior on each target.
