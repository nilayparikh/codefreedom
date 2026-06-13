---
title: Proxy
description: Self-hosted LiteLLM proxy with embedded PostgreSQL for model routing.
---

# Proxy

A self-hosted LiteLLM proxy with embedded PostgreSQL. One local endpoint routes to any LLM provider.

## Quick Start

```bash
# Full commands
cf run proxy start               # Start the proxy
cf run proxy status              # Check status
cf run proxy stop                # Stop the proxy
cf run proxy restart             # Restart
cf run proxy validate            # Validate config

# Short aliases
cf r px start
cf r px status
cf r px stop
cf r px restart
cf r px validate
```

## How It Works

```
Agent → localhost:4000 → LiteLLM Proxy → AI Model
```

Your agent talks to `localhost:4000`. The proxy routes the request to whichever model you configured. Change the model? Edit your proxy config. No agent changes needed.

## Configuration

Proxy config lives in `~/.codefreedom/proxy/`:

```
~/.codefreedom/proxy/
├── config/
│   ├── config.yaml              # LiteLLM config
│   ├── providers/               # Provider configs
│   │   ├── openai.yaml
│   │   ├── anthropic.yaml
│   │   └── ...
│   └── model-alias/             # Model aliases
│       └── alias.yaml
├── .env                         # Proxy environment
├── .env.secrets                 # API keys
└── docker-compose.yml           # Docker Compose
```

### Adding API Keys

Edit `~/.codefreedom/proxy/.env.secrets`:

```bash
# Add your keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
```

Restart the proxy to pick up changes:

```bash
cf run proxy restart
# or
cf r px restart
```

### Model Aliases

Model aliases let you use short names for models. Edit `~/.codefreedom/proxy/config/model-alias/alias.yaml`:

```yaml
- litellm_alias_name: "gpt-4o"
  litellm_params:
    model: "gpt-4o"
    api_base: "https://api.openai.com"
```

Now your agent can request `gpt-4o` and the proxy routes it correctly.

## Docker Compose

The proxy runs in Docker. The compose file is at `~/.codefreedom/proxy/docker-compose.yml`.

### Custom Port

```bash
cf run proxy start --port 8080
# or
cf r px start -p 8080
```

### Custom Host Bind

```bash
cf run proxy start --host 127.0.0.1
# or
cf r px start --host 127.0.0.1
```

## Troubleshooting

### Proxy Won't Start

```bash
# Check Docker
docker ps

# Check logs
docker logs codefreedom-proxy

# Validate config
cf run proxy validate
# or
cf r px validate
```

### Model Not Found

```bash
# Check available models
curl http://localhost:4000/v1/models

# Check proxy logs
docker logs codefreedom-proxy
```

### API Key Issues

```bash
# Check secrets file
cat ~/.codefreedom/proxy/.env.secrets

# Validate config
cf run proxy validate
# or
cf r px validate
```

## Command Reference

### `cf run proxy`

```
usage: codefreedom run proxy [-h] [-p PORT] [--host HOST] {start,status,stop,restart,validate} ...

positional arguments:
  start                 Start the proxy (Docker Compose)
  status                Show proxy status
  stop                  Stop the proxy
  restart               Restart the proxy
  validate              Validate proxy configuration

options:
  -h, --help            show this help message and exit
  -p, --port PORT       Port to publish on the host
  --host HOST           Host bind address
```
