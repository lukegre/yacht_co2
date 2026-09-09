# yacht-co2

`yacht-co2` turns SubCtech OceanPack expedition logs into traceable xarray
datasets, optional environmental enrichments, scientific exports, an interactive
static website, and synchronized MP4 video. It preserves every raw observation;
quality control is represented by flags rather than destructive filtering.

## Quick start

```console
uv sync
uv run yacht-co2 validate examples/fastnet.yaml
uv run yacht-co2 run examples/fastnet.yaml --no-enrich
```

The example writes NetCDF, Zarr v2, CSV, hosted-site, single-HTML, and run-report
artifacts under `outputs/fastnet/`. To render video, set `outputs.video: true`; FFmpeg must
be on `PATH`.

## Manifest

Scientific processing requires an `expedition.yaml`; raw functions
`read_log_file` and `read_expedition` can be used without one. Paths are relative
to the manifest. A compact manifest looks like:

```yaml
expedition:
  name: Fastnet 2023
inputs:
  logs: ../data/2306_fastnet/*.log
  timezone: UTC
phases:
  analysis: [5]
calibration:
  method: instrument
equilibrator:
  h2o: h2o
  pressure: cellpress
  equilibrator_temperature: celltemp
  sea_temperature: watertemp
qc:
  analysis_phases: [5]
  minimum_water_flow: 0.1
  minimum_gas_flow: 0.1
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

Each item in `products` declares a provider (`cmems`, `era5`, `noaa_mbl`, or
`local`), product ID, variables, optional spatial/time padding and collocation
tolerances, and whether failure is required. Requests span the whole padded
track and are cached by provider, version, variables, bounds, and time.

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
from the public WeatherBench 2 Google Cloud Zarr store (install the `era5`
extra). The default archive is 6-hourly at 0.25° and ends on 10 January 2023;
requests outside its declared coverage fail explicitly. Set `product_id` to a
newer WeatherBench-compatible Zarr URL when needed. Remote fetching is never
performed by the static application. The NOAA adapter downloads the public
global marine-boundary-layer monthly reference series.

## Processing and conventions

The canonical dataset has a timezone-naive UTC `time` coordinate, decimal-degree
`lat`/`lon`, original `raw_*` fields, source file and line, a `uint16` QC mask,
manifest/code hashes, and processing history. QC bits are stable:

| Mask | Meaning |
|---:|---|
| 1 | parse failure |
| 2 | invalid time |
| 4 | invalid position |
| 8 | excluded phase |
| 16 | instrument status |
| 32 | flow |
| 64 | physical range |
| 128 | missing calibration |
| 256 | collocation tolerance |

CO2 stages are separately callable. Wet xCO2 is calibrated, dried using the
logger H2O mole fraction, pressure-corrected, corrected from equilibrator to sea
temperature with Takahashi (1993), and converted to fugacity with Weiss (1974).
Flux uses Weiss solubility and Wanninkhof (2014) gas transfer. Wind is squared
before collocation; positive flux means ocean outgassing.

Atmospheric priority is valid onboard air-phase data, then a manifest-supplied
observation product, then NOAA MBL. `air_co2_source` records the choice for each
observation.

## Python API

```python
from yacht_co2 import Pipeline, read_expedition

raw = read_expedition("data/2306_fastnet")
result = Pipeline("examples/fastnet.yaml").run(enrich=False)
print(result.dataset)
print(result.artifacts)
```

Public processing stages are `read_log_file`, `read_expedition`, `apply_qc`,
`calibrate_co2`, `derive_pco2`, `derive_fco2`, `fetch_products`,
`collocate_track`, `resolve_air_co2`, `derive_flux`, `export_dataset`,
`build_site`, `render_video`, `load_platform`, `summarise`, `write_report`, and
`Pipeline.run`.

## Run report

Every run writes `report.json` and `REPORT.md` into the output directory. Both
render the same structure, produced by `summarise(ds, manifest=..., platform=...)`:
expedition and platform identity, temporal and spatial extent, sampling
statistics (median interval, count and duration of gaps of at least five
minutes, resulting coverage), per-QC-bit record counts, per-source-file record
counts, a variable inventory whose ranges cover QC-good records only, product
fetch statuses, and the manifest/code hashes. `report.json` supersedes the
former `run.json`, whose contents it includes.

To report on a dataset produced earlier, without re-running the pipeline:

```console
uv run yacht-co2 report outputs/fastnet/track.nc \
  --output outputs/fastnet --manifest examples/fastnet.yaml
```

The manifest is optional; without it the platform section falls back to the
`expedition` attribute stored in the dataset.

### Platform defaults

Vessel identity and instrument serials belong to the project, not to one race,
so they live in the `platform` block of [`project.yaml`](#project-defaults)
rather than being repeated in every manifest:

```yaml
platform:
  vessel_name: Yoroshiku (Oliver Heer)
  vessel_type: yacht IMOCA 60 class
  instrument: SubCtech OceanPack Race
  co2_sensor: LI850
  ctd_sensor: CTD48-1892
  meteo_sensor: PTB10_Barometer-U0250319
