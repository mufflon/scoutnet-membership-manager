"""Scoutnet Membership Manager — an internal Scoutnet tool for a Swedish scoutkår."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth for the version: whatever ``pyproject.toml`` declares,
    # read back from the installed package metadata. Do not hardcode it anywhere
    # else — bump ``pyproject.toml`` (and the git tag) and everything follows.
    __version__ = version("scoutnet-membership-manager")
except PackageNotFoundError:  # a bare source checkout with no install
    __version__ = "0.0.0+unknown"
