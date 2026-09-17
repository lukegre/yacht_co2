"""The simulated browser, serving the page from inside the suite.

The ``user`` fixture NiceGUI ships runs a main file, which would make
``yacht_co2.gui.app`` the module that owns the page -- and a page's module is
unloaded when the simulation tears down. Building the page from a function
defined here keeps that unloading inside the suite, where it is harmless.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation

from yacht_co2.gui.app import Workbench


def workbench_page() -> None:
    """The page under test, which is the one :func:`launch` serves."""
    Workbench()


@pytest.fixture
async def user() -> AsyncGenerator[User, None]:
    async with user_simulation(root=workbench_page) as simulated:
        yield simulated
