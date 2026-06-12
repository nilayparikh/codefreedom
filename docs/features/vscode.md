---
title: VS Code
description: Use CodeFreedom's proxy inside VS Code — two methods, no third-party extensions required.
---

# VS Code

Use your CodeFreedom proxy inside VS Code. Two methods — pick whichever fits your workflow.

## Method 1: Built-in (No Extension Required)

VS Code's built-in Copilot Chat supports custom OpenAI-compatible endpoints. CodeFreedom generates the config for you.

### Step 1: Start the Proxy

```bash
codefreedom run proxy start
codefreedom run proxy status
```

### Step 2: Generate the Config

```bash
# On the same machine as VS Code
codefreedom setup config vscode proxy config --host localhost

# On a different machine (LAN/VPN)
codefreedom setup config vscode proxy config --host 192.168.1.42
```

This prints a JSON fragment to stdout.

### Step 3: Add to VS Code

Open VS Code's `chatLanguageModels.json` and append the generated entry:

```jsonc
[
  // ... existing entries ...
  {
    "name": "CodeFreedom",
    "vendor": "customendpoint",
    "apiKey": "${input:codefreedom.litellm.master_key}",
    "apiType": "chat-completions",
    "models": [ ... ]
  }
]
```

### Step 4: Wire the Master Key

1. In VS Code, run **"Add Secret Input"** command
2. Use the key name: `codefreedom.litellm.master_key`
3. Paste your `LITELLM_MASTER_KEY` value

VS Code substitutes it at runtime — the secret never lands in the file.

## Method 2: Claude Code Extension

The [Claude Code VS Code extension](https://marketplace.visualstudio.com/items?itemName=Anthropic.claude-code) from Anthropic runs Claude Code inside VS Code. CodeFreedom generates a `settings.json` fragment.

### Step 1: Generate

```bash
codefreedom setup config vscode claude config              # Default profile
codefreedom setup config vscode claude config --profile ultra   # Specific profile
codefreedom setup config vscode claude config --host proxy.lan --port 4000  # Remote proxy
```

### Step 2: Merge into VS Code

Open **Preferences: Open User Settings (JSON)** and merge the output.

### Secret Safety

The generator replaces secrets with `${env:VARNAME}` references. Set the real values as system environment variables:

```bash
# Linux / macOS — add to ~/.bashrc or ~/.zshrc
export ANTHROPIC_AUTH_TOKEN="sk-your-key-here"
```

Then **fully restart VS Code** so it picks up the env vars.

## Which Method to Choose

| | Built-in | Claude Code Extension |
|---|---------|----------------------|
| Extension needed | No | Yes (Claude Code) |
| Works with | Any VS Code chat | Claude Code in VS Code |
| Setup | One JSON file | settings.json merge |
| Model access | All proxy models | Profile-based |
