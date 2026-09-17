"""The test suite is a package so that its modules are named ``tests.*``.

NiceGUI's simulated browser evicts from ``sys.modules`` the module that
registered each page, together with every one of its parent packages, unless
that module is named ``tests.*``. Without the package, tearing down a page
defined outside the suite would unload ``yacht_co2`` itself and every test
after it would monkey-patch a different copy of the package.
"""
