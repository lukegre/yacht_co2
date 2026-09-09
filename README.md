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

The example writes NetCDF, Zarr v2, CSV, hosted-site, and single-HTML artifacts
under `outputs/fastnet/`. To render video, set `outputs.video: true`; FFmpeg must
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
`build_site`, `render_video`, and `Pipeline.run`.

## Upload raw observations to Zenodo

`zenodo-upload` is a standalone command for creating a resumable draft with the
top-level files from one raw-data folder:

```console
export ZENODO_ACCESS_TOKEN="..."
uv run zenodo-upload data/2306_fastnet \
  --title "Raw underway CO₂ observations — Fastnet 2023"
```

Tokens may instead be stored in `.env` using the names shown in
`.env.example`. Immediately before authentication, the command loads `.env`
from the uploaded folder, the directory containing an alternative `--config`,
and the current directory, in that order. Values already exported into the
process environment are never overwritten. `.env` is ignored by Git, excluded
from uploads as a hidden file, and is not read during `--dry-run`.

On first use, `--title` is required and the command writes a complete, editable
`data/2306_fastnet/zenodo.yaml` before contacting Zenodo. Its publication date
is the current date and its default embargo ends on the same calendar date 12
months later (29 February is clamped to 28 February when needed). Configuration
is resolved in this order: packaged defaults, the folder YAML (or `--config`),
then CLI overrides.

Creators form an ordered YAML list. Each item must contain exactly a last name,
first name, and checksum-valid ORCID separated by commas. Bare ORCIDs and ORCID
URLs are accepted; a folder list replaces the packaged creator list completely.

```yaml
title: Raw underway CO₂ observations — Fastnet 2023
creators:
  - Gregor, Luke, 0000-0001-6071-1857
  - Smith, Jane, https://orcid.org/0000-0002-1825-0097
community: vendee-globe-co2
resource_type: dataset
license: cc-by-4.0
description: Raw underway carbon dioxide observations from an ocean-going yacht.
language: eng
keywords: [carbon dioxide, underway observations, ocean]
publication_date: 2026-09-09
embargo:
  enabled: true
  months: 12
  until: 2027-09-09
notes: ""
sandbox: false
```

Only top-level regular files are uploaded. Hidden files, symlinks,
`zenodo.yaml`, `.zenodo-upload.json`, and directories are excluded. Markdown
files are also copied into the record's notes with HTML escaped. The command
reserves a DOI but leaves the record as a draft unless `--publish` is supplied:

```console
uv run zenodo-upload data/2306_fastnet --publish
```

Here, “publish” means submit the draft to the configured community for review.
The record becomes public only when a community curator accepts it. While a
review is pending, reruns report it without changing metadata or files.

Non-secret upload progress is kept in `.zenodo-upload.json`. A retry resumes the
same draft, skips checksum-identical files, and replaces changed files. Files
that exist only in the remote draft prevent review submission; inspect them and
use `--prune` to delete them deliberately. Published records are immutable and
need `--new-version` (optionally with `--record-id`) before more files can be
uploaded.

Use `--no-embargo` to make files public immediately, or `--embargo-until
YYYY-MM-DD` to select an explicit end date. For safe end-to-end experiments,
use a separate sandbox account and token:

```console
export ZENODO_SANDBOX_ACCESS_TOKEN="..."
uv run zenodo-upload data/2306_fastnet --sandbox --dry-run
uv run zenodo-upload data/2306_fastnet --sandbox
```

`--dry-run` may generate and validates the YAML and checksums locally, but makes
no API requests. API requests retry rate limits and transient server/network
failures. Tokens are read only from the environment and are never written to
the YAML, state file, output, or exception details.

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
