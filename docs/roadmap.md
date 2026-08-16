# Implementation Roadmap

The project is implemented in evidence-preserving slices. A later phase may
extend an earlier phase, but it must not collapse static support into runtime
proof.

## Phase 0 — Foundation

- Define the compatibility and evidence model.
- Add surface-specific capability profiles.
- Validate Agent Skills against the open specification.
- Compare declared MCP requirements with target profiles.
- Provide text and JSON reports.
- Package a portable `verify-compatibility` skill.

## Phase 1 — Skill analysis depth

- Validate referenced files, scripts, and path portability.
- Model execution dependencies and sandbox assumptions.
- Detect proprietary invocation and permission semantics more precisely.
- Add installation-path assessment and generated installation instructions.

## Phase 2 — MCP implementation inspection

- Add adapters for common Python, TypeScript, and protocol SDK layouts.
- Derive candidate capabilities from server code and configuration.
- Compare implementation evidence with the explicit requirements manifest.
- Report disagreement without silently choosing either declaration.

## Phase 3 — Runtime verification harness

- Define signed, version-bound runtime evidence records.
- Exercise discovery, invocation, and referenced-file loading for skills.
- Exercise MCP initialization, negotiation, listing, representative calls,
  authentication, timeout, cancellation, and failure behavior.
- Keep runtime results separate for each product surface.

## Phase 4 — Profile maintenance

- Detect changes in official documentation and schemas.
- Generate reviewable profile-update proposals.
- Enforce freshness policies without rewriting claims automatically.
- Preserve source snapshots or hashes where licensing and access permit.

## Phase 5 — Explicit remediation

- Add opt-in, transactional fixes for safe conformance defects.
- Generate host adapters without modifying the portable core.
- Require a diff review and rerun all affected checks before acceptance.
- Never remove a required capability merely to achieve a passing grade.

## Phase 6 — Distribution and integration

- Publish the Python package and portable Agent Skill.
- Provide reusable GitHub Actions and pre-commit integration.
- Define stable report schemas and compatibility-policy configuration.
- Add targets beyond Claude Code, GitHub Copilot, and Codex through the same
  evidence model.
