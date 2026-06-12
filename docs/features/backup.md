---
title: Backup & Restore
description: Backup, restore, and manage your CodeFreedom configuration.
---

# Backup & Restore

Protect your `~/.codefreedom/` configuration. Backup, restore, and clean up old snapshots.

## Backup

```bash
codefreedom manage admin backup
```

Saves to `~/.codefreedom/backup/` with a timestamped filename:

```
codefreedom-backup-default-20260604-143022-my-workstation.tar.gz
```

### Options

```bash
codefreedom manage admin backup --out /tmp/snapshot.tar.gz    # Custom path
codefreedom manage admin backup --profile work-profile         # Tag with profile name
codefreedom manage admin backup --passphrase "my-secret"       # Encrypt with AES-256
```

### What Gets Backed Up

| What | Included |
|------|----------|
| Profile JSON files | Yes |
| Proxy config | Yes |
| `.env` files | Yes |
| Secrets | **Redacted** by default (keys preserved, values masked) |
| Encrypted backup (`--passphrase`) | Full secrets included |
| Sandbox data | No |
| Runtime state | No |

## Restore

```bash
codefreedom manage admin restore /path/to/backup.tar.gz
```

Shows a diff before making changes:

```
  Status   Path                            Size       Action
  -------- ------------------------------ ---------- ------------
  [ADD]    .env.claude                    45 B       New file
  [MOD]    profiles/claude-code.json      4.2 KB     SHA256 differs
  [OK]     proxy/config/config.yaml       2.1 KB     Unchanged
```

### Restore Options

```bash
codefreedom manage admin restore backup.tar.gz --dry-run   # Preview only
codefreedom manage admin restore backup.tar.gz --force     # Skip confirmation
codefreedom manage admin restore backup.tar.gz --passphrase "my-secret"  # Encrypted
```

## List Backups

```bash
codefreedom manage admin list-backups
codefreedom manage admin ls    # Short alias
```

```
  Date                      Profile          Hostname             Files       Size Secrets
  ------------------------ ---------------- -------------------- ------ ---------- --------
  2026-06-04T14:30:22Z     default          my-workstation          12    45.2 KB redacted
```

## Inspect a Backup

```bash
codefreedom manage admin inspect /path/to/backup.tar.gz
```

See what's inside without extracting.

## Clean Up Old Backups

```bash
codefreedom manage admin prune --keep 5           # Keep 5 most recent
codefreedom manage admin prune --older-than 30d   # Delete backups older than 30 days
codefreedom manage admin prune --keep 3 --older-than 90d   # Both
```

Duration suffixes: `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks).

## Short Alias

```bash
codefreedom manage admin backup    # or
cf manage adm backup
```
