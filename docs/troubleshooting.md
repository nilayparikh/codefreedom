# Troubleshooting

## Proxy Won't Start

### "litellm package not installed"

```
[ERROR] litellm package not installed.
   Install: pip install codefreedom[litellm]
```

**Cause:** Running `codefreedom proxy start` (native mode) without the LiteLLM dependency.

**Fix:**

```bash
pip install codefreedom[litellm]
```

Or use Docker Compose mode instead: `codefreedom proxy start --docker`.

### "Could not find docker-compose.yaml"

```
[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml
   Run: codefreedom proxy init
```

**Cause:** Proxy configs were not initialized.

**Fix:**

```bash
codefreedom proxy init
# If configs exist, init will skip. Delete them first, or merge manually.
```

### Port Already in Use

**Cause:** Another service is using port 4000.

**Fix:** Use a different port:

```bash
codefreedom proxy start --port 4001
```

### Auth Errors in Logs

LiteLLM logs failed authentication attempts at `ERROR` level — this is **normal**. Unauthenticated health checks or requests without the `Authorization` header appear as ERROR lines but the proxy is functioning correctly.

To reduce noise:

```bash
export LITELLM_LOG_LEVEL=WARNING
```

## Profile Issues

### "Profile not found"

```
[ERROR] Profile 'my-profile' not found in ~/.codefreedom/profiles/claude-code.json.
```

**Fix:** Check available profiles:

```bash
codefreedom claude --list-profiles
```

Then either use an existing profile or add your profile to `~/.codefreedom/profiles/claude-code.json`.

### Profile Not Applying Expected Model

**Checklist:**

1. Verify the profile exists: `codefreedom claude --list-profiles`
2. Check that the proxy is running and has the model configured
3. Verify model aliases point to an enabled provider:
   ```bash
   codefreedom proxy validate
   ```
4. Check env chain — a workspace `.env` may override the profile:
   ```bash
   # Look for [ENV] logs when launching
   codefreedom claude --profile bare 2>&1 | grep ENV
   ```

## Sandbox Issues

### "Failed to start container"

**Checklist:**

1. Is Docker running? `docker info`
2. Is the image pulled? `docker pull docker.io/nilayparikh/codefreedom:latest`
3. Check Docker logs for GPU driver issues

### GPU Passthrough Errors

Sandbox mode always uses `--gpus all`. If you have no GPU:

- **CUDA image:** Will fail without an NVIDIA GPU with the NVIDIA container toolkit installed.
- **ROCm image:** Will fail without an AMD GPU with ROCm support.
- **Ubuntu image:** Works without a GPU — use this for CPU-only workloads.

Select the Ubuntu image:

```bash
export CLAUDE_CODE_IMAGE_TAG=latest
codefreedom claude --sandbox
```

### "Docker not found"

**Cause:** Docker is not installed or not on PATH.

**Fix:** Install Docker from [docker.com](https://docs.docker.com/engine/install/).

## Claude Code Issues

### "Claude CLI not found"

```
[ERROR] Claude CLI not found.
   Install: npm install -g @anthropic-ai/claude-code
```

**Fix:**

```bash
npm install -g @anthropic-ai/claude-code
```

### How Do I Know Which Model I'm Using?

Check the profile and model alias chain:

```bash
# 1. See which env vars the profile sets
codefreedom claude --list-profiles

# 2. Check proxy model aliases
codefreedom proxy validate

# 3. List models available from the proxy
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

## Configuration Validation

Validate the entire proxy configuration:

```bash
codefreedom proxy validate
```

This checks:

- Provider files exist and are valid YAML
- Environment variables for API keys are set
- Model aliases are defined
- Database connection (warns if stateless)

## General Debugging

### See Full Environment Loading

All env and profile loading is logged to stderr:

```bash
codefreedom claude --profile bare 2>&1 | grep -E '\[ENV\]|\[PROFILE\]'
```

Output shows the load chain:

```
[ENV] Loading configuration...
  [ENV] Loaded config from ~/.codefreedom/.env
  [ENV] Loaded secrets from ~/.codefreedom/.env.secrets
[PROFILE] Loading 'pro' (inherits from 'default')...
     ANTHROPIC_BASE_URL=http://localhost:4000
     ANTHROPIC_AUTH_TOKEN=sk-****
     CLAUDE_MODEL=CodeFreedom/Pro
```

### Custom Profile Location

If profiles are not loading from the expected location, check:

```bash
echo $CODEFREEDOM_PROFILES_FILE
```

If set, profiles are loaded from this path instead of `~/.codefreedom/profiles/claude-code.json`.
