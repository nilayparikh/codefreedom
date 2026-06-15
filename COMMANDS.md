# CodeFreedom CLI — Command Reference

Version: auto-detected at runtime (`cf -v`)

---

## Quick Reference

```text
cf -v                                Show version and system info
cf s i                              Initialize (install _default recipe)
cf s i -pa <recipe>                 Plan + apply a recipe (interactive)
cf s i -l                           List available recipes
cf r px start                       Start the LLM proxy
cf r ag cc                          Launch Claude Code agent
cf m dr                             Run diagnostics
```

---

## setup (s) — One-time setup and configuration

### cf setup init — `cf s i`

Initialize CodeFreedom configuration via recipes.

```text
cf s i                                Install _default base recipe
cf s i -pa <name>                     Plan and apply a recipe (interactive preview + confirm)
cf s i -p <name>                      Preview a recipe (generate .patch files, no apply)
cf s i -a <plan-id>                   Apply a previously generated plan
cf s i -l                             List available recipes from the store
cf s i --store <url-or-path>          Use a custom recipe store (GitHub URL or local folder)
cf s i --staging                      Use recipes from the 'staging' branch
```

|Flag|Long|Description|
|-----|-----|------------|
|`-p`|`--plan`|Preview mode: generate patches without applying|
|`-a`|`--apply`|Apply a previously generated plan by ID|
|`-pa`|`--plan-and-apply`|Plan + confirm + apply in one step|
|`-l`|`--list`|List all available recipes|
|`-s`|`--store`|Custom recipe store path or GitHub URL|
||`--staging`|Use staging branch of recipe store|

### cf setup config — `cf s c`

Generate configuration files. Currently supports VS Code only.

```text
cf s c vscode                         Generate chatLanguageModels.json for VS Code
cf s c vscode --host HOST             Proxy host address (default: localhost)
cf s c vscode --port PORT             Proxy port (default: 4000)
cf s c vscode --name NAME             VS Code profile name
cf s c vscode --out PATH              Write to file instead of stdout
```

|Flag|Long|Description|
|-----|-----|------------|
||`--host`|Proxy host address|
||`--port`|Proxy port number|
||`--name`|VS Code profile name|
||`--out`|Output file path|

### cf setup deinit — `cf s di`

Tear down CodeFreedom: stop containers and remove config.

```text
cf s di                               Interactive teardown (asks for confirmation)
cf s di -f                            Force teardown (skip confirmation)
```

|Flag|Long|Description|
|-----|-----|------------|
|`-f`|`--force`|Skip confirmation prompt|

---

## run (r) — Daily workflows

### cf run agent — `cf r ag`

Launch coding agents.

```text
cf r ag cc                            Launch Claude Code
cf r ag mc                            Launch MiMo Code
cf r ag oc                            Launch OpenCode
cf r ag list                          List available agents
cf r ag cc --sandbox                  Launch Claude Code in Docker sandbox
cf r ag cc -- <args>                  Pass extra args to the agent
```

|Flag|Long|Description|
|-----|-----|------------|
|`-p`|`--profile`|Load a named profile (default: 'default')|
|`-l`|`--list-profiles`|List available profiles and exit|
||`--sandbox`|Run inside a Docker container|
||`--run-as-me`|Run sandbox as host user (uid/gid match)|

**claude-code specific:**

|Flag|Description|
|-----|------------|
|`--cuda`|Use CUDA sandbox image for NVIDIA GPUs|
|`--rocm`|Use ROCm sandbox image for AMD GPUs|
|`--native-models`|Use native Anthropic models/auth|
|`--dangerously-skip-permissions`|Skip Claude Code permission prompts|

### cf run proxy — `cf r px`

Manage the LLM proxy (LiteLLM via Docker Compose).

```text
cf r px start                         Start the proxy
cf r px start -p PORT                 Start on a custom host port
cf r px start --host ADDR             Bind to a specific host address
cf r px stop                          Stop the proxy
cf r px restart                       Restart the proxy
cf r px status                        Show proxy status
cf r px validate                      Validate proxy configuration
```

