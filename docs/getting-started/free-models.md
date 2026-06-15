---
title: Free Models
description: Try models without spending credits.
---

Try models without spending credits.

## Available Free Models

| Model | Provider | Command |
| --- | --- | --- |
| DeepSeek R1 | OpenCode | `cf run agent claude-code --profile bare` |
| DeepSeek V3 | OpenCode | `cf run agent claude-code --profile air` |
| Qwen3.6-27B | Local | `cf run agent claude-code --profile local` |

## Quick Start

```bash
# Use DeepSeek R1 (free)
cf run agent claude-code --profile bare
# or
cf r ag cc -p bare

# Use DeepSeek V3 (free)
cf run agent claude-code --profile air
# or
cf r ag cc -p air

# Use local Qwen3.6-27B (free)
cf run agent claude-code --profile local
# or
cf r ag cc -p local
```

## How It Works

Free models are configured in your proxy. When you use a profile, the proxy routes requests to the appropriate provider.

## Limitations

- **Rate limits** — free tiers have usage limits
- **Queue times** — free models may have longer wait times
- **Model versions** — free models may not be the latest versions

## Next Steps

- **[Proxy](../features/proxy.md)** — configure your own models
- **[Recipes](../recipes/index.md)** — pre-built configurations
