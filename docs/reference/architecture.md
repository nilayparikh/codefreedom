# Architecture

CodeFreedom is a CLI tool that provides a unified interface for code agents with LLM routing, sandboxing, and profile management. All configuration is managed from `~/.codefreedom`.

## Bird's-Eye View

```mermaid
graph TD
    CLI["<b>codefreedom CLI</b><br/>cf / codefreedom"]

    CLI -->|"codefreedom claude init"| INIT_C["Init Claude profiles + .env.claude"]
    CLI -->|"codefreedom proxy init"| INIT_P["Init proxy configs + .env.proxy"]
    CLI -->|"codefreedom claude"| CLAUDE["Code Agent Launcher"]
    CLI -->|"codefreedom proxy"| PROXY["LLM Proxy"]

    subgraph "Profile System"
        PROFILES["claude-code.json<br/>Profile definitions"]
        PROFILES -->|default| P_DEFAULT["CodeFreedom/Flash<br/>(built-in)"]
        PROFILES -->|bare| P_BARE["Minimal<br/>(built-in)"]
        PROFILES -->|"custom (pro, ultra, …)"| P_CUSTOM["User-created<br/>profiles"]
    end

    subgraph "Execution Modes"
        CLAUDE --> NATIVE["Native Mode<br/>Host claude CLI"]
        CLAUDE --> SANDBOX["Sandbox Mode<br/>Docker + GPU"]
        NATIVE --> PROFILES
        SANDBOX --> PROFILES
    end

    subgraph "Sandbox Images<br/>(docker.io/nilayparikh/codefreedom)"
        SANDBOX --> IMG_CUDA["CUDA<br/>NVIDIA GPUs"]
        SANDBOX --> IMG_ROCM["ROCm<br/>AMD GPUs"]
        SANDBOX --> IMG_UBUNTU["Ubuntu<br/>General purpose"]
    end

    subgraph "LLM Proxy"
        PROXY --> UP["docker compose up<br/>localhost:4000"]
        PROXY --> DOWN["docker compose down"]
        PROXY --> VALIDATE["Validate config"]
        UP --> LITELLM_IMG["codefreedom:litellm-latest<br/>(patch baked in)"]
        LITELLM_IMG --> ROUTER["Model Router"]
    end

    subgraph "Provider Backends"
        ROUTER --> DS["DeepSeek API<br/>(cloud)"]
        ROUTER --> AZ["Azure Foundry<br/>(cloud)"]
        ROUTER --> NV["NVIDIA AI<br/>(cloud)"]
        ROUTER --> OZ["OpenCode Zen<br/>(cloud)"]
        ROUTER --> LOCAL["Self-Hosted<br/>(OpenAI/Anthropic)"]
    end

    PROFILES -.->|model routing| ROUTER
```

## CLI Design

The CLI uses a subcommand structure:

```
codefreedom / cf
├── claude (cc)         # Launch code agent
│   ├── init            # Initialize Claude profiles + .env.claude (clean target only)
│   ├── --profile       # Model profile
│   ├── --sandbox       # Docker container
│   ├── --native-models # Bypass proxy
│   ├── --stop          # Stop containers
│   ├── --status        # Container status
│   └── --list-profiles # List profiles
├── proxy (px)          # Manage LLM proxy
│   ├── init            # Initialize proxy configs + .env.proxy (clean target only)
│   ├── start           # Start proxy (Docker Compose, default)
│   ├── stop            # Stop proxy
│   ├── restart         # Restart proxy (preserves state, no image pull)
│   ├── status          # Proxy status
│   └── validate        # Validate config
└── tools               # Manage auxiliary tools
    ├── chrome          # Chrome browser (Xvfb + CDP)
    │   └── init|start|stop|status|url
    └── web             # Web search tool (MCP)
        └── init|start|stop|status
```

## Configuration Flow

Each component loads its own subset of the env chain — they do not share component-specific files.

