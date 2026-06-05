# Profiles

Profiles are the core configuration mechanism in CodeFreedom. They control which model a code agent uses, which tools are available, and how the agent connects to LLM providers -- all through environment variables.

## Directory Layout

All CodeFreedom state lives under `~/.codefreedom/` (configurable via `CODEFREEDOM_HOME`):

```
~/.codefreedom/
├── profiles/                      # Profile and tool configuration JSON
│   ├── claude-code.json           # Claude Code profiles (model routing, tools)
│   ├── claude-code.schema.json    # JSON Schema for editor validation
│   ├── chrome.json                # Chrome browser tool settings
│   ├── chrome.schema.json         # JSON Schema for chrome.json
│   ├── web.json                   # Camoufox web tool settings
│   └── web.schema.json            # JSON Schema for web.json
├── proxy/                         # LiteLLM proxy configuration
│   ├── config/
│   │   ├── config.yaml            # Main proxy config
│   │   └── providers/             # Provider YAML fragments
│   │       ├── deepseek.yaml
│   │       ├── azure-foundry.yaml
│   │       └── ...
│   ├── docker-compose.yaml        # Docker Compose deployment
│   └── .env.proxy.secrets.example # Provider API key templates
├── sandbox/                       # Isolated sandbox state
│   ├── <profile-name>/            # One directory per profile
│   │   └── .claude/               # Claude Code state (isolated per profile)
│   │       └── .claude.json       # Fresh config on each launch
│   └── tools/                     # Shared tool data
│       ├── chrome/                # Chrome persistent data (user-data-dir)
│       ├── web/                   # Camoufox persistent data
│       └── .cache/                # Shared cache directory
├── proc/                          # Runtime process tracking (tool lifecycle)
│   ├── sessions/                  # Per-session tracking files
│   │   └── codefreedom-a1b2.json  # Session: tools acquired, PID, timestamp
│   └── tools/                     # Per-tool lock files
│       ├── chrome.json            # Chrome: ref_count, active sessions
│       └── web.json               # Web: ref_count, active sessions
├── backups/                       # Admin backup archives
├── .env.claude                    # Claude Code component env (loaded by claude subcommand)
├── .env.claude.secrets            # Claude Code secrets (API keys, tokens)
├── .env.proxy                     # Proxy component env (loaded by proxy subcommand)
├── .env.proxy.secrets             # Proxy secrets (provider API keys)
├── .env                           # Shared config (all components)
└── .env.secrets                   # Shared secrets (all components)
```

### Key Directories

| Path                 | Purpose                                        | Created By                                                 |
| -------------------- | ---------------------------------------------- | ---------------------------------------------------------- |
| `profiles/`          | Profile JSON + tool settings + schemas         | `codefreedom claude init`, `codefreedom tools <tool> init` |
| `proxy/`             | LiteLLM proxy config + providers               | `codefreedom proxy init`                                   |
| `sandbox/<profile>/` | Isolated Claude Code state per profile         | Automatic on first sandbox launch                          |
| `sandbox/tools/`     | Persistent tool data (browser profiles, cache) | Automatic on first tool start                              |
| `proc/`              | Runtime reference counting for tool containers | Automatic during tool lifecycle                            |
| `backups/`           | Config backup archives                         | `codefreedom admin backup`                                 |

## JSON Schema Validation

Every profile file comes with a companion `.schema.json` for editor validation and autocomplete:

| Profile File                | Schema File                        | Purpose                                                     |
| --------------------------- | ---------------------------------- | ----------------------------------------------------------- |
| `profiles/claude-code.json` | `profiles/claude-code.schema.json` | Claude Code profiles (model routing, tools, sandbox images) |
| `profiles/chrome.json`      | `profiles/chrome.schema.json`      | Chrome browser tool settings                                |
| `profiles/web.json`         | `profiles/web.schema.json`         | Camoufox web tool settings                                  |

Each `*.json` file references its schema via the `$schema` property, so compatible editors apply validation automatically.

### Editor Setup

**VS Code:** Install the [JSON Schema Validator](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-json) extension (included by default in most VS Code installations). Open any profile file -- validation and autocomplete work automatically via the `$schema` reference.

