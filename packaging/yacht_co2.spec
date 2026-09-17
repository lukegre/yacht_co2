# -*- mode: python ; coding: utf-8 -*-
"""How the application is frozen, on every platform that gets one.

PyInstaller works out most of what to include by following imports from
:mod:`packaging.launcher`. What it cannot work out is listed here, and it is
always one of three things: a file that is data rather than code, a module
reached by name at run time rather than by an ``import`` statement, or
something in the development environment that has no business being shipped.
Each is grouped and explained below, because a bundle that is missing one of
them fails at run time, in a window, with nowhere to print why.

Build it through ``packaging/build.py`` rather than directly: the wrapper
settles the version, the icon and the archive, and this file is what it hands
to PyInstaller.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent  # noqa: F821 - PyInstaller defines SPECPATH
PACKAGE = ROOT / "src" / "yacht_co2"

NAME = "yacht-co2"
BUNDLE_IDENTIFIER = "ch.datascience.yacht-co2"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

MACOS, WINDOWS = sys.platform == "darwin", sys.platform == "win32"

# -- data ---------------------------------------------------------------------
# The two YAML templates a first launch seeds into the user's configuration.
# They are read through importlib.resources, which works inside a bundle only
# if they are actually in it, and nothing imports them so nothing finds them.
datas = [(str(PACKAGE / "templates"), "yacht_co2/templates")]
binaries = []
hiddenimports = []

# -- packages that carry their own files or resolve their own modules ---------
# NiceGUI is mostly static assets -- its JavaScript, its fonts, its Quasar and
# Tailwind builds -- and loads its elements by name. numcodecs registers its
# compiled codecs through entry points, which is a lookup PyInstaller cannot
# see. uvicorn picks its event loop and its HTTP protocol at startup, by
# importing whatever "auto" resolves to on this machine. pywebview chooses the
# platform binding the same way, and is absent from the Linux build.
for package in ("nicegui", "numcodecs", "uvicorn", "webview"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception:  # noqa: BLE001 - an absent optional package is not an error
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# Read at run time by code that asks what version it is running, or that looks
# a distribution up to find its entry points. A bundle has no site-packages for
# either question to be answered from unless the metadata comes along.
for distribution in ("nicegui", "xarray", "zarr", "numcodecs", "h5netcdf"):
    try:
        datas += copy_metadata(distribution)
    except Exception:  # noqa: BLE001 - as above
        pass

# xarray finds its file formats through a registry keyed by name, so the
# reader for each format we write is named here rather than imported anywhere.
hiddenimports += ["h5netcdf", "h5py", "zarr", "xarray.backends.h5netcdf_", "xarray.backends.zarr"]

if MACOS:
    # pywebview draws its window with WebKit through pyobjc, and reaches each
    # framework by name once it has chosen the Cocoa binding.
    hiddenimports += ["objc", "Foundation", "AppKit", "WebKit", "Quartz"]
if WINDOWS:
    # ... and with WebView2 through pythonnet, which loads the .NET runtime.
    hiddenimports += ["clr", "clr_loader", "pythonnet"]
    hiddenimports += collect_submodules("webview.platforms")

# -- what to leave out --------------------------------------------------------
# Present in a development environment, unwanted in an application. The two
# collocation providers are the deliberate omission: copernicusmarine and the
# dask/gcsfs stack roughly double the download, they are both useless without
# credentials and a network, and both are imported lazily -- so a manifest that
# asks for one fails with its own message rather than crashing the window.
excludes = [
    # numpy.f2py is a wrapper around a Fortran compiler, which an application
    # has no use for, and it is the only thing that reaches scipy: nothing the
    # package runs imports scipy at all -- the one interpolation it does is
    # numpy's, and the one lookup is pandas'. Between them that is 35 MB.
    "numpy.f2py",
    "scipy",
    "copernicusmarine",
    "dask",
    "distributed",
    "gcsfs",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "mypy",
    "ruff",
    "coverage",
    "PyInstaller",
    # matplotlib comes in through the video renderer and would otherwise bring
    # every interactive backend it can find with it; the application draws no
    # figures on screen, so none of the toolkits are wanted.
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "wx",
]

analysis = Analysis(  # noqa: F821 - PyInstaller injects its own names
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)  # noqa: F821

# The icon is written by packaging/build.py before PyInstaller is called, so
# that both the executable and the macOS bundle can be given the same one.
icon = ROOT / "build" / "icons" / ("yacht-co2.icns" if MACOS else "yacht-co2.ico")
icon_argument = str(icon) if icon.is_file() else None

executable = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX breaks code signing on macOS and trips virus scanners on Windows
    # No console: this is opened by double-clicking it, and everything it would
    # have printed goes to the log file yacht_co2.desktop configures instead.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_argument,
)

collection = COLLECT(  # noqa: F821
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=NAME,
)

if MACOS:
    app = BUNDLE(  # noqa: F821
        collection,
        name=f"{NAME}.app",
        icon=icon_argument,
        bundle_identifier=BUNDLE_IDENTIFIER,
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            # Without this the window is drawn in light mode on a dark desktop,
            # while the pages inside it follow the system and go dark.
            "NSRequiresAquaSystemAppearance": False,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
