# CLI Reference

Complete command reference for `codefreedom` / `cf`.

## Command Structure

```
cf <command> [action|target] [options]

# Agent Commands
cf agent <name> [options] [-- <agent-args>]  # Launch agent
cf agent list                                 # List agents

# Configuration
cf config <target> [options]                  # Unified config
cf setup init [-p/-a/-l/--pa]               # Initialize recipes

# Lifecycle
cf proxy start|stop|restart|status|validate   # Manage proxy (alias: px)
cf tools start|stop|restart|status            # Manage tools

# Admin
cf admin backup|restore|list|inspect|prune    # Config management (alias: adm)
cf doctor [--verbose]                         # Validate environment
cf update [--services...]                     # Check for updates
cf deinit [--force]                           # Tear down
```

## Agent Commands

```bash
cf agent <name> [options] [-- <agent-args>]
cf agent list

# Supported agents: claude, mimo

# Options:
--profile NAME        Load a named profile (default: 'default')
--sandbox             Run inside Docker container
--run-as-me           Match host uid/gid in sandbox
--list-profiles       List available profiles and exit
```

## Configuration Commands

```bash
# Claude config (shell exports)
cf config claude [--profile NAME] [--out FILE] [--bash|--ps]

# MiMo config (mimocode.json)
cf config mimo [--profile NAME] [--out FILE]

# VS Code config
cf config vscode claude [--host HOST] [--port PORT] [--out PATH]
cf config vscode proxy --host HOST [--port PORT] [--name NAME] [--out PATH]
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
cf proxy start [--port PORT] [--host HOST]
cf proxy stop
cf proxy restart
cf proxy status
cf proxy validate
```

## Tools Commands

```bash
cf tools [start|stop|restart|status]       # Default: status
```

## Admin Commands

```bash
cf admin backup [--out PATH] [--profile NAME] [--passphrase SEC]
cf admin restore PATH [--dry-run] [--force]
cf admin list
cf admin inspect PATH
cf admin prune [--keep N] [--older-than 30d]
```

## Other Commands

```bash
cf doctor [--verbose]                      # Validate environment
cf update [services...]                    # Check for updates
cf deinit [--force]                        # Tear down
```

## Aliases

| Command | Alias |
|---------|-------|
| `proxy` | `px` |
| `admin` | `adm` |

## Deprecated Commands

| Deprecated | Replacement |
|------------|-------------|
| `cf claude` | `cf agent claude` |
| `cf mimo` | `cf agent mimo` |
| `cf vscode` | `cf config vscode` |
