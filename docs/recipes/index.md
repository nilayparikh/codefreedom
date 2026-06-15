---
title: Recipes
description: Pre-built configurations for common workflows.
---

Pre-built configurations for common workflows.

## Available Recipes

| Recipe | Description | Command |
| --- | --- | --- |
| `_default` | Base recipe with all providers | `cf setup init` |
| `costeffective-coding` | Cloud-only models, no local | `cf setup init --plan costeffective-coding` |
| `costeffective-coding-with-local` | Cloud + local models | `cf setup init --plan costeffective-coding-with-local` |

## List Recipes

```bash
cf setup init --list
# or
cf s i -l
```

## Install a Recipe

```bash
# Install default
cf setup init
# or
cf s i

# Plan + apply in one step (prompts for confirmation)
cf setup init --plan-and-apply costeffective-coding
# or
cf s i -pa costeffective-coding

# Two-step: preview first, then apply separately
cf setup init --plan costeffective-coding
cf s i -p costeffective-coding
```

## How Recipes Work

Recipes are YAML manifests that define:

- **Profiles** — model configurations
- **Proxy config** — LiteLLM settings
- **Docker Compose** — container definitions
- **Environment** — variables and secrets

They use intelligent structural merging via DeepDiff, so running a recipe again (or a different recipe on top) merges changes without overwriting your existing settings.

## Custom Recipe Store

```bash
# Use a custom GitHub URL
cf setup init --store https://github.com/user/recipes
# or
cf s i -s https://github.com/user/recipes

# Use a local folder
cf setup init --store /path/to/recipes
# or
cf s i -s /path/to/recipes
```

## Staging Branch

```bash
cf setup init --staging
# or
cf s i --staging
```
