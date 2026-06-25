# Configuration Architecture Redesign

> **Status:** Design Proposal  
> **Scope:** All configuration loading, merging, interpolation, validation, and recipe deployment  
> **Constraints:**
>
> - Zero backward compatibility — full rewrite freedom
> - No `.env` files — all vars and non-secrets come from YAML, secrets from machine env vars only
> - Interpolation happens at runtime only — never at install time
> - Files are installed with literal `${VAR}` references, resolved hot on every load
> **Goal:** A single, predictable, extensible configuration layer for any current or future component

---

## 1. Current Architecture — What's Wrong

### 1.1 Fragmented Entry Points

Seven independent load paths, each with its own timing and context:

| Caller | Entry Point | Files Read | Interpolation Timing |
|---|---|---|---|
| Agent launcher | `load_profiles()` → `load_profile_env()` → `get_env()` | profiles.yaml, override.yaml, 9-tier .env chain | After env chain resolves CF_CLI_* |
| Tool launcher | `load_tool_profile()` | profiles.yaml (tools section) | Self-contained, inline |
| Proxy starter | `get_env()` + `_build_proxy_env()` | .env.proxy, override.yaml | Partial — only env chain |
| Recipe init | `init_recipe()` | recipe.yaml, vars files | At install time with skip_pattern |
| Doctor | Custom checks | All files | Independent, per check |

**Result:** Same `${VAR}` in tools vs. agents can resolve to different values. Same value in `override.yaml` works for agents but may not for tools.

### 1.2 .env Chain Complexity

The 9-tier .env chain is:

- Hard to reason about (which of 9 files wins?)
- Spread across config dir and workspace dirs — no single source of truth
- `.env.secrets` files store secrets on disk, violating the principle that secrets come from machine env only
- `python-dotenv` dependency for something that should be a simple env var lookup

### 1.3 Install-Time Interpolation

Current code resolves `${VAR}` during recipe install (`_install_recipe_files`), with a `skip_pattern` to preserve `CF_CLI_*` placeholders. This creates two problems:

- **Timing dependency:** install-time vs. runtime resolution can produce different results
- **Complexity:** `skip_pattern`, `_SECRET_VAR_RE`, double interpolation logic — hard to reason about
- **Stale values:** if a user changes an env var after install, the baked-in YAML still has the old value

### 1.4 Schema Validation is Best-Effort

Every validation uses `try/except ValidationError: pass`. Malformed configs proceed. Runtime failures happen minutes later, unrelated to the root cause.

### 1.5 override.yaml Merging is Ad-Hoc

40-line manual dict walk that only handles `env` keys. You cannot override `tools`, `sandbox_images`, `extensions`, `lsp_servers`, or any structural property.

### 1.6 Silent Error Swallowing

```python
try:
    ...
except Exception:
    pass  # Malformed override.yaml vanishes silently
```

### 1.7 No Cross-File Validation

Profile references `tools: [chromee]` → runtime silently gets empty config. The typo is never caught.

---

## 2. Design Principles

1. **One entry point, one load.** `load_config()` loads everything for every component. Consumers don't touch files directly.

2. **YAML for config, machine env for secrets.** No `.env` files. Profiles/config in `profiles.yaml`/`override.yaml`. Secrets in `os.environ`/`CF_CLI_*` only.

3. **Runtime-only interpolation.** Files are stored with literal `${VAR}` references. Every `load_config()` call resolves them hot from current machine env. No install-time baking. No `skip_pattern`. No stale values.

4. **Validate early, strictly.** Schema violations are fatal at load time. Clear, actionable messages. No silent `except: pass`.

5. **Predictable three-layer model.** Recipe defaults → user overrides (override.yaml, full schema) → machine overrides (env vars). Every layer has unambiguous precedence.

6. **Single-pass interpolation.** `${VAR}` resolves once after all layers merge. Every consumer sees exactly the same resolved values for the same `load_config()` call.

7. **Extensible by section.** Add a key to `profiles.yaml` `agents:` map to support a new agent. Add a key to `tools:` for a new tool. Add a top-level section for a future component. No Python code changes needed.

8. **Recipe provides a setup script.** Generates a script that helps users export secrets to their shell environment. The script writes to shell profile — the config system never reads files for secrets.

---

## 3. Proposed Architecture

### 3.1 Data Flow

