"""VS Code config generators — claude settings and proxy model discovery."""

from codefreedom.agents.vscode.claude_settings import cmd_vscode_claude_config
from codefreedom.agents.vscode.proxy_models import cmd_vscode_proxy_config

__all__ = [
    "cmd_vscode_claude_config",
    "cmd_vscode_proxy_config",
]