```

Keys are reported verbatim, so add or rename them freely. A manifest's
`expedition:` block overrides them key by key, which is where per-expedition
fields such as `id` and `race_name` belong. The block is optional and its
absence is not an error.

## Project defaults

One `project.yaml` holds everything shared across expeditions, in a block per
consumer — `platform:` for the run report, `zenodo:` for archival metadata:

```yaml
platform:
  vessel_name: Yoroshiku (Oliver Heer)
  co2_sensor: LI850
zenodo:
  creators:
    - Gregor, Luke, 0000-0001-6071-1857
  community: vendee-globe-co2
  title_template: Surface ocean CO2 measurements on board {vessel} during the {campaign} ({campaign_date})
```

Both blocks resolve the same way. `config_directories(start)` climbs from
`start` towards the repository root, stopping at `.git`, and every `project.yaml`
found is deep-merged root-first — so a file in a sub-directory refines the one
above it, and one file beside `data/` serves every folder beneath it whatever
the working directory. Nearer configuration then wins: an expedition manifest
for `platform:`, a data folder's `zenodo.yaml` for `zenodo:`.

The vessel names the same boat in both blocks, so it is declared once as
`platform.vessel_name` (or `platform.vessel`) and inherited by the Zenodo
`{vessel}` token. Setting `zenodo.vessel` explicitly overrides that, for when a
record should be archived under a different name than it is reported under.

The superseded standalone files `zenodo_project.yaml` and `.env.zenodo` are
still read as whole mappings — a project that has not merged its configuration
keeps working — and rank below a `zenodo:` block in the same directory.

## Upload raw observations to Zenodo

`zenodo-upload` is a standalone command for creating a resumable Zenodo draft
with the top-level files from one raw-data folder and, by default, submitting
it to a community for review:

```console
export ZENODO_ACCESS_TOKEN="..."
uv run zenodo-upload data/2306_fastnet \
  --campaign "Fastnet Race" --campaign-date 2023-07-24
```

Tokens may instead be stored in `.env` using the names shown in
`.env.example`. Immediately before authentication, the command loads `.env`
from the uploaded folder, the directory containing an alternative `--config`,
and the current directory, in that order. Values already exported into the
process environment are never overwritten. `.env` is ignored by Git, excluded
from uploads as a hidden file, and is not read during `--dry-run`.

### Naming a record

Zenodo mints record ids and DOIs itself and has no settable slug, so a record's
name is its title. Rather than typing one per folder, a record is named from its
campaign:

```yaml
# data/2306_fastnet/zenodo.yaml — the whole file
campaign: Fastnet Race
campaign_date: 2023-07-24
```

which, with `vessel` and `title_template` inherited from the project defaults,
yields:

```
Surface ocean CO2 measurements on board YOROSHIKU (Oliver Heer) during the Fastnet Race (2023-07-24)
```

`campaign` and `campaign_date` are both required, and `campaign_date` accepts
`YYYY-MM-DD`, `YYYY-MM`, or `YYYY`. A record that cannot be named this way may
set `title:` explicitly instead — but not alongside a campaign, since that
would leave two competing names for the same record. `title_template` may use
`{vessel}`, `{campaign}`, `{campaign_date}`, `{year}`, and `{slug}`; an unknown
or unset field is reported rather than rendered blank.

The folder name becomes the record's `slug`, published as an alternate
identifier (scheme `other`) — the stable join key between a record, its data
folder, and the manifest that processed it — and `campaign_date` is published as
a `collected` date so the campaign period is queryable rather than readable only
in the title. Set `slug:` to override the folder name. Nothing in an upload
reads the data files to derive any of this.

### Where configuration lives

Shared metadata lives in the `zenodo:` block of
[`project.yaml`](#project-defaults), and a folder's `zenodo.yaml` carries only
its own facts. Resolution order is: project defaults, the folder's `zenodo.yaml`
(or `--config`), then CLI flags. Defaults are searched for by climbing from the
data folder towards the repository root, stopping at `.git`, plus the current
directory and any `--config` directory, which rank lowest. Every file found is
merged root-first, so one file beside `data/` serves every folder beneath it
whatever the working directory, and a data folder can still override a single
shared key (e.g. just `community:`) without restating the whole file. The
repository ships one at its root; if no `zenodo:` block is found anywhere, the
command fails and names the directories it searched. The superseded names
`zenodo_project.yaml` and `.env.zenodo` are still read as whole mappings.

On first use the command writes the folder's `zenodo.yaml` before contacting
Zenodo, containing just the campaign (or explicit title) and any flag that was
overridden — everything shared stays inherited. Today's date is used as the
publication date unless one is set.

Creators form an ordered YAML list. Each item must contain exactly a last name,
first name, and checksum-valid ORCID separated by commas. Bare ORCIDs and ORCID
URLs are accepted; a folder list replaces the shared creator list completely.

```yaml
# project.yaml
platform:
  vessel_name: Yoroshiku (Oliver Heer)  # inherited as {vessel} below
