---
title: Azure Foundry
description: GPT-5.4 family via Azure Foundry — GPT-5.4, Mini, Nano.
---

# Azure Foundry

Microsoft's GPT-5.4 family through Azure Foundry.

## Models Available

| Model | Description |
|-------|-------------|
| GPT-5.4 | Full model — best reasoning |
| GPT-5.4-Mini | Smaller, faster |
| GPT-5.4-Nano | Lightweight, mechanical tasks |

## Step 1: Get an API Key

1. Sign up at [Foundry](https://foundry.azure.com)
2. Create a project and get your API key

## Step 2: Add the Key

Edit `~/.codefreedom/.env.proxy.secrets`:

```bash
MICROSOFT_FOUNDRY_API_KEY="your-key-here"
```

## Step 3: Enable Models

In `~/.codefreedom/proxy/config/config.yaml`, make sure the Azure Foundry provider is included:

```yaml
include:
  - providers/azure-foundry.yaml
```

## Step 4: Restart

```bash
codefreedom proxy restart
```

## Use It

Set model aliases in `~/.codefreedom/.env.proxy`:

```bash
LITELLM_MODEL_ALIAS_ULTRA="Azure/GPT-5.4"
LITELLM_MODEL_ALIAS_PRO="Azure/GPT-5.4"
LITELLM_MODEL_ALIAS_FLASH="Azure/GPT-5.4-Mini"
LITELLM_MODEL_ALIAS_AIR="Azure/GPT-5.4-Nano"
```

Then:

```bash
codefreedom claude --profile ultra    # GPT-5.4
codefreedom claude --profile air     # GPT-5.4-Nano
```