```text
INSTALL TIME                          RUNTIME (every load_config call)
══════════════════                    ════════════════════════════════

recipe.yaml                           load_config(config_dir)
  ├─ lists files to copy                │
  ├─ declares config_vars               ├─ Read profiles.yaml   (literal ${VAR})
  └─ declares required_secrets          ├─ Read override.yaml   (literal ${VAR})
       │                                ├─ Merge (override wins structurally)
       ▼                                ├─ Build context:
~/.codefreedom/config/                   │   ├─ os.environ
  ├─ profiles.yaml       (literal)      │   ├─ CF_CLI_* (stripped, highest)
  ├─ override.yaml       (literal)      │   └─ flattened dotted keys (common.*)
  ├─ recipe.yaml         (manifest)     ├─ Resolve ${VAR} once, single pass
  ├─ proxy/              (literal)      ├─ Validate Pydantic (FATAL)
  └─ scripts/setup-env.sh               ├─ Validate cross-references (FATAL)
       │                                ▼
       run once ──→ user exports      ResolvedConfig (frozen)
       secrets to shell profile             │
       (.bashrc/.zshrc)                     ├─ .for_agent("claude-code", "default")
       or runs setup-env.sh                 ├─ .for_tool("chrome")
                                            └─ .for_component("proxy")
```

### 3.2 Core Insight: What Changes Where

| Concern | Stored Where | Resolved When |
|---|---|---|
| Profile structure, defaults | `profiles.yaml` (literal `${VAR}`) | Runtime, every load |
| User overrides | `override.yaml` (literal `${VAR}`) | Runtime, every load |
| Config vars with defaults | `profiles.yaml` as `${VAR:-default}` | Runtime, by interpolation |
| Secrets | Machine env only (`os.environ`) | Runtime, by interpolation |
| Recipe manifest | `recipe.yaml` | Doctor/upgrade only |
| Setup script | `scripts/setup-env.sh` (generated) | Once, by user |

**Files are stored with literal `${VAR}` references. Every `load_config()` resolves them hot.**
No install-time baking. No stale values. No `skip_pattern`.

### 3.3 File Layout

```text
~/.codefreedom/config/
├── profiles.yaml              RECIPE-MANAGED. All agents, tools, common settings.
│                              Contains literal ${VAR} and ${VAR:-default}
│                              references. Never modified after install.
│
├── override.yaml              USER-MANAGED. Same schema as profiles.yaml.
│                              User edits to override any recipe default.
│                              Can replace env, tools, sandbox_images,
│                              extensions — anything in the schema.
│
├── recipe.yaml                RECIPE-MANAGED. Copy of recipe manifest.
│                              Reference metadata for doctor, upgrades.
│
├── proxy/                     RECIPE-MANAGED.
│   ├── docker-compose.yaml    Literal ${VAR} references (resolved at runtime
│   │                          via docker compose subprocess env)
│   └── config/
│       ├── config.yaml        LiteLLM config
│       └── providers/*.yaml
│
└── scripts/
    └── setup-env.sh           GENERATED ONCE. Prompts for secrets, writes
                               exports to shell profile (.bashrc/.zshrc).
```

**What no longer exists:**

- No `~/.codefreedom/.env.claude` — component env files
- No `~/.codefreedom/.env` — shared env file
- No `~/.codefreedom/.env.secrets` — secrets in files
- No `~/.codefreedom/.env.user` — user override env file
- No workspace `.env` / `.env.secrets`
- No `env_loader.py` (the 9-tier chain removed)
- No `load_dotenv()` (python-dotenv dependency removed)
- No `merge: env` strategy in recipes
- No `env_template` generated artifact
- No `skip_pattern` / `_SECRET_VAR_RE` (no install-time interpolation)

### 3.4 Central Configuration Schema

