PS C:\Users\nilayparikh> cf -h
usage: codefreedom [-h] {setup,run,manage} ...

Unified CLI for code agents.
LLM proxy routing, Docker sandboxing, profile management.

commands:
{setup,run,manage}
setup (s) One-time setup and configuration (init, config, deinit)
run (r) Daily workflows (agent, proxy, tools)
manage (m) Occasional maintenance (doctor, update, admin)
examples:
cf run agent claude-code Launch Claude Code agent
cf r ag cc Short form of above
cf r ag mc Launch MiMo Code agent
cf r proxy start Start the LLM proxy
cf setup init Initialize configuration
cf manage doctor Validate environment
PS C:\Users\nilayparikh> cf s i -p costeffective-coding
[STORE] Cloning <https://github.com/nilayparikh/codefreedom-recipes.git> -> C:\Users\nilayparikh\.codefreedom\stores\nilayparikh-codefreedom-recipes-main (branch: main)
[plan] Recipe: costeffective-coding (extends \_default)
[plan] Plan ID: 2KycV9tYrA
[plan] Files: C:\Users\nilayparikh\.codefreedom\plans\2KycV9tYrA/
[plan]
[plan] 17 new files
[plan] 0 files to replace
[plan] 0 unchanged (skipped)
[plan] 2 directories to create
[plan]
[plan] SOURCE DESTINATION
[plan] -------- ------------ ---------------------------------------------------------------------------
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\.env.claude.secrets
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\.env.proxy.secrets
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\.env.mimo.secrets
[plan] CREATE \_default C:\Users\nilayparikh\.codefreedom\profiles\chrome.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\profiles\mimo-code.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\profiles\opencode.yaml
[plan] CREATE \_default C:\Users\nilayparikh\.codefreedom\profiles\web.yaml
[plan] CREATE \_default C:\Users\nilayparikh\.codefreedom\profiles\github.yaml
[plan] CREATE \_default C:\Users\nilayparikh\.codefreedom\profiles\web-bridge.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\docker-compose.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\config.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\plugins\reasoning-efforts\reasoning-efforts-mapping.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\.env.opencode.secrets
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\profiles\claude-code.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\providers\azure-foundry.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\providers\opencode.yaml
[plan] CREATE costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\providers\openrouter.yaml
[plan] MKDIR recipe C:\Users\nilayparikh\.codefreedom\pg\data/
[plan] MKDIR recipe C:\Users\nilayparikh\.codefreedom\pg\backup/
[plan]
[plan] To apply: cf setup init --apply 2KycV9tYrA
[plan] To review: cat C:\Users\nilayparikh\.codefreedom\plans\2KycV9tYrA/<patch-file>.diff
PS C:\Users\nilayparikh> cf setup init --apply 2KycV9tYrA
[ADMIN] No running LiteLLM container found — skipping PostgreSQL dump.
[RECIPE] Backup: C:\Users\nilayparikh\.codefreedom\backup\codefreedom-backup-pre-apply-2KycV9tYrA-20260613-170858-govardhan.tar.gz
[RECIPE] Applying plan 2KycV9tYrA...
[CREATE] .env.claude.secrets
[CREATE] .env.proxy.secrets
[CREATE] .env.mimo.secrets
[CREATE] profiles/chrome.yaml
[CREATE] profiles/mimo-code.yaml
[CREATE] profiles/opencode.yaml
[CREATE] profiles/web.yaml
[CREATE] profiles/github.yaml
[CREATE] profiles/web-bridge.yaml
[CREATE] proxy/docker-compose.yaml
[CREATE] proxy/config/config.yaml
[CREATE] proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml
[CREATE] .env.opencode.secrets
[CREATE] profiles/claude-code.yaml
[CREATE] proxy/config/providers/azure-foundry.yaml
[CREATE] proxy/config/providers/opencode.yaml
[CREATE] proxy/config/providers/openrouter.yaml
[MKDIR] pg/data/
[MKDIR] pg/backup/

Created 2 mountable director(ies).
(Ownership mapping is handled automatically on this platform.)

[RECIPE] Plan applied — 17 file(s) updated.
PS C:\Users\nilayparikh> cf r px start
[PROXY] Starting LiteLLM via Docker Compose (C:\Users\nilayparikh\.codefreedom\proxy\docker-compose.yaml)...
[TOOLS] Ensuring tools are running...