**Neovim:** Use `nvim-lspconfig` with `vscode-json-language-server` -- it respects `$schema` references out of the box.

### Validating from the Command Line

```bash
# Validate Claude Code profiles
python -m jsonschema \
  ~/.codefreedom/profiles/claude-code.schema.json \
  ~/.codefreedom/profiles/claude-code.json

# Validate Chrome tool profile
python -m jsonschema \
  ~/.codefreedom/profiles/chrome.schema.json \
  ~/.codefreedom/profiles/chrome.json

# Validate web tool profile
python -m jsonschema \
  ~/.codefreedom/profiles/web.schema.json \
  ~/.codefreedom/profiles/web.json
```

Install the validator with `pip install jsonschema`.

## Profile File Structure

Claude Code profiles live in `~/.codefreedom/profiles/claude-code.json`:

```json
{
  "profiles": {
    "default": {
      "description": "Base profile -- routes through proxy",
      "env": {
        "CLAUDE_MODEL": "your-model-alias",
        "ANTHROPIC_BASE_URL": "http://localhost:4000",
        "ANTHROPIC_AUTH_TOKEN": "${LITELLM_MASTER_KEY}"
      },
      "sandbox_images": {
        "default": "your-registry/image:default-tag",
        "cuda": "your-registry/image:cuda-tag",
        "rocm": "your-registry/image:rocm-tag"
      },
      "tools": ["chrome", "web"],
      "sandbox": {
        "env": {
          "IS_SANDBOX": "1"
        }
      }
    },
    "ultra": {
      "description": "Inherits from default -- uses Ultra model",
      "env": {
        "CLAUDE_MODEL": "your-model-alias-ultra"
      }
    }
  }
}
```

### Profile Fields

Each profile supports these fields:

| Field            | Type     | Required | Description                                                 |
| ---------------- | -------- | -------- | ----------------------------------------------------------- |
| `description`    | string   | **Yes**  | Human-readable description                                  |
| `env`            | object   | **Yes**  | Environment variables (applied in both modes)               |
| `sandbox_images` | object   | No       | Docker images keyed by GPU type (`default`, `cuda`, `rocm`) |
| `tools`          | string[] | No       | Tool containers to auto-start (`"chrome"`, `"web"`)         |
| `sandbox.env`    | object   | No       | Env vars applied only in sandbox mode                       |
| `local.env`      | object   | No       | Env vars applied only in local/native mode                  |

Profile names must match `^[a-zA-Z0-9_-]+$`.

## Inheritance

Inheritance eliminates duplication. Custom profiles inherit from `default` -- you only set what differs.

### Inheritance Rules

1. **`default` and `bare` are standalone** -- they do not inherit from anything.
2. **All other profiles inherit from `default`** -- their `env` merges on top of `default`'s resolved env.
3. **Mode-specific overrides inherit too** -- `sandbox.env` and `local.env` from `default` are applied first, then the child's overrides merge on top.
4. **`sandbox_images` inherit** -- child profiles deep-merge from `default`'s images dict.
5. **`tools` inherit** -- child profiles get `default`'s tools list first, then append their own (deduplicated, order-preserving). Set `"tools": []` to opt out.

### Inheritance Example

```json
{
  "profiles": {
    "default": {
      "description": "Base profile",
      "env": {
        "ANTHROPIC_BASE_URL": "http://localhost:4000",
        "ANTHROPIC_AUTH_TOKEN": "${LITELLM_MASTER_KEY}",
        "CLAUDE_MODEL": "your-model-alias"
      },
      "tools": ["chrome", "web"],
      "sandbox": {
        "env": {
          "IS_SANDBOX": "1"
        }
      }
    },
    "my-profile": {
      "description": "Custom -- overrides model",
      "env": {
        "CLAUDE_MODEL": "your-model-alias-ultra"
      }
    }
  }
}
```

When `my-profile` is loaded, the effective env is:

```
ANTHROPIC_BASE_URL = http://localhost:4000    # inherited from default
ANTHROPIC_AUTH_TOKEN = <resolved from LITELLM_MASTER_KEY>  # inherited, resolved
CLAUDE_MODEL = your-model-alias-ultra         # overridden by my-profile
```

