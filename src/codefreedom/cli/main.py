"""Top-level CLI entry point — parses args and dispatches to subcommands.

Entry point: codefreedom | cf

Lifecycle grouping (v3) with aliases:
    cf setup    (s)   init (i) | config (c) | deinit (di)
    cf run      (r)   agent (ag) | proxy (px) | tools (tl)
    cf manage   (m)   doctor (dr) | update (up) | admin (adm)

Short examples:
    cf r ag cc          # run agent claude-code
    cf r ag mc          # run agent mimo-code
    cf r ag oc          # run agent open-code
    cf r ag pc          # run agent pi-code
    cf s i              # setup init
    cf r px start       # run proxy start
    cf m dr             # manage doctor
    cf m ad backup      # manage admin backup (alias adm)

"""

from __future__ import annotations

import argparse
import sys

from codefreedom.log import eprint, tag
from codefreedom.cli.formatter import CodeFreedomHelpFormatter


def _print_version() -> None:
    """Print version, Python, Docker, and dependency info."""
    import importlib.metadata
    import platform
    import subprocess
    from pathlib import Path

    try:
        ver = importlib.metadata.version("codefreedom")
    except importlib.metadata.PackageNotFoundError:
        ver = "dev"

    git_hash = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
            cwd=str(Path(__file__).resolve().parent.parent.parent.parent),
        )
        if result.returncode == 0 and result.stdout.strip():
            git_hash = f" ({result.stdout.strip()})"
    except Exception:
        pass

    print(f"codefreedom {ver}{git_hash}")
    print(f"  python     {platform.python_version()}")
    print(f"  platform   {platform.platform()}")

    deps = [
        "PyYAML", "deepdiff", "pydantic", "GitPython",
        "httpx", "docker",
    ]
    for dep in deps:
        try:
            dver = importlib.metadata.version(dep)
            print(f"  {dep:<16} {dver}")
        except importlib.metadata.PackageNotFoundError:
            print(f"  {dep:<16} (not installed)")

    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=5,
        )
        docker_server = result.stdout.strip() if result.returncode == 0 else "not running"
    except Exception:
        docker_server = "not found"
    print(f"  docker server   {docker_server}")


def _add_subparser(
    parent: argparse._SubParsersAction,
    name: str,
    *,
    aliases: list[str] | None = None,
    help: str = "",
    description: str = "",
) -> argparse.ArgumentParser:
    """Create a subparser with the custom formatter applied."""
    parser = parent.add_parser(
        name,
        aliases=aliases or [],
        help=help,
        description=description,
        formatter_class=CodeFreedomHelpFormatter,
    )
    return parser


def _expand_pa_flag() -> None:
    """Expand ``-pa <name>`` to ``setup init install <name>`` for argparse.

    Kept for backward compatibility with muscle memory. Prefer
    ``cf setup init install <name>`` (or the ``i`` alias) directly.
    """
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "-pa" and i + 1 < len(argv):
            sys.argv = argv[:i] + ["install", argv[i + 1]] + argv[i + 2:]
            return
        if arg.startswith("-pa=") and len(arg) > 4:
            sys.argv = argv[:i] + ["install", arg[4:]] + argv[i + 1:]
            return