```mermaid
flowchart LR
    subgraph "codefreedom claude (7 layers)"
        C1[".env.claude"]
        C2[".env.claude.secrets"]
        S1[".env (shared)"]
        S2[".env.secrets (shared)"]
        W1["workspace/.env"]
        W2["workspace/.env.secrets"]
        SYS1["System env"]
    end

    subgraph "codefreedom proxy (7 layers)"
        P1[".env.proxy"]
        P2[".env.proxy.secrets"]
        S1B[".env (shared)"]
        S2B[".env.secrets (shared)"]
        W1B["workspace/.env"]
        W2B["workspace/.env.secrets"]
        SYS2["System env"]
    end

    subgraph "codefreedom tools (5 layers)"
        T1[".env (shared)"]
        T2[".env.secrets (shared)"]
        T3["workspace/.env"]
        T4["workspace/.env.secrets"]
        T5["System env"]
    end
```

See [Environment Configuration](environment.md) for the full precedence chain and variable interpolation details.

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as codefreedom CLI
    participant Claude as Claude Code
    participant Proxy as LiteLLM Proxy
    participant Provider as AI Provider

    User->>CLI: cf cc --profile my-profile
    CLI->>CLI: Load env chain (.env → .env.secrets → system)
    CLI->>CLI: Resolve profile (inherits from default)
    CLI->>Claude: Launch with merged env vars
    Claude->>Proxy: POST /v1/chat/completions
    Proxy->>Proxy: Route by model name
    Proxy->>Provider: Forward request
    Provider-->>Proxy: Response
    Proxy-->>Claude: Response
    Claude-->>User: Result
```

## Image Supply Chain

Every published container image goes through a build → sign → verify pipeline before consumers can `docker pull` it.

```mermaid
flowchart LR
    A["Dockerfile + build context"] --> B["build job<br/>(push + cosign-sign)"]
    B --> C["docker.io + ghcr.io<br/>(image@digest)"]
    C --> D["verify job<br/>(cosign-verify)"]
    D --> E{"Signature valid<br/>and from this repo?"}
    E -->|yes| F["CI green"]
    E -->|no| G["CI red"]
```

### Composite Actions

The pattern is captured in two reusable composite actions so adding a new image family is a copy-paste of any `docker-*.yml` workflow:

- **`.github/actions/cosign-sign`** — `cosign sign --yes <image@digest>`. Caller logs in first.
- **`.github/actions/cosign-verify`** — `cosign verify` against the GitHub OIDC issuer and the repo identity regexp. Caller logs in first.

Both install cosign v2.4.1 via the official `sigstore/cosign-installer@v3`. No long-lived private key — the workflow run is the signer.

### Why a separate verify job

Splitting sign (in `build`) from verify (in `needs: build`) means a compromised image can't pass CI: a successful verify proves the published digest is reachable and the signature is valid against the repo's OIDC identity. A bad push fails verify, even though build/push/sign all succeeded.

### Consumer verification

```bash
cosign verify \
  --certificate-identity-regexp 'https://github.com/nilayparikh/codefreedom' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  ghcr.io/nilayparikh/codefreedom:cuda-latest
```

## Key Design Decisions

| Decision                         | Rationale                                                                                                                                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Single config home**           | All configuration lives in `~/.codefreedom` — profiles, proxy, sandbox                                                                                                                    |
| **Stateless proxy by default**   | Zero-config startup — no database, no Prisma, no migrations                                                                                                                               |
| **Profile inheritance**          | Custom profiles only need to override what differs from `default`                                                                                                                         |
| **Ephemeral sandbox containers** | No container-locking from shared reuse — each session gets a fresh container                                                                                                              |
| **Opt-in providers**             | Set an API key to enable; leave empty to disable                                                                                                                                          |
| **Proxy is Docker-only**         | The proxy always runs via `docker compose` against the self-hosted `codefreedom:litellm-latest` image (with the WebSearch count patch baked in). No host-side `litellm` install required. |
| **Env chain loading**            | `.env` → `.env.secrets` → system env — later overrides earlier                                                                                                                            |

## See Also

- [Proxy Overview](proxy/index.md) — provider list with per-model links
- [Providers](proxy/providers/index.md) — full provider configuration reference
- [Proxy Configuration](proxy/config.md) — model aliases, retry policy, fallbacks
- [Profiles](../guides/profiles.md) — Claude Code profile schema and inheritance
- [Code Agents](../guides/agents.md) — local vs sandbox mode
- [Browser Tools](../guides/tools/index.md) — Chrome and web tool profiles
