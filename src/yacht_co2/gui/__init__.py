"""A browser front end for the procedure the README's quick start describes.

The package is driven from a terminal by people who have one. This subpackage
is for the people who do not: the same five steps, the same functions behind
them, and the shared defaults kept in the user's own configuration directory so
that they outlive any one campaign and any one checkout.

It is optional. ``uv sync --extra gui`` installs what it needs; nothing else in
the package imports it.
"""

from __future__ import annotations

from .app import launch

__all__ = ["launch"]
