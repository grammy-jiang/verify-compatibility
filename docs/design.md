# Verify Compatibility: System Design

## 1. Purpose

Verify Compatibility determines whether an Agent Skill or MCP server can be
used with equivalent intended capability across selected AI-agent surfaces.
The initial targets are Claude Code, GitHub Copilot, and Codex.

The project exists because open formats do not produce identical client
behavior by themselves. Products can accept the same file while differing in:

- discovery and installation locations;
- frontmatter extensions and invocation controls;
- tool naming and permission semantics;
- MCP transports and authentication;
- MCP tools, resources, prompts, instructions, and extensions;
- execution environment and sandbox policy;
- context loading and runtime limits.

A useful verifier must expose these differences rather than hide them behind a
single “compatible” flag.

## 2. Goals

The system will:

1. validate open-format conformance;
2. extract the capabilities an artifact requires or provides;
3. compare those requirements against versioned target-surface profiles;
4. identify portability gaps and host-specific behavior;
5. recommend the smallest portable-core or adapter change;
6. collect target-specific runtime evidence;
7. produce stable human-readable and machine-readable reports;
8. support review-only and explicitly requested remediation workflows;
9. detect profile drift as product documentation changes.

## 3. Non-goals

The system will not:

- claim identical model judgment or output quality;
- treat a successfully parsed file as behavioral parity;
- infer one product surface from another surface by the same vendor;
- silently rewrite artifacts during an audit;
- embed credentials in profiles or reports;
- make unsupported capability claims to produce a cleaner matrix;
- replace each vendor's own conformance, security, or publication checks.

## 4. Terminology

### 4.1 Artifact

An artifact is the item being reviewed:

- an Agent Skill directory containing `SKILL.md`; or
- an MCP server implementation, package, endpoint, or requirements manifest.

### 4.2 Target

A target is a concrete product surface, not merely a vendor. Examples:

- Claude Code;
- GitHub Copilot CLI;
- GitHub Copilot cloud agent;
- Codex local host shared by Codex CLI, the IDE extension, and the ChatGPT
  desktop app.

A target profile may later be version-bounded when behavior changes materially.

### 4.3 Portable core

The portable core is the portion of an artifact whose syntax and intended
behavior are supported across every selected target.

### 4.4 Adapter

An adapter is explicit host-specific packaging or configuration that preserves
the portable core while enabling behavior available only on one target.
Examples include an OpenAI `agents/openai.yaml` file, a generated installation
path, or target-specific MCP configuration.

### 4.5 Evidence

Evidence supports a capability claim. Recognized evidence classes are:

- protocol specification;
- official product documentation;
- official schema or source code;
- executable runtime probe;
- controlled manual observation.

Runtime evidence is stronger for behavioral claims. Documentation remains the
source of truth for declared product support and configuration contracts.

## 5. Compatibility dimensions

The verifier reports four dimensions independently.

### 5.1 Format conformance

Questions include:

- Does `SKILL.md` satisfy the Agent Skills specification?
- Does a requirements manifest satisfy this project's schema?
- Are required fields present and correctly typed?
- Does the skill name match its directory?

Conformance is deterministic and does not establish runtime compatibility.

### 5.2 Discovery and installation

Questions include:

- Does the target scan the supplied repository or user path?
- Does it support symlinked skills?
- Does it require a plugin or separate registration?
- Is the MCP configuration scope available on that surface?

The canonical artifact should not be duplicated merely to satisfy different
paths. Installation adapters should place or link it appropriately.

### 5.3 Capability compatibility

Questions include:

- Are frontmatter fields accepted and semantically equivalent?
- Are required tool permissions expressible?
- Are MCP features, transports, and authentication methods supported?
- Are proprietary variables, dynamic commands, hooks, or subagent execution
  required?

This dimension can identify documented incompatibility without running a host.

### 5.4 Behavioral compatibility

Questions include:

- Is the skill discovered?
- Is implicit and explicit invocation correct?
- Are scripts and references resolved from the expected directory?
- Does MCP initialization negotiate the intended protocol and capabilities?
- Can representative operations run with equivalent permissions and results?
- Are failure, timeout, cancellation, and authentication behaviors acceptable?

Behavioral compatibility requires runtime evidence. It cannot be inferred from
static analysis alone.

## 6. Assessment model

### 6.1 Conformance status

- `pass` — the governing static format checks pass;
- `fail` — at least one mandatory format check fails;
- `unknown` — the artifact cannot be statically characterized;
- `not-applicable` — no conformance format applies to this stage.

### 6.2 Target status

