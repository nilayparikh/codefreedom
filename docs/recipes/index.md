---
title: Recipes
description: Pre-configured setups for different use cases.
---

Recipes are pre-configured setups that define which providers, secrets, and tools are included.

## Available Recipes

| Recipe | Description |
| --- | --- |
| `costeffective-coding` | Full setup with cloud providers (Azure, OpenRouter, OpenCode Zen) |
| `costeffective-coding-with-local` | Same as above + local model backends via LiteLLM |

## Apply a Recipe

```bash
cf setup init --plan-and-apply <recipe-name>
```

Or with short alias:

```bash
cf s i -pa <recipe-name>
```

Example:

```bash
cf s i -pa costeffective-coding-with-local
```

## What Happens

1. CodeFreedom clones the recipe from the remote store
2. Generates a plan showing which files will be created/updated
3. Applies the plan after confirmation
4. Reports which secrets are set and which are missing

## After Applying

Run the setup script to configure your API keys:

```bash
bash ~/.codefreedom/scripts/<recipe-name>/setup-secrets.sh
```
