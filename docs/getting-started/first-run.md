---
title: First Run
description: Three commands to get Claude Code talking to an AI model.
---

# First Run

Three commands. No editing required — defaults work out of the box.

## Step 1: Initialize Config

```bash
codefreedom --init
```

This creates config files in `~/.codefreedom/`. You don't need to edit anything yet.

**Output:**

```
[claude init] [CREATE] ~/.codefreedom/profiles/claude-code.json
[claude init] [CREATE] ~/.codefreedom/profiles/claude-code.schema.json
[claude init] [CREATE] ~/.codefreedom/.env.claude
[claude init] [CREATE] ~/.codefreedom/.env.claude.secrets

[claude init] Done -- 4 created.
[proxy init] [CREATE] ~/.codefreedom/proxy/config/config.yaml
[proxy init] [CREATE] ~/.codefreedom/proxy/docker-compose.yaml
[proxy init] [CREATE] ~/.codefreedom/.env.proxy
[proxy init] [CREATE] ~/.codefreedom/.env.proxy.secrets
...

[proxy init] Done -- 12 created.
[init] Done.
```

If you run it again, it skips (won't overwrite existing files):

```
[claude init] Config already exists — init only bootstraps clean directories.
```

## Step 2: Start the Proxy

```bash
codefreedom proxy start
```

This pulls and starts the proxy Docker container. First run takes a moment to pull the image.

Wait for:

```
[OK] Proxy ready at http://localhost:4000
```

Check it's running:

```bash
codefreedom proxy status
```

## Step 3: Launch Claude Code

```bash
codefreedom claude
```

You're now in Claude Code, routed through your proxy. Try switching models:

```bash
codefreedom claude --profile ultra    # strongest model
codefreedom claude --profile air      # fastest, lightweight
codefreedom claude --list-profiles    # see all profiles
```

## What Happened

- `codefreedom --init` wrote profile and proxy config files
- `codefreedom proxy start` brought up the proxy container
- `codefreedom claude` loaded your profile, pointed Claude Code at `localhost:4000`

## Stop the Proxy

```bash
codefreedom proxy stop
```

The proxy is independent of Claude Code sessions. Leave it running between sessions, or stop it to free resources.

## Next Steps

- **[Profiles](../features/claude-code.md#profiles)** — switch models with one flag
- **[Free models](../recipes/providers/opencode-zen/index.md)** — try models without spending credits
- **[Sandbox mode](../features/claude-code.md#sandbox-mode)** — isolated Docker containers
