# yacht-co2

Turns SubCtech OceanPack campaign logs into traceable xarray datasets, with
optional environmental enrichment, scientific exports, a static website, and
synchronized MP4 video. Every raw observation is preserved; quality control is
represented by flags rather than destructive filtering.

## Quick start

```console
uv sync
uv run yacht-co2 build-manifest data/2307_fastnet/zenodo.yaml
uv run yacht-co2 validate data/2307_fastnet/manifest.yaml
uv run yacht-co2 run data/2307_fastnet/manifest.yaml
```

`run` takes a campaign manifest and treats its folder as the campaign. It

1. uploads the folder's raw logs using the normal Zenodo defaults;
2. reads them back from the archived record, so what is published is provably
   what was processed;
3. ingests, processes and exports the track;
4. writes the JSON run report;
5. builds the single-file interactive site, titled `Fastnet Race (2023-07-24)`.

Every artifact is named `yacht_co2-<campaign>-<campaign date>-<kind>.<ext>`:
a hyphen separates the fields, and within a field every other character becomes
an underscore — so this campaign writes
`yacht_co2-fastnet_race-2023_07_24-track.nc`, `-report.json` and `-site.html`,
and nothing collides when several campaigns share a folder or a record.

Nothing is redone: an already-published Zenodo record is left untouched (the
upload is skipped and the products are still built against its DOI), the
manifest is never rewritten, and a rerun resumes where the last one stopped.
`process`, `enrich` and `site` redo one step of that procedure on its own.

The manifest's `outputs.formats` decides what the dataset is written as —
compressed NetCDF by default, plus Zarr v2 and CSV on request — and
`outputs.video: true` renders video (needs FFmpeg on `PATH`) when the pipeline
is driven from Python.

## Manifest

Scientific processing needs a `manifest.yaml`; the raw readers
(`read_log_file`, `read_campaign`) work without one. Paths are relative to the
manifest.

Build one beside an existing `zenodo.yaml`; `campaign.name` comes from its
campaign (or explicit title), `campaign.date` from its campaign date, and
`campaign.id` from its slug or the data-folder name. The remaining values come from `examples/defaults.yaml`:

```console
uv run yacht-co2 build-manifest data/2306_fastnet/zenodo.yaml
```

```yaml
campaign:
  id: fastnet-2023
  name: Fastnet 2023
  date: 2023-07-24 # names the site "Fastnet 2023 (2023-07-24)"
inputs:
  repository: 10.5281/zenodo.12345 # omit to read from the local filesystem
  logs: ./*.log
  timezone: UTC
calibration:
  method: instrument          # or: linear
equilibrator:
  h2o: h2o
  pressure: cellpress
  water_temperature: watertemp # water at the equilibrator, never LI-850 CellTemp
  sea_temperature: watertemp
phases:
  analysis: [5]
qc:
  minimum_water_flow: 0.1
  minimum_gas_flow: 0.1
  phase_transition_lag:       # settling seconds after each phase switch
    analysis: 180
  ranges:
    co2: [100, 1000]
products: []
flux:
  formulation: wanninkhof2014
outputs:
  directory: ../outputs/fastnet
  formats: [netcdf, zarr, csv]
  site: true
  single_html: true
```

When `inputs.repository` is set to a Zenodo DOI, record URL, API URL, or record
ID, `inputs.logs` selects files in that record instead of the local filesystem.
Downloads are cached below `outputs.cache`. `build-manifest` uses the `doi` in
`zenodo.yaml` as the default repository and fails clearly if no DOI is present.

### Enrichment products

Each `products` entry declares a provider (`cmems`, `era5`, `noaa_mbl`,
`local`), a product ID, variables, optional padding/tolerances, and whether
failure is fatal. Requests span the whole padded track and are cached.

```yaml
products:
  - name: era5
    provider: era5
    product_id: gs://weatherbench2/datasets/era5/1959-2023_01_10-wb13-6h-1440x721_with_derived_variables.zarr
    variables: [u10, v10]
    required: true
    time_tolerance: 90min
  - name: sst
    provider: cmems
    product_id: <catalogue-dataset-id>
    variables: [analysed_sst]
    required: false
```

