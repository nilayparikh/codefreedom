# CLI Reference

Complete command reference for `codefreedom` / `cf`.

## Command Structure

```
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
```

## Agent Commands

```bash
cf run agent <name> [options] [-- <agent-args>]
cf run agent list

# Supported agents: claude-code (cc), mimo-code (mc), open-code (oc)

# Options:
--profile NAME        Load a named profile (default: 'default')
--sandbox             Run inside Docker container
--run-as-me           Match host uid/gid in sandbox
--list-profiles       List available profiles and exit
```

## Configuration Commands

```bash
# VS Code config
cf setup config vscode claude [--host HOST] [--port PORT] [--out PATH]
cf setup config vscode proxy --host HOST [--port PORT] [--name NAME] [--out PATH]
```

## Init Command

```bash
cf setup init                              # Install _default base recipe
cf setup init -l                           # List recipes
cf setup init -p NAME                      # Preview a recipe
cf setup init -pa NAME                     # Plan + apply interactively (prompts to confirm)
cf setup init -a PLAN_ID                   # Apply a plan
cf setup init --store URL                  # Custom recipe store
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

## Aliases

| Command | Alias |
|---------|-------|
| `cf run proxy` | `cf r px` |
| `cf run agent claude-code` | `cf r ag cc` |
| `cf run agent mimo-code` | `cf r ag mc` |
| `cf run agent open-code` | `cf r ag oc` |
| `cf run tools` | `cf r tl` |
| `cf manage admin` | `cf m ad` |
| `cf manage doctor` | `cf m dr` |
| `cf manage update` | `cf m up` |
| `cf setup init` | `cf s i` |
| `cf setup config` | `cf s c` |
| `cf setup deinit` | `cf s di` |

## Deprecated Commands

| Deprecated | Replacement |
|------------|-------------|
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
