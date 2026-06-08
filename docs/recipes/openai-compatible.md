---
title: OpenAI Compatible
description: Connect any OpenAI-compatible endpoint to your proxy.
---

# OpenAI Compatible

Connect any service that speaks the OpenAI `/v1/chat/completions` API — local models, custom deployments, third-party providers.

## Step 1: Add the Provider

Edit `~/.codefreedom/proxy/config/providers/openai-compatible.yaml`:

```yaml
model_list:
  - model_name: "MyCustom/Model"
    openai_api_base: "https://your-api.example.com/v1"
    openai_api_key: "${YOUR_API_KEY}"
    litellm_additional_model_kwargs:
      temperature: 0.7
```

## Step 2: Add the API Key

Edit `~/.codefreedom/.env.proxy.secrets`:

```bash
YOUR_API_KEY="your-key-here"
```

## Step 3: Enable the Provider

In `~/.codefreedom/proxy/config/config.yaml`:

```yaml
include:
  - providers/openai-compatible.yaml
```

## Step 4: Restart

```bash
codefreedom proxy restart
```

## Common Use Cases

### Local Ollama

```yaml
model_list:
  - model_name: "Local/Llama"
    openai_api_base: "http://localhost:11434/v1"
    openai_api_key: "not-needed"
```

### Custom Deployment

```yaml
model_list:
  - model_name: "Custom/Mixtral"
    openai_api_base: "https://api.my-deployment.com/v1"
    openai_api_key: "${MY_DEPLOY_KEY}"
```

## Use It

```bash
export LITELLM_MODEL_ALIAS_PRO="MyCustom/Model"
codefreedom claude --profile pro
```