CMEMS uses the normal Copernicus Marine Toolbox login. ERA5 is read anonymously
from the public WeatherBench 2 Zarr store (install the `era5` extra); the
default archive is 6-hourly at 0.25° and ends 2023-01-10 — requests outside its
coverage fail explicitly, so point `product_id` at a newer Zarr if needed. NOAA
MBL downloads the public monthly reference series. The static site never fetches
remotely.

## Conventions

The canonical dataset has a timezone-naive UTC `time` coordinate,
decimal-degree `lat`/`lon`, original `raw_*` fields, source file and line, a
`uint16` QC mask, manifest/code hashes, and processing history. QC bits are
stable:

| Mask | Meaning | Mask | Meaning |
|---:|---|---:|---|
| 1 | parse failure | 32 | flow |
| 2 | invalid time | 64 | physical range |
| 4 | invalid position | 128 | missing calibration |
| 8 | excluded phase | 256 | collocation tolerance |
| 16 | instrument status | 512 | transition lag |

Wet xCO2 is calibrated, dried with the logger H2O mole fraction,
pressure-corrected, adjusted from equilibrator to sea temperature (Takahashi
1993), and converted to fugacity (Weiss 1974). Flux uses Weiss solubility and
Wanninkhof (2014); wind is squared before collocation and positive flux means
outgassing.

Atmospheric CO2 is taken from valid onboard air-phase data, else a
manifest-supplied product, else NOAA MBL; `air_co2_source` records the choice
per observation.

## Python API

```python
from yacht_co2 import Pipeline, read_campaign

raw = read_campaign("data/2306_fastnet")
result = Pipeline("examples/fastnet.yaml").run(enrich=False)
print(result.dataset, result.artifacts)
```

Stages are also callable individually: `read_log_file`, `read_campaign`,
`apply_qc`, `calibrate_co2`, `derive_pco2`, `derive_fco2`, `fetch_products`,
`collocate_track`, `resolve_air_co2`, `derive_flux`, `export_dataset`,
`build_site`, `render_video`, `load_platform`, `summarise`, `write_report`.

## Run report

Every run writes `yacht_co2-<campaign>-<date>-report.json`: campaign and platform identity,
temporal/spatial extent, sampling statistics (median interval, gaps ≥5 min,
coverage), per-QC-bit and per-file record counts, a variable inventory over
QC-good records, product fetch statuses, and the manifest/code hashes. The site
reads it for the campaign info panel.

## Project defaults

One `project.yaml` holds everything shared across campaigns, one block per
consumer — `platform:` for the run report, `zenodo:` for archival metadata:

```yaml
platform:
  vessel_name: Yoroshiku (Oliver Heer)   # inherited as {vessel} below
  vessel_type: yacht IMOCA 60 class
  instrument: SubCtech OceanPack Race
  co2_sensor: LI850
zenodo:
  creators:
    - Gregor, Luke, 0000-0001-6071-1857
  community: vendee-globe-co2
  title_template: Surface ocean CO2 measurements on board {vessel} during the {campaign} ({campaign_date})
```

Resolution: `config_directories(start)` climbs from `start` to the repository
root (stopping at `.git`), and every `project.yaml` found is deep-merged
root-first, so a nested file refines the one above it. Nearer configuration then
wins — a campaign manifest for `platform:`, a data folder's `zenodo.yaml` for
`zenodo:`. `platform` keys are reported verbatim, so add or rename them freely;
  per-campaign identity is the manifest's `campaign.id` and `campaign.name`.

`YACHT_CO2_PROJECT_CONFIG` (exported, or set in a `.env` anywhere up to the
repository root) points at a project configuration outside the repository.
Being the *default*, it ranks below the search. A path that does not exist is an
error, not a silent fallback.

The superseded `zenodo_project.yaml` and `.env.zenodo` are still read as whole
mappings, ranking below a `zenodo:` block in the same directory.

## Validating configuration

`yacht-co2 validate` checks the project configuration and, when given one, an
campaign manifest — before any data is read, reporting every problem at once:

```console
uv run yacht-co2 validate examples/fastnet.yaml
```

```
project configuration: /…/project.yaml
project configuration: ok
examples/fastnet.yaml: warning: flux.formulation: is not read by anything; check the spelling
valid: Fastnet 2023 (cfc9536c…)
```

- **error** (exits non-zero) — the run would fail or silently do the wrong
  thing: a section of the wrong type, an unknown `calibration.method`, an
  unwritable export format, a `qc.ranges` pair that is not increasing,
  malformed `creators`, an unknown `title_template` token.