In sandbox mode, `IS_SANDBOX=1` is also inherited from `default`'s `sandbox.env`.

### Resolution Order

Variable resolution happens in two passes for inherited profiles:

1. **Resolve `default`'s env** against the base environment chain (`.env` files + system env).
2. **Resolve the child's env** against `{base_env, resolved_default_env}` -- so child overrides can reference both system vars and inherited values.

This means a child profile can do:

```json
{
  "env": {
    "CUSTOM_URL": "${ANTHROPIC_BASE_URL}/custom"
  }
}
```

and `${ANTHROPIC_BASE_URL}` will resolve to the inherited value from `default`.

## Variable Interpolation

Profile values support `${VAR}` references, resolved from the environment chain:

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "${LITELLM_MASTER_KEY}",
    "CLAUDE_MODEL": "${MODEL_NAME:-your-default-model}",
    "PROXY_URL": "${PROXY_URL:-http://localhost:4000}"
  }
}
```

Resolution order for each `${VAR}`:

1. Check already-resolved env vars from the same or higher-precedence profile.
2. Check system environment (`os.environ`).
3. Use `${VAR:-default}` fallback if present.
4. Warn and resolve to empty string if nothing matches.

**Empty-string env vars are valid overrides.** Setting `export FOO=""` does not fall through to defaults -- it is a deliberate override.

## Creating Custom Profiles

### Step 1: Edit the Profiles File

```bash
nano ~/.codefreedom/profiles/claude-code.json
```

Add your profile to the `"profiles"` object:

```json
{
  "profiles": {
    "research": {
      "description": "Research profile -- uses fast model for quick queries",
      "env": {
        "CLAUDE_MODEL": "your-model-alias-air"
      }
    }
  }
}
```

### Step 2: Validate

```bash
python -m jsonschema \
  ~/.codefreedom/profiles/claude-code.schema.json \
  ~/.codefreedom/profiles/claude-code.json
```

### Step 3: Use It

```bash
codefreedom claude --profile research
codefreedom claude --sandbox --profile research
```

### Standardization Guidelines

To keep profiles maintainable:

| Guideline                                   | Reason                                                           |
| ------------------------------------------- | ---------------------------------------------------------------- |
| **Inherit from `default`**                  | Set only what differs -- model, endpoint, or a few flags         |
| **Use `${VAR:-default}`**                   | Provide sensible fallbacks so profiles work out of the box       |
| **Name profiles by purpose**                | `research`, `production`, `local-dev` -- not `model-x` or `fast` |
| **Use `sandbox.env` for sandbox-only vars** | Keep local and sandbox configs separate                          |
| **Use `local.env` for local-only vars**     | Same principle in reverse                                        |
| **Keep `env` for cross-mode settings**      | Proxy URL, auth token, model selection                           |
| **Validate with the schema**                | Catch errors before runtime                                      |

## Tool Declarations

Profiles can declare `"tools"` to auto-start tool containers alongside the code agent:

```json
{
  "profiles": {
    "web-dev": {
      "description": "Full web dev profile with browser tools",
      "tools": ["chrome", "web"]
    },
    "no-tools": {
      "description": "No browser tools",
      "tools": []
    }
  }
}
```

### How Tool Auto-Start Works

1. When a session starts with a profile that declares tools, CodeFreedom checks if the tool containers are running.
2. If not, it starts them (Docker containers).
3. A **reference count** tracks how many sessions are using each tool.
4. When the last session exits, the tool container is stopped.

### Tool Lifecycle

```
Session A starts (tools: ["chrome"])
  -> Chrome container started, ref_count = 1

Session B starts (tools: ["chrome", "web"])
  -> Chrome already running, ref_count = 2
  -> Web container started, ref_count = 1

Session A exits
  -> Chrome ref_count = 1 (still running, Session B needs it)

Session B exits
  -> Chrome ref_count = 0 -> container stopped
  -> Web ref_count = 0 -> container stopped
