# Admin -- Backup & Restore

> **Caution:** These commands manipulate your `~/.codefreedom/` configuration
> directory. Always preview a restore with `--dry-run` before applying it.

## When to Use

| Scenario                                   | Command                                         |
| ------------------------------------------ | ----------------------------------------------- |
| Before upgrading CodeFreedom               | `codefreedom admin backup`                      |
| Porting config to a new machine            | `backup` → copy archive → `restore`    |
| After a misconfigured restore              | `restore --dry-run` to preview, then `restore`   |
| Cleaning up old backups                    | `codefreedom admin prune --keep 5`              |
| Checking what a backup contains            | `codefreedom admin inspect path.tar.gz`         |

## Commands

### `codefreedom admin backup`

Archive your managed CodeFreedom configuration files into a portable `.tar.gz`
archive. Only the following files are backed up:

| Path                  | Description                                   |
| --------------------- | --------------------------------------------- |
| `profiles/`           | Profile JSON files (claude-code, chrome, web) |
| `proxy/`              | Proxy config, docker-compose, provider YAMLs  |
| `.env.claude`         | Claude Code environment config                |
| `.env.claude.secrets` | **Redacted** -- keys preserved, values masked  |
| `.env.proxy`          | Proxy environment config                      |
| `.env.proxy.secrets`  | **Redacted** -- keys preserved, values masked  |

Other directories (`sandbox/`, `proc/`, `backup/`) are **not** backed up.

```bash
# Default: saves to ~/.codefreedom/backup/
codefreedom admin backup

# Explicit output path
codefreedom admin backup --out /tmp/snapshot.tar.gz

# Tag with a profile label (stored in manifest and filename)
codefreedom admin backup --profile work-profile

# Encrypt with passphrase (secrets stored with full values)
codefreedom admin backup --passphrase "my-secret"
```

By default, backups go to `~/.codefreedom/backup/`. Each filename follows a
standard naming convention for easy identification:

```
codefreedom-backup-{profile}-{YYYYMMDD}-{HHMMSS}-{hostname}.tar.gz
codefreedom-backup-default-20260604-143022-my-workstation.tar.gz
```

**Backup scope:**

| Category   | Contents                                                                                       |
| ---------- | ---------------------------------------------------------------------------------------------- |
| `profiles` | `claude-code.json`, `chrome.json`, `web.json`                                                  |
| `proxy`    | `config.yaml`, `docker-compose.yaml`, providers                                                |
| `env`      | `.env.claude`, `.env.proxy`, `.env.claude.secrets` (redacted), `.env.proxy.secrets` (redacted) |

**What is NOT backed up:** `sandbox/`, `proc/`, `backup/`, or any other files.

#### Encryption with `--passphrase`

By default, secrets files are backed up with **redacted values** -- key names and
structure are preserved, but values show only the first 2 and last 1 character
(e.g., `sk-secret-abc` → `sk***c`).

Use `--passphrase` to encrypt the entire archive with **AES-256-GCM** (PBKDF2 key
derivation). When encrypted, secrets are stored with **full values** (not redacted).

```bash
# Encrypted backup with full secrets
codefreedom admin backup --passphrase "strong-passphrase"
```

**Requirements:** Encryption requires the `cryptography` package:

```bash
pip install codefreedom[encrypt]
```

Without it, `--passphrase` will fail with an error.

### `codefreedom admin restore`

Restore configuration from a backup archive. Always shows a diff preview
before making changes.

```bash
# Interactive restore with confirmation prompt
codefreedom admin restore /path/to/backup.tar.gz

# Preview only -- no changes made
codefreedom admin restore /path/to/backup.tar.gz --dry-run

# Skip confirmation prompt
codefreedom admin restore /path/to/backup.tar.gz --force

# Decrypt and restore an encrypted backup
codefreedom admin restore /path/to/backup.tar.gz --passphrase "my-secret"
```

The restore workflow:

1. Reads the manifest embedded in the archive
2. Compares every managed file against current state on disk (SHA-256)
3. Displays a status table (only managed files -- other directories are untouched)