- **warning** — it still runs but looks like a mistake: a key nothing reads,
  `inputs.logs` matching no files, a `platform` block with no vessel, or
  `campaign`/`title` set project-wide.

The same checks run inside `load_manifest`, so every command refuses a broken
manifest up front. `zenodo-upload --dry-run` validates a data folder's own
`zenodo.yaml`.

## Uploading raw observations to Zenodo

`zenodo-upload` creates a resumable Zenodo draft from the top-level files of one
raw-data folder and, by default, submits it to a community for review:

```console
export ZENODO_ACCESS_TOKEN="..."
uv run zenodo-upload data/2306_fastnet \
  --campaign "Fastnet Race" --campaign-date 2023-07-24
```

Tokens may instead live in `.env` (see `.env.example`), loaded from the uploaded
folder, any `--config` directory, then the current directory; already-exported
values are never overwritten. `.env` is Git-ignored, excluded from uploads, and
not read during `--dry-run`.

### Naming a record

Zenodo has no settable slug, so a record's name is its title, built from its
campaign:

```yaml
# data/2306_fastnet/zenodo.yaml — the whole file
campaign: Fastnet Race
campaign_date: 2023-07-24
```

With `vessel` and `title_template` inherited from the project defaults this
yields *Surface ocean CO2 measurements on board Yoroshiku (Oliver Heer) during
the Fastnet Race (2023-07-24)*. Both keys are required; `campaign_date` accepts
`YYYY-MM-DD`, `YYYY-MM` or `YYYY`. A record that cannot be named this way may
set `title:` instead — but not alongside a campaign. `title_template` accepts
`{vessel}`, `{campaign}`, `{campaign_date}`, `{year}` and `{slug}`; unknown or
unset tokens are reported rather than rendered blank.

The folder name becomes the record's `slug`, published as an alternate
identifier (scheme `other`) — the stable join key between record, data folder
and manifest — and `campaign_date` is published as a `collected` date. Set
`slug:` to override. Nothing in an upload reads the data files.

### Configuration

Shared metadata lives in the `zenodo:` block of `project.yaml`; a folder's
`zenodo.yaml` carries only its own facts. Order: project defaults, the folder's
`zenodo.yaml` (or `--config`), then CLI flags. If no `zenodo:` block is found
anywhere the command fails and names the directories it searched.

```yaml
zenodo:
  creators:
    - Gregor, Luke, 0000-0001-6071-1857
    - Smith, Jane, https://orcid.org/0000-0002-1825-0097
  community: vendee-globe-co2
  resource_type: dataset
  license: cc-by-4.0
  publisher: Zenodo            # required — DataCite needs it to register the DOI
  description: Raw underway carbon dioxide observations from an ocean-going yacht.
  language: eng
  keywords: [carbon dioxide, underway observations, ocean]
  publication_date: 2026-09-09
  embargo: {enabled: false, months: 12, until: null}
  sandbox: false
```

Creators are an ordered list of `last, first, ORCID` (bare ORCIDs and ORCID URLs
accepted, checksum-validated); a folder list replaces the shared list entirely.
On first use the command writes the folder's `zenodo.yaml` before contacting
Zenodo, containing only the campaign (or explicit title) and any overridden
flag.

### Uploading

Only top-level regular files are uploaded — hidden files, symlinks,
`zenodo.yaml`, `.zenodo-upload.json` and directories are excluded. A Zenodo
record's files are a flat namespace, so subfolders cannot be uploaded at all:
every run warns and names them. Pack a subfolder into an archive if its contents
must be archived. Markdown files are also copied into the record's notes with
HTML escaped.

The command reserves a DOI and submits a first draft to its community for review
(the slug is resolved to an id automatically); `--no-publish` stops at the
draft. The record becomes public only when a curator accepts it. A new version
of an already published record is not reviewable — Zenodo rejects a second
review request, because the community was agreed when the first version was
accepted — so `--new-version` publishes the draft outright once its files are
uploaded. The reserved DOI is written back as `doi:` into the folder's
`zenodo.yaml`, and `submitted: YYYY-MM-DD` once the draft is handed over,
making that file the durable record of what the folder produced. While a review
is pending, reruns change nothing unless the notes changed; files are frozen, so
a rerun that finds new or changed files warns and points at `--new-version`.