```

### Tool Inheritance

Child profiles inherit `default`'s tools list (merged, deduplicated):

```json
{
  "profiles": {
    "default": {
      "tools": ["chrome"]
    },
    "full-stack": {
      "tools": ["web"]    # Effective tools: ["chrome", "web"]
    },
    "minimal": {
      "tools": []         # Effective tools: [] (opt-out)
    }
  }
}
```

## Tool Profiles

Each tool has its own profile file in `~/.codefreedom/profiles/`, generated by `codefreedom tools <tool> init`. Tool profiles are independent of Claude Code profiles -- they configure Docker container settings (image, ports, data directories).

### Chrome (`chrome.json`)

```json
{
  "chrome": {
    "image": "your-registry/chrome:latest",
    "container_name": "codefreedom-chrome",
    "port": 9222,
    "data_dir": "~/.codefreedom/sandbox/tools/chrome",
    "env": {
      "CHROME_DEBUG_PORT": "9222"
    }
  }
}
```

| Setting          | Default                               | Description                                |
| ---------------- | ------------------------------------- | ------------------------------------------ |
| `image`          | `codefreedom:chrome`                  | Docker image for headless Chrome container |
| `container_name` | `codefreedom-chrome`                  | Container name                             |
| `port`           | `9222`                                | CDP debug port for agent connection        |
| `data_dir`       | `~/.codefreedom/sandbox/tools/chrome` | Persistent browser data                    |
| `env`            | `CHROME_DEBUG_PORT=9222`              | Extra env vars forwarded to container      |

Schema: `~/.codefreedom/profiles/chrome.schema.json`

> Chrome runs headless (no Xvfb, no display server). For stealth / anti-bot
> browsing, use the [web tool](web.json) (Camoufox) instead.

### Web / Camoufox (`web.json`)

```json
{
  "web": {
    "image": "your-registry/web:latest",
    "container_name": "codefreedom-web",
    "port": 8420,
    "data_dir": "~/.codefreedom/sandbox/tools/web",
    "env": {},
    "search_engines": {},
    "parser_registry": {
      "standard": {
        "result_selectors": "your-css-selectors-here",
        "link_selector": "your-link-selector-here",
        "snippet_selectors": "your-snippet-selectors-here",
        "ai_selectors": ["selector-1", "selector-2"]
      }
    }
  }
}
```

| Setting           | Default                            | Description                                    |
| ----------------- | ---------------------------------- | ---------------------------------------------- |
| `image`           | `codefreedom:web`                  | Docker image for Camoufox container            |
| `container_name`  | `codefreedom-web`                  | Container name                                 |
| `port`            | `8420`                             | MCP server port                                |
| `data_dir`        | `~/.codefreedom/sandbox/tools/web` | Persistent data                                |
| `search_engines`  | `{}`                               | Search engine configurations (user-configured) |
| `parser_registry` | `{}`                               | CSS selector parsers for search results        |

Schema: `~/.codefreedom/profiles/web.schema.json`

### Tool Initialization

Tools require explicit user acceptance before initialization (third-party software notice):

```bash
codefreedom tools chrome init    # Requires typing "I understand"
codefreedom tools web init       # Requires typing "I understand"
```

Tools refuse to start without successful initialization. Init copies both the profile JSON and its schema file to `~/.codefreedom/profiles/`.

## Sensitive Value Masking

When profiles are loaded, values for keys containing `TOKEN`, `KEY`, `SECRET`, `AUTH`, or `PASSWORD` (case-insensitive) are masked in log output:

```
[PROFILE] Loading 'default' (standalone)...
     ANTHROPIC_AUTH_TOKEN=a****...ty
     ANTHROPIC_BASE_URL=http://localhost:4000
     CLAUDE_MODEL=your-model-alias
```

## Custom Profile Location

Override the default profile file location:

```bash
export CODEFREEDOM_PROFILES_FILE="/path/to/custom/profiles.json"
```

This is useful for:

- Version-controlling profiles in a shared team repo
- A/B testing different model configurations
- Keeping work profiles separate from personal ones

## Listing Profiles

```bash
codefreedom claude --list-profiles
```

Shows each profile, its description, inheritance status, and which environment variables it sets.

See [Environment Configuration](../environment.md) for the full env chain and [Sandbox Mode](sandbox.md) for container isolation details.
