# CodeFreedom 0.1.9 Design Spec

> **Date:** 2026-06-13
> **Status:** Approved for implementation
> **Target version:** 0.1.9 (current: 0.1.8)
> **Delivery:** Single PR
> **Execution:** All implementation by agent

---

## 1. Objective

Ship a more understandable, safer-to-change, and operationally clearer version of CodeFreedom without changing its core workflows. Focus on three outcomes:

1. Make the product easier to understand by documenting shipped capabilities that are hard to discover.
2. Make the codebase safer to change by adding tests around failure-prone runtime seams before refactoring.
3. Make the architecture deeper and easier to maintain by reducing duplicated orchestration logic.

---

## 2. Scope

### 2.1 Items included (31 total)

| ID | Workstream | Items | Risk |
|----|-----------|-------|------|
| WS1 | Documentation & discoverability | 6 | Low |
| WS2 | Reliability & test coverage | 5 | Low |
| WS3 | Config resolution consolidation | 3 | High |
| WS4 | Tool lifecycle consolidation | 3 | Medium |
| WS5 | Launcher seam clarification | 4 | High |
| WS6 | Agent dispatch & CLI validation | 4 | Medium |
| WS7 | Diagnostics & support flow | 2 | Low-Medium |
| H1 | ARCHITECTURE.md inventory update | 1 | Low |
| H2 | CI/CD workflow updates | 1 | Low |
| H3 | Docs pipeline verification | 1 | Low |
| H4 | Version bump + CHANGELOG | 1 | Low |

### 2.2 Deferred items

#### 3.4 — Remove duplicate config assembly paths

**Why deferred:** Only 4 config modules exist today. Removing old paths before enough callers validate the new seam risks breaking less-visible code paths. The consolidation (3.2, 3.3) will establish the new seam and migrate callers, but old paths will remain as thin wrappers.

**When to pick up:** 0.2.0, after the new config seam has been exercised by multiple release cycles and caller diversity has increased.

#### 4.3 — Standardize tool interface shape

**Why deferred:** Only 4 tools exist (chrome, web, github, web_bridge). Designing a shared protocol for this few tools is premature abstraction — the tools have different enough lifecycles that a shared interface would either be too generic to be useful or force awkward fitting.

**When to pick up:** 0.2.0 or later, when the number of tools grows to 6+ and real inconsistency pain emerges.

### 2.3 Removed items

#### 7.3 — "Keep the support path simple"

This is a principle, not a deliverable. It has no files, no tests, no code changes. It is already embedded as a constraint in items 7.1 and 7.2 and will be stated in those PR descriptions.

### 2.4 Non-goals

- Adding brand-new providers or agents
- Redesigning the proxy model from scratch
- Redesigning sandbox execution from scratch
- Changing the config format away from YAML
- Introducing a generic plugin framework
- Broad cleanup of unrelated code

### 2.5 Constraints preserved

- YAML remains native config format
- Current env-chain behavior intact
- Canonical env loading through `get_env()`
- Profile inheritance stable
- Deterministic Docker/container naming
- `cf doctor` as primary diagnostics path
- Existing agent aliases and workflows
- Command names and compatibility aliases

---

## 3. Execution Order

Single PR with logical commit groups. Work is sequenced to avoid breaking things mid-cycle.

```
Phase 1: Safety net (WS2)
  Tests FIRST, before any refactoring

Phase 2: Documentation (WS1)
  Low risk, no code changes; can interleave with Phase 1

Phase 3: Architecture refactors (WS3, WS4, WS5)
  Config consolidation (WS3)
  Tool lifecycle (WS4)
  Launcher seam (WS5)
  Each refactor validated against Phase 1 tests

Phase 4: CLI cleanup (WS6)
  Benefits from Phase 3 seam clarity

Phase 5: Diagnostics (WS7)
  Benefits from WS1 docs existing

Phase 6: Housekeeping (H1-H4)
  ARCHITECTURE.md, CI/CD, docs verification
  Version bump + CHANGELOG last
```

**Rationale:**
- Tests before refactors (core planning principle)
- Docs are independent, low risk
- High-risk refactors happen behind test safety net
- WS6 benefits from WS3/WS5 clarity
- WS7 benefits from WS1 docs
- Housekeeping after all code stabilizes

---

## 4. Detailed Item Breakdown

### Phase 1 — WS2: Reliability & Test Coverage

#### 2.1 — Launcher tests

**Targets:** `src/codefreedom/launcher.py`, `src/codefreedom/sandbox/launcher.py`
**Create:** `tests/test_launcher.py`, `tests/test_sandbox_launcher.py`
**Cover:**
- Startup path
- Status checks
- Stop/cleanup behavior
- MCP config generation/merge
- Docker failure cases

