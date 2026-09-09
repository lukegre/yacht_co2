"""Dependency-free static interactive track explorer."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger

STYLE = """
:root{color-scheme:light dark;font:15px system-ui;--bg:#f4f7f8;--panel:#fff;--ink:#132b33;--sea:#dceff4;--accent:#e6533d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}header{padding:1rem 1.4rem;background:#073b4c;color:white}
main{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:1rem;padding:1rem}.panel{background:var(--panel);border-radius:10px;padding:1rem;box-shadow:0 2px 10px #0002}
#map,#chart{width:100%;height:360px;background:var(--sea);border-radius:6px}svg{width:100%;height:100%}.controls{display:flex;gap:1rem;flex-wrap:wrap;align-items:end}
label{display:grid;gap:.25rem}select,input{font:inherit;padding:.35rem}input[type=range]{width:min(600px,80vw)}.meta{font-variant-numeric:tabular-nums}
@media(max-width:760px){main{grid-template-columns:1fr}#map,#chart{height:280px}}@media(prefers-color-scheme:dark){:root{--bg:#0d2027;--panel:#17323b;--ink:#edf8fa;--sea:#102e3a}}
"""

SCRIPT = r"""
const S=window.YACHT_DATA, ns='http://www.w3.org/2000/svg';
const q=x=>document.querySelector(x), mk=(tag,a={})=>{let e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(a))e.setAttribute(k,v);return e};
const finite=(x)=>Number.isFinite(x), extent=a=>{let v=a.filter(finite);return v.length?[Math.min(...v),Math.max(...v)]:[0,1]}, scale=(v,a,b,c,d)=>c+(v-a)*(d-c)/(b-a||1);
let good=S.qc.map(x=>x===0), variable=S.variables[0];
function draw(){let keep=S.time.map((_,i)=>!q('#good').checked||good[i]), lons=S.lon.filter((_,i)=>keep[i]&&finite(S.lon[i])),lats=S.lat.filter((_,i)=>keep[i]&&finite(S.lat[i]));
 let [xmin,xmax]=extent(lons),[ymin,ymax]=extent(lats),map=q('#map');map.innerHTML='';let svg=mk('svg',{viewBox:'0 0 700 360',role:'img','aria-label':'Expedition map'});let pts=S.lon.map((x,i)=>keep[i]&&finite(x)&&finite(S.lat[i])?`${scale(x,xmin,xmax,25,675)},${scale(S.lat[i],ymin,ymax,335,25)}`:'').filter(Boolean).join(' ');svg.append(mk('polyline',{points:pts,fill:'none',stroke:'#087e8b','stroke-width':2}));svg.append(mk('circle',{id:'marker',r:6,fill:'#e6533d'}));map.append(svg);
 let y=S.data[variable], valid=y.filter((v,i)=>keep[i]&&finite(v)),[lo,hi]=extent(valid),chart=q('#chart');chart.innerHTML='';let cs=mk('svg',{viewBox:'0 0 700 360',role:'img','aria-label':variable+' time series'});let line=y.map((v,i)=>keep[i]&&finite(v)?`${scale(i,0,y.length-1,25,675)},${scale(v,lo,hi,335,25)}`:'').filter(Boolean).join(' ');cs.append(mk('polyline',{points:line,fill:'none',stroke:'#087e8b','stroke-width':1.5}));cs.append(mk('line',{id:'cursor',y1:20,y2:340,stroke:'#e6533d','stroke-width':2}));chart.append(cs);move(+q('#time').value)}
function move(i){q('#time').value=i;let [xmin,xmax]=extent(S.lon),[ymin,ymax]=extent(S.lat),m=q('#marker');m?.setAttribute('cx',scale(S.lon[i],xmin,xmax,25,675));m?.setAttribute('cy',scale(S.lat[i],ymin,ymax,335,25));q('#cursor')?.setAttribute('x1',scale(i,0,S.time.length-1,25,675));q('#cursor')?.setAttribute('x2',scale(i,0,S.time.length-1,25,675));q('#stamp').textContent=`${S.time[i]} | ${variable}: ${S.data[variable][i] ?? 'missing'} | QC ${S.qc[i]}`}
for(const v of S.variables){let o=document.createElement('option');o.value=o.textContent=v;q('#variable').append(o)}q('#variable').onchange=e=>{variable=e.target.value;draw()};q('#good').onchange=draw;q('#time').max=S.time.length-1;q('#time').oninput=e=>move(+e.target.value);q('#time').onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft')move(Math.max(0,Math.min(S.time.length-1,+q('#time').value+(e.key==='ArrowRight'?1:-1))))};draw();
"""


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _model(ds: xr.Dataset, max_points: int | None = None) -> dict[str, Any]:
    indices = np.arange(ds.sizes["time"])
    if max_points and len(indices) > max_points:
        indices = np.linspace(0, len(indices) - 1, max_points).astype(int)
    candidates = [
        name
        for name, arr in ds.data_vars.items()
        if arr.dims == ("time",) and np.issubdtype(arr.dtype, np.number) and name != "qc_flag"
    ]
    preferred = [
        name
        for name in (
            "fco2_seawater",
            "pco2_seawater",
            "raw_co2",
            "raw_watertemp",
            "raw_salinity",
            "co2_flux",
        )
        if name in candidates
    ]
    variables = preferred + [name for name in candidates if name not in preferred]
    return {
        "time": [pd.Timestamp(item).isoformat() for item in ds.time.values[indices]],
        "lat": [_json_value(item) for item in ds.lat.values[indices]],
        "lon": [_json_value(item) for item in ds.lon.values[indices]],
        "qc": [int(item) for item in ds.qc_flag.values[indices]],
        "variables": variables,
        "data": {
            name: [_json_value(item) for item in ds[name].values[indices]] for name in variables
        },
    }


def _body(title: str) -> str:
    return f"""<header><h1>{title}</h1><div class=controls><label>Variable<select id=variable aria-label="Displayed variable"></select></label><label><input id=good type=checkbox> QC-good only</label></div></header><main><section class=panel><h2>Track</h2><div id=map></div></section><section class=panel><h2>Time series</h2><div id=chart></div></section><section class=panel style="grid-column:1/-1"><label>Time<input id=time type=range min=0 value=0 aria-label="Time scrubber"></label><output id=stamp class=meta aria-live=polite></output></section></main>"""


def build_site(
    ds: xr.Dataset,
    destination: str | Path,
    *,
    title: str = "Yacht CO2 expedition",
    single_file: bool = False,
    max_points: int | None = None,
) -> Path:
    """Build a hosted static bundle or fully self-contained HTML artifact."""
    destination = Path(destination)
    title = escape(title)
    model = json.dumps(_model(ds, max_points), separators=(",", ":"), allow_nan=False)
    if single_file:
        path = destination if destination.suffix == ".html" else destination / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        html = f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>{title}</title><style>{STYLE}</style></head><body>{_body(title)}<script>window.YACHT_DATA={model};</script><script>{SCRIPT}</script></body></html>"
        path.write_text(html)
    else:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "style.css").write_text(STYLE)
        (destination / "app.js").write_text(SCRIPT)
        (destination / "data.js").write_text(f"window.YACHT_DATA={model};")
        path = destination / "index.html"
        path.write_text(
            f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>{title}</title><link rel=stylesheet href=style.css></head><body>{_body(title)}<script src=data.js></script><script src=app.js></script></body></html>"
        )
    logger.success("Built static site {} ({:.1f} MiB)", path, path.stat().st_size / 2**20)
    return path
