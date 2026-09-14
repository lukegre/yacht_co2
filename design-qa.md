# Fastnet explorer design QA

- Source visual truth: original `http://localhost:3000/` dashboard captured during the current Product Design audit; interaction requirements recorded in `outputs/fastnet/design-audit.md` and the user's accepted layout notes.
- Implementation: `http://localhost:3000/`, generated from `src/yacht_co2/site.py` and `src/yacht_co2/_site_frontend.py`.
- Source screenshot: Codex in-app browser capture in the current task before implementation.
- Implementation screenshots: Codex in-app browser desktop and 390 × 844 responsive captures in the current task after implementation.
- Desktop viewport: 1546 × 1039 CSS px; captured at browser density.
- Mobile viewport: 390 × 844 CSS px; captured at browser density.
- State: light theme, QC-good filter enabled, one time-series card with seawater fCO₂, time x-axis, and an active chart zoom window.

## Full-view comparison evidence

The implementation preserves the source's two-column expedition/map row and full-width time-series region. It intentionally replaces the source's prose-heavy summary, detached range slider, and single raw-variable control with the accepted metric summary, chart scrubbing, map-colour control, and addable chart controls.

No horizontal overflow was detected: desktop document width was 1531 px in a 1546 px viewport; mobile document width was 375 px in a 390 px viewport. The top layout measured two 743 px columns on desktop and one 354 px column on mobile.

## Focused-region evidence

- Expedition: vessel, instrument, dates, four metrics, coverage warning, flag badges, and collapsible variable summary are visible and readable at both tested widths. The QC control exposes a concise explanation on hover and keyboard focus.
- Map: the colour-variable control, named landmark, current marker, and labelled Spectral_r colour scale are visible. The scale uses QC-good values so flagged outliers do not flatten the useful colour range; route observations expose value, time, and coordinates on hover.
- Time series: the long missing interval is rendered as a true gap. The chart has a visible selected-observation cursor, thicker 2.8 px traces, unit-labelled axes, restrained grid, legend, shared readout, and a compact zoom toolbar.
- Chart controls: adding water temperature beside seawater fCO₂ produced two selectors, two legend entries, a left µatm axis, and a right °C axis. Adding a chart produced two independent chart cards and two remove controls; changing the second chart updated its title and data independently.
- X-axis and zoom: each chart exposes Time, Latitude, and Longitude. Latitude was selected and visibly relabelled in the browser; zooming reduced the plotted range and updated the map legend to `3167 observations in chart window`.
- Linked map: observations outside the active chart window are neutral grey while observations inside it retain their Spectral_r colours. No white track highlight is used, and the map viewport stays stable during chart zoom.
- Ocean variables: water temperature, salinity, and chlorophyll are present and human-labelled in the Fastnet selectors. Dissolved-oxygen aliases are supported by the generator; the current Fastnet source file contains no oxygen observations, so no unavailable option is shown.
- Interaction: clicking the chart and keyboard arrow stepping update the shared timestamp and map marker; dragging zooms the x-axis. Changing the map variable updates its legend, hover values, and scale.

## Required fidelity surfaces

- Typography: system UI stack retained from the source, with clearer hierarchy, consistent weights, and readable small labels.
- Spacing and layout: card rhythm is consistent; desktop proportions preserve the source; narrow layout reflows without horizontal overflow.
- Colours and tokens: marine teal palette retained; warning colour is reserved for limited coverage; chart lines use a calmer colour-blind-friendly palette; map observations use Spectral_r and zoom-excluded markers use neutral grey.
- Image quality and assets: no source imagery was replaced. Leaflet tiles and markers remain sharp at both widths.
- Copy and content: implementation uses human-readable variable labels, explicit UTC time, explanatory chart instructions, readable QC help, and typographically correct µatm display units while retaining the source data unchanged.

## Comparison history

1. P1: the first implementation derived the map scale from flagged outliers, producing a -0.70 to 5332.05 range and visually flattening good observations. Fixed by deriving the stable scale from QC-good values; revised range is 38.20 to 224.13 for seawater fCO₂.
2. P2: initial trace assignment allowed visually similar colours for two comparison lines. Fixed with a stable session colour registry; add-line verification now renders seawater fCO₂ and seawater pCO₂ as distinct traces.
3. P2: comparison lines with different units initially shared one y-axis. Fixed with a two-axis compatibility plan based on units and robust value ranges; the browser verification shows seawater fCO₂ on the left and temperature on the right.
4. P2: the original scrub-by-drag gesture conflicted with x-axis zoom. Fixed by reserving click for observation selection and drag for zoom, with double-click and the toolbar for reset. Browser verification confirms latitude selection, zoom controls, and linked map-window highlighting.
5. P2: the first zoom-linked map treatment left outside observations faintly coloured and outlined focused observations in white. Fixed by rendering outside observations neutral grey and removing track outlines; the revised browser capture shows a grey contextual route.
6. P2: the default Plotly toolbar used a heavy grey treatment. Fixed with a white surface, subtle border and shadow, and dark teal-grey icons. Computed browser styles confirm a white background.

## Findings

- No actionable P0, P1, or P2 findings remain in the tested desktop state.

## Residual P3 polish

- A future persistence layer could remember chart configurations across reloads; persistence was not part of this implementation.
- Very large numbers of stacked charts may eventually benefit from collapse and reorder controls.

## Verification

- Focused site tests: 5 passed.
- Static checks: passed.
- Generated JavaScript syntax: passed.
- Browser warnings/errors after final reload: none.
- Full repository suite: 113 passed and 6 unrelated project-configuration tests failed because the workspace-level `project.yaml` is being merged into temporary test repositories.

final result: passed