**Approach:** Mock Docker client calls and subprocess behavior. Focus on behavioral tests, not implementation coupling.

#### 2.2 — Agent dispatch tests

**Target:** `src/codefreedom/cli/run/agent.py`
**Create:** `tests/test_agent_dispatch.py`
**Cover:**
- Agent lookup by name
- Alias handling
- Invalid agent names
- Argument routing
- Failure when agent modules unavailable

#### 2.3 — Agent entrypoint tests

**Targets:** `cli/claude.py`, `cli/mimo.py`, `cli/opencode.py`
**Expand:** `tests/test_mimo.py`
**Create:** `tests/test_claude.py`, `tests/test_opencode.py`
**Cover:**
- Sandbox vs local selection
- Profile loading behavior
- Shared flag handling
- Launcher handoff behavior
- Expected failure behavior

#### 2.4 — Failure-path tests

**Across:** launcher, dispatch, entrypoints, docker client
**Cover:**
- Docker unavailable
- Malformed YAML/config files
- Permission errors under `~/.codefreedom`
- Signal forwarding behavior
- Subprocess failures and non-zero exits

**Approach:** Use existing conftest fixtures and monkeypatch patterns. Prefer deterministic failure simulation over environment-dependent tests.

#### 2.5 — Coverage reporting

**Changes:**
- Add `pytest-cov` to dev dependencies in `pyproject.toml`
- Add `[tool.coverage.run]` config targeting `src/codefreedom/`
- Add `[tool.coverage.report]` config
- Document coverage command

**Approach:** Reporting-only, no thresholds enforced. Goal is visibility, not gatekeeping.

---

### Phase 2 — WS1: Documentation & Discoverability

#### 1.1 — Document WebSearch interception

**Create:** `docs/proxy/websearch-interception.md`
**Content:**
- User problem: Claude Code WebSearch often unavailable/unreliable
- Solution flow: Claude Code → proxy callback → web-bridge → MCP web_search → Camoufox
- Runtime pieces: proxy, LiteLLM callback, docker/web-bridge/, web tool
- Prerequisites, limitations, troubleshooting links

**Cross-link from:** `docs/features/proxy.md`, `README.md`

#### 1.2 — Document MiMoCode as first-class agent

**Create:** `docs/features/mimo-code.md`
**Content:**
- Command surface: `cf mimo` / `cf mc`
- Config generation behavior
- Proxy integration model
- Sandbox support
- Profile behavior
- Shared runtime relationship with CodeFreedom layers

**Cross-link from:** `README.md`, `docs/index.md`, `docs/getting-started/first-run.md`

#### 1.3 — Clarify recipe sourcing

**Update:** `docs/recipes/index.md`, `recipes/README.md`
**Content:**
- What a recipe is
- Bundled recipes in this repo
- External/store-backed recipes
- How to list and choose (`cf setup init --list`)
- Example commands

**Ensure:** Both docs tell the same story. No claims about bundled recipes that don't exist.

#### 1.4 — Add troubleshooting guide

**Create:** `docs/guides/troubleshooting.md`
**Content per issue:**
- Symptom
- Likely cause
- What to run/check
- When `cf doctor` helps

**Issues covered:**
- Docker daemon unavailable
- Port conflicts
- Invalid/missing API keys
- Proxy startup failures
- Permission issues in `~/.codefreedom`
- Image/cache issues

#### 1.5 — Add FAQ

**Create:** `docs/guides/faq.md`
**Content:**
- Local vs sandbox mode
- When proxy is needed
- How profiles work
- Switching providers/models
- What tools are available
- Which agents are supported
- How browser tools fit in

**Approach:** Concise answers that link to deeper docs. Not duplicate documentation.

#### 1.6 — Fix navigation and landing flow

**Update:** `mkdocs.yml`, `docs/index.md`, `docs/getting-started/index.md`, `docs/getting-started/first-run.md`
**Changes:**
- Add `Guides` section in mkdocs.yml nav
- Add new pages in correct order
- Update homepage to reflect multiple agents and WebSearch
- Route users from getting-started into recipes and troubleshooting

---

### Phase 3 — Architecture Refactors

#### WS3: Config Resolution Consolidation

##### 3.1 — Audit current config responsibilities

**Read:** `env_loader.py`, `core/interpolate.py`, `core/profiles.py`, `core/config.py`
**Output:** Responsibility map documenting:
- File/env loading ownership
- Interpolation ownership
- Defaults handling
- Override handling
- Profile inheritance
- Path resolution
- Overlaps between modules

