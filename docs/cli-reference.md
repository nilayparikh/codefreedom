# CLI Reference

Complete command reference for `codefreedom` / `cf`.

## Command Structure

```text
cf <command> [action|target] [options]

# Agent Commands
cf run agent <name> [options] [-- <agent-args>]  # Launch agent
cf run agent list                                 # List agents

# Configuration
cf setup config <target> [options]                  # Unified config
cf setup init [-p/-a/-l/--pa]               # Initialize recipes

# Lifecycle
cf run proxy start|stop|restart|status|validate   # Manage proxy (alias: px)
cf run tools start|stop|restart|status            # Manage tools

# Admin
cf manage admin backup|restore|list|inspect|prune    # Config management (alias: adm)
cf manage doctor [--verbose]                         # Validate environment
cf manage update [--services...]                     # Check for updates
cf setup deinit [--force]                           # Tear down

# Git workflows
cf git cmt [options] [files]                        # LLM-powered commit (alias: g c)
cf git pr create|generate [options]                 # LLM-powered PR (alias: g p)
```

## Agent Commands

```bash
cf run agent <name> [options] [-- <agent-args>]
cf run agent list

# Supported agents: claude-code (cc), mimo-code (mc), open-code (oc), pi-code (pc), codex-code (cx)

# Options:
--profile NAME        Load a named profile (default: 'default')
--list-profiles       List available profiles and exit
```

## Configuration Commands

```bash
# Proxy config
cf setup config proxy --remote-url http://192.168.1.5:4000  # Remote proxy
cf setup config proxy --local             # Switch back to local
cf setup config proxy --bind 127.0.0.1    # Loopback-only bind

# Tool config
cf setup config tools chrome --remote-url http://192.168.1.5:9223  # Remote tool
cf setup config tools chrome --local      # Switch back to local
cf setup config tools chrome --bind 127.0.0.1  # Loopback-only bind

# Global bind address
cf setup config bind --address 0.0.0.0    # Default: all interfaces

# VS Code config
cf setup config vscode --host HOST [--port PORT] [--name NAME] [--out PATH]
```

## Init Command

```bash
cf setup init                              # Install _default base recipe
cf setup init -l                           # List recipes
cf setup init -p NAME                      # Preview a recipe
cf setup init -pa NAME                     # Plan + apply interactively (prompts to confirm)
cf setup init -a PLAN_ID                   # Apply a plan
cf setup init --store URL                  # Custom recipe store
cf setup init -f PATH                      # Write override.yaml copy to <PATH>/.cf.yaml
```

## Proxy Commands

```bash
cf run proxy start [--port PORT] [--host HOST]
cf run proxy stop
cf run proxy restart
cf run proxy status
cf run proxy validate
```

## Tools Commands

```bash
cf run tools [start|stop|restart|status]       # Default: status
cf run tools [-c] [-w] [-g] [--web-bridge]    # Filter by tool
```

## Admin Commands

```bash
cf manage admin backup [--out PATH] [--profile NAME] [--passphrase SEC]
cf manage admin restore PATH [--dry-run] [--force]
cf manage admin list
cf manage admin inspect PATH
cf manage admin prune [--keep N] [--older-than 30d]
```

## Other Commands

```bash
cf manage doctor [--verbose]                      # Validate environment
cf manage update [services...]                    # Check for updates
cf setup deinit [--force]                        # Tear down
```

## Git Commands

```bash
cf git cmt [options] [files]                     # LLM-powered commit workflow
cf git pr create [options]                       # Create PR via gh CLI
cf git pr generate [options]                     # Generate PR title/body only

# Options for git cmt:
-m, --message MSG      Provide commit message directly
-y, --yes              Auto-commit without confirmation
-n, --no-scope         Skip scope in conventional commit
-S, --signed           Sign commit with GPG
--no-sign              Don't sign this commit
--dry-run              Preview without committing
-s, --stage-only       Only commit manually staged changes

# Options for git pr:
-s, --source BRANCH    Source branch (default: current)
-t, --target BRANCH    Target branch (default: main)
-b, --browser-mode     Open browser instead of gh CLI
--dry-run              Preview without action
```

## Aliases

| Command | Alias |
|---|---|
| `cf run proxy` | `cf r px` |
| `cf run agent claude-code` | `cf r ag cc` |
| `cf run agent mimo-code` | `cf r ag mc` |
| `cf run agent open-code` | `cf r ag oc` |
| `cf run agent pi-code` | `cf r ag pc` |
| `cf run tools` | `cf r tl` |
| `cf manage admin` | `cf m ad` |
| `cf manage doctor` | `cf m dr` |
| `cf manage update` | `cf m up` |
| `cf setup init` | `cf s i` |
| `cf setup config` | `cf s c` |
| `cf setup deinit` | `cf s di` |
| `cf git` | `cf g` |
| `cf git cmt` | `cf g c` |
| `cf git pr` | `cf g p` |

## Deprecated Commands

| Deprecated | Replacement |
|---|---|
| `cf claude` | `cf r ag cc` |
| `cf mimo` | `cf r ag mc` |
| `cf opencode` | `cf r ag oc` |
| `cf vscode` | `cf s c vscode` |
| `cf proxy` | `cf r px` |
| `cf tools` | `cf r tl` |
| `cf admin` | `cf m ad` |
| `cf doctor` | `cf m dr` |
| `cf deinit` | `cf s di` |
| `cf config` | `cf s c` |