```yaml
# ~/.codefreedom/config/profiles.yaml
#
# All ${VAR} references are resolved at runtime from machine environment.
# Use ${VAR:-default} for config vars with fallback values.
# Secrets have no default — they MUST be set in the machine environment.

# ── Common settings (dotted keys available for ${common.*} references) ─
common:
  sandbox_images:
    default: "docker.io/nilayparikh/codefreedom:ubuntu-latest"
    cuda: "docker.io/nilayparikh/codefreedom:cuda-latest"
    rocm: "docker.io/nilayparikh/codefreedom:rocm-latest"
  proxy:
    bind_host: "127.0.0.1"
    bind_port: 4000
  postgres:
    host_data_dir: "~/.codefreedom/config/pg/data"
    host_port: "${POSTGRES_HOST_PORT:-5433}"
    user: "pguser"
    password: "${POSTGRES_PASSWORD:-pgpassword}"
  suffix_id: "${SUFFIX_ID:-0000}"

# ── Agent profiles ─────────────────────────────────────────────────────
agents:
  claude-code:
    profiles:
      default:
        description: "Default profile with all tools"
        env:
          ANTHROPIC_BASE_URL: "http://127.0.0.1:${common.proxy.bind_port}"
          ANTHROPIC_AUTH_TOKEN: "${LITELLM_MASTER_KEY}"
        tools: [chrome, web, github]
        sandbox_images:
          default: "docker.io/nilayparikh/codefreedom:ubuntu-latest"
        sandbox:
          env:
            IS_SANDBOX: "true"

      bare:
        description: "Minimal — no tools, no sandbox"
        env:
          ANTHROPIC_BASE_URL: "http://127.0.0.1:4000"

      ui-ux:
        description: "Vision-capable profile"
        env:
          ANTHROPIC_MODEL: "claude-sonnet-4-20250514"
        tools: [chrome]

  mimo-code:
    profiles:
      default:
        env:
          MIMO_API_KEY: "${MIMO_API_KEY:-}"
        tools: [chrome, web]

# ── Tool definitions ────────────────────────────────────────────────────
tools:
  chrome:
    image: "docker.io/nilayparikh/codefreedom:chrome-latest"
    container_name: "codefreedom-chrome-${common.suffix_id}"
    port: 9222
    env:
      CHROME_FLAGS: "--headless"

  web:
    image: "docker.io/nilayparikh/codefreedom:web-latest"
    container_name: "codefreedom-web-${common.suffix_id}"
    port: 8420

  github:
    image: "ghcr.io/github/github-mcp-server"
    container_name: "codefreedom-github-${common.suffix_id}"
    port: 8129
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_PERSONAL_ACCESS_TOKEN}"

  git:
    model: "gpt-4o-mini"
    conventional_commit: true

# ── For future components, add a top-level section ─────────────────────
# plugins:
#   web-search-interception:
#     enabled: "${WEB_SEARCH_INTERCEPTION:-true}"
```

### 3.5 override.yaml — Full Schema Mirror

Same schema as `profiles.yaml`. Any value here overrides the recipe default. Override can replace **any** key — not just `env`:

```yaml
# ~/.codefreedom/config/override.yaml
#
# Mirrors profiles.yaml structure. Any value here overrides the recipe.
# Absent values fall through to what the recipe provides.
#
# ${VAR} references are also supported here and resolve from the same
# machine environment context.

common:
  proxy:
    bind_host: "0.0.0.0"        # Expose proxy externally
  suffix_id: "${SUFFIX_ID:-0000}"

agents:
  claude-code:
    profiles:
      default:
        env:
          CLAUDE_MODEL: "claude-sonnet-4-20250514"
        tools: [chrome, web, github]
        sandbox_images:
          default: "my-registry/my-image:custom"

tools:
  chrome:
    port: 9224
```

**Merge rules (structural, not env-only):**

- `env` dicts: key-by-key merge (override key wins, base keys preserved)
- `tools` lists: full replacement (not append)
- `sandbox_images` dicts: key-by-key
- `extensions` / `lsp_servers`: full replacement
- Nested `sandbox`/`local` blocks: deep merge
- Scalars: full replacement

### 3.6 The Load Function