##### 3.2 — Define canonical config seam

**Design:** One internal API in `core/config.py` for "give me resolved config for this workflow"
**Preserve:**
- Env precedence
- Interpolation rules
- Profile inheritance behavior

**API should answer:**
- What inputs it takes
- How env and profile data combine
- When interpolation is applied
- What output the caller receives

**Avoid:** Over-abstracting into a too-generic manager. Design around real caller needs.

##### 3.3 — Migrate callers incrementally

**Order:**
1. Agent entrypoints (claude.py, mimo.py, opencode.py)
2. Proxy-related config consumers
3. Tool config loaders

**Approach:**
- Move one caller group at a time
- Keep tests green after each migration
- Keep old paths as thin wrappers delegating to new seam
- Remove redundant access patterns only after migration succeeds

#### WS4: Tool Lifecycle Consolidation

##### 4.1 — Make registry the single orchestration owner

**Move from:** `cli/run/tools.py`
**Move to:** `tools/registry.py`
**Registry should own:**
- Acquire/release rules
- Session tracking
- Lifecycle bookkeeping
- MCP endpoint coordination
- First-user/last-user behavior

##### 4.2 — Thin CLI tool layer

**`cli/run/tools.py` should only:**
- Parse command intent
- Invoke registry operations
- Report results to user

**Remove:** Duplicated lifecycle helpers. Keep output formatting local.

##### 4.4 — Expand lifecycle tests

**Add to:** `tests/test_tool_registry.py`
**Cover:**
- First-one-starts / last-one-stops
- Stale session cleanup
- Already-running tool adoption
- MCP endpoint reporting

#### WS5: Launcher Seam Clarification

##### 5.1 — Map launcher responsibilities

**Read:** `launcher.py`, `sandbox/launcher.py` line by line
**Map:**
- Runtime launch ownership
- Docker execution ownership
- MCP config handling
- Status/stop behavior
- Binary lookup
- Helper wrappers
- Overlaps between files

##### 5.2 — Decide canonical launcher owner

**Choose one module** based on:
- Current responsibilities
- Testability
- Locality
- Minimized duplication

##### 5.3 — Convert non-owner to wrapper

- Move logic into chosen owner
- Keep only necessary wrapper behavior in secondary module
- Update imports gradually
- Preserve compatibility

##### 5.4 — Regression protection + ARCHITECTURE.md

- Update launcher tests to cover chosen seam
- Update `ARCHITECTURE.md` launcher section

---

### Phase 4 — WS6: Agent Dispatch & CLI Validation

#### 6.1 — Explicit agent registry

**Create:** Minimal registry structure (in `cli/run/agent.py` or new `cli/agents.py`)
**Include per agent:**
- Canonical name
- Aliases
- Description
- Entrypoint reference

**Keep minimal:** No metadata beyond what dispatch actually uses today.

#### 6.2 — Centralize shared CLI validation

**Extract shared rules:**
- Sandbox flag compatibility
- GPU mode compatibility
- Profile-related validation
- Shared argument constraints

**Create:** Shared validation helper
**Keep:** Agent-specific behavior in agent modules

#### 6.3 — Preserve command compatibility

- Add compatibility tests before cleanup
- Preserve alias resolution behavior
- Keep help text accurate

#### 6.4 — Dispatch and validation tests

**Create:** `tests/test_agent_registry.py`
**Cover:**
- Alias resolution
- Invalid agent handling
- Parser wiring
- Validation failures

---

### Phase 5 — WS7: Diagnostics & Support Flow

#### 7.1 — Expand cf doctor

**Target:** `cli/manage/doctor.py`
**Add checks for:**
- Port conflicts
- Missing Docker images / daemon availability
- Agent prerequisites
- Proxy/sandbox permissions
- Recipe/store confusion points

**Avoid:** Noisy or unactionable checks. Only checks that produce actionable output.

#### 7.2 — Align troubleshooting docs with cf doctor

- Add `cf doctor` references into troubleshooting sections
- Add links from setup/feature docs to troubleshooting
- Ensure doctor output wording matches doc terminology

---

### Phase 6 — Housekeeping

#### H1 — ARCHITECTURE.md inventory update

**Add missing modules:**
- `cli/mimo.py`
- `cli/opencode.py`
- `cli/common.py`
- `cli/formatter.py`
- `cli/manage/doctor.py`
- `cli/manage/update.py`
- `cli/manage/admin.py`
- `cli/setup/recipe.py`
- `cli/setup/config.py`
- `cli/setup/deinit.py`
- Other missing modules