[CHROME] --- Third-Party Notice ---
[CHROME] This container includes third-party components:
[CHROME] _Google Chrome / Chromium (Google LLC)
[CHROME]_ dumb-init (PID 1 supervisor) (Yelp, Inc.)
[CHROME]
[CHROME] CodeFreedom is not responsible for their behavior, security, or privacy practices.
[CHROME] ---
[CHROME] CDP port: 9222 MCP port: 9223
[CHROME] Using data dir: C:\Users\nilayparikh\.codefreedom\sandbox\tools\chrome
[CHROME] Image 'docker.io/nilayparikh/codefreedom:chrome-latest' not found locally, pulling...
[CHROME] Image pulled.
[CHROME] Starting container 'codefreedom-tools-chrome'...
[CHROME] Container started.
CDP debug URL: <http://127.0.0.1:9222>
MCP endpoint: <http://127.0.0.1:9223/mcp>
DevTools: devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9222

[WEB] --- Third-Party Notice ---
[WEB] This container includes third-party components:
[WEB] _Camoufox (stealth browser) (daijro)
[WEB]_ Firefox (Mozilla Foundation)
[WEB]
[WEB] CodeFreedom is not responsible for their behavior, security, or privacy practices.
[WEB]
[WEB] WARNING: The web scraping tool is designed for internal websites or permissible public infrastructure. DO NOT USE or REPURPOSE the tool beyond permissible use cases.
[WEB] ---
[WEB] Using data dir: C:\Users\nilayparikh\.codefreedom\sandbox\tools\web
[WEB] Image 'docker.io/nilayparikh/codefreedom:web-latest' not found locally, pulling...
[WEB] Image pulled.
[WEB] Starting container 'codefreedom-web'...
[WEB] Container started.
[WEB] Container started.
[WEB] MCP endpoint: <http://127.0.0.1:8420/mcp>

[GITHUB] --- Third-Party Notice ---
[GITHUB] This container includes third-party components:
[GITHUB] \* GitHub MCP Server (GitHub, Inc.)
[GITHUB]
[GITHUB] CodeFreedom is not responsible for their behavior, security, or privacy practices.
[GITHUB]
[GITHUB] WARNING: This tool requires a GITHUB*PERSONAL_ACCESS_TOKEN with appropriate repository permissions. Store the token securely in the profile's env section.
[GITHUB] ---
[ERROR] GITHUB_PERSONAL_ACCESS_TOKEN is not set.
Set it in ~/.codefreedom/profiles/github.yaml under env:
"env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp*..." }
[WEB-BRIDGE] Using data dir: C:\Users\nilayparikh\.codefreedom\sandbox\tools\web-bridge
[WEB-BRIDGE] Image 'docker.io/nilayparikh/codefreedom:web-bridge' not found locally, pulling...
[WEB-BRIDGE] Image pulled.
[WEB-BRIDGE] Starting container 'codefreedom-web-bridge'...
[WEB-BRIDGE] Container started.
[WEB-BRIDGE] Container started.
[WEB-BRIDGE] SearXNG endpoint: <http://127.0.0.1:8500/search>
[WEB-BRIDGE] Health: <http://127.0.0.1:8500/healthz>
[PROXY] Creating shared 'codefreedom' Docker network...
[PROXY] Network 'codefreedom' created.
[+] up 16/16
✔ Image docker.io/nilayparikh/codefreedom:litellm-latest Pulled 40.0s
✔ Container litellm-codefreedom-0000 Started 6.8s
[PROXY] Proxy started at <http://localhost:4000> (litellm-codefreedom-0000)

---

PS C:\Users\nilayparikh> cf s i -pa costeffective-coding
  [STORE] Cloning <https://github.com/nilayparikh/codefreedom-recipes.git> -> C:\Users\nilayparikh\.codefreedom\stores\nilayparikh-codefreedom-recipes-main (branch: main)