def main() -> int:
    _expand_pa_flag()
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description=(
            "Unified CLI for code agents.\n"
            "LLM proxy routing, profile management."
        ),
        formatter_class=CodeFreedomHelpFormatter,
        epilog=(
            "examples:\n"
            "  cf r ag cc                   Launch Claude Code agent\n"
            "  cf r ag mc                   Launch MiMo Code agent\n"
            "  cf r ag pc                   Launch Pi Code agent\n"
            "  cf r px start                Start the LLM proxy\n"
            "  cf s i                       Initialize configuration\n"
            "  cf m dr                      Validate environment"
        ),
    )
    parser.add_argument(
        "-V", "--version", action="store_true", help="Show version and system info"
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── setup — one-time setup and configuration ────────────────────────────
    setup_parser = _add_subparser(
        subparsers,
        "setup",
        aliases=["s"],
        help="One-time setup and configuration (init, folder, config, deinit)",
    )
    setup_sub = setup_parser.add_subparsers(dest="setup_command", title="setup commands")

    # setup init
    init_parser = _add_subparser(
        setup_sub,
        "init",
        aliases=["i"],
        help="Initialize CodeFreedom config via a recipe (install, plan, apply, list)",
        description="Initialize CodeFreedom configuration via a recipe.",
    )
    _build_init_args(init_parser)

    # setup folder
    folder_parser = _add_subparser(
        setup_sub,
        "folder",
        aliases=["f"],
        help="Seed a per-folder .cf.yaml override (copies override.yaml)",
        description=(
            "Copy the current override.yaml into <PATH>/.cf.yaml so the "
            "folder can carry its own overrides (highest-priority YAML layer). "
            "Activate by exporting CF_CLI_CF_YAML=<PATH>/.cf.yaml."
        ),
    )
    _build_folder_args(folder_parser)

    # setup config
    config_parser = _add_subparser(
        setup_sub,
        "config",
        aliases=["c"],
        help="Generate configuration for targets (claude, mimo, vscode)",
    )
    from codefreedom.cli.setup.config import build_parser as build_config_parser
    build_config_parser(config_parser)

    # setup deinit
    deinit_parser = _add_subparser(
        setup_sub,
        "deinit",
        aliases=["di"],
        help="Tear down CodeFreedom: stop containers and remove config",
    )
    _build_deinit_args(deinit_parser)

    # ── run — daily workflows ──────────────────────────────────────────────
    run_parser = _add_subparser(
        subparsers,
        "run",
        aliases=["r"],
        help="Daily workflows (agent, proxy, tools)",
    )
    run_sub = run_parser.add_subparsers(dest="run_command", title="run commands")

    # run agent
    agent_parser = _add_subparser(
        run_sub,
        "agent",
        aliases=["ag"],
        help="Launch coding agents (claude-code, mimo-code, open-code, pi-code)",
    )
    from codefreedom.cli.run.agent import build_parser as build_agent_parser
    build_agent_parser(agent_parser)

    # run proxy
    proxy_parser = _add_subparser(
        run_sub,
        "proxy",
        aliases=["px"],
        help="Manage the LLM proxy (start, stop, status, validate)",
    )
    _build_proxy_args(proxy_parser)

    # run tools
    tools_parser = _add_subparser(
        run_sub,
        "tools",
        aliases=["tl"],
        help="Manage auxiliary tools (Chrome, web search, GitHub MCP, web bridge)",
    )
    _build_tools_args(tools_parser)

    # ── manage — occasional maintenance ────────────────────────────────────
    manage_parser = _add_subparser(
        subparsers,
        "manage",
        aliases=["m"],
        help="Occasional maintenance (doctor, update, admin)",
    )
    manage_sub = manage_parser.add_subparsers(dest="manage_command", title="manage commands")

    # manage doctor
    doctor_parser = _add_subparser(
        manage_sub,
        "doctor",
        aliases=["dr"],
        help="Validate the full CodeFreedom environment",
    )
    _build_doctor_args(doctor_parser)

    # manage update
    update_parser = _add_subparser(
        manage_sub,
        "update",
        aliases=["up"],
        help="Check Docker images and PyPI package for updates",
    )
    _build_update_args(update_parser)

    # manage admin
    admin_parser = _add_subparser(
        manage_sub,
        "admin",
        aliases=["adm"],
        help="Backup, restore, list, inspect, and prune configuration",
    )
    from codefreedom.cli.manage.admin import build_parser as build_admin_parser
    build_admin_parser(admin_parser)

    # ── git — commit & PR workflows ──────────────────────────────────────
    git_parser = _add_subparser(
        subparsers,
        "git",
        aliases=["g"],
        help="Git workflows: commit messages, PR creation (commit, pr)",
    )
    from codefreedom.cli.git import build_parser as build_git_parser
    build_git_parser(git_parser)

    # ══════════════════════════════════════════════════════════════════════
    # Argument parsing & dispatch
    # ══════════════════════════════════════════════════════════════════════

    args, unknown = parser.parse_known_args()

    if getattr(args, "version", False):
        _print_version()
        sys.exit(0)

    def _dispatch(module: str, fn: str, *fn_args, **fn_kwargs) -> None:
        if unknown:
            eprint(f"{tag('ERROR')} Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        import importlib
        mod = importlib.import_module(module)
        sys.exit(getattr(mod, fn)(*fn_args, **fn_kwargs))

    cmd = args.command

    # ── setup ──────────────────────────────────────────────────────────────
    if cmd in ("setup", "s"):
        sc = args.setup_command
        if sc in ("init", "i"):
            _dispatch_init(args)
        elif sc in ("folder", "f"):
            _dispatch_folder(args)
        elif sc in ("config", "c"):
            _dispatch_config(args)
        elif sc in ("deinit", "di"):
            _dispatch_deinit(args)
        else:
            setup_parser.print_help()
            sys.exit(1)

    # ── run ────────────────────────────────────────────────────────────────
    elif cmd in ("run", "r"):
        rc = args.run_command
        if rc in ("agent", "ag"):
            _dispatch_agent(args, unknown)
        elif rc in ("proxy", "px"):
            _dispatch("codefreedom.cli.run.proxy", "run", args)
        elif rc in ("tools", "tl"):
            _dispatch("codefreedom.cli.run.tools", "run", args)
        else:
            run_parser.print_help()
            sys.exit(1)

    # ── manage ─────────────────────────────────────────────────────────────
    elif cmd in ("manage", "m"):
        mc = args.manage_command
        if mc in ("doctor", "dr"):
            _dispatch("codefreedom.cli.manage.doctor", "run", verbose=getattr(args, "verbose", False))
        elif mc in ("update", "up"):
            _dispatch("codefreedom.cli.manage.update", "run", args)
        elif mc in ("admin", "adm"):
            _dispatch("codefreedom.cli.manage.admin", "run", args)
        else:
            manage_parser.print_help()
            sys.exit(1)

    # ── git ────────────────────────────────────────────────────────────────
    elif cmd in ("git", "g"):
        _dispatch("codefreedom.cli.git", "run", args)

    # ── Fallback ───────────────────────────────────────────────────────────
    else:
        parser.print_help()
        sys.exit(0)

    return 0  # unreachable — every branch calls sys.exit()


# ══════════════════════════════════════════════════════════════════════════════
# Parser builders for inline subcommands
# ══════════════════════════════════════════════════════════════════════════════


def _build_init_args(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="init_command", title="init commands", metavar="<command>")
    sub.required = False

    install_p = sub.add_parser(
        "install",
        aliases=["i"],
        help="Install a recipe (apply directly to the live config)",
        description="Install a recipe: resolve the recipe, generate a plan, and apply it in one step.",
    )
    install_p.add_argument("recipe", metavar="RECIPE", help="Recipe name to install (e.g., costeffective-coding)")
    _add_store_args(install_p)
    p.set_defaults(init_command="install", action_recipe="install")

    plan_p = sub.add_parser(
        "plan",
        aliases=["p"],
        help="Preview a recipe: generate .patch files without applying",
        description="Plan a recipe: write .patch files into the plans dir so you can review the diff first.",
    )
    plan_p.add_argument("recipe", metavar="RECIPE", help="Recipe name to plan (e.g., costeffective-coding)")
    _add_store_args(plan_p)
    p.set_defaults(action_recipe="plan")

    apply_p = sub.add_parser(
        "apply",
        aliases=["a"],
        help="Apply a previously generated plan by its ID",
        description="Apply a plan that was generated by 'cf setup init plan'.",
    )
    apply_p.add_argument("plan_id", metavar="PLAN_ID", help="Plan identifier (as shown by 'plan')")
    p.set_defaults(action_recipe="apply")

    list_p = sub.add_parser(
        "list",
        aliases=["l"],
        help="List all available recipes from the repository",
        description="List recipes from the recipe store without applying any of them.",
    )
    _add_store_args(list_p)
    p.set_defaults(action_recipe="list")


def _add_store_args(p: argparse.ArgumentParser) -> None:
    """Add the common --store / --staging flags to a setup init subcommand."""
    p.add_argument("-s", "--store", type=str, metavar="URL_OR_PATH", default=None, help="Custom recipe store: GitHub URL or local folder path")
    p.add_argument("--staging", action="store_true", help="Use recipes from the 'staging' branch instead of 'main'")


def _build_folder_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "path", type=str, nargs="?", default=".",
        metavar="PATH",
        help="Folder to write .cf.yaml into (default: current directory)",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Overwrite existing .cf.yaml (skips the user-edit safety check)",
    )


def _build_proxy_args(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="action", title="actions")
    sub.required = False
    sub.add_parser("status", help="Show proxy status")
    p.set_defaults(action="status")
    start_p = sub.add_parser("start", help="Start the proxy (Docker Compose)")
    start_p.add_argument("-p", "--port", type=int, default=None, help="Port to publish on the host")
    start_p.add_argument("--host", type=str, default=None, help="Host bind address")
    sub.add_parser("stop", help="Stop the proxy")
    sub.add_parser("restart", help="Restart the proxy (Docker Compose)")
    sub.add_parser("validate", help="Validate proxy configuration")


def _build_tools_args(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="action", title="actions")
    sub.required = False

    def _add_filters(sp: argparse.ArgumentParser) -> None:
        grp = sp.add_argument_group("tool filters (omit for all tools)")
        grp.add_argument("-c", "--chrome", action="store_true", help="Include Chrome browser")
        grp.add_argument("-w", "--web", action="store_true", help="Include Web search")
        grp.add_argument("-g", "--github", action="store_true", help="Include GitHub MCP")
        grp.add_argument("--web-bridge", action="store_true", help="Include Web bridge")

    sub.add_parser("status", help="Show tool status (default if no action given)")
    _add_filters(sub.add_parser("start", help="Start all (or filtered) tools"))
    _add_filters(sub.add_parser("stop", help="Stop all (or filtered) tools"))
    _add_filters(sub.add_parser("restart", help="Restart all (or filtered) tools"))
    p.set_defaults(action="status")


def _build_doctor_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-v", "--verbose", action="store_true", help="Show detailed information for all checks")


def _build_update_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("services", nargs="*", metavar="SERVICE", help="Filter by service: chrome, web, proxy, tools, all (default)")


def _build_deinit_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-f", "--force", action="store_true", help="Skip confirmation prompt before removing the CodeFreedom directory")
    p.add_argument("--clean-images", action="store_true", help="Also remove CodeFreedom Docker images, volumes, and dangling images")


# ══════════════════════════════════════════════════════════════════════════════
# Dispatch helpers
# ══════════════════════════════════════════════════════════════════════════════


def _dispatch_agent(args, unknown) -> None:
    from codefreedom.cli.run.agent import handle_args
    agent_name = getattr(args, "agent_name", None)
    if agent_name and agent_name != "list":
        args.agent_args = unknown
    elif unknown:
        eprint(f"{tag('ERROR')} Unrecognized arguments: {' '.join(unknown)}")
        sys.exit(2)
    sys.exit(handle_args(args))


def _dispatch_config(args) -> None:
    from codefreedom.cli.setup.config import handle_args
    sys.exit(handle_args(args))


def _dispatch_init(args) -> None:
    cmd = getattr(args, "init_command", None) or "install"
    store = getattr(args, "store", None)
    staging = getattr(args, "staging", False)

    if cmd in ("install", "i"):
        recipe = getattr(args, "recipe", None)
        if not recipe:
            eprint(f"{tag('ERROR')} A recipe name is required. Use 'cf setup init list' to list available recipes.")
            sys.exit(2)
        from codefreedom.cli.setup.recipe import plan_and_apply_recipe
        sys.exit(plan_and_apply_recipe(recipe, store=store, staging=staging))

    if cmd in ("plan", "p"):
        recipe = getattr(args, "recipe", None)
        if not recipe:
            eprint(f"{tag('ERROR')} A recipe name is required. Use 'cf setup init list' to list available recipes.")
            sys.exit(2)
        from codefreedom.cli.setup.recipe import plan_recipe
        sys.exit(plan_recipe(recipe, store=store, staging=staging))

    if cmd in ("apply", "a"):
        plan_id = getattr(args, "plan_id", None)
        if not plan_id:
            eprint(f"{tag('ERROR')} A plan ID is required. Use 'cf setup init plan <name>' to generate one.")
            sys.exit(2)
        from codefreedom.cli.setup.recipe import apply_plan
        sys.exit(apply_plan(plan_id))

    if cmd in ("list", "l"):
        from codefreedom.cli.setup.recipe import list_recipes
        sys.exit(list_recipes(store=store, staging=staging))


def _dispatch_folder(args) -> None:
    """Seed a per-folder ``.cf.yaml`` override file.

    Runs the ``cf s folder [path]`` (``cf s f [path]``) subcommand. Copies
    the active ``override.yaml`` into ``<path>/.cf.yaml`` so the folder
    can carry its own overrides (highest-precedence YAML layer). An
    existing ``.cf.yaml`` is preserved unless ``--force`` is passed.
    """
    from codefreedom.cli.setup.recipe import seed_cf_yaml
    from codefreedom.core.config import get_config_dir

    path = getattr(args, "path", ".") or "."
    force = getattr(args, "force", False)
    sys.exit(seed_cf_yaml(config_dir=get_config_dir(), folder=path, force=force))


def _dispatch_deinit(args) -> None:
    from codefreedom.cli.setup.deinit import run
    sys.exit(run(args))


if __name__ == "__main__":
    main()
