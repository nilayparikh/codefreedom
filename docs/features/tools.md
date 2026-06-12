---
title: Tools
description: Containerized tools for your code agent — browser automation, web search, GitHub API.
---

# Tools

CodeFreedom ships containerized tools that your code agent can use. Each tool runs as a Docker container, managed with simple commands.

## Available Tools

| Tool                | What It Does                              | Port |
| ------------------- | ----------------------------------------- | ---- |
| [Chrome](chrome.md) | Headless browser automation via CDP       | 9222 |
| [Web](web.md)       | Web search and scraping (stealth browser) | 8420 |
| [GitHub](github.md) | GitHub API (issues, PRs, repos)           | 8082 |

## Common Pattern

Every tool follows the same three commands:

```bash
codefreedom tools <tool> start   # Start container
codefreedom tools <tool> status  # Check status
codefreedom tools <tool> stop    # Stop container
```

## Tool Profiles

Each tool has a profile in `~/.codefreedom/profiles/<tool>.json` controlling its Docker settings (image, port, data directory). Created by `cf init`, editable afterward.

## Auto-Start from Profiles

Declare tools in your Claude Code profile and they start automatically:

```json
{
  "profiles": {
    "web-dev": {
      "description": "Full web dev with browser tools",
      "tools": ["chrome", "web"]
    }
  }
}
```

When you launch `codefreedom claude --profile web-dev`, the Chrome and Web containers start alongside Claude Code. When the session ends, they stop.

## When to Use Which

| Need                                              | Tool   |
| ------------------------------------------------- | ------ |
| Automate browser interactions (click, fill forms) | Chrome |
| Search the web, scrape pages (stealth/anti-bot)   | Web    |
| Manage GitHub repos, issues, PRs                  | GitHub |