[PLAN] Recipe: costeffective-coding (extends _default)
[PLAN] Plan ID: 9HsXYijTkz
[PLAN] Files:   C:\Users\nilayparikh\.codefreedom\plans\9HsXYijTkz/
[PLAN]
[PLAN]   0 new files
[PLAN]   6 files to replace
[PLAN]   11 unchanged (skipped)
[PLAN]
[PLAN]            SOURCE       DESTINATION
[PLAN]   -------- ------------ ---------------------------------------------------------------------------
[PLAN]   REPLACE  costeffectiv C:\Users\nilayparikh\.codefreedom\.env.claude.secrets
[PLAN]   REPLACE  costeffectiv C:\Users\nilayparikh\.codefreedom\.env.proxy.secrets
[PLAN]   REPLACE  costeffectiv C:\Users\nilayparikh\.codefreedom\.env.mimo.secrets
[PLAN]   SAME_default     C:\Users\nilayparikh\.codefreedom\profiles\chrome.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\profiles\mimo-code.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\profiles\opencode.yaml
[PLAN]   SAME     _default     C:\Users\nilayparikh\.codefreedom\profiles\web.yaml
[PLAN]   SAME_default     C:\Users\nilayparikh\.codefreedom\profiles\github.yaml
[PLAN]   REPLACE  _default     C:\Users\nilayparikh\.codefreedom\profiles\web-bridge.yaml
[PLAN]   REPLACE  costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\docker-compose.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\config.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\plugins\reasoning-efforts\reasoning-efforts-mapping.yaml
[PLAN]   REPLACE  costeffectiv C:\Users\nilayparikh\.codefreedom\.env.opencode.secrets
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\profiles\claude-code.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\providers\azure-foundry.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\providers\opencode.yaml
[PLAN]   SAME     costeffectiv C:\Users\nilayparikh\.codefreedom\proxy\config\providers\openrouter.yaml
[PLAN]
[PLAN] To apply:  cf s i -a 9HsXYijTkz
[PLAN] Quick:     cf s i -pa costeffective-coding
[PLAN] To review: cat C:\Users\nilayparikh\.codefreedom\plans\9HsXYijTkz/<patch-file>.diff

[RECIPE] Apply this plan? [y/N] y
  [STORE] Cloning <https://github.com/nilayparikh/codefreedom-recipes.git> -> C:\Users\nilayparikh\.codefreedom\stores\nilayparikh-codefreedom-recipes-main (branch: main)
[RECIPE] Installing base recipe '_default' first...
  [SAME]  .env.claude.secrets
  [SAME]  .env.proxy.secrets
  [MERGE] .env.mimo.secrets
  [SKIP]  profiles/chrome.yaml (auto-merge safe)
  [MERGE] profiles/mimo-code.yaml
  [SKIP]  profiles/opencode.yaml (auto-merge safe)
  [SKIP]  profiles/web.yaml (auto-merge safe)
  [SKIP]  profiles/github.yaml (auto-merge safe)
  [MERGE] profiles/web-bridge.yaml
  [MERGE] proxy/docker-compose.yaml
  [MERGE] proxy/config/config.yaml
  [MERGE] proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml

  Recipe applied — 6 file(s) created/updated.
  [SAME]  .env.claude.secrets
  [SAME]  .env.proxy.secrets
  [SAME]  .env.mimo.secrets
  [SAME]  .env.opencode.secrets
  [SKIP]  profiles/claude-code.yaml (auto-merge safe)
  [MERGE] profiles/mimo-code.yaml
  [SKIP]  profiles/opencode.yaml (auto-merge safe)
  [MERGE] proxy/docker-compose.yaml
  [MERGE] proxy/config/config.yaml
  [MERGE] proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml
  [SKIP]  proxy/config/providers/azure-foundry.yaml (auto-merge safe)
  [SKIP]  proxy/config/providers/opencode.yaml (auto-merge safe)
  [SKIP]  proxy/config/providers/openrouter.yaml (auto-merge safe)

  Recipe applied — 4 file(s) created/updated.

  No orphaned files to clean up.
  [CREATE] .env.user (user-managed overrides)

Recipe: costeffective-coding
  Cloud inference — DeepSeek, Azure, OpenCode, OpenRouter via LiteLLM proxy
  -------------------------------------------------------

  [INFO]  Instructions written to C:\Users\nilayparikh\.codefreedom\RECIPE.md

  Secrets:
  [MISSING] LITELLM_MASTER_KEY  —  LiteLLM proxy master key
           Run: openssl rand -hex 32  (default: sk-codefreedom-local)
  [MISSING] DEEPSEEK_API_KEY  —  DeepSeek API key
           Get key at <https://platform.deepseek.com/api_keys>
  [MISSING] MICROSOFT_FOUNDRY_API_KEY  —  Azure Foundry API key
           Set in Azure AI Foundry portal
  [MISSING] OPENCODE_ZEN_API_KEY  —  OpenCode Zen API key
           Get key from OpenCode dashboard
  [MISSING] OPENROUTER_API_KEY  —  OpenRouter API key
           Get key at <https://openrouter.ai/keys>

  Configuration (set in ~/.codefreedom/.env.user):
  [MISSING] MICROSOFT_FOUNDRY_API_BASE  —  Azure Foundry base URL
           Azure AI Foundry workspace endpoint

  For interactive secret setup (recommended), run the assisted script:
    Bash:       bash scripts/setup-secrets.sh
    PowerShell: .\scripts\setup-secrets.ps1
  The script sets CF_CLI_* machine environment variables, persists them
  in your shell profile, and reports which services are configured.

5 secret(s) missing — set them before starting the proxy
  -------------------------------------------------------

PS C:\Users\nilayparikh>

---