|Subcommand|Description|
|-----------|------------|
|`start`|Start proxy via Docker Compose|
|`stop`|Stop all proxy containers|
|`restart`|Restart proxy containers|
|`status`|Show container status and ports|
|`validate`|Check config files and env vars|

### cf run tools — `cf r tl`

Manage auxiliary tools (Chrome, web search, GitHub MCP, web bridge).

```text
cf r tl status                        Show tool status (default)
cf r tl start                         Start all tools
cf r tl stop                          Stop all tools
cf r tl restart                       Restart all tools
cf r tl -c                            Include Chrome only
cf r tl -w                            Include Web search only
cf r tl -g                            Include GitHub MCP only
cf r tl --web-bridge                  Include Web bridge only
```

|Flag|Long|Description|
|-----|-----|------------|
|`-c`|`--chrome`|Include Chrome browser tool|
|`-w`|`--web`|Include Web search tool|
|`-g`|`--github`|Include GitHub MCP tool|
||`--web-bridge`|Include Web bridge tool|

|Subcommand|Description|
|-----------|------------|
|`status`|Show running/stopped state of each tool|
|`start`|Start selected (or all) tool containers|
|`stop`|Stop selected (or all) tool containers|
|`restart`|Restart selected (or all) tool containers|

---

## manage (m) — Occasional maintenance

### cf manage doctor — `cf m dr`

Validate the full CodeFreedom environment.

```text
cf m dr                               Run all checks
cf m dr -v                            Show detailed info for all checks
```

|Flag|Long|Description|
|-----|-----|------------|
|`-v`|`--verbose`|Show detailed info for all checks|

### cf manage update — `cf m up`

Check Docker images and PyPI package for updates.

```text
cf m up                               Check all services
cf m up sandbox                       Check sandbox image only
cf m up proxy                         Check proxy image only
cf m up tools                         Check tool images only
```

### cf manage admin — `cf m ad`

Backup, restore, list, inspect, and prune configuration.

```bash
cf m ad bu                            Create a backup archive
cf m ad bu --out PATH                 Backup to explicit path
cf m ad res <file>                    Interactive restore with diff preview
cf m ad res <file> --dry-run          Diff preview only
cf m ad res <file> --force            Skip confirmation
cf m ad ls                            List all backups
cf m ad ins <file>                    Inspect a backup archive
cf m ad pr --keep N                   Keep N most recent backups
cf m ad pr --older-than 30d           Delete backups older than duration
```

|Subcommand|Alias|Description|
|-----------|-----|------------|
|`backup`|`bu`|Create backup archive (auto-dumps PG if proxy running)|
|`restore`|`res`|Restore from backup (shows diff preview)|
|`list-backups`|`ls`|List all backup archives|
|`inspect`|`ins`|Show manifest of a backup archive|
|`prune`|`pr`|Remove old backups (never deletes last one)|

**backup flags:**

|Flag|Long|Description|
|-----|-----|------------|
||`--out`|Output path (default: `~/.codefreedom/backup/`)|
||`--profile`|Profile label for manifest|
||`--passphrase`|Encrypt archive with passphrase|
||`--skip-pg-dump`|Skip automatic PostgreSQL dump|

**restore flags:**

|Flag|Long|Description|
|-----|-----|------------|
||`--dry-run`|Show diff without applying|
|`-f`|`--force`|Skip confirmation|
||`--passphrase`|Decrypt encrypted backup|

**prune flags:**

|Flag|Long|Description|
|-----|-----|------------|
||`--keep`|Keep N most recent backups|
||`--older-than`|Delete backups older than duration (e.g. `30d`, `6m`, `12h`, `2w`)|

---

## Global Flags

```text
-v, --version                         Show version, Python, Docker, and dependency info
-h, --help                            Show help for a command
```

---

## Agent Aliases

|Alias|Canonical Name|Docker Image|
|------|---------------|--------------|
|`cc`|`claude-code`|`codefreedom:claude-code-latest`|
|`mc`|`mimo-code`|`codefreedom:mimo-code-latest`|
|`oc`|`open-code`|`codefreedom:open-code-latest`|

Bare names (`claude`, `mimo`, `opencode`) are invalid — always use hyphenated forms.
