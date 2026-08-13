"""dataprocessing — AI-native data processing, callable as a library, a REST
API, or an MCP server."""
from importlib.metadata import PackageNotFoundError, version as _version

try:
    # Single source of truth is pyproject.toml. Reading it back from the
    # installed metadata is what stops the two drifting: /health reported
    # 0.1.0 for the whole of 0.1.1 because the number was written twice.
    __version__ = _version("dataprocessing-ai")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
