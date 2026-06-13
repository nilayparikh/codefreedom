# CodeFreedom CLI — Command Reference

Version: auto-detected at runtime (`cf -v`)

---

## Quick Reference

```
cf -v                            Show version and system info
cf s i                          Initialize (install _default recipe)
cf s i -pa <recipe>             Plan + apply a recipe (interactive)
cf s i -l                       List available recipes
cf px start                     Start the LLM proxy
cf cc                           Launch Claude Code agent
cf m dr                         Run diagnostics
```

---

## setup (s) — One-time setup and configuration

### cf setup init (cf s i)

Initialize CodeFreedom configuration via recipes. Without flags, installs the `_default` base recipe.

```
cf s i                              Install _default base recipe
cf s i -pa <name>                   Plan and apply a recipe (interactive preview + confirm)
cf s i -p <name>                    Preview a recipe (generate .patch files, no apply)
cf s i -a <plan-id>                 Apply a previously generated plan
cf s i -l                           List available recipes from the store
cf s i --store <url-or-path>        Use a custom recipe store (GitHub URL or local folder)
cf s i --staging                    Use recipes from the 'staging' branch
```

### cf setup config (cf s c)

Generate shell environment configuration for targets.

```
cf s c list                         List available config targets
cf s c claude                       Generate exports for Claude Code
cf s c claude --profile NAME        Use a specific profile
cf s c claude --out FILE            Write to file instead of stdout
cf s c claude --bash                Force bash format
cf s c claude --powershell          Force PowerShell format
cf s c mimo                         Generate config for MiMo Code
cf s c vscode                       Generate VS Code settings
```

### cf setup deinit (cf s di)

Tear down CodeFreedom: stop containers and remove config.

```
cf s di                             Interactive teardown (asks for confirmation)
cf s di -f                          Force teardown (skip confirmation)
```

---

## run (r) — Daily workflows

### cf run agent (cf r ag)

Launch coding agents.

```
cf r ag cc                          Launch Claude Code
cf r ag mc                          Launch MiMo Code
cf r ag oc                          Launch OpenCode
cf r ag list                        List available agents
cf r ag cc --sandbox                Launch Claude Code in Docker sandbox
cf r ag cc -- <args>                Pass extra args to the agent
```

### cf run proxy (cf r px)

Manage the LLM proxy (LiteLLM via Docker Compose).

```
cf r px start                       Start the proxy
cf r px start -p PORT               Start on a custom host port
cf r px start --host ADDR           Bind to a specific host address
cf r px stop                        Stop the proxy
cf r px restart                     Restart the proxy
cf r px status                      Show proxy status
cf r px validate                    Validate proxy configuration
```

### cf run tools (cf r tl)

Manage auxiliary tools (Chrome, web search, GitHub MCP, web bridge).

```
cf r tl status                      Show tool status (default)
cf r tl start                       Start all tools
cf r tl stop                        Stop all tools
cf r tl restart                     Restart all tools
cf r tl -c                          Include Chrome only
cf r tl -w                          Include Web search only
cf r tl -g                          Include GitHub MCP only
cf r tl --web-bridge                Include Web bridge only
```

---

## manage (m) — Occasional maintenance

### cf manage doctor (cf m dr)

Validate the full CodeFreedom environment.

```
cf m dr                             Run all checks
cf m dr -v                          Show detailed info for all checks
```

### cf manage update (cf m up)

Check Docker images and PyPI package for updates.

```
cf m up                             Check all services
cf m up sandbox                     Check sandbox image only
cf m up proxy                       Check proxy image only
cf m up tools                       Check tool images only
```

### cf manage admin (cf m ad)

Backup, restore, list, inspect, and prune configuration.

```
cf m ad backup                      Create a backup archive
cf m ad backup --out PATH           Backup to explicit path
cf m ad restore --in PATH           Interactive restore with diff preview
cf m ad restore --in PATH --dry-run Diff preview only
cf m ad restore --in PATH --force   Skip confirmation
cf m ad list-backups                List all backups
cf m ad inspect PATH                Inspect a backup archive
cf m ad prune --keep N              Keep N most recent backups
cf m ad prune --older-than 30d      Delete backups older than duration
```

---

## Global Flags

```
-v, --version                       Show version, Python, Docker, and dependency info
-h, --help                          Show help for a command
```
