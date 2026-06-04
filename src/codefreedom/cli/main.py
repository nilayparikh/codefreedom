"""Top-level CLI entry point -- parses args and dispatches to subcommands.

Entry point: codefreedom | cf
"""

from __future__ import annotations

import argparse
import sys

from codefreedom.env_loader import eprint


def main() -> None:
    """Top-level CLI entry point: codefreedom | cf."""
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description="CodeFreedom -- Single wrapper for all code agents. Simple LLM routing, sandboxing, profile management, and isolation. All config in ~/.codefreedom.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize all profiles, proxy configs, and env files in ~/.codefreedom/",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── claude subcommand ──────────────────────────────────────────────────
    claude_parser = subparsers.add_parser(
        "claude",
        aliases=["cc"],
        help="Launch code agent with profile-based model routing",
        description="Run a code agent natively (default) or in a sandboxed Docker container.",
    )
    # GPU image flags (mutually exclusive, only meaningful with --sandbox)
    claude_gpu = claude_parser.add_mutually_exclusive_group()
    claude_gpu.add_argument(
        "--cuda",
        action="store_true",
        dest="gpu_cuda",
        help="Use CUDA sandbox image for NVIDIA GPUs (only with --sandbox)",
    )
    claude_gpu.add_argument(
        "--rocm",
        action="store_true",
        dest="gpu_rocm",
        help="Use ROCm sandbox image for AMD GPUs (only with --sandbox)",
    )
    claude_parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run inside a sandboxed Docker container (default: native)",
    )
    claude_parser.add_argument(
        "--run-as-me",
        action="store_true",
        help="Run sandbox container as host user (uid/gid match). Only valid with --sandbox.",
    )
    claude_parser.add_argument(
        "--native-models",
        action="store_true",
        help="Use native Anthropic models/auth (/login) -- strips ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN",
    )
    claude_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Load a named profile (default: 'default')",
    )
    claude_parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop and remove the persistent Docker container",
    )
    claude_parser.add_argument(
        "--status",
        action="store_true",
        help="Show persistent container status and exit",
    )
    claude_parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit",
    )
    claude_parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Skip Claude Code permission prompts (use in CI/non-interactive environments)",
    )

    # ── tools subcommand ──────────────────────────────────────────────────
    tools_parser = subparsers.add_parser(
        "tools",
        help="Manage auxiliary tools (chrome browser, etc.)",
        description="Manage auxiliary tools used by coding agents (Chrome browser with Xvfb, etc.).",
    )
    tools_subparsers = tools_parser.add_subparsers(dest="tool", title="tools")

    # ── chrome tool ─────────────────────────────────────────────────────
    chrome_parser = tools_subparsers.add_parser(
        "chrome",
        help="Chrome browser with Xvfb for undetectable headed browsing",
        description="Start/stop/manage a Chrome browser container with virtual display (Xvfb) for undetectable web browsing. Coding agents connect via Chrome DevTools Protocol (CDP) at port 9222.",
    )
    chrome_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "status", "url", "init"],
        help="Action to perform (default: status). 'init' copies tool profile to ~/.codefreedom/.",
    )
    chrome_parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="CDP debug port (default: 9222)",
    )

    # ── web / camoufox tool ─────────────────────────────────────────────
    web_parser = tools_subparsers.add_parser(
        "web",
        aliases=["camoufox"],
        help="Camoufox stealth browser for web search and scraping (MCP)",
        description="Start/stop/manage a Camoufox browser container for stealth web search and scraping. The container runs an MCP-only server on port 8420 with web_search and web_fetch tools.",
    )
    web_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "status", "init"],
        help="Action to perform (default: status). 'init' copies tool profile to ~/.codefreedom/.",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8420,
        help="MCP server port (default: 8420)",
    )

    # ── proxy subcommand ───────────────────────────────────────────────────
    proxy_parser = subparsers.add_parser(
        "proxy",
        aliases=["px"],
        help="Manage the LLM proxy (start, stop, status, validate, init)",
        description="Manage the LLM proxy lifecycle (Docker or native).",
    )
    proxy_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "status", "validate", "init"],
        help="Action to perform (default: status). 'init' copies proxy configs to ~/.codefreedom/.",
    )
    proxy_parser.add_argument(
        "--docker",
        action="store_true",
        help="Run via Docker Compose instead of native Python",
    )
    proxy_parser.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Port for proxy (default: 4000)",
    )
    proxy_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind host for proxy (default: 0.0.0.0)",
    )

    args, unknown = parser.parse_known_args()

    # ── Top-level --init ────────────────────────────────────────────────────
    if args.init:

        from codefreedom.cli.claude import init_claude
        from codefreedom.cli.proxy import init_proxy

        code = 0

        code |= init_claude()
        code |= init_proxy()

        # Legacy shared .env (placeholder for backward compatibility)
        from codefreedom.config import get_codefreedom_dir

        env_path = get_codefreedom_dir() / ".env"
        if env_path.exists():
            print(f"[init] [SKIP] Already exists: {env_path}")
        else:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text(
                "# CodeFreedom — Legacy shared environment\n"
                "# Prefer component-specific .env files (.env.claude, .env.proxy, etc.)\n"
            )
            print(f"[init] [OK]   Created {env_path}")

        print()
        print("[init] Done.")
        print("       Docs: https://nilayparikh.github.io/codefreedom/")
        sys.exit(code)

    if args.command in ("claude", "cc"):
        # ── Rescue known flags swallowed by parse_known_args ────────────────
        _CLAUDE_BOOL_FLAGS = {
            "--cuda": "gpu_cuda",
            "--rocm": "gpu_rocm",
            "--sandbox": "sandbox",
            "--run-as-me": "run_as_me",
            "--native-models": "native_models",
            "--stop": "stop",
            "--status": "status",
            "--list-profiles": "list_profiles",
            "--dangerously-skip-permissions": "dangerously_skip_permissions",
        }
        forwarded: list[str] = []
        _unknown_iter = iter(unknown)
        for arg in _unknown_iter:
            if arg in _CLAUDE_BOOL_FLAGS:
                setattr(args, _CLAUDE_BOOL_FLAGS[arg], True)
            elif arg == "--profile":
                try:
                    args.profile = next(_unknown_iter)
                except StopIteration:
                    forwarded.append(arg)
            else:
                forwarded.append(arg)
        # ── claude init action (subparser-free: check forwarded args) ──────
        if forwarded and forwarded[0] == "init":
            forwarded.pop(0)  # strip "init", keep anything else
            from codefreedom.cli.claude import init_claude

            sys.exit(init_claude())

        # ── Forward everything remaining to claude CLI ─────────────────────
        args.claude_args = forwarded
        from codefreedom.cli.claude import run as claude_run

        sys.exit(claude_run(args))
    elif args.command in ("proxy", "px"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.proxy import run as proxy_run

        sys.exit(proxy_run(args))
    elif args.command == "tools":
        if args.tool == "chrome":
            if getattr(args, "action", None) == "init":
                if unknown:
                    eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                    sys.exit(2)
                from codefreedom.cli.chrome import init_tool

                sys.exit(init_tool())
            if unknown:
                eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                sys.exit(2)
            from codefreedom.cli.chrome import run as chrome_run

            sys.exit(chrome_run(args))
        elif args.tool in ("web", "camoufox"):
            if getattr(args, "action", None) == "init":
                if unknown:
                    eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                    sys.exit(2)
                from codefreedom.cli.web import init_tool

                sys.exit(init_tool())
            if unknown:
                eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                sys.exit(2)
            from codefreedom.cli.web import run as web_run

            sys.exit(web_run(args))
        elif args.tool is None:
            tools_parser.print_help()
            sys.exit(0)
        else:
            eprint(f"[ERROR] Unknown tool: {args.tool}")
            eprint("   Available tools: chrome, web (camoufox)")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
