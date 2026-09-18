"""Build and probe the Docker image without credentials or external services.

Run with ``uv run python packaging/docker_smoke.py``.  The check deliberately
uses a unique image tag, container name, and temporary directory.  Its cleanup
only removes those resources, including when Docker or the page fails midway.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 90.0
CONTAINER_CONFIG = "/home/renku/.config/yacht_co2"
# Keep the smoke-test bind separate from ``CONTAINER_DATA``. Nested bind
# mounts make Docker create the inner mountpoint inside the outer host mount;
# on Linux/macOS that stub can be owned by the container uid and prevent the
# temporary directory from being removed after an otherwise successful run.
CONTAINER_USER_CONFIG = "/tmp/yacht-co2-user-config"
CONTAINER_DATA = "/home/renku/work"
TOKEN_SENTINEL = "docker-smoke-not-a-credential"
PROJECT_SENTINEL = "docker-smoke-shared-project"
MANIFEST_SENTINEL = "docker-smoke-shared-manifest"


def docker(*arguments: str, check: bool = True, **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run Docker, keeping a failed command useful to the contributor."""
    return subprocess.run(
        ["docker", *arguments],
        check=check,
        text=True,
        cwd=ROOT,
        **kwargs,
    )


def free_port() -> int:
    """Reserve an ephemeral loopback port long enough to learn its number."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_page(port: int, container: str) -> str:
    """Return the GUI page or report Docker logs when it does not become ready."""
    deadline = time.monotonic() + TIMEOUT
    last_error: Exception | None = None
    url = f"http://127.0.0.1:{port}/"
    while time.monotonic() < deadline:
        state = docker("inspect", "--format", "{{.State.Status}}", container, check=False,
                       capture_output=True)
        if state.stdout.strip() in {"exited", "dead"}:
            logs = docker("logs", container, check=False, capture_output=True)
            raise RuntimeError(f"Container exited before readiness:\n{logs.stdout}{logs.stderr}")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                page = response.read().decode("utf-8", "replace")
            if response.status == 200:
                return page
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = exc
        time.sleep(1)
    logs = docker("logs", container, check=False, capture_output=True)
    raise RuntimeError(
        f"Nothing answered at {url} within {TIMEOUT:.0f}s: {last_error}\n{logs.stdout}{logs.stderr}"
    )


def verify_mounts(container: str, data: Path, user_config: Path) -> None:
    """Prove mounted defaults, env credentials, seeded state, and logs are in use."""
    code = f"""
from pathlib import Path
from yacht_co2.project import config_paths
from yacht_co2.userconfig import read_token
assert Path('{CONTAINER_CONFIG}/project.yaml') in config_paths()
assert read_token() == '{TOKEN_SENTINEL}'
assert Path('{CONTAINER_USER_CONFIG}/project.yaml').is_file()
assert Path('{CONTAINER_USER_CONFIG}/manifest.yaml').is_file()
assert Path('{CONTAINER_USER_CONFIG}/logs/desktop.log').is_file()
assert '{PROJECT_SENTINEL}' in Path('{CONTAINER_USER_CONFIG}/project.yaml').read_text()
assert '{MANIFEST_SENTINEL}' in Path('{CONTAINER_USER_CONFIG}/manifest.yaml').read_text()
"""
    docker("exec", container, "python", "-c", code)
    for relative in ("project.yaml", "manifest.yaml", "logs/desktop.log", "gui.yaml"):
        if not (user_config / relative).is_file():
            raise RuntimeError(f"The writable configuration mount did not receive {relative}.")
    settings = (user_config / "gui.yaml").read_text(encoding="utf-8")
    if PROJECT_SENTINEL not in (user_config / "project.yaml").read_text(encoding="utf-8"):
        raise RuntimeError("The shared project defaults were not copied into writable config.")
    if MANIFEST_SENTINEL not in (user_config / "manifest.yaml").read_text(encoding="utf-8"):
        raise RuntimeError("The shared manifest defaults were not copied into writable config.")
    if str(data) in settings:
        raise RuntimeError("The GUI recorded the host path instead of its mounted data path.")
    if CONTAINER_DATA not in settings:
        raise RuntimeError("The GUI did not use the mounted container data path.")


def main() -> int:
    if shutil.which("docker") is None:
        raise SystemExit("Docker is not on PATH. Start Docker Desktop (or Docker Engine) and retry.")
    docker("info", check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    identity = uuid.uuid4().hex[:12]
    image = f"yacht-co2-smoke:{identity}"
    container = f"yacht-co2-smoke-{identity}"
    port = free_port()
    print("Building the Docker image (this may take a few minutes on first run)…")
    try:
        docker("build", "--tag", image, ".")
        with tempfile.TemporaryDirectory(prefix="yacht-co2-docker-smoke-") as scratch:
            temporary = Path(scratch)
            defaults = temporary / "defaults"
            data = temporary / "data"
            user_config = temporary / "user-config"
            defaults.mkdir()
            data.mkdir(mode=0o777)
            user_config.mkdir(mode=0o777)
            # Bind mounts retain host ownership.  Make these deliberately
            # throwaway directories writable to the image's uid 1000 on Linux
            # too, where the contributor may have a different uid.
            data.chmod(0o777)
            user_config.chmod(0o777)
            shutil.copy2(ROOT / "src/yacht_co2/templates/project.yaml", defaults / "project.yaml")
            shutil.copy2(ROOT / "src/yacht_co2/templates/manifest.yaml", defaults / "manifest.yaml")
            (defaults / "project.yaml").write_text(
                (defaults / "project.yaml").read_text(encoding="utf-8")
                + f"\nsmoke_sentinel: {PROJECT_SENTINEL}\n",
                encoding="utf-8",
            )
            (defaults / "manifest.yaml").write_text(
                (defaults / "manifest.yaml").read_text(encoding="utf-8")
                + f"\nsmoke_sentinel: {MANIFEST_SENTINEL}\n",
                encoding="utf-8",
            )
            docker(
                "run", "--detach", "--name", container,
                "--publish", f"127.0.0.1:{port}:8080",
                "--volume", f"{defaults}:{CONTAINER_CONFIG}:ro",
                "--volume", f"{data}:{CONTAINER_DATA}",
                "--volume", f"{user_config}:{CONTAINER_USER_CONFIG}",
                "--env", f"YACHT_CO2_USER_CONFIG_DIR={CONTAINER_USER_CONFIG}",
                "--env", f"ZENODO_ACCESS_TOKEN={TOKEN_SENTINEL}",
                image,
            )
            page = wait_for_page(port, container)
            if "yacht-co2" not in page.lower():
                raise RuntimeError("The HTTP endpoint responded, but it was not the Yacht CO2 page.")
            verify_mounts(container, data, user_config)
    finally:
        docker("rm", "--force", container, check=False, stdout=subprocess.DEVNULL)
        docker("image", "rm", "--force", image, check=False, stdout=subprocess.DEVNULL)

    print("Docker smoke check passed: GUI ready; mounted defaults, data, writable config, and log used.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        raise SystemExit(f"Docker smoke check failed: {exc}") from exc
