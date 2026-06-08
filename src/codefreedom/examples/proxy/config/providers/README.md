# Provider Configs

Each YAML file in this directory defines models for one provider. They are included by `config.yaml` and loaded by the LiteLLM proxy at startup.

## Philosophy

**One active model per file. Everything else is a commented example.**

Every provider file follows this pattern:

- **1 uncommented model** — the one that works immediately once you set the API key in `.env.proxy.secrets`.
- **1-2 commented examples** — patterns showing how to add more models. Uncomment and adapt.
- **Two exceptions** — `openai-compatible.yaml` and `anthropic-compatible.yaml` are blank templates (every deployment is different), so the entire file is commented. Copy, uncomment, adapt.

### Why this way

**Model specs change constantly.** Context windows grow, pricing drops, model IDs get deprecated, and new models replace old ones. If we shipped a long list of every available model for every provider, every file would be outdated within weeks. We'd be maintaining stale specs instead of shipping features.

**The pattern is the point.** One working model teaches you the structure — `litellm_params`, `model_info`, `codefreedom.plugins`. The commented example shows one variation — different `extra_body`, different `model_info` caps, a different reasoning-effort rule. From these two examples you can add any model, because the shape is always the same.

**Less maintenance surface.** When DeepSeek changes their model names or Azure updates their pricing, we update one active entry in each file, not ten. That's the difference between a config we can keep correct and one we can't.

**The user's actual model list is theirs, not ours.** Every project needs different models. We provide the *template*; users add what they need. Starting from a minimal, correct base is easier than deleting stale entries from a long list.

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

That's it. The uncommented model in each file works as soon as you set the key.

### How to Add More Models

1. Uncomment the example block in the provider's YAML file, or copy the active model as a template.
2. Change `model_name`, `model`, and `model_info.id` to match your model.
3. Adjust `context_window`, `max_tokens` and `max_input_tokens` to the model's documented specs.
4. If the model supports reasoning, add a `codefreedom.plugins.reasoning-efforts.rule` referencing a rule from `config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml`.
5. Add a new rule to the mapping YAML if one doesn't exist for your model.

### How to Disable a Provider

Comment out the include line in `config.yaml`. If the API key is empty, LiteLLM skips the provider anyway — nothing phones home.

## Files

| File | Provider | Active Model |
|------|----------|-------------|
| `deepseek.yaml` | DeepSeek API | DeepSeek-V4-Flash |
| `azure-foundry.yaml` | Azure Foundry | GPT-5.4 |
| `nvidia.yaml` | NVIDIA AI Endpoints | DeepSeek-V4-Flash |
| `opencode-zen.yaml` | OpenCode Zen | MiMo-V2.5-FREE |
| `openrouter.yaml` | OpenRouter | Nemotron-3-Ultra (free) |
| `local.yaml` | Local self-hosted | Qwen3.6-27B |
| `openai-compatible.yaml` | Generic OpenAI API | (blank template) |
| `anthropic-compatible.yaml` | Generic Anthropic API | (blank template) |
