---
description: Free model endpoints -- what they offer, what to watch out for, and how to use them safely.
---

# Free Models

Free model endpoints let you get started without paying for API credits. This page covers where to find them, what trade-offs to expect, and how to use them safely.

## Why Free Models Matter

Free endpoints lower the barrier to experimentation. They're great for:

- Testing CodeFreedom profiles and proxy routing before committing to a paid provider.
- Running non-sensitive tasks (public repos, open-source projects, learning).
- Prototyping workflows before scaling to paid tiers with better rate limits.

## Free Endpoint Providers

### OpenRouter Free Tier

[OpenRouter](https://openrouter.ai/) offers a selection of free-tier models alongside its paid catalog. Free models are marked with `:free` in the model identifier.

| Model                                                                  | Identifier                                          | Notes                                    |
| ---------------------------------------------------------------------- | --------------------------------------------------- | ---------------------------------------- |
| [Nemotron-3-Ultra-550B-A55B](../recipes/providers/openrouter/index.md) | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | Large context, vision support            |
| [FreeRouter](../recipes/providers/openrouter/index.md)                 | `openrouter/openrouter/free`                        | Auto-routes to best available free model |

**Setup:** Requires a free OpenRouter account and API key. Set `OPENROUTER_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.

**CodeFreedom config:** See [OpenRouter provider docs](../recipes/providers/openrouter/index.md).

### OpenCode Zen

[OpenCode Zen](https://opencode.ai/zen) provides free-tier models through an OpenAI-compatible API. You need a free account and API key — sign up at [opencode.ai/auth](https://opencode.ai/auth). Free models are subject to quota and rate limiting.

| Model                                                                | Identifier                      | Notes                                             |
| -------------------------------------------------------------------- | ------------------------------- | ------------------------------------------------- |
| [MiMo-V2.5-FREE](../recipes/providers/opencode-zen/index.md)         | `openai/mimo-v2.5-free`         | Xiaomi, 1M context, vision + reasoning            |
| [Nemotron-3-Super-FREE](../recipes/providers/opencode-zen/index.md)  | `openai/nemotron-3-super-free`  | NVIDIA, 262K, text-only                           |
| [Nemotron-3-Ultra-FREE](../recipes/providers/opencode-zen/index.md)  | `openai/nemotron-3-ultra-free`  | NVIDIA, 1M context, vision                        |
| [DeepSeek-V4-Flash-FREE](../recipes/providers/opencode-zen/index.md) | `openai/deepseek-v4-flash-free` | 1M context, 384K output, fast inference           |
| [Big-Pickle](../recipes/providers/opencode-zen/index.md)             | `openai/big-pickle`             | 262K, general purpose, text-only                  |
| [MiniMax-M3-FREE](../recipes/providers/opencode-zen/index.md)        | `minimax/minimax-m3-free`       | 512K context, vision + reasoning, internal parser |

**Setup:** Sign up at [opencode.ai/auth](https://opencode.ai/auth), copy your API key, and set `OPENCODE_ZEN_API_KEY` in `~/.codefreedom/.env.proxy.secrets`. Free models don't require a paid balance but are subject to rate limits and quotas.

**CodeFreedom config:** See [OpenCode Zen provider docs](../recipes/providers/opencode-zen/index.md).

### NVIDIA Free Endpoints

[NVIDIA](https://build.nvidia.com/explore/discover) offers free serverless API endpoints for select foundation models. You need a free NVIDIA account and API key from [build.nvidia.com](https://build.nvidia.com) — no billing required to access free endpoints.

| Model                                                     | Identifier                             | Notes                         |
| --------------------------------------------------------- | -------------------------------------- | ----------------------------- |
| [DeepSeek-V4-Flash](../recipes/providers/nvidia/index.md) | `openai/deepseek-ai/deepseek-v4-flash` | 1M context, 384K output       |
| [DeepSeek-V4-Pro](../recipes/providers/nvidia/index.md)   | `openai/deepseek-ai/deepseek-v4-pro`   | 1M context, strong reasoning  |
| [GLM-5.1](../recipes/providers/nvidia/index.md)           | `openai/z-ai/glm-5.1`                  | 204K, multilingual, reasoning |
| [Kimi-K2.6](../recipes/providers/nvidia/index.md)         | `openai/moonshotai/kimi-k2.6`          | 256K, vision, thinking mode   |
| [Step-3.7-Flash](../recipes/providers/nvidia/index.md)    | `stepfun-ai/step-3.7-flash`            | 262K, vision, fast            |

**Setup:** Sign up at [build.nvidia.com](https://build.nvidia.com), get your free API key, and set `NVIDIA_API_KEY` in `~/.codefreedom/.env.proxy.secrets`. Free endpoints are subject to rate limits.

**CodeFreedom config:** See [NVIDIA provider docs](../recipes/providers/nvidia/index.md).

### Local Models

Running models locally is the ultimate in privacy and control. No data leaves your machine. The two pre-configured entries in `local.yaml` map to `CodeFreedom/Pro` and `CodeFreedom/Air`.

| Model                                                  | Port | Identifier               | Notes                   |
| ------------------------------------------------------ | ---- | ------------------------ | ----------------------- |
| [Qwen3.6-27B](../recipes/providers/local/index.md)     | 8000 | `openai/qwen3.6_27b`     | Primary, 131K context   |
| [Qwen3.6-35B-A3B](../recipes/providers/local/index.md) | 8001 | `openai/qwen3.6_35b_a3b` | Secondary, 262K context |

**Inference servers** (any of these works with the local provider):

| Tool                              | Description                                       |
| --------------------------------- | ------------------------------------------------- |
| [Ollama](https://ollama.com/)     | Local inference server with OpenAI-compatible API |
| [LM Studio](https://lmstudio.ai/) | GUI for local models with API server              |
| [vLLM](https://docs.vllm.ai/)     | High-throughput serving for self-hosted models    |

**Setup:** Point CodeFreedom's local provider at your inference server. See [Local provider docs](../recipes/providers/local/index.md).

## What to Watch Out For

Free endpoints are subsidized for a reason. Before sending sensitive code, understand the trade-offs.

### Data Logging and Retention

Most free providers log requests for operational purposes (abuse prevention, rate limiting, debugging). Some may:

- **Retain conversation data** -- your prompts and responses may be stored for days, months, or indefinitely.
- **Use inputs for model training** -- some providers explicitly reserve the right to use free-tier inputs to improve their models.
- **Share data with third parties** -- check whether logs are accessible to partners, advertisers, or researchers.

**What to do:** Read the provider's privacy policy and terms of service. Look for sections on "data retention," "training data," and "request logging." If the policy is unclear, assume your inputs are retained.

### Rate Limits and Reliability

Free tiers impose constraints to manage cost:

- **Rate limits** -- requests per minute/hour, often stricter than paid tiers.
- **No SLA** -- free endpoints can go down without notice.
- **Model changes** -- the model behind a free endpoint may change without warning.
- **Queue times** -- free requests may be deprioritized during peak load.

**What to do:** Don't rely on free endpoints for time-sensitive work. Have a paid or local fallback configured.

### Security Considerations

- **Code exposure** -- assume any code you send to a free endpoint is visible to the provider's infrastructure.
- **API key safety** -- never send real API keys, secrets, or credentials in prompts to free endpoints.
- **Sensitive projects** -- use local models or paid providers with explicit data privacy guarantees for proprietary code.

**What to do:** Use sandbox mode (`--sandbox`) to isolate sessions. Use local models for sensitive work. Strip secrets from code before sending to external endpoints.

### Quality Variance

Free models may be:

- **Smaller or quantized** -- reduced capability compared to paid counterparts.
- **Outdated** -- not the latest version of a model.
- **Inconsistent** -- quality may vary as providers rotate models behind the same endpoint.

**What to do:** Evaluate output quality for your use case. Switch to a paid tier when quality matters.

## Safe Usage Checklist

Before using a free endpoint, verify:

- [ ] I've read the provider's privacy policy and terms of service.
- [ ] I understand what data is logged and for how long.
- [ ] I know whether inputs may be used for model training.
- [ ] I've removed all secrets, API keys, and sensitive data from my prompts.
- [ ] I'm comfortable with the provider potentially seeing my code.
- [ ] I have a fallback provider configured in case the free endpoint goes down.

## Using Free Models with CodeFreedom

Free models use the same provider YAML pattern as paid providers. The only difference is the model identifier and API key.

1. **Enable the provider** -- uncomment the models in the provider YAML file.
2. **Set the API key** -- use the key from your provider (OpenRouter, OpenCode Zen, NVIDIA, etc.).
3. **Start the proxy** -- `codefreedom run proxy start`.
4. **Launch** -- `codefreedom run agent claude` routes through your configured free models.

See [Providers](../recipes/providers/index.md) for the full provider configuration guide.

## When to Upgrade to Paid

Consider a paid provider when you need:

- **Data privacy guarantees** -- explicit "no training on your data" policies.
- **Reliability** -- SLAs, uptime guarantees, consistent rate limits.
- **Quality** -- access to the latest, most capable models.
- **Scale** -- higher throughput for production workflows.

CodeFreedom makes switching trivial -- change the provider YAML, update your env file, restart the proxy.

## Provider Privacy Policies

| Provider             | Privacy Policy                                                          | Key Points                                                  |
| -------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------- |
| OpenRouter           | [Privacy Policy](https://openrouter.ai/privacy)                         | Logs requests for routing; check free-tier terms            |
| OpenCode Zen         | [Terms](https://opencode.ai/)                                           | Requires account + API key; review data retention policies  |
| NVIDIA               | [Privacy Statement](https://www.nvidia.com/en-us/about-nvidia/privacy/) | Free endpoints require API key; review terms for data usage |
| Local (Ollama, etc.) | N/A                                                                     | No external data transmission -- most private option        |

> **Note:** Privacy policies change. Always check the current policy before relying on a free endpoint.

## See Also

- [Providers Overview](../recipes/providers/index.md) -- enabling, disabling, and adding providers.
- [Proxy Configuration](../features/proxy.md) -- LiteLLM proxy setup.
