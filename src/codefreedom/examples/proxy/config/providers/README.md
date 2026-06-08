# Provider Configs

Each YAML file in this directory defines models for one provider. They are included by `config.yaml` and loaded by the LiteLLM proxy at startup.

> **New to LiteLLM?** Start with [`understanding-litellm.md`](../understanding-litellm.md) — it explains every field in these YAML files, how the proxy routes requests, and how CodeFreedom uses each feature.

## Philosophy

**Every model entry is commented out.**

There are no active (uncommented) models in any provider file. This keeps the examples minimal, readable, and free of stale specs. Every file is a template — copy, uncomment, and adapt.

### Why this way

**Model specs change constantly.** Context windows grow, pricing drops, model IDs get deprecated, and new models replace old ones. If we shipped a long list of every available model for every provider, every file would be outdated within weeks. We'd be maintaining stale specs instead of shipping features.

**The pattern is the point.** Each file shows 1-2 commented model entries that teach you the structure — `litellm_params`, `model_info`, `codefreedom.plugins`. From these examples you can add any model, because the shape is always the same.

**Less maintenance surface.** When DeepSeek changes their model names or Azure updates their pricing, we update comments in one file, not model specs across ten. That's the difference between a config we can keep correct and one we can't.

**The user's actual model list is theirs, not ours.** Every project needs different models. We provide the *template*; users uncomment and customize what they need. Starting from a clean commented base is easier than deleting stale entries from a long list.

### How to Enable a Provider

1. **Set the API key** in `~/.codefreedom/.env.proxy.secrets`:
   ```bash
   PROVIDER_API_KEY="your-key-here"
   ```
2. **Uncomment the model block** in the provider's YAML file — remove the `# ` prefix from every line of the model entry you want to enable.
3. **Make sure the include is active** in `~/.codefreedom/proxy/config/config.yaml`:
   ```yaml
   include:
     - providers/deepseek.yaml
   ```
4. **Restart** the proxy:
   ```bash
   codefreedom proxy restart
   ```

### How to Add More Models

1. Copy one of the commented model blocks in the provider's YAML file as a template.
2. Change `model_name`, `model`, and `model_info.id` to match your model.
3. Adjust `context_window`, `max_tokens` and `max_input_tokens` to the model's documented specs.
4. If the model supports reasoning, add a `codefreedom.plugins.reasoning-efforts.rule` referencing a rule from `config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml`.
5. Add a new rule to the mapping YAML if one doesn't exist for your model.
6. Remove the `# ` prefix from every line (uncomment the block).

### How to Disable a Provider

Comment out the include line in `config.yaml`. If the API key is empty, LiteLLM skips the provider anyway — nothing phones home.

## Files

| File | Provider | Examples shown |
|------|----------|----------------|
| `deepseek.yaml` | DeepSeek API | V4-Flash + V4-Pro tier |
| `azure-foundry.yaml` | Azure Foundry | GPT-5.4 + GPT-5.4-Mini variant |
| `nvidia.yaml` | NVIDIA AI Endpoints | DeepSeek-V4-Flash + Kimi-K2.6 (different extra_body) |
| `opencode-zen.yaml` | OpenCode Zen | MiMo-V2.5-FREE + Nemotron-3-Ultra variant |
| `openrouter.yaml` | OpenRouter | Nemotron-3-Ultra + FreeRouter (dynamic endpoint) |
| `local.yaml` | Local self-hosted | Qwen3.6-27B + Qwen3.6-35B-A3B (different port) |
| `openai-compatible.yaml` | Generic OpenAI API | One fully-commented template |
| `anthropic-compatible.yaml` | Generic Anthropic API | One fully-commented template |
