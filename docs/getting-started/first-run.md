---
title: First Run
description: Three commands to get Claude Code talking to an AI model.
---

Three commands. No editing required — defaults work out of the box.

## Step 1: Install a Recipe

```bash
cf setup init
```

Short alias: `cf s i`

This applies the **`_default` base recipe** — it creates profiles, proxy config,
env files, and Docker Compose files in `~/.codefreedom/`.

Recipes use intelligent structural merging via DeepDiff, so running a recipe
again (or a different recipe on top) merges changes without overwriting your
existing settings.

**Output (first run):**

```text
[recipe] Installing recipe '_default'...
[recipe] [CREATE] ~/.codefreedom/profiles/claude-code.json
[recipe] [CREATE] ~/.codefreedom/profiles/claude-code.schema.json
[recipe] [CREATE] ~/.codefreedom/.env.claude
[recipe] [CREATE] ~/.codefreedom/.env.claude.secrets
[recipe] [CREATE] ~/.codefreedom/.env.proxy
[recipe] [CREATE] ~/.codefreedom/.env.proxy.secrets
[recipe] Done — 6 created.
```

See available recipes:

```bash
cf setup init --list
# or
cf s i -l
```

## Step 2: Start the Proxy

```bash
cf run proxy start
# or
cf r px start
```

This pulls and starts the proxy Docker container. First run takes a moment to pull the image.

Wait for:

```text
[OK] Proxy ready at http://localhost:4000
```

Check it's running:

```bash
cf run proxy status
# or
cf r px status
```

## Step 3: Launch an Agent

```bash
cf run agent claude-code
# or
cf r ag cc
```

You're now in Claude Code, routed through your proxy. Try switching models:

```bash
cf run agent claude-code --profile ultra    # strongest model
cf run agent claude-code --profile air      # fastest, lightweight
cf run agent claude-code --list-profiles    # see all profiles
```

Short aliases:

```bash
cf r ag cc -p ultra    # cf run agent claude-code --profile ultra
cf r ag cc -l          # cf run agent claude-code --list-profiles
```

## Available Agents

| Agent | Full name | Alias | Command |
| --- | --- | --- | --- |
| Claude Code | `claude-code` | `cc` | `cf r ag cc` |
| MiMo Code | `mimo-code` | `mc` | `cf r ag mc` |
| OpenCode | `open-code` | `oc` | `cf r ag oc` |

## What Happened

- `cf setup init` applied the `_default` recipe (profiles, proxy config, env files)
- `cf run proxy start` brought up the proxy container
- `cf run agent claude-code` loaded your profile, pointed Claude Code at `localhost:4000`

## Stop the Proxy

```bash
cf run proxy stop
# or
cf r px stop
```

The proxy is independent of agent sessions. Leave it running between sessions, or stop it to free resources.

## Next Steps

- **[Profiles](../features/claude-code.md#profiles)** — switch models with one flag
- **[Free models](../recipes/providers/opencode-zen/index.md)** — try models without spending credits
- **[Sandbox mode](../features/claude-code.md#sandbox-mode)** — isolated Docker containers
