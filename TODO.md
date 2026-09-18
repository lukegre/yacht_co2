# Agent-ready backlog for Renkulab Branch

These tickets describe the intended result, boundaries, and evidence needed to
close each item. They are ordered by dependency; items in the same numbered
section can be worked on independently once the preceding section is complete.

## 1. Configure Zenodo credentials from Renku secrets

- [x] **Mount Zenodo token for uploads using Renku Secrets**

  **Problem:** Uploading data to Zenodo requires a token. 

  **Solution:**

  - Mount a secrets file with `ZENODO_ACCESS_TOKEN` and, when applicable,
    `ZENODO_SANDBOX_ACCESS_TOKEN`.
  - When `/secrets` exists, read approved `KEY=value` secret files from it (secrets/*.env); do not execute or shell-source arbitrary files. Document the expected filename(s) and format.
  - Use this precedence: GUI session token, inherited environment, `/secrets` file, then the configuration directory's `.env`. A GUI-supplied token lasts only for the current session.
  - If the selected token is not set in the environment after this resolution, tell the user that Zenodo uploads are unavailable and explain how to add it through a RenkuLab secret or the GUI.
  - Select `ZENODO_SANDBOX_ACCESS_TOKEN` when the configured upload target is the sandbox; otherwise select `ZENODO_ACCESS_TOKEN`.

## 2. Deployment-specific defaults

### 2.1 Supply the Oliver Heer image defaults

- [x] **Provide configurable locations for Yacht CO2 defaults and logs in the Docker image.**

  **Problem:** the image currently hard-codes the per-user configuration at
  `/home/renku/.config/yacht_co2`. A Renku deployment needs its mounted
  configuration (including logs) to be discoverable without rebuilding the image.

  **Solution:**

  - Use the published Renku data connector **yacht-co2 defaults: Oliver Heer (Yoroshiku)**
    (DOI `10.5281/zenodo.22825109`), mounted read-only from its root at the confirmed path
    `/home/renku/.config/yacht_co2`. It contains `project.yaml` and `manifest.yaml`.
  - Continue to support `YACHT_CO2_CONFIG_DIR` as the explicit configuration-location override.
  - Treat the connector as shared, immutable defaults. User changes must be written to a
    writable user or campaign-level configuration location; never attempt to edit the mounted
    connector in place. Define and document the resulting precedence.


## 3. GUI workflow improvements

### 3.1 Add a raw-log upload/import panel to the landing page

- [x] **Let users upload `.log` files through the GUI and create/select their campaign.**

  **Problem:** the browser interface only discovers folders already present on the server filesystem; a Renku/browser user cannot start from local OceanPack logs.

  **Scope:**

  - Move **Open a published record** above **Campaign folders**.
  - Place a second, adjacent landing-page panel for raw-log import. It accepts `.log` files only, including an extension/type check on the server as well as client-side filtering. Drag and drop also possible for files
  - Ask for a campaign name and date before import. Create the ID as `[name]-[date]` and reject
    an existing campaign rather than silently overwriting it. Use a shared
    `normalise_campaign_id(name, date)` validator: lowercase; replace spaces and hyphens with
    `_`; replace each run of other non-alphanumeric characters with `_`; trim leading/trailing
    `_`; reject an empty name; and accept dates only in `YYYY-MM` or `YYYY-MM-DD` format.
  - Store uploaded logs in `[data-root]/[campaign-id]/` with their basename only. Reject duplicate
    filenames in one upload and path-like or malicious filenames. Preserve source files already
    on disk.
  - Accept files with a `.log` suffix server-side; use the browser MIME/type filter only as a
    convenience. Set configurable maximum file-count and total-upload-size limits.
  - When import succeeds, refresh and select the new campaign so the normal archive → manifest →
    process workflow can begin. Also show an explicit **Process raw logs directly** action which bypasses optional archive creation without changing the source logs.
  - Show actionable validation and I/O errors; do not leave partial accepted files behind after a failed multi-file import (stage then move, or clean up only files created by this action).

### 3.2 Download artifacts instead of opening them in Renku

- [x] **Make completed-campaign artifact actions download files in a Renku browser session.**

  **Problem:** the current artifact action calls desktop open/reveal commands. That is correct for local/native use, but in Renku it opens or reveals paths in the container, not on the user’s computer.

  **Scope:**
  - Detect Renku from the existing `RENKU_BASE_URL_PATH` integration (do not infer it from hostnames).
  - In that mode, replace “open/reveal” artifact actions with browser downloads for the site HTML, NetCDF track, and report JSON. Preserve normal desktop `open_file`/`reveal` behaviour outside Renku.
  - Serve downloads through one resolver that maps an artifact key, rather than a supplied path,
    to an allowlisted output of the selected campaign: site HTML, NetCDF track, or report JSON.
    Set a filename and appropriate content type; do not expose arbitrary container paths or allow
    path traversal.
  - Keep downloaded-product campaigns usable: their artifact actions must also download instead of attempting to open a container path.

  **Acceptance criteria:**

  - With `RENKU_BASE_URL_PATH` set, each available artifact exposes a download action/URL and no desktop process launcher is called.
  - Outside Renku, existing local/native behaviour and tests remain unchanged.
  - Requests for an unrecognized or out-of-folder path are rejected.
  - GUI/route tests cover mode selection, filenames/content types, and access restrictions.

## 4. End-to-end container verification

### 4.1 Add a repeatable local Docker smoke test

- [x] **Document and automate the supported local Docker checks.**

  **Goal:** prove the image can start and serve the GUI with the intended data and
  configuration mounts. Dropbox and real `/secrets`/Zenodo integrations are deliberately
  excluded from the automated local check.

  **Scope:**

  - Add a short documented command sequence (or `make`/script target) that builds the
    image, runs it with a temporary data directory and a temporary configuration
    directory, waits for its health/UI endpoint, and stops it reliably.
  - Use fixture configuration containing no real credential. Exercise the environment-variable
    paths from item 1 and assert the process can read its defaults and create logs. The temporary
    configuration mount must be writable for config seeding and logs.
  - If a Docker healthcheck is practical, add one based on an inexpensive local endpoint;
    otherwise make the smoke script’s readiness probe explicit.
  - State exactly what is manual-only: Dropbox volumes, an actual Renku secret injection,
    and a live Zenodo upload.

  **Acceptance criteria:**

  - A contributor can run one documented command (for example,
    `uv run python packaging/docker_smoke.py`) on Docker Desktop/Linux and get a clear pass/fail
    result without credentials or network calls to Zenodo.
  - The check cleans up its temporary container and only its own temporary files on
    success or failure.
  - It verifies the page is reachable under the configured port and the mounted
    config/data locations are used.

  **Dependencies:** 1.1 and 1.2; ideally run after 2.1 so the deployment image is tested
  as shipped.
