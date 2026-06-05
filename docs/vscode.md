# VS Code

Use CodeFreedom's proxy as your OpenAI-compatible endpoint inside VS Code.

> **Third-party notice.** This page describes integration with a third-party
> extension **"LiteLLM Provider for GitHub Copilot Chat"** by **Vivswan**
> ([marketplace](https://marketplace.visualstudio.com/items?itemName=vivswan.litellm-vscode-chat),
> [GitHub](https://github.com/Vivswan/litellm-vscode-chat)).
> CodeFreedom is not affiliated with, endorsed by, or responsible for this
> extension. Each user is responsible for evaluating its suitability for their
> own use.

## 1. Install the Extension

Search for **"LiteLLM Provider for GitHub Copilot Chat"** by **Vivswan** in the VS Code extensions marketplace, or install directly:

- [marketplace.visualstudio.com/items?itemName=vivswan.litellm-vscode-chat](https://marketplace.visualstudio.com/items?itemName=vivswan.litellm-vscode-chat)
- [GitHub repository](https://github.com/Vivswan/litellm-vscode-chat)

![LiteLLM Provider for GitHub Copilot Chat extension](assets/vscode-1-extension.png)

## 2. Add the Proxy as a Server

In VS Code settings (`Ctrl+,` or `Cmd+,`), search for **`litellm-vscode-chat`** and set the server URL to your proxy endpoint:

| Setting                   | Value                     |
| ------------------------- | ------------------------- |
| `litellm-vscode-chat.url` | `http://localhost:4000`   |
| `litellm-vscode-chat.key` | Your `LITELLM_MASTER_KEY` |

![Adding the proxy server in VS Code settings](assets/vscode-2-add-server.png)

## 3. Test the Connection

Open the VS Code chat panel and pick **"LiteLLM"** as the provider. You should see the models from your proxy listed — pick one and start chatting.

![Testing the server connection](assets/vscode-3-test-the-server.png)

## 4. All Models Available

Once configured, every model from your proxy appears in the VS Code model picker. Switch between DeepSeek, Claude (via proxy), local models, or any other provider — all in one place.

![All proxy models available in VS Code](assets/vscode-4-configured.png)

## Configuration

Enable prompt caching (recommended — reduces latency and token usage):

```json
{
  "litellm-vscode-chat.promptCaching.enabled": true
}
```

## Important Notes

- **Do not override parameters in VS Code.** Configure `drop_params` in your LiteLLM proxy
  (`~/.codefreedom/proxy/config/config.yaml`) instead:

  ```yaml
  general_settings:
    drop_params: true
  ```

  This lets the proxy safely ignore unsupported parameters rather than sending them to the upstream provider and causing errors.

- **Model routing.** All model selection, fallback, and parameter tuning happens in the
  [proxy config](proxy/index.md) — VS Code just points to the proxy URL.

- **Prompt caching.** The extension supports Anthropic-style prompt caching
  through the proxy. Enable it in your VS Code settings (see above), then
  configure caching in the proxy provider config.

- **Third-party responsibility.** CodeFreedom is not responsible for the
  behavior, security, or compatibility of any third-party extension, including
  the LiteLLM Provider for GitHub Copilot Chat. Users should review the
  extension's source code, permissions, and privacy policy before installing.

## Built-in: `chatLanguageModels.json` (no extension required)

VS Code's built-in Copilot Chat supports **custom OpenAI-compatible
endpoints** via the user-level `chatLanguageModels.json` file. CodeFreedom
ships a generator that reads your proxy's `/v1/model/info` and emits a
ready-to-paste entry — no third-party extension needed.

### 1. Start the proxy

```bash
codefreedom proxy start             # native
codefreedom proxy start --docker    # Docker Compose
codefreedom proxy status            # confirm it's up
```

### 2. Generate the entry

`--host` is required because the proxy's bind host (`LITELLM_BIND_HOST`,
usually `0.0.0.0`) is not a routable address. Use the host VS Code should
use to reach the proxy.

```bash
# From the same machine as VS Code
codefreedom vscode proxy config --host localhost

# From a different machine on the LAN / VPN
codefreedom vscode proxy config --host proxy.lan
codefreedom vscode proxy config --host 192.168.1.42
```

The command prints a JSON object on stdout. The full schema matches
VS Code's `chatLanguageModels.json` list-of-providers format.

### 3. Merge into VS Code

VS Code's `chatLanguageModels.json` is a **list** of provider entries.
Open the file (the path differs by OS — see VS Code's
[official docs](https://code.visualstudio.com/docs/copilot/customization/language-models))
and append the generated entry to the list, or replace an existing
`CodeFreedom` entry if you already have one.

```jsonc
[
  // ... your existing entries ...
  {
    "name": "CodeFreedom",
    "vendor": "customendpoint",
    "apiKey": "${input:codefreedom.litellm.master_key}",
    "apiType": "chat-completions",
    "models": [
      {
        "id": "DGX/Qwen3.6-27B",
        "name": "DGX/Qwen3.6-27B",
        "url": "http://proxy.lan:4000/v1",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 114688,
        "maxOutputTokens": 16384,
      },
    ],
  },
]
```

### 4. Wire the master key

The generator's `apiKey` is a VS Code **input variable** placeholder, not
a real key. To wire your `LITELLM_MASTER_KEY`:

1. Run **"Add Secret Input"** in VS Code (opens the
   `github.copilot.chat.customOAIModels` secret input command).
2. Use the same key name: `codefreedom.litellm.master_key`.
3. Paste your `LITELLM_MASTER_KEY` value.

VS Code will substitute it at runtime — the secret never lands in
`chatLanguageModels.json` itself.

If you already have a VS Code-managed secret input ref
(`${input:chat.lm.secret.<hash>}`), just replace the placeholder with
that string.

### Requirements recap

| Requirement                | Notes                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------- |
| Proxy running              | `codefreedom proxy status`                                                             |
| `LITELLM_MASTER_KEY` known | Exported in the shell **or** present in `~/.codefreedom/.env.proxy.secrets`            |
| A routable `--host`        | Pass the host VS Code will use to reach the proxy (e.g. `localhost`, LAN IP, DNS name) |

See the full command reference in [Proxy → Generate VS Code Configuration](proxy/index.md#generate-vs-code-configuration).

## Claude Code Extension (native integration)

The [Claude Code VS Code extension](https://marketplace.visualstudio.com/items?itemName=Anthropic.claude-code)
from Anthropic runs the same `claude` CLI inside VS Code, but reads its
configuration from a different place than the terminal CLI. CodeFreedom
ships a generator that emits a ready-to-paste `settings.json` fragment
so the extension picks up the same profile, auth, and model routing as
`codefreedom claude` on the command line.

### 1. Initialize (once)

If you haven't already:

```bash
codefreedom claude init
```

This writes `~/.codefreedom/profiles/claude-code.json` and
`~/.codefreedom/.env.claude*` from the bundled examples.

### 2. Generate the fragment

```bash
# Default profile
codefreedom vscode claude config

# A specific profile
codefreedom vscode claude config --profile ultra

# Override the proxy host/port (e.g. when VS Code runs on a different
# machine than the proxy)
codefreedom vscode claude config --host proxy.lan --port 4000

# Write to a file instead of stdout
codefreedom vscode claude config --out /tmp/cf-fragment.json
```

The command prints a JSON object on stdout with the
[`claudeCode.*`](https://code.claude.com/docs/en/vs-code#extension-settings)
settings and an `environmentVariables` array populated from the resolved
profile env.

### 3. Merge into VS Code

Open your VS Code User settings (Ctrl+Shift+P → **Preferences: Open User
Settings (JSON)**) and merge the generated fragment. The file path
differs by OS:

| OS      | Path                                                    |
| ------- | ------------------------------------------------------- |
| Windows | `%APPDATA%\Code\User\settings.json`                     |
| macOS   | `~/Library/Application Support/Code/User/settings.json` |
| Linux   | `~/.config/Code/User/settings.json`                     |

The generated fragment contains the full env array, but secret-looking
env var names (containing `TOKEN`, `_KEY`, `SECRET`, `PASSWORD`,
`PASSWD`, or `CREDENTIAL`) have their **resolved value replaced with a
`${env:VARNAME}` reference** using the same env var name. The
resolved secret value is never written to stdout or disk. The list of
referenced secrets is printed on stderr so you know which env vars to
set on your system.

For example, given a profile that exports
`ANTHROPIC_AUTH_TOKEN=sk-ant-…`, the fragment contains:

```jsonc
{
  "claudeCode.environmentVariables": [
    {
      "name": "ANTHROPIC_AUTH_TOKEN",
      "value": "${env:ANTHROPIC_AUTH_TOKEN}", // ← reference, not the key
    },
    // …other env vars
  ],
}
```

### Secret management

> **Never write resolved secret values to `settings.json`.** VS Code
> shares that file across your machine and, for workspace-scoped
> settings, sometimes syncs it to other machines. The Claude Code
> VS Code extension also **deletes
> `claudeCode.environmentVariables` on activation in trusted
> workspaces** ([anthropics/claude-code#10217](https://github.com/anthropics/claude-code/issues/10217),
> [#10224](https://github.com/anthropics/claude-code/issues/10224)),
> and does **not** support VS Code's `${input:id}` secret prompt
> syntax that would store the value in OS-keychain-backed
> `SecretStorage` ([#44158](https://github.com/anthropics/claude-code/issues/44158)
> closed as not planned).

CodeFreedom uses the standard VS Code pattern: **`${env:VARNAME}`
reference in the fragment, real value in the system/user environment**.
VS Code substitutes the actual value at runtime — the resolved
secret never appears in `settings.json` on disk.

#### 1. Set the secret as a system / user env var

```bash
# Linux / macOS (add to ~/.bashrc, ~/.zshrc, etc.)
export ANTHROPIC_AUTH_TOKEN="sk-your-key-here"
```

```powershell
# Windows PowerShell (User scope persists across sessions)
[System.Environment]::SetEnvironmentVariable(
    "ANTHROPIC_AUTH_TOKEN",
    "sk-your-key-here",
    "User"
)
```

Or use the GUI: **System Properties → Environment Variables**.

**Fully restart VS Code** after changing system env vars so the
extension picks them up. (VS Code reads `${env:}` at startup.)

#### 2. Run the generator

```bash
codefreedom vscode claude config
```

The generator replaces secret values with `${env:VARNAME}` references
and prints a stderr notice listing the secrets it referenced — for
example:

```text
[vscode] 1 secret env var(s) emitted as ${env:VARNAME} references
        (set them as system/user env vars):
         - ANTHROPIC_AUTH_TOKEN  ->  ${env:ANTHROPIC_AUTH_TOKEN}
         VS Code substitutes the actual value at runtime from your
         system environment.  Set them with:
           Windows:  System Properties -> Environment Variables
           Linux/macOS:  export VARNAME=value  (in ~/.bashrc, ~/.zshrc, etc.)
```

#### 3. Paste the fragment into `settings.json`

The fragment is safe to paste — it only contains references, not
resolved values. The settings entry that ships in the fragment looks
like this (with the full env array abbreviated):

```jsonc
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_AUTH_TOKEN", "value": "${env:ANTHROPIC_AUTH_TOKEN}" },
    { "name": "ANTHROPIC_BASE_URL", "value": "http://localhost:4000" },
    // …
  ],
}
```

#### Alternative: `~/.claude/settings.json` (shared with CLI)

If you also use the terminal `claude` CLI and want a single file for
both, put the secret in `~/.claude/settings.json` (the official
Claude Code config). This file is **not** deleted by the extension:

```jsonc
// ~/.claude/settings.json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-your-key-here",
  },
}
```

With this approach you can drop `ANTHROPIC_AUTH_TOKEN` from the
generated `claudeCode.environmentVariables` array (or just ignore it
— the CLI file takes precedence when the extension reads it).

#### Why not `${input:id}` in `settings.json`?

VS Code's built-in `${input:id}` syntax stores values in
`SecretStorage` (OS keychain) and is the recommended pattern for
`chatLanguageModels.json`, `tasks.json`, and `launch.json`. The
Claude Code extension **does not implement this** for
`claudeCode.environmentVariables` (the feature request was closed as
not planned by Anthropic), so there's no way to reference a
`SecretStorage`-backed secret from the extension's settings today.

### Troubleshooting

| Symptom                                                                         | Likely cause                                                             | Fix                                                                                                                  |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `claudeCode.environmentVariables` disappears from `settings.json` after restart | Extension deletes the setting in trusted workspaces (bug #10217, #10224) | Set the secrets as system env vars — the extension still reads them from `process.env` even after deleting the array |
| Extension reports `Unauthorized` / `ANTHROPIC_AUTH_TOKEN missing`               | The system env var isn't visible to the extension                        | Fully restart VS Code (env vars are read at launch)                                                                  |
| `claudeCode.selectedModel` not in fragment                                      | Profile has no `CLAUDE_MODEL` env var                                    | Add `CLAUDE_MODEL: CodeFreedom/Flash` to your profile env                                                            |

See the full command reference in [Claude Code → VS Code settings](claude-code/local.md#vs-code-settings).
