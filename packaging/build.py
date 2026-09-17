"""Build the application for whichever platform this is, and archive it.

PyInstaller freezes for the machine it runs on and nothing else, so there is no
cross-compiling here and none anywhere: a Windows application is built on
Windows, a macOS one on macOS. What this script does is make the three builds
identical in everything else -- same spec, same icon, same archive name -- so
that the only difference between them is the one that cannot be helped.

    uv sync --extra desktop --group build
    uv run python packaging/build.py

The result is one archive in ``dist/``, named for the version, the platform and
the processor, ready to be attached to a release.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from icon import platform_icon  # noqa: E402 - needs the line above to be importable

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "yacht_co2.spec"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "yacht-co2"


def version() -> str:
    """Return the version the archive is named for."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def platform_tag() -> str:
    """Return the part of the archive name that says what it runs on.

    The processor is in there because macOS and Linux both ship for two, and an
    Apple Silicon build will start on an Intel Mac and then fail somewhere
    unhelpful. Named, it is obvious which one to download.
    """
    system = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    machine = {"AMD64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine(), platform.machine().lower()
    )
    return f"{system}-{machine}"


def built_application() -> Path:
    """Return what PyInstaller just produced: an ``.app`` bundle, or a folder."""
    bundle = DIST / f"{NAME}.app"
    return bundle if bundle.is_dir() else DIST / NAME


def freeze() -> Path:
    """Draw the icon, run PyInstaller, and return what it built."""
    written = platform_icon(BUILD / "icons")
    print(f"icon: {written}")

    environment = dict(os.environ)
    # PyInstaller otherwise caches the binaries it has processed under the
    # user's home directory, where it outlives the checkout and is shared with
    # every other project on the machine. Keeping it in build/ means "delete
    # build/" is the whole of starting again.
    environment["PYINSTALLER_CONFIG_DIR"] = str(BUILD / "pyinstaller-cache")

    # --clean, because a stale work directory is the commonest reason a bundle
    # that used to work stops working after a dependency changes.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD / "pyinstaller"),
            str(SPEC),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    application = built_application()
    if not application.exists():
        raise SystemExit(f"PyInstaller reported success but {application} is not there.")
    return application


def archive(application: Path) -> Path:
    """Pack the built application into one file, and return it."""
    DIST.mkdir(parents=True, exist_ok=True)
    stem = f"{NAME}-{version()}-{platform_tag()}"

    if sys.platform == "darwin":
        # ditto rather than zip: an .app is held together by symlinks and by the
        # executable bit, and a plain zip quietly loses both -- which shows up
        # as a bundle that is "damaged" only once somebody has downloaded it.
        destination = DIST / f"{stem}.zip"
        destination.unlink(missing_ok=True)
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(application),
                str(destination),
            ],
            check=True,
        )
        return destination

    if sys.platform == "win32":
        destination = DIST / f"{stem}.zip"
        destination.unlink(missing_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(application.rglob("*")):
                bundle.write(path, Path(NAME) / path.relative_to(application))
        return destination

    # Linux: a tarball, which is the only common format that keeps the
    # executable bit on the launcher.
    destination = DIST / f"{stem}.tar.gz"
    destination.unlink(missing_ok=True)
    with tarfile.open(destination, "w:gz") as bundle:
        bundle.add(application, arcname=NAME)
    return destination


def sign_ad_hoc(application: Path) -> None:
    """Sign a macOS bundle with no identity, so that it will open at all.

    Apple Silicon refuses to run unsigned code outright. PyInstaller signs the
    executable it writes, but the bundle is assembled afterwards, and it is the
    bundle Gatekeeper looks at. This is not notarisation and does not pretend to
    be: a downloaded copy still has to be let through once, which the README
    says how to do.
    """
    if sys.platform != "darwin":
        return
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(application)],
        check=False,  # a signing failure is worth reporting, not worth stopping for
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Build the application but leave it unpacked, which is what you want while "
        "you are iterating on it.",
    )
    arguments = parser.parse_args()

    if os.environ.get("CI"):
        # A bundle that differs between two builds of the same commit is a
        # bundle nobody can check, and the hash seed is the usual reason.
        os.environ.setdefault("PYTHONHASHSEED", "0")

    application = freeze()
    sign_ad_hoc(application)
    size = sum(path.stat().st_size for path in application.rglob("*") if path.is_file())
    print(f"built: {application} ({size / 1e6:.0f} MB)")

    if arguments.no_archive:
        return 0
    destination = archive(application)
    print(f"archived: {destination} ({destination.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
