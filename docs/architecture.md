# Architecture

CodeFreedom is a CLI tool that provides a unified interface for code agents with LLM routing, sandboxing, and profile management. All configuration is managed from `~/.codefreedom`.

## Bird's-Eye View

```mermaid
graph TD
    CLI["<b>codefreedom CLI</b><br/>cf / codefreedom"]

    CLI -->|"codefreedom --init"| INIT["Initialize ~/.codefreedom/<br/>profiles + proxy configs"]
    CLI -->|"codefreedom claude"| CLAUDE["Code Agent Launcher"]
    CLI -->|"codefreedom proxy"| PROXY["LLM Proxy"]

    subgraph "Profile System"
        PROFILES["claude-code.json<br/>Profile definitions"]
        PROFILES -->|default| P_DEFAULT["Flash model<br/>(built-in)"]
        PROFILES -->|bare| P_BARE["Minimal<br/>(built-in)"]
        PROFILES -->|"custom (pro, ultra, …)"| P_CUSTOM["User-created<br/>profiles"]
    end

    subgraph "Execution Modes"
        CLAUDE --> NATIVE["Native Mode<br/>Host claude CLI"]
        CLAUDE --> SANDBOX["Sandbox Mode<br/>Docker + GPU"]
        NATIVE --> PROFILES
        SANDBOX --> PROFILES
    end

    subgraph "Sandbox Images<br/>(ghcr.io/nilayparikh/codefreedom)"
        SANDBOX --> IMG_CUDA["CUDA<br/>NVIDIA GPUs"]
        SANDBOX --> IMG_ROCM["ROCm<br/>AMD GPUs"]
        SANDBOX --> IMG_UBUNTU["Ubuntu<br/>General purpose"]
    end

    subgraph "LLM Proxy"
        PROXY --> UP["docker compose up<br/>localhost:4000"]
        PROXY --> DOWN["docker compose down"]
        PROXY --> VALIDATE["Validate config"]
        UP --> ROUTER["Model Router"]
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
├── --init              # Bootstrap ~/.codefreedom/
├── claude (cc)         # Launch code agent
│   ├── --profile       # Model profile
│   ├── --sandbox       # Docker container
│   ├── --native-models # Bypass proxy
│   ├── --stop          # Stop containers
│   ├── --status        # Container status
│   └── --list-profiles # List profiles
└── proxy (px)          # Manage LLM proxy
    ├── --up            # Start proxy (native)
    ├── --up --docker   # Start via Docker Compose
    ├── --down          # Stop proxy
    ├── --status        # Proxy status
    └── --validate      # Validate config
```

## Configuration Flow

```mermaid
flowchart LR
    subgraph "Environment Loading"
        ENV[".env file"]
        SECRETS[".env.secrets file"]
        SYS["System env vars"]
    end

    subgraph "Profile Resolution"
        PROF["claude-code.json"]
        DEFAULT["default profile"]
        CUSTOM["custom profile"]
        MERGED["Merged env dict"]
    end

    subgraph "Execution"
        CLAUDE_EXEC["Launch Claude Code<br/>with merged env"]
    end

    ENV --> MERGED
    SECRETS --> MERGED
    SYS --> MERGED
    PROF --> DEFAULT --> MERGED
    PROF --> CUSTOM --> MERGED
    MERGED --> CLAUDE_EXEC
```

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

## Key Design Decisions

| Decision                         | Rationale                                                                    |
| -------------------------------- | ---------------------------------------------------------------------------- |
| **Single config home**           | All configuration lives in `~/.codefreedom` — profiles, proxy, sandbox       |
| **Stateless proxy by default**   | Zero-config startup — no database, no Prisma, no migrations                  |
| **Profile inheritance**          | Custom profiles only need to override what differs from `default`            |
| **Ephemeral sandbox containers** | No container-locking from shared reuse — each session gets a fresh container |
| **Opt-in providers**             | Set an API key to enable; leave empty to disable                             |
| **Docker is optional**           | Proxy runs natively or via Docker Compose; Docker only required for sandbox  |
| **Env chain loading**            | `.env` → `.env.secrets` → system env — later overrides earlier               |
