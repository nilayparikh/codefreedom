# Provider Configs

Each YAML file in this directory defines models for one provider. They are included by `config.yaml` and loaded by the LiteLLM proxy at startup.

## Philosophy

**One working model per file. Everything else is commented out.**

This keeps the examples small, readable, and easy to maintain. Model specs, pricing, and capabilities change over time — a minimal active config means there's less to go stale.

### How to Enable a Provider

1. **Set the API key** in `~/.codefreedom/.env.proxy.secrets`:
   ```bash
   PROVIDER_API_KEY="your-key-here"
   ```
2. **Make sure the include is active** in `~/.codefreedom/proxy/config/config.yaml`:
   ```yaml
   include:
     - providers/deepseek.yaml
   ```
3. **Restart** the proxy:
   ```bash
   codefreedom proxy restart
   ```

That's it. Each file ships with one model already uncommented — it works as soon as you set the key.

### How to Add More Models

1. Uncomment the block for the model you want, or copy the active model as a template.
2. Change `model_name`, `model`, and `model_info.id`.
3. Adjust `context_window`, `max_tokens` and `max_input_tokens` to match the model's specs.
4. If the model supports reasoning, add a `codefreedom.plugins.reasoning-efforts.rule` referencing a rule from `config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml`.

### How to Disable a Provider

Comment out the include line in `config.yaml`. If the API key is empty, LiteLLM skips the provider anyway — nothing phones home.

## Files

| File | Provider | Active Model |
|------|----------|-------------|
| `deepseek.yaml` | DeepSeek API | DeepSeek-V4-Flash |
| `azure-foundry.yaml` | Azure Foundry | GPT-5.4 |
| `nvidia.yaml` | NVIDIA AI Endpoints | DeepSeek-V4-Flash |
| `opencode-zen.yaml` | OpenCode Zen | Nemotron-3-Ultra-FREE |
| `openrouter.yaml` | OpenRouter | Nemotron-3-Ultra (free) |
| `local.yaml` | Local self-hosted | Qwen3.6-27B, Qwen3.6-35B-A3B |
| `openai-compatible.yaml` | Generic OpenAI API | (template) |
| `anthropic-compatible.yaml` | Generic Anthropic API | (template) |