```python
@dataclass(frozen=True)
class ResolvedConfig:
    """Fully resolved, validated configuration. Immutable after construction.

    Created by load_config(). Every field has ${VAR} resolved.
    Every reference is validated (all tool names exist in tools section).
    """
    common: CommonSection
    agents: dict[str, AgentDefinition]
    tools: dict[str, ToolDefinition]
    provenance: dict[str, str]          # where each resolved value came from
    # Future: plugins, etc. added as new attributes


def load_config(config_dir: Path) -> ResolvedConfig:
    """THE single configuration entry point.

    Loads YAML files, merges layers, resolves ${VAR} from machine env,
    validates, and returns an immutable ResolvedConfig.

    Resolution order (later wins):
      1. profiles.yaml             (recipe-provided defaults)
      2. override.yaml             (user overrides — same schema)
      3. Machine env (os.environ)  (always available)
      4. CF_CLI_* env vars         (highest priority, prefix stripped)

    ${VAR} interpolation happens ONCE after all layers are merged.
    Every consumer sees exactly the same resolved values.
    """
    # Step 1: Load YAML layers
    base = _load_yaml_or_die(config_dir / "profiles.yaml")
    override = _load_yaml_optional(config_dir / "override.yaml")

    # Step 2: Full structural merge (override can replace ANY key)
    merged = _merge_deep(base, override)

    # Step 3: Build resolution context from machine env only
    context: dict[str, str] = {}
    context.update(os.environ)
    context.update(_load_cf_cli_overrides())
    # Also add common.* dotted keys for ${common.proxy.bind_host} style refs
    common_section = merged.get("common", {})
    if isinstance(common_section, dict):
        context.update(_flatten_dict(common_section, "common"))

    # Step 4: Single-pass ${VAR} resolution
    # This resolves ${VAR} and ${VAR:-default} in ALL string values.
    # No skip_pattern. No partial resolution. Everything at once.
    resolved = _interpolate_all_strings(merged, context)

    # Step 5: Fatal schema validation
    try:
        config_model = ConfigModel.model_validate(resolved)
    except ValidationError as e:
        _die(f"[FATAL] Configuration error in {config_dir / 'profiles.yaml'}:\n{e}\n"
             f"Fix the file and try again. Run: cf doctor config")

    # Step 6: Fatal cross-reference validation
    errors = _validate_references(config_model)
    if errors:
        _die(f"[FATAL] Configuration reference errors:\n" + "\n".join(errors))

    return ResolvedConfig(
        common=config_model.common,
        agents=config_model.agents,
        tools=config_model.tools,
        provenance=_build_provenance(merged, resolved),
    )


def _merge_deep(base: dict, override: dict | None) -> dict:
    """Recursive dict merge. Override values win. None values are skipped."""
    if not override:
        return deepcopy(base)
    result = deepcopy(base)
    for key, val in override.items():
        if val is None:
            continue
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _merge_deep(result[key], val)
        else:
            result[key] = deepcopy(val)
    return result


def _load_cf_cli_overrides() -> dict[str, str]:
    """Extract CF_CLI_* env vars, stripping the prefix."""
    return {
        key[7:]: val
        for key, val in os.environ.items()
        if key.startswith("CF_CLI_")
    }
```

### 3.7 Consumer API

```python
# Every consumer calls the same load_config():
config = load_config(get_config_dir())

# Agent launcher:
agent_cfg = config.for_agent(
    agent="claude-code",
    profile="default",
    mode="sandbox",
)
# Returns AgentConfig with:
#   env: {...}                   # resolved env dict
#   tools: ["chrome", "web"]     # inherited from default + profile
#   sandbox_images: {...}        # resolved image refs
#   extensions: [".py", ".js"]

# Tool launcher:
tool_cfg = config.for_tool("chrome")
# Returns ToolConfig with:
#   image, container_name, port, env, extra_ports, data_dir

# Proxy starter:
proxy_env = config.for_component("proxy")
# Returns dict of proxy-specific env vars for docker compose

# Doctor:
report = config.diagnose()
# Returns a list of issues: missing secrets, unresolved refs, etc.
```

**Profile inheritance** (built into the model, not scattered across functions):

```python
class AgentDefinition(BaseModel):
    profiles: dict[str, ProfileEntry]

    def resolve_profile(self, name: str, mode: str | None = None) -> ProfileEntry:
        if name in ("default", "bare"):
            return self.profiles[name]
        
        # Non-standalone profiles inherit from default
        default = self.profiles.get("default", ProfileEntry())
        child = self.profiles.get(name, ProfileEntry())
        
        return ProfileEntry(
            env={**default.env, **child.env},
            tools=default.tools + [t for t in child.tools if t not in default.tools],
            sandbox_images={**default.sandbox_images, **child.sandbox_images},
            extensions=child.extensions or default.extensions,
            sandbox=ModeEnv(env={**(default.sandbox.env or {}), **(child.sandbox.env or {})}),
            local=ModeEnv(env={**(default.local.env or {}), **(child.local.env or {})}),
        )
```

---

## 4. Recipe Changes

### 4.1 What recipe.yaml No Longer Does

