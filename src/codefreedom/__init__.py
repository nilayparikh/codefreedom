"""CodeFreedom -- Single wrapper for all code agents with simple LLM routing, sandboxing, and profile management."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("codefreedom")
except PackageNotFoundError:
    __version__ = "0.0.0"
