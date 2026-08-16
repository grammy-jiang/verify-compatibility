---
name: verify-compatibility
description: Audit an Agent Skill or MCP server for portable use across Claude Code, GitHub Copilot, and Codex. Use when reviewing cross-agent compatibility, investigating a host-specific failure, refreshing capability evidence, or adapting an artifact without overstating runtime parity.
compatibility: Requires Python 3.10+ and the verify-compatibility CLI installed in the current environment.
metadata:
  author: grammy-jiang
  version: "0.1.0a0"
---

# Verify Compatibility

Use deterministic analysis first. Treat official documentation and executable
runtime evidence as the sources of truth; do not substitute model memory for a
capability claim.

## Inputs

Establish these inputs from the request and repository:

- artifact path;
- artifact kind: Agent Skill or MCP server;
- concrete target surfaces;
- whether the user requested review only or also requested changes;
- any required behavior that must remain equivalent across targets.

Do not reduce `GitHub Copilot` to one target when the CLI and cloud agent have
different contracts.

## Procedure

1. Inspect the artifact and identify its canonical portable core, existing host
   adapters, installation assumptions, scripts, dependencies, transports, and
   authentication requirements.
2. Run the verifier. Prefer machine-readable output for further analysis:

   ```bash
   verify-compatibility audit ARTIFACT_PATH --format json
   ```

   Add repeated `--target TARGET_ID` options when the request limits the target
   set. For an MCP server without an automatically discovered manifest, use:

   ```bash
   verify-compatibility audit ARTIFACT_PATH \
     --kind mcp \
     --manifest PATH_TO_REQUIREMENTS_JSON \
     --format json
   ```

3. Keep the report dimensions separate:
   - format or declaration conformance;
   - static portability;
   - runtime verification.
4. Review every target result and finding. A static `portable` grade means no
   gap was found in the reviewed profiles; it does not prove equivalent runtime
   behavior.
5. When a required capability is `unknown`, stale, or disputed, consult the
   current official documentation for that exact product surface. Update the
   relevant profile, source record, review date, and tests together. Prefer
   `unknown` when the official source is silent.
6. When changes are requested, preserve a standards-based portable core and
   isolate host-specific behavior in explicit adapters. Apply the smallest
   change that preserves intended behavior. Do not weaken security controls or
   silently remove required capability.
7. Rerun the audit after every change. Run the repository's own tests and
   target-specific runtime probes when they exist.
8. Report the evidence boundary honestly. Do not claim runtime parity until the
   artifact has been exercised on every selected target surface.

## Output

Provide:

- artifact and selected target surfaces;
- conformance, static portability, and runtime-verification status;
- target-by-target differences;
- prioritized findings with concrete remediation;
- changes made, when changes were requested;
- commands and tests executed;
- unresolved unknowns and the exact additional evidence required.

Read [the compatibility model](references/compatibility-model.md) before
interpreting grades. For MCP declarations, read
[the requirements manifest reference](references/mcp-requirements-manifest.md).
For capability updates, read
[the profile maintenance procedure](references/profile-maintenance.md).
