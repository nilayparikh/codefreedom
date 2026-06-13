---
title: Backup
description: Backup, restore, and manage your CodeFreedom configuration.
---

# Backup

Backup, restore, and manage your CodeFreedom configuration.

## Quick Start

```bash
# Full commands
cf manage admin backup                    # Backup config
cf manage admin restore                   # Restore from latest backup
cf manage admin list                      # List backups
cf manage admin inspect                   # Inspect a backup
cf manage admin prune                     # Clean old backups

# Short aliases
cf m ad backup
cf m ad restore
cf m ad list
cf m ad inspect
cf m ad prune
```

## Backup

Create a timestamped backup of your CodeFreedom config:

```bash
cf manage admin backup
# or
cf m ad backup
```

Backups are stored in `~/.codefreedom/backups/` as tar.gz archives:

```
~/.codefreedom/backups/
├── codefreedom-backup-20250101-120000.tar.gz
├── codefreedom-backup-20250102-120000.tar.gz
└── codefreedom-backup-20250103-120000.tar.gz
```

## Restore

Restore from the latest backup:

```bash
cf manage admin restore
# or
cf m ad restore
```

Restore from a specific backup:

```bash
cf manage admin restore --file codefreedom-backup-20250101-120000.tar.gz
# or
cf m ad restore --file codefreedom-backup-20250101-120000.tar.gz
```

## List Backups

```bash
cf manage admin list
# or
cf m ad list
```

## Inspect

View the contents of a backup:

```bash
cf manage admin inspect --file codefreedom-backup-20250101-120000.tar.gz
# or
cf m ad inspect --file codefreedom-backup-20250101-120000.tar.gz
```

## Prune

Remove old backups:

```bash
# Keep last 5
cf manage admin prune --keep 5
# or
cf m ad prune --keep 5

# Keep last 30 days
cf manage admin prune --days 30
# or
cf m ad prune --days 30
```

## Command Reference

### `cf manage admin`

```
usage: codefreedom manage admin [-h] {backup,restore,list,inspect,prune} ...

positional arguments:
  backup                Backup CodeFreedom config
  restore               Restore from latest backup
  list                  List backups
  inspect               Inspect a backup
  prune                 Clean old backups

options:
  -h, --help            show this help message and exit
```
