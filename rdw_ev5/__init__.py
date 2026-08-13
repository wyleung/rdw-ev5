"""Kia EV5 registration tracker."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth is pyproject.toml — read the installed metadata
    # rather than hardcoding a second copy here that can drift from it.
    __version__ = version("rdw-ev5")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