zenodo:
  creators:
    - Gregor, Luke, 0000-0001-6071-1857
    - Smith, Jane, https://orcid.org/0000-0002-1825-0097
  community: vendee-globe-co2
  resource_type: dataset
  license: cc-by-4.0
  publisher: Zenodo
  description: Raw underway carbon dioxide observations from an ocean-going yacht.
  language: eng
  keywords: [carbon dioxide, underway observations, ocean]
  title_template: Surface ocean CO2 measurements on board {vessel} during the {campaign} ({campaign_date})
  publication_date: 2026-09-09
  embargo:
    enabled: false
    months: 12
    until: null
  notes: ""
  sandbox: false
```

Only top-level regular files are uploaded. Hidden files, symlinks,
`zenodo.yaml`, `.zenodo-upload.json`, and directories are excluded. A Zenodo
record's files are a flat namespace of keys with no directory concept, so
subfolders cannot be uploaded at all: every run warns about the ones it finds
and names them (`--dry-run` also lists them as `skipped subfolders`). Pack a
subfolder into a single archive beside the other files if its contents have to
be archived. Markdown
files are also copied into the record's notes with HTML escaped. `publisher`
(default `Zenodo`) is required — DataCite needs it before Zenodo will register
the DOI. The command reserves a DOI and, by default, submits the draft to its
configured community for review (the community slug is resolved to its id
automatically); pass `--no-publish` to stop at the draft stage:

```console
uv run zenodo-upload data/2306_fastnet --no-publish
```

The record becomes public only when a community curator accepts it. Once a
DOI is reserved it is written back as `doi:` into the folder's `zenodo.yaml`;
once the draft has been submitted for review, `submitted: YYYY-MM-DD` is added
too, making `zenodo.yaml` the durable record of what a folder produced. While
a review is pending, reruns leave it unchanged unless the notes — the folder's
markdown files plus the `notes:` config value — have changed, in which case
the updated notes are pushed to the draft and the review stays pending. Files
are frozen for the duration of the review, so a rerun that finds new or
changed local files warns that they will not be uploaded and points at
`--new-version` once the curator has decided.

Non-secret upload progress is kept in `.zenodo-upload.json`. A retry resumes the
same draft, skips checksum-identical files, and replaces changed files. Every
run logs what it is about to do before transferring anything — the draft it
resumed and where that record id came from, a file plan counting new, changed,
unchanged and remote-only files, one line per file as its upload starts, and a
closing summary of how many files the draft now holds. Files
that exist only in the remote draft prevent review submission; inspect them and
use `--prune` to delete them deliberately. Published records are immutable and
need `--new-version` (optionally with `--record-id`) before more files can be
uploaded; the new draft imports the previous version's files, so files
unchanged since then are not re-uploaded.

Files are public immediately unless embargoed. Pass `--embargo YYYY-MM-DD` to
restrict them until that date. An embargo can also be set in
`project.yaml`/`zenodo.yaml` via `embargo: {enabled: true, months: N}`; an
explicit `until` wins, and otherwise the release date is `months` after the
publication date (clamped to the end of short months, e.g. 29 February clamps
to 28 February). For safe end-to-end experiments, use a separate sandbox
account and token:

```console
export ZENODO_SANDBOX_ACCESS_TOKEN="..."
uv run zenodo-upload data/2306_fastnet --sandbox --dry-run
uv run zenodo-upload data/2306_fastnet --sandbox
```

`--dry-run` generates and validates the YAML and computes checksums locally,
but makes no API requests. Otherwise, uploads talk to Zenodo's modern records
API (`/api/records`) directly over `requests`; there is no third-party Zenodo
client dependency. Requests retry connection errors and HTTP
429/500/502/503/504 with bounded exponential backoff, honouring
`Retry-After`; each file is streamed from disk — never read fully into
memory — through the records API's initiate/upload/commit steps, and its md5
is verified against the local checksum before the upload counts as done. The
token is sent only as an `Authorization` header, never in a URL, and is
redacted from error messages; it is read only from the environment and never
written to the YAML, state file, output, or exception details.

The same workflow is available from Python through `load_zenodo_config`,
`generate_zenodo_config`, `parse_creators`, `ZenodoClient`, and
`upload_raw_folder`.

CSV is intentionally a flattened track view and cannot contain gridded products.
NetCDF/Zarr preserve the complete supplied dataset; fetched grids are exported
as separate NetCDF files.

## Legacy migration

Code under `docs/legacy_code` is reference-only and is never imported at
runtime. `read_mflog` maps to `read_expedition`; its dataframe columns now appear
as xarray `raw_*` variables. Legacy row filtering should be replaced with
`apply_qc(...).where(ds.qc_good)` so rejected data remain inspectable.

## Development

```console
uv run ruff check .
uv run mypy
uv run pytest --cov=yacht_co2 --cov-branch
```

Offline tests use synthetic provider fixtures and do not require credentials.