Progress is kept in `.zenodo-upload.json` (no secrets). A retry resumes the same
draft, skips checksum-identical files and replaces changed ones. Every run logs
its plan — the resumed draft and where its id came from, counts of new, changed,
unchanged and remote-only files, one line per file, and a closing summary.
Remote-only files block publishing; inspect them and use `--prune` to
delete them deliberately. Published records are immutable and need
`--new-version` (optionally with `--record-id`); the new draft imports the
previous version's files, so unchanged files are not re-uploaded.

Files are public immediately unless embargoed: `--embargo YYYY-MM-DD`, or
`embargo: {enabled: true, months: N}` in config (an explicit `until` wins;
otherwise `months` after the publication date, clamped to the end of short
months). For end-to-end experiments use a sandbox account:

```console
export ZENODO_SANDBOX_ACCESS_TOKEN="..."
uv run zenodo-upload data/2306_fastnet --sandbox --dry-run
uv run zenodo-upload data/2306_fastnet --sandbox
```

`--dry-run` generates and validates the YAML and computes checksums locally
without any API request. Otherwise uploads talk to Zenodo's records API
(`/api/records`) over `requests`, with no third-party client dependency:
connection errors and HTTP 429/500/502/503/504 retry with bounded exponential
backoff honouring `Retry-After`; each file is streamed from disk through the
initiate/upload/commit steps and its md5 verified against the local checksum.
The token is sent only as an `Authorization` header, redacted from errors, read
only from the environment, and never written to YAML, state, output or
exceptions.

The same workflow is available from Python via `load_zenodo_config`,
`generate_zenodo_config`, `parse_creators`, `ZenodoClient` and
`upload_raw_folder`.

## Site

The site is built from the manifest, so one campaign is described one way:

```console
uv run yacht-co2 site data/2306_fastnet/manifest.yaml
```

Every argument comes from the manifest, so the command builds what a full run
would:

| Manifest                | Gives the site                                      |
| ----------------------- | --------------------------------------------------- |
| `campaign.name`, `.date`| the page title `Fastnet 2023 (2023-07-24)`, and the slugified file name |
| `outputs.directory`     | where it is written, and where the track NetCDF is read from |
| `outputs.site`          | the hosted `yacht_co2-fastnet-2023_07_24-site/` bundle |
| `outputs.single_html`   | the self-contained `yacht_co2-fastnet-2023_07_24-site.html` |
| `outputs.site_options`  | `max_bytes` (page budget, e.g. `10 MB`), `max_points`, and `variables` (the columns the page stores) |
| `phases`                | the phase codes QC, calibration and the atmosphere step share, and the names in the page's sampling-phase picker |
| `qc`                    | the documented QC criteria in the page               |

A manifest written before `campaign.date` existed takes the date from the
`zenodo.yaml` beside it. `--output` builds one site somewhere else, and
`--single-file/--no-single-file` overrides `outputs.single_html` for one build.

The processed track NetCDF in `outputs.directory` is the input; when there is
none the campaign is processed first and exported as NetCDF (whatever
`outputs.formats` asks for), so a rebuild reuses it instead of reading the logs
again. The run report beside it becomes the campaign info panel.

The page carries a stepped-down copy of the track, never the whole of it, so a
footer under the charts reports how many of the campaign's observations it is
showing and what share that is, and says plainly that the page is for viewing
the campaign quickly — any analysis belongs on the full dataset.

## Exports

NetCDF is the default format and the one every other artifact is built from.
NetCDF/Zarr preserve the complete dataset; fetched grids are exported as
separate NetCDF files. CSV is intentionally a flattened track view and cannot
contain gridded products.

Every NetCDF file this package writes — the exported track and the cached
product grids alike — is deflate-compressed (`zlib`, level 4) for each numeric
variable and coordinate. Strings and scalars are stored uncompressed, as HDF5
cannot chunk them.

## Legacy migration

Code under `docs/legacy_code` is reference-only and never imported at runtime.
`read_mflog` maps to `read_campaign`, with its dataframe columns now appearing
as xarray `raw_*` variables. Replace legacy row filtering with
`apply_qc(...).where(ds.qc_good)` so rejected data remain inspectable.

## Development

```console
uv run ruff check .
uv run mypy
uv run pytest --cov=yacht_co2 --cov-branch
```

Offline tests use synthetic provider fixtures and need no credentials.