- `supported` — documented static requirements are supported;
- `degraded` — the artifact loads or can be adapted, but behavior is lost;
- `incompatible` — a required capability is documented as unsupported;
- `unknown` — available evidence does not establish support;
- `not-applicable` — the capability does not apply to the target.

### 6.3 Static portability grade

- `portable` — no static gap was found across selected targets;
- `portable-with-adapters` — explicit host adapters are needed but preserve the
  common behavior;
- `degraded` — at least one selected target loses intended behavior;
- `incompatible` — at least one selected target cannot meet a requirement;
- `unverified` — static evidence is insufficient to grade the artifact.

### 6.4 Runtime verification status

- `verified` — required runtime scenarios pass on every selected target at the
  exact artifact revision;
- `partial` — some targets or scenarios have evidence;
- `failed` — at least one required runtime scenario fails;
- `unverified` — no sufficient runtime evidence exists.

The initial implementation reports runtime status as `unverified`. A future
runtime harness will promote it only from retained evidence.

## 7. Architecture

### 7.1 Command-line interface

The CLI is the deterministic entry point. The Agent Skill orchestrates it rather
than reimplementing its rules in prose.

Initial commands:

```text
verify-compatibility audit <path>
verify-compatibility profiles
```

Planned commands:

```text
verify-compatibility probe <path-or-endpoint>
verify-compatibility fix <path>
verify-compatibility refresh-profiles
verify-compatibility verify-evidence <report>
```

### 7.2 Artifact inspectors

Each artifact type has a separate inspector:

- `skill_audit.py` parses and validates Agent Skills;
- `mcp_audit.py` compares declared MCP requirements;
- future runtime modules will inspect MCP initialization and target behavior.

The inspectors emit a shared report model and stable finding codes.

### 7.3 Standards registry

Standards data contains format constraints that are independent of a target.
The initial registry contains the Agent Skills frontmatter contract.

Standards data is reviewed and versioned. Code can enforce constraints, but the
registry records where those constraints came from and when they were checked.

### 7.4 Target profiles

Each profile describes one target surface and contains:

- identity and scope;
- review date;
- official sources;
- Agent Skill discovery and frontmatter behavior;
- MCP feature, transport, and authentication support;
- explicit `unknown` entries where documentation is silent.

Profiles are not generated from marketing summaries. They are maintained as
reviewed source data.

### 7.5 Rule engine

The first implementation uses explicit Python rules because the rule set is
small and correctness is easier to review. A future declarative rule layer may
be introduced only when it reduces duplication without obscuring behavior.

Rules emit:

- a stable code;
- severity;
- affected path;
- affected targets;
- concise explanation;
- remediation guidance where available.

### 7.6 Reporting

Reports support text and JSON. JSON is the integration contract for CI and
future agent orchestration.

A report includes:

- artifact kind and path;
- selected target profiles and review dates;
- conformance status;
- static portability grade;
- runtime verification status;
- per-target status and reasons;
- ordered findings;
- evidence boundary.

### 7.7 Agent Skill

The canonical `verify-compatibility` skill uses only open Agent Skills
frontmatter. It tells an AI agent to:

1. identify the artifact and requested target surfaces;
2. run the deterministic audit;
3. inspect findings and evidence freshness;
4. consult official documentation only when a profile is stale or unknown;
5. propose or implement the smallest portable-core or adapter change;
6. rerun the audit and, when available, runtime probes;
7. report residual uncertainty explicitly.

The skill does not give itself broad pre-approved tools in portable frontmatter,
because tool names and permission semantics differ across hosts.

## 8. Agent Skill analysis

### 8.1 Open-format checks

The static auditor checks:

- `SKILL.md` presence;
- YAML frontmatter structure;
- required `name` and `description`;
- field types and length constraints;
- skill-name syntax and directory match;
- standard optional-field constraints;
- non-standard frontmatter;
- recommended size limits.

### 8.2 Host-extension checks

The auditor compares fields with every target profile. Examples include:

- Claude Code invocation controls;
- Claude Code forked-context fields;
- host-specific path variables;
- host-specific argument substitution;
- `allowed-tools` dialect and permission semantics;
- optional OpenAI adapter metadata.

A proprietary extension is not automatically an error. It becomes an explicit
adapter or a degradation finding, depending on whether common behavior is
preserved.

### 8.3 Script and reference checks

Later phases will add:

- referenced-file existence;
- executable and interpreter availability;
- dependency declarations;
- platform assumptions;
- network and filesystem requirements;
- safe script invocation;
- target-specific sandbox constraints.

## 9. MCP analysis

### 9.1 Static boundary

An MCP repository does not have one universally adopted static manifest that
proves what the running server negotiates. Source-code inference is unreliable
across languages and SDKs.

