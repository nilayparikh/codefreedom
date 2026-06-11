# MiMo Code fails to call locally hosted Qwen models via LiteLLM proxy

## Summary

MiMo Code cannot use locally hosted Qwen models and many other models (e.g., `Qwen3.6-35B-A3B`). The request fails with a Jinja chat template error: **"System message must be at the beginning"**.

Other IDEs (e.g., OpenCode, Cursor) work fine with the same proxy configuration.

## Steps to Reproduce

1. Set up a Qwen model (e.g., `Qwen3.6-35B-A3B`) configured with `chat_template_kwargs: { enable_thinking: true }`
2. Configure MiMo Code to use the proxy via `@ai-sdk/openai-compatible`
3. Send any request to the model

## Actual Behavior

MiMo Code returns an `AI_APICallError` with HTTP 400. The LiteLLM proxy logs:

```
litellm.BadRequestError: OpenAIException - Unable to generate parser for this template.
Automatic parser generation failed:
While executing CallExpression at line 119, column 32 in source:
...first %}↵            {{- raise_exception('System message must be at the beginnin...
Error: Jinja Exception: System message must be at the beginning..
```

## Root Cause

MiMo Code sends **multiple `system` role messages** in a single request. For example, when generating a conversation title, the request contains:

```json
{
  "messages": [
    {"role": "system", "content": "You are a title generator..."},
    {"role": "system", "content": "# Memory system\n\nYou have a persistent file-based memory system..."},
    {"role": "user", "content": "Generate a title for this conversation:"},
    {"role": "user", "content": "What is this model?"}
  ]
}
```

The model's Jinja chat template enforces a strict rule: **only one system message is allowed, and it must be the first message**. When multiple system messages are present, the template parser throws an exception.

### Why Other IDEs Work

Mostly other IDEs/Code Agents typically:
- Send only a single system message
- Merge system-level instructions into one message
- Use models with more permissive chat templates

### Reproduction via cURL

**Fails (two system messages):**
```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3.6-35B-A3B",
    "max_tokens": 100,
    "messages": [
      {"role": "system", "content": "You are a title generator."},
      {"role": "system", "content": "Memory system instructions."},
      {"role": "user", "content": "hi"}
    ]
  }'
```

Response: HTTP 400 — `"System message must be at the beginning"`

**Works (single system message):**
```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3.6-35B-A3B",
    "max_tokens": 100,
    "messages": [
      {"role": "system", "content": "You are a title generator."},
      {"role": "user", "content": "hi"}
    ]
  }'
```

Response: HTTP 200 — successful completion

## Environment

- **MiMo Code version:** latest
- **Provider config:** `@ai-sdk/openai-compatible` pointing to LiteLLM proxy at `http://localhost:4000/v1`
- **LiteLLM config:** Model `Qwen3.6-35B-A3B` with `chat_template_kwargs: { enable_thinking: true }`
- **Backend:** Local inference server (llama.cpp / vLLM) serving `qwen3.6_35b_a3b`

## Suggested Fixes

### Option 1: Merge system messages in MiMo Code (Recommended)

Before sending requests, MiMo Code should concatenate multiple system messages into a single system message:

```json
{
  "role": "system",
  "content": "You are a title generator...\n\n# Memory system\n\n..."
}
```

### Option 2: LiteLLM callback to merge system messages

Add a LiteLLM callback that merges multiple system messages before forwarding to the backend:

```python
# In litellm config or custom callback
def merge_system_messages(messages):
    system_msgs = [m for m in messages if m["role"] == "system"]
    other_msgs = [m for m in messages if m["role"] != "system"]
    if len(system_msgs) > 1:
        merged = {"role": "system", "content": "\n\n".join(m["content"] for m in system_msgs)}
        return [merged] + other_msgs
    return messages
```

### Option 3: Update model chat template

Modify the Qwen model's Jinja chat template to accept multiple system messages by concatenating them internally.

### Option 4: Use a model with permissive template

Switch to a model variant that supports multiple system messages (e.g., some GGUF quantizations ship with patched templates).

## Impact

This blocks MiMo Code from using locally hosted Qwen models entirely. Users who run self-hosted inference for cost or privacy reasons cannot use MiMo Code with these models.

## Workaround

None available without modifying either MiMo Code's message construction or the model's chat template.

## Fix (CodeFreedom LiteLLM Plugin)

A LiteLLM callback plugin (`system_message_merger`) has been implemented that automatically merges multiple system messages into a single message before forwarding to the backend.

### Files Changed

- `docker/litellm/plugins/system_message_merger.py` — Plugin implementation
- `docker/litellm/Dockerfile.LiteLLM` — Bake plugin into image
- `docker/litellm/entrypoint.sh` — Symlink plugin at startup
- `recipes/costeffective-coding-with-local/proxy/config/config.yaml` — Register callback
- `recipes/costeffective-coding-with-local/proxy/config/providers/local.yaml` — Enable per-model
- `recipes/costeffective-coding-with-local/proxy/config/plugins/system-message-merger/system-message-merger.yaml` — Plugin config

### How It Works

1. Plugin intercepts requests via `async_pre_request_hook` / `async_log_pre_api_call`
2. Counts system messages in the request
3. If 2+ system messages exist, merges them into a single message with `\n\n` separator
4. Only activates for models with `codefreedom.plugins.system-message-merger.enabled: true`

### Configuration

Per-model opt-in in `local.yaml`:

```yaml
codefreedom:
  plugins:
    system-message-merger:
      enabled: true
```

Or global opt-in in the plugin YAML:

```yaml
models:
  - Qwen3.6-27B
  - Qwen3.6-35B-A3B
```

### Rebuild Required

The Docker image must be rebuilt to include the plugin:

```bash
docker build \
  --build-arg IMAGE_VERSION=0.2.0 \
  -t docker.io/nilayparikh/codefreedom:litellm-latest \
  -f docker/litellm/Dockerfile.LiteLLM docker/litellm/
```