| Current | Change |
|---|---|
| Installs `.env.*` files | **Remove** — no .env files at all |
| Installs `.env.*.secrets` files | **Remove** — secrets from machine env only |
| Generates `env_template` artifacts | **Remove** — nothing writes .env files |
| Interpolates `${VAR}` during install | **Remove** — files stay literal |
| Uses `skip_pattern` / `_SECRET_VAR_RE` | **Remove** — no install-time interpolation |

### 4.2 What recipe.yaml Still Does

| Current | Status |
|---|---|
| Installs `profiles.yaml` with literal `${VAR}` | **Keep** — never resolved at install time |
| Installs `override.yaml` template | **Keep** — empty scaffold, user edits |
| Declares `config_vars` with defaults | **Keep** — documentation. Translates to `${VAR:-default}` in profiles.yaml |
| Declares `required_secrets` | **Keep** — used for setup script gen. Translates to `${VAR}` (no default) in profiles.yaml |
| Installs proxy config files | **Keep** — docker-compose.yaml, config.yaml, providers |
| Generates setup scripts | **Update** — writes to shell profile instead of .env files |
| File merge (deepdiff/overwrite) | **Keep** — for profile updates |

### 4.3 How config_vars and required_secrets Map to profiles.yaml

```yaml
# In recipe.yaml:
config_vars:
  - var: SUFFIX_ID
    default: "0000"
    prompt: "Unique suffix for container names"
  - var: POSTGRES_HOST_PORT
    default: "5433"
    prompt: "PostgreSQL host port"

required_secrets:
  - var: LITELLM_MASTER_KEY
    prompt: "LiteLLM proxy master key"
    hint: "openssl rand -hex 32"
  - var: GITHUB_PERSONAL_ACCESS_TOKEN
    prompt: "GitHub personal access token"

# ↓ recipe generates profiles.yaml with these patterns

# In profiles.yaml (installed literally):
common:
  suffix_id: "${SUFFIX_ID:-0000}"          # ← config_var with default
  postgres:
    host_port: "${POSTGRES_HOST_PORT:-5433}" # ← config_var with default

# Secrets have no default — will raise at runtime if missing:
agents:
  claude-code:
    profiles:
      default:
        env:
          ANTHROPIC_AUTH_TOKEN: "${LITELLM_MASTER_KEY}"  # ← no default

tools:
  github:
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_PERSONAL_ACCESS_TOKEN}"  # ← no default
```

**Key rule:** If a value has a `default` in `recipe.yaml`'s `config_vars`, it gets `${VAR:-default}` in `profiles.yaml`. If it has no default (`required_secrets`), it gets `${VAR}` — and will warn or fail at runtime if the env var isn't set.

### 4.4 Setup Script Behavior

The generated script helps users set machine environment variables (secrets only — config vars already have defaults):

```bash
#!/usr/bin/env bash
# setup-env.sh — Generated by codefreedom recipe
#
# Prompts for required secrets and adds them to your shell profile.
# Run this once after installation:
#   bash setup-env.sh
#
# Or set the environment variables yourself in ~/.bashrc, ~/.zshrc, or
# your preferred env management tool.

set -euo pipefail

detect_profile() {
    if [ -n "${ZSH_VERSION:-}" ]; then
        echo "${HOME}/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ]; then
        echo "${HOME}/.bashrc"
    else
        echo "${HOME}/.profile"
    fi
}

PROFILE="$(detect_profile)"
RECIPE_NAME="costeffective-coding"

echo "=== CodeFreedom: ${RECIPE_NAME} Environment Setup ==="
echo ""
echo "This script will prompt for required secrets and add them to"
echo "your shell profile (${PROFILE})."
echo ""

# ── Secrets (no defaults — must be provided) ──────────────────────────────

prompt_secret() {
    local var="$1"
    local prompt="$2"
    local hint="$3"
    local val=""

    if [ -n "${!var:-}" ]; then
        echo "  [OK] ${var} is already set in this shell."
        return 0
    fi

    if [ -n "${!CF_CLI_${var}:-}" ]; then
        echo "  [OK] CF_CLI_${var} is already set in this shell."
        return 0
    fi

    read -p "  ${prompt}: " val
    if [ -z "${val}" ]; then
        echo "  [WARN] ${var} not provided. Set it later with:"
        echo "         export CF_CLI_${var}=\"your-value\""
        return 0
    fi
    export "CF_CLI_${var}=${val}"
    echo "export CF_CLI_${var}=\"${val}\"" >> "${PROFILE}"
    echo "  [OK] ${var} set and persisted."
}

echo "--- Required Secrets ---"
prompt_secret "LITELLM_MASTER_KEY" \
    "LiteLLM proxy master key" \
    "Generate: openssl rand -hex 32"
prompt_secret "GITHUB_PERSONAL_ACCESS_TOKEN" \
    "GitHub personal access token" \
    "Create: https://github.com/settings/tokens"

echo ""
echo "--- Optional Config ---"
# Config vars already have ${VAR:-default} in profiles.yaml,
# so these are truly optional. Script shows them for awareness.
echo "  SUFFIX_ID=0000           (default — set CF_CLI_SUFFIX_ID to override)"
echo "  POSTGRES_HOST_PORT=5433  (default — set CF_CLI_POSTGRES_HOST_PORT to override)"

echo ""
echo "Setup complete for ${RECIPE_NAME}."
echo ""
echo "To apply changes to your current shell:"
echo "  source ${PROFILE}"
echo ""
echo "Secrets are stored in your shell profile. ${PROFILE}."
```