The initial implementation therefore accepts an explicit requirements manifest.
It compares required features and offered transport/authentication alternatives
with target profiles. The report labels this evidence as static declaration,
not runtime verification.

### 9.2 Runtime handshake

A later runtime harness should:

1. start or connect to the server without exposing credentials;
2. send MCP initialization with an explicit protocol version;
3. record negotiated version and capabilities;
4. exercise listing for tools, resources, and prompts where declared;
5. invoke safe representative operations;
6. exercise authentication, timeout, cancellation, and error behavior;
7. repeat through each target client or an official automation interface;
8. bind evidence to the artifact commit and target version.

### 9.3 Capability comparison

The initial MCP vocabulary includes:

Features:

- `tools`;
- `resources`;
- `prompts`;
- `server-instructions`;
- `elicitation`.

Transports:

- `stdio`;
- `streamable-http`;
- `sse`;
- `websocket`.

Authentication:

- `none`;
- `headers`;
- `bearer`;
- `oauth`;
- `oidc`.

The vocabulary will expand with protocol extensions and product-specific
configuration only when supported by evidence.

## 10. Profile lifecycle

### 10.1 Freshness

Every profile has `reviewed_at`. A future policy will define a freshness window
and force a refresh when:

- a target version exceeds the profile's tested range;
- official documentation changes;
- a required capability remains `unknown`;
- a scheduled documentation-drift job detects changed source content.

### 10.2 Updating a profile

A profile change must:

1. identify the exact surface;
2. use official primary sources;
3. update `reviewed_at`;
4. change only claims supported by the source;
5. add or update tests for changed behavior;
6. note whether runtime evidence exists;
7. avoid promoting `unknown` from inference alone.

### 10.3 Source snapshots

The repository initially stores source URLs and review dates, not copied vendor
documentation. Future drift detection may retain hashes or compact extracted
facts, subject to copyright and source terms.

## 11. Remediation strategy

Remediation follows this priority:

1. remove accidental non-portable behavior;
2. express the behavior through the open portable core;
3. isolate unavoidable host behavior in an adapter;
4. provide an explicit degraded mode when parity is impossible;
5. fail clearly when a required capability is unsupported.

A future `fix` command must:

- require explicit invocation;
- show a proposed plan or diff;
- preserve comments and unrelated formatting where practical;
- create backups or use version control;
- rerun the audit;
- never modify credentials;
- never claim runtime verification from a successful rewrite.

## 12. Security model

Compatibility tooling processes executable scripts and MCP servers, which are
untrusted inputs.

Static audit must not execute artifact code. Runtime probes must use:

- an isolated working directory;
- explicit network and filesystem policy;
- read-only or harmless test operations by default;
- strict timeouts and output limits;
- redaction of credential-like values;
- a target-specific approval model;
- retained command and environment metadata without secret values.

MCP write tools require separate opt-in scenarios. A profile stating that a
client supports write tools does not authorize this verifier to invoke them.

## 13. Initial delivery plan

### Phase 0 — foundation

- shared report model;
- target profile schema and initial profiles;
- Agent Skills conformance and portability audit;
- MCP requirements-manifest comparison;
- text and JSON CLI;
- portable Agent Skill;
- tests and CI.

### Phase 1 — deeper static analysis

- script and reference validation;
- dependency and platform analysis;
- target installation adapters;
- richer MCP repository inspection;
- profile schema validation and freshness policy.

### Phase 2 — runtime evidence

- generic MCP protocol probe;
- skill discovery and invocation probes where automatable;
- exact target-version capture;
- evidence storage and replay;
- behavioral scenario definitions.

### Phase 3 — remediation

- dry-run adapter generation;
- transactional `--fix`;
- target configuration generation;
- compatibility regression gates for CI.

### Phase 4 — profile maintenance

- official-documentation drift detection;
- scheduled review issues;
- source fact extraction with human review;
- expanded target and version coverage.

## 14. Design decisions

### 14.1 One repository, separate analyzers

Agent Skills and MCP share target profiles, evidence, reporting, and CI. They
remain separate analyzers because their conformance and runtime models differ.

### 14.2 Python core, skill orchestration

The deterministic Python core owns validation and comparison. The Agent Skill
owns task orchestration, source review, remediation judgment, and user-facing
explanation. This avoids encoding correctness only in an LLM prompt.

### 14.3 Explicit uncertainty

`unknown` and `unverified` are first-class outcomes. They are not failures of the
project; they prevent unsupported claims.

### 14.4 Portable core over exact file identity

The objective is equivalent capability, not necessarily byte-identical host
packaging. A canonical core plus generated adapters is preferable to weakening
the artifact or pretending proprietary extensions are portable.
