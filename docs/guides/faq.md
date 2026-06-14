# Frequently Asked Questions

## General

### What is CodeFreedom?

CodeFreedom is a unified CLI for code agents. It provides LLM proxy routing, Docker sandboxing, profile management, and browser tools — all configured from `~/.codefreedom`.

### Which agents are supported?

- **Claude Code** (`cf r ag cc` / `cf r ag cc`) — Anthropic's coding agent
- **MiMoCode** (`cf r ag mc` / `cf r ag mc`) — Xiaomi's coding agent
- **OpenCode** (`cf r ag oc` / `cf r ag oc`) — Terminal-native AI coding agent

### Local vs sandbox mode — what's the difference?

**Local mode** runs the agent directly on your host machine. Simple, fast, no Docker required.

**Sandbox mode** (`--sandbox`) runs the agent inside an ephemeral Docker container. Provides isolation, GPU passthrough, and clean sessions.

```bash
# Local
cf r ag cc

# Sandbox
cf r ag cc --sandbox
```

## Proxy

### When do I need the proxy?

The proxy is needed when:

- You want to route through a LiteLLM proxy for model management
- You want WebSearch interception (local stealth search)
- You want automatic model discovery for MiMoCode/OpenCode

You do NOT need the proxy for:

- Direct Anthropic API usage with Claude Code
- Local model inference without routing

### How do I switch providers or models?

1. Edit your profile: `~/.codefreedom/profiles/claude-code.yaml`
2. Or use a recipe: `cf s i -l` then `cf s i -pa <recipe-name>`

## Configuration

### How do profiles work?

Profiles define environment variables, tools, and sandbox settings per agent. They're stored in `~/.codefreedom/profiles/`.

```yaml
profiles:
  default:
    env:
      ANTHROPIC_API_KEY: sk-ant-...
    tools:
      - chrome
      - web
  production:
    inherits: default
    env:
      ANTHROPIC_API_KEY: sk-ant-prod-...
```

### Can I use multiple API keys?

Yes. Use profiles to switch between keys:

```bash
cf r ag cc --profile dev        # uses dev profile's keys
cf r ag cc --profile production # uses production profile's keys
```

## Tools

### What tools are available?

- **Chrome** — Chrome DevTools MCP server for browser automation
- **Web** — Camoufox-backed web search and browsing
- **GitHub** — GitHub MCP integration
- **Web Bridge** — Translates WebSearch requests for the proxy

### How do browser tools fit into the flow?

Browser tools run as Docker containers alongside your agent session. They're auto-managed:

- Started when your agent session begins
- Stopped when your session ends (if no other sessions use them)
- Shared across multiple concurrent sessions
