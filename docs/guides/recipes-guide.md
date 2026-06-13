# Recipes Guide

Recipes are pre-built configuration templates that set up CodeFreedom for specific providers and use cases.

## Recipe Sources

### Bundled Recipes

These ship with the CodeFreedom repository under `recipes/`. They cover common provider setups:

- **DeepSeek** — DeepSeek API configuration
- **Azure Foundry** — Azure OpenAI setup
- **NVIDIA** — NVIDIA NIM endpoints
- **OpenRouter** — OpenRouter multi-provider routing
- **OpenAI Compatible** — Generic OpenAI-compatible endpoints
- **Anthropic Compatible** — Generic Anthropic-compatible endpoints
- **Local** — Local model inference (Ollama, etc.)

### External Recipes

Additional recipes are available from the recipe store at [github.com/nilayparikh/codefreedom-recipes](https://github.com/nilayparikh/codefreedom-recipes). These are community-maintained and cover more specialized setups.

## Working with Recipes

### List Available Recipes

```bash
cf init --list
```

Shows both bundled and available store recipes.

### Preview a Recipe

```bash
cf init --plan <recipe-name>
```

Shows what the recipe would change without applying it.

### Apply a Recipe

```bash
cf init
```

Applies the default base recipe. Or specify one:

```bash
cf init --plan deepseek
```

## Recipe Structure

Each recipe contains:

- **Environment variables** — API keys, endpoints, model settings
- **Profile configuration** — Agent-specific settings
- **Proxy configuration** — LiteLLM routing rules

Recipes merge with your existing configuration. They never overwrite your `.env.user` file — that's reserved for your personal overrides.

## Creating Custom Recipes

See the [recipe store documentation](https://github.com/nilayparikh/codefreedom-recipes) for details on creating your own recipes.