### 4.5 Recipe Manifest Changes

```yaml
# recipe.yaml — Updated schema

name: costeffective-coding
version: 1
extends: _default

vars: config.vars.yaml

files:                                    # No .env files here
  - path: profiles.yaml
    target: profiles.yaml
    merge: deepdiff
  - path: proxy/docker-compose.yaml
    merge: overwrite
  - path: proxy/config/config.yaml
    merge: deepdiff
  - path: proxy/config/providers/*.yaml
    merge: deepdiff

required_secrets:                         # → generates ${VAR} in profiles.yaml
  - var: LITELLM_MASTER_KEY               #   → generates setup-env.sh
    prompt: "LiteLLM proxy master key"
    hint: "openssl rand -hex 32"
  - var: GITHUB_PERSONAL_ACCESS_TOKEN
    prompt: "GitHub personal access token"

config_vars:                              # → generates ${VAR:-default} in profiles.yaml
  - var: SUFFIX_ID
    default: "0000"
    prompt: "Unique suffix for container names"
  - var: POSTGRES_HOST_PORT
    default: "5433"
    prompt: "PostgreSQL host port"

generated_artifacts:                      # Only setup_script_bash/powershell
  - kind: setup_script_bash
    target: scripts/setup-env.sh
  - kind: setup_script_powershell
    target: scripts/setup-env.ps1
```

**Removed from the recipe schema:**

- `FileEntry.merge == "env"` — removed. Only `deepdiff` and `overwrite` remain.
- `generated_artifacts[].kind == "env_template"` — removed.
- `.env.*` file entries in every recipe's `files:` list

---

## 5. Runtime Characteristics

### 5.1 Performance

`load_config()` runs on every command invocation (agent launch, tool start, proxy start, doctor). This is acceptable because:

- Profile files are small (< 50KB)
- YAML parsing is fast (< 10ms)
- Single-pass interpolation is O(n) over string values
- No I/O beyond reading 1-2 YAML files

**Optional optimization:** Add file hash caching. If `profiles.yaml` and `override.yaml` haven't changed since last load, return cached `ResolvedConfig`. Reset on `SIGHUP` or explicit `cf config reload`.

### 5.2 Error Handling

All errors are fatal, with actionable messages:

```text
# Missing secret (no default in profiles.yaml):
[FATAL] Configuration error: Variable 'LITELLM_MASTER_KEY' is required
  but not set in environment.
  Set it: export CF_CLI_LITELLM_MASTER_KEY="your-key"
  Or add to ~/.bashrc and restart your shell.

# Typo in tool reference:
[FATAL] Configuration error: Agent 'claude-code' profile 'default'
  references tool 'chromee' which is not defined in profiles.yaml.
  Did you mean 'chrome'?
  Known tools: chrome, web, github, web-bridge, git

# Malformed YAML:
[FATAL] Failed to parse /home/user/.codefreedom/config/profiles.yaml:
  YAML parse error at line 42, column 8: mapping values not allowed here

# Unresolved ${VAR} with no default:
[WARN] Variable 'MY_OPTIONAL_FEATURE' is not set and has no default.
  The literal text "${MY_OPTIONAL_FEATURE}" will be used.
  Set it: export CF_CLI_MY_OPTIONAL_FEATURE="true"
```

