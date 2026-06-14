# Troubleshooting

Start here when something isn't working. Run `cf manage doctor` first — it catches most common issues.

## Quick Diagnosis

```bash
cf manage doctor
```

This checks Docker, config files, profiles, ports, and tool status.

## Common Issues

### Docker daemon unavailable

**Symptom:** `Cannot connect to the Docker daemon`

**Fix:**

```bash
# Linux
sudo systemctl start docker

# macOS/Windows — start Docker Desktop
```

### Port conflicts

**Symptom:** `Port already in use` or proxy won't start

**Check:**

```bash
# Check what's using port 4000 (LiteLLM)
lsof -i :4000

# Check what's using port 9223 (Chrome DevTools)
lsof -i :9223
```

**Fix:** Stop the conflicting service or change the port in your tool profile.

### Invalid or missing API keys

**Symptom:** `AuthenticationError` or model calls fail

**Check:**

```bash
# Verify your .env file has the right keys
cat ~/.codefreedom/.env

# Check secrets
cat ~/.codefreedom/.env.secrets
```

**Fix:** Update the relevant `.env` file with valid API keys.

### Proxy startup failures

**Symptom:** `cf run proxy start` fails or proxy exits immediately

**Check:**

```bash
# Check proxy logs
docker logs codefreedom-litellm

# Check if compose file exists
ls ~/.codefreedom/proxy/docker-compose.yaml
```

**Fix:** Run `cf manage doctor` for specific diagnostics. Common causes:

- PostgreSQL data directory permission issues
- Port 4000 already in use
- Invalid proxy configuration

### Permission issues in ~/.codefreedom

**Symptom:** `Permission denied` errors

**Fix:**

```bash
# Fix ownership
sudo chown -R $(whoami) ~/.codefreedom

# Fix sandbox directory permissions (if using --run-as-me)
sudo chown -R 1000:1000 ~/.codefreedom/sandbox
```

### Image or cache issues

**Symptom:** Container fails to start or uses stale images

**Fix:**

```bash
# Pull latest images
docker pull docker.io/nilayparikh/codefreedom:latest

# Clear Docker cache
docker system prune
```

## When to Run `cf manage doctor`

Run `cf manage doctor` when:

- First setting up CodeFreedom
- After changing `.env` files
- After upgrading CodeFreedom
- When any agent fails to launch
- When proxy or tools won't start
- Before opening a bug report