**Update:**
- Dependency graph
- Request flows
- Component inventory
- Reflect post-refactor ownership decisions

#### H2 — CI/CD workflow updates

**Review:** `.github/workflows/gated-checkin.yml`
**Add:** Coverage reporting step
**Verify:** Docs build step in `publish-docs.yml`

#### H3 — Docs pipeline verification

- Verify `publish-docs.yml` builds successfully with new pages
- Test `mkdocs build --strict` locally

#### H4 — Version bump + CHANGELOG

- Bump `pyproject.toml` version: 0.1.8 → 0.1.9
- Update `CHANGELOG.md` with workstream summaries

---

## 5. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Single PR too large for review | High | Medium | Logical commits within PR; each workstream is a distinct commit group |
| Refactors break existing tests | Medium | High | Phase 1 tests establish baseline; run full suite after each refactor item |
| Config consolidation over-abstracts | Medium | High | Preserve old paths as thin wrappers; migrate incrementally |
| Launcher ownership decision is wrong | Low | High | Map responsibilities first (5.1) before deciding (5.2) |
| Docs inaccurate after refactors | Medium | Low | Docs written before refactors for WS1; ARCHITECTURE.md updated last (H1) |
| Coverage reporting adds noise | Low | Low | Reporting-only, no thresholds |
| Merge conflicts in single PR | Low | Medium | Sequential workstream execution |

---

## 6. Success Criteria

### Per-workstream

| WS | Success criterion |
|----|-------------------|
| WS1 | All new pages exist, nav works, docs build succeeds, no broken links |
| WS2 | Launcher/dispatch/entrypoint tests exist, failure paths covered, coverage reportable |
| WS3 | Config seam defined, key callers migrated, old paths delegate to new seam |
| WS4 | Registry owns lifecycle, CLI layer is thinner, lifecycle tests pass |
| WS5 | One canonical launcher owner, secondary is wrapper, ARCHITECTURE.md updated |
| WS6 | Agent registry explicit, shared validation centralized, CLI aliases preserved |
| WS7 | Doctor catches more real issues, troubleshooting docs route to cf doctor |

### Final verification

```bash
python -m pytest tests/ -v --tb=short
ruff check src/ tests/
mypy src/
mkdocs build --strict
```

### Smoke flows

- `cf setup init`
- `cf doctor`
- `cf proxy start`
- `cf run agent claude`
- `cf run agent mimo`
- `cf run agent claude --sandbox`

### Regression checks

- Env precedence unchanged
- Profile inheritance unchanged
- YAML config format unchanged
- Command aliases still work
- Docs match runtime behavior

---

## 7. Commit Strategy

Single PR with logical commit groups:

```
Phase 1 commits:
  test: add launcher and sandbox launcher tests
  test: add agent dispatch and entrypoint tests
  test: add failure-path coverage
  chore: add pytest-cov coverage reporting

Phase 2 commits:
  docs: add websearch interception page
  docs: add mimo-code feature page
  docs: clarify recipe sourcing
  docs: add troubleshooting guide
  docs: add FAQ
  docs: update navigation and landing flow

Phase 3 commits:
  refactor: audit and define canonical config seam
  refactor: migrate callers to new config seam
  refactor: consolidate tool lifecycle ownership
  refactor: thin CLI tool layer
  refactor: clarify launcher ownership

Phase 4 commits:
  refactor: add explicit agent registry
  refactor: centralize shared CLI validation
  test: add dispatch and validation tests

Phase 5 commits:
  feat: expand cf doctor checks
  docs: align troubleshooting with cf doctor

Phase 6 commits:
  docs: update ARCHITECTURE.md inventory
  ci: update workflow coverage reporting
  chore: bump version to 0.1.9
  docs: update CHANGELOG
```

---

## 8. Deferred Items Detail

### 3.4 — Remove duplicate config assembly paths

**Reason for deferral:** Only 4 config modules exist. Removing old paths before enough callers validate the new seam risks breaking less-visible code. The new seam (3.2) and caller migration (3.3) will establish the pattern, but old paths remain as thin wrappers.

**Pick-up criteria for 0.2.0:**
- New config seam has been exercised for at least one release cycle
- At least 3 distinct caller groups have migrated
- No regressions reported from the migration

### 4.3 — Standardize tool interface shape

**Reason for deferral:** Only 4 tools exist (chrome, web, github, web_bridge). Designing a shared protocol for this few tools is premature abstraction.

**Pick-up criteria for 0.2.0+:**
- Number of tools reaches 6+
- Real inconsistency pain emerges from tool lifecycle differences
- Registry code shows clear duplication that a shared interface would eliminate