```
  Status   Path                            Size       Action
  -------- ------------------------------ ---------- ------------
  [ADD]    .env.claude                    45 B       New file
  [MOD]    profiles/claude-code.json      4.2 KB     SHA256 differs
  [OK]     proxy/config/config.yaml       2.1 KB     Unchanged
```

4. Prompts for confirmation (unless `--force` or `--dry-run`)
5. Extracts only new and modified files

**Platform mismatch warning:** If the backup was created on a different platform
(e.g., macOS backup restored on Linux), a warning is displayed but the restore
can still proceed.

**Encrypted backups:** Require `--passphrase` to decrypt. Without it, restore
fails with an error pointing to the flag.

### `codefreedom admin list-backups`

List all backups in the default backup directory (`~/.codefreedom/backup/`).

```bash
codefreedom admin list-backups
codefreedom admin ls  # alias
```

Output example:

```
  Date                      Profile          Hostname             Files       Size Secrets
  ------------------------ ---------------- -------------------- ------ ---------- --------
  2026-06-04T14:30:22Z     default          my-workstation          12    45.2 KB redacted
  2026-06-03T09:15:00Z     default          my-workstation          12    44.8 KB redacted
```

Encrypted backups show `included` for the secrets column (full values are stored).

### `codefreedom admin inspect`

Peek inside a backup archive without extracting anything. Shows the full
manifest metadata and a file listing grouped by category.

```bash
# Inspect an unencrypted backup
codefreedom admin inspect ~/.codefreedom/backup/codefreedom-backup-default-20260604-143022-my-workstation.tar.gz

# Inspect an encrypted backup
codefreedom admin inspect /path/to/backup.tar.gz --passphrase "my-secret"
```

### `codefreedom admin prune`

Remove old backup archives by count or age.

```bash
# Keep 5 most recent backups
codefreedom admin prune --keep 5

# Delete backups older than 30 days
codefreedom admin prune --older-than 30d

# Combine both filters
codefreedom admin prune --keep 3 --older-than 90d
```

**Duration suffixes:** `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks).

**How filters combine:** When both `--keep` and `--older-than` are specified, the
union of both deletion sets is removed. For example, `--keep 3 --older-than 90d`
deletes anything older than 90 days, then ensures at least 3 remain.

**Safety:** Prune will never delete the only remaining backup.

## Archive Format

Backups are standard `.tar.gz` files. The first entry is always
`manifest.json`, which contains:

```json
{
  "schema_version": 1,
  "tool_version": "0.0.6",
  "created_at": "2026-06-04T14:30:22Z",
  "hostname": "my-workstation",
  "platform": "linux",
  "profile": "default",
  "secrets_redacted": true,
  "contents": {
    "profiles": [
      {
        "path": "profiles/claude-code.json",
        "size": 1234,
        "sha256": "abc...",
        "mode": 644
      }
    ]
  },
  "categories": {
    "profiles": { "count": 3, "total_size": 12345 },
    "proxy": { "count": 8, "total_size": 45678 }
  }
}
```

You can inspect any backup with standard tools:

```bash
tar tzf backup.tar.gz                          # list contents
tar xzf backup.tar.gz manifest.json -O | jq .  # read manifest
```

## Exit Codes

| Code | Meaning                                                        |
| ---- | -------------------------------------------------------------- |
| 0    | Success                                                        |
| 1    | Error -- file not found, invalid archive, parse error, or cancelled restore |

## Security

- **Secrets files are backed up with VALUES REDACTED** by default. Key names and structure
  are preserved; values show only the first 2 and last 1 character
  (e.g., `sk-secret-abc` → `sk***c`). This lets you identify which
  secrets need replacement after restore.
- **Encrypted backups** (`--passphrase`) store full secret values with AES-256-GCM encryption.
- Unencrypted backups are plain `.tar.gz` -- protect them with filesystem
  permissions or your own encryption.
- The backup directory is `~/.codefreedom/backup/` by default.