### 5.3 Environment Variable Resolution Order

```
1. os.environ (bare names)        ← lowest priority machine env
2. CF_CLI_* (stripped prefix)     ← highest priority machine env
3. common.* dotted keys           ← from merged profiles.yaml
4. ${VAR:-default} fallback       ← inline default in YAML
5. Empty string ""                ← if nothing else resolves
```

---

## 6. Dependency Changes

| Library | Status | Reason |
|---|---|---|
| `python-dotenv` | **Remove** | No .env files to parse |
| `deepdiff` | **Keep** | Still needed for YAML merge at recipe install |
| `PyYAML` | **Keep** | YAML parsing |
| `pydantic` | **Keep** | Schema validation |

---

## 7. Migration Plan

### Phase 1: Core Loader (`core/loader.py`)

Build the single load function:

- `load_config(config_dir) → ResolvedConfig`
- `_merge_deep(base, override)` — structural merge
- `_interpolate_all_strings(data, context)` — single-pass resolution
- `_load_cf_cli_overrides()` — CF_CLI_* extraction
- `ResolvedConfig` dataclass with `for_agent()`, `for_tool()`, `for_component()`, `diagnose()`

### Phase 2: Schema (`schemas/config.py`)

Replace current `schemas/profiles.py`:

- `ConfigModel` — top-level with `common`, `agents`, `tools`
- `AgentDefinition` — profiles dict, inheritance logic
- `ProfileEntry` — env, tools, sandbox_images, sandbox/local blocks
- `ToolDefinition` — typed fields per tool
- `@model_validator` — cross-reference validation
- Strict `extra="forbid"` everywhere

### Phase 3: Recipe System Changes

Remove:

- `.env` file entries from all recipe files
- `merge: env` strategy from `recipe/merge.py`
- `env_template` artifact from `recipe/generated_artifacts.py`
- `skip_pattern` / `_SECRET_VAR_RE` from `recipe/apply.py`
- All install-time interpolation logic

Add:

- `setup_script_bash`/`powershell` that writes to shell profile
- `config_vars` → `${VAR:-default}` mapping in recipe-installed `profiles.yaml`

### Phase 4: Consumer Rewrites

Replace all existing config loading with `load_config()`:

- `cli/claude.py` → `config.for_agent("claude-code", profile, mode)`
- `cli/mimo.py` → same pattern
- `cli/opencode.py` → same pattern
- `cli/pi.py` → same pattern
- `cli/codex.py` → same pattern
- `cli/docker_utils.py:load_tool_profile()` → `config.for_tool(name)`
- `cli/run/proxy.py:_build_proxy_env()` → `config.for_component("proxy")`
- `cli/manage/doctor.py` → `config.diagnose()`

### Phase 5: Delete Dead Code

Remove files:

- `env_loader.py` — entire module (9-tier chain)
- `core/interpolate.py` — move `_VAR_REF_RE` into `core/loader.py`
- `core/profiles.py` — all profile loading consolidated into `loader.py`
- `schemas/profiles.py` — replaced by `schemas/config.py`
- `recipe/generated_artifacts.py` — only `env_template` removed, setup scripts rewritten

Remove dependencies:

- `python-dotenv` from `pyproject.toml`

---

## 8. Summary

| Dimension | Before | After |
|---|---|---|
| Entry points | 7+ independent load functions | 1 function: `load_config()` |
| Config sources | YAML + 9-tier .env chain + machine env | YAML + machine env only |
| Secrets storage | `.env.*.secrets` files + machine env | **Machine env only** |
| Validation | Non-fatal warnings | **Fatal** with actionable messages |
| Override scope | Only `env` keys | **Any key** in schema |
| Interpolation timing | Install-time (with skip_pattern) + runtime | **Runtime only** — hot every load |
| Interpolation passes | 2-3 passes, different context each time | **Single pass**, deterministic |
| Cross-references | Not validated | **Validated** at load time |
| Schema | 2 models (legacy + unified) | **1 model**, all sections |
| Error handling | Silent `except: pass` | **Always reported**, fatal |
| New component | Need new load path + env chain tier | **Add section to YAML** |
| Env dependency | `python-dotenv` | **None** |
| Recipe setup | Writes `.env.*.secrets` files | **Generates shell profile script** |
