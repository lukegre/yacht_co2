# Yacht CO2 on RenkuLab

Yacht CO2 runs on RenkuLab as a containerised browser application. Start a
session from the project launcher, then open its generated URL. The application
listens on port `8080`; Renku's `RENKU_BASE_URL_PATH` is picked up automatically
so the interface, static assets, and WebSocket connection work behind the
platform proxy.

## Mounts that matter

Mount the project workspace at `/home/renku/work`. It is the application's data
root: keep campaign folders and generated outputs here so they persist with the
Renku project.

Also mount the **yacht-co2 defaults: Oliver Heer (Yoroshiku)** connector
read-only at `/home/renku/.config/yacht_co2`. The connector is published at DOI
`10.5281/zenodo.22825109` and provides the shared `project.yaml` and
`manifest.yaml` defaults.

| Path | Role |
| --- | --- |
| `/home/renku/work` | Writable campaigns, outputs, settings, and logs |
| `/home/renku/.config/yacht_co2` | Read-only shared defaults connector |
| `/secrets` | Optional read-only Zenodo credentials |

The container never writes to the shared connector. Its user-specific state is
stored under `/home/renku/work/.config/yacht_co2`, including GUI preferences and
service logs.

## Configuration layering

Settings are composed, rather than replaced. Shared connector defaults form the
baseline, then writable user defaults can refine them. An optional
`YACHT_CO2_PROJECT_CONFIG`, repository/project configuration, and finally the
campaign configuration take precedence in that order. This lets each campaign
override only the values it needs while retaining the common vessel and
instrument metadata.

## Zenodo uploads

For uploads, create a RenkuLab secret and mount it at `/secrets`. Store tokens
in an `.env` file, for example `/secrets/zenodo.env`:

```dotenv
ZENODO_ACCESS_TOKEN=your-production-token
ZENODO_SANDBOX_ACCESS_TOKEN=your-sandbox-token
```

Only direct `/secrets/*.env` files are read. Tokens are never written into
campaign YAML or the read-only defaults connector. When more than one token is
available, Yacht CO2 uses this priority: a token pasted into the active GUI
session, an inherited environment variable, the mounted Renku secret, then the
writable user configuration `.env`.

## Runtime defaults

The image runs as the `renku` user and starts the application with these
defaults:

```text
YACHT_CO2_DATA_ROOT=/home/renku/work
YACHT_CO2_HOST=0.0.0.0
YACHT_CO2_PORT=8080
```

On startup it seeds writable configuration where needed, creates a persistent
service log, and serves the GUI.
