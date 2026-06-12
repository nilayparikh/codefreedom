---
title: First Run
description: Three commands to get Claude Code talking to an AI model.
---

# First Run

Three commands. No editing required — defaults work out of the box.

## Step 1: Install a Recipe

```bash
cf setup init
```

This applies the **`_default` base recipe** — it creates profiles, proxy config,
env files, and Docker Compose files in `~/.codefreedom/`.

Recipes use intelligent structural merging via DeepDiff, so running a recipe
again (or a different recipe on top) merges changes without overwriting your
existing settings.

**Output (first run):**

```
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
```

## Step 2: Start the Proxy

```bash
codefreedom run proxy start
```

This pulls and starts the proxy Docker container. First run takes a moment to pull the image.

Wait for:

```
[OK] Proxy ready at http://localhost:4000
```

Check it's running:

```bash
codefreedom run proxy status
```

## Step 3: Launch Claude Code

```bash
codefreedom run agent claude
```

You're now in Claude Code, routed through your proxy. Try switching models:

```bash
codefreedom run agent claude --profile ultra    # strongest model
codefreedom run agent claude --profile air      # fastest, lightweight
codefreedom run agent claude --list-profiles    # see all profiles
```

## What Happened

- `cf setup init` applied the `_default` recipe (profiles, proxy config, env files)
- `codefreedom run proxy start` brought up the proxy container
- `codefreedom run agent claude` loaded your profile, pointed Claude Code at `localhost:4000`

## Stop the Proxy

```bash
codefreedom run proxy stop
```

The proxy is independent of Claude Code sessions. Leave it running between sessions, or stop it to free resources.

## Next Steps

- **[Profiles](../features/claude-code.md#profiles)** — switch models with one flag
- **[Free models](../recipes/providers/opencode-zen/index.md)** — try models without spending credits
- **[Sandbox mode](../features/claude-code.md#sandbox-mode)** — isolated Docker containers
