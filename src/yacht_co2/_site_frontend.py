"""Frontend assets for the static campaign explorer."""

STYLE = """
:root{color-scheme:light;font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--bg:#f3f7f8;--panel:#fff;--ink:#102a33;--muted:#587079;--border:#dbe6e9;--sea:#e4f1f4;--accent:#e6533d;--teal:#087e8b;--teal-soft:#e8f5f6;--warning:#9b5700;--warning-bg:#fff4dc;--shadow:0 4px 18px #0b2b3412}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}button,select{font:inherit}button,select,input{accent-color:var(--teal)}button{cursor:pointer}
.masthead{display:flex;justify-content:space-between;align-items:end;gap:1.5rem;padding:1.15rem max(1.25rem,calc((100vw - 1500px)/2));background:#073b4c;color:white}.masthead h1{margin:.05rem 0 0;font-size:clamp(1.65rem,2vw,2.15rem);line-height:1.15}.eyebrow{margin:0;color:var(--muted);font-size:.72rem;font-weight:750;letter-spacing:.09em;text-transform:uppercase}.masthead .eyebrow{color:#b9d6de}.filters-panel{grid-column:1/-1}.filters-row{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem 1.5rem;flex-wrap:wrap}.filter-toggles{display:flex;align-items:center;gap:1.1rem;flex-wrap:wrap}.phase-field{color:var(--muted)}.phase-pills{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.15rem}.phase-pill{min-height:36px;padding:.32rem .7rem;border:1px solid var(--pill-colour,var(--border));border-radius:99px;background:var(--panel);color:var(--muted);font-size:.78rem;font-weight:650;display:inline-flex;align-items:center;gap:.45rem}.phase-pill:hover{color:var(--ink);box-shadow:inset 0 0 0 1px var(--pill-colour,var(--teal))}.phase-pill[aria-pressed=true]{background:var(--pill-colour,var(--teal));color:var(--pill-ink,#fff);font-weight:750;border-color:transparent;box-shadow:0 1px 4px #0b2b3426}.phase-pill[aria-pressed=true]:hover{border-color:transparent;filter:brightness(1.06)}.phase-pill-all[aria-pressed=true]{background:var(--teal);color:#fff}.phase-qc-note{margin:.75rem 0 0;font-size:.78rem;font-weight:500;color:var(--muted)}.toggle-wrap{position:relative}.info-wrap{position:relative;display:inline-flex}.toggle{display:inline-flex;align-items:center;gap:.55rem;min-height:44px;font-weight:650;white-space:nowrap}.toggle input{width:1.15rem;height:1.15rem}.qc-popover{position:absolute;z-index:1001;top:calc(100% + .45rem);right:0;width:min(620px,calc(100vw - 2rem));padding:.8rem;border:1px solid #cfdcdf;border-radius:9px;background:#fff;color:#29454e;box-shadow:0 8px 24px #062a3540;font-size:.78rem;font-weight:500;line-height:1.35;white-space:normal;opacity:0;pointer-events:none;transform:translateY(-3px);transition:opacity .15s,transform .15s}.toggle-wrap:hover .qc-popover,.toggle-wrap:focus-within .qc-popover,.info-wrap:hover .qc-popover,.info-wrap:focus-within .qc-popover{opacity:1;pointer-events:auto;transform:translateY(0)}.qc-popover>strong,.qc-intro{display:block}.qc-popover>strong{margin-bottom:.15rem;font-size:.86rem}.qc-intro{margin-bottom:.55rem;color:#587079}.qc-table-wrap{display:block;max-height:min(58vh,390px);overflow:auto}.qc-popover table{font-size:.74rem;white-space:normal}.qc-popover th,.qc-popover td{padding:.34rem .42rem;text-align:left;color:#29454e;vertical-align:top}.qc-popover thead th{color:#587079}.qc-popover tbody th{font-size:.74rem;text-transform:none;letter-spacing:0}
main{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:1rem;max-width:1532px;margin:auto;padding:1rem}.panel,.chart-panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow)}.panel{padding:1.1rem}.panel-heading,.section-heading,.chart-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem}.panel-heading h2,.section-heading h2{margin:.12rem 0 0;font-size:1.3rem;line-height:1.2}
#map{width:100%;height:390px;margin-top:.9rem;background:var(--sea);border:1px solid var(--border);border-radius:9px;overflow:hidden}.compact-field{display:grid;gap:.2rem;color:var(--muted);font-size:.78rem;font-weight:650}.compact-field select,.line-select{min-height:40px;padding:.45rem 2.2rem .45rem .65rem;border:1px solid #b9cbd0;border-radius:7px;background:var(--panel);color:var(--ink)}
.map-footer{display:flex;justify-content:space-between;align-items:end;gap:.75rem 1rem;flex-wrap:wrap;margin-top:.65rem}.map-variable{min-height:40px;padding:.45rem 2.2rem .45rem .65rem;border:1px solid #b9cbd0;border-radius:7px;background:var(--panel);color:var(--ink)}.map-footer .map-legend{margin-top:0}.map-legend{display:grid;grid-template-columns:auto minmax(90px,170px) auto;align-items:center;justify-content:end;gap:.5rem;margin-top:.65rem;color:var(--muted);font-size:.78rem;font-variant-numeric:tabular-nums}.colour-bar{height:1em;border-radius:99px;background:linear-gradient(90deg,#5e4fa2,#3288bd,#66c2a5,#abdda4,#e6f598,#ffffbf,#fee08b,#fdae61,#f46d43,#d53e4f,#9e0142)}.legend-title{grid-column:1/-1;text-align:right;font-weight:650;color:var(--ink)}.track-tooltip strong,.track-tooltip span{display:block}.track-tooltip strong{margin-bottom:.12rem}.track-tooltip span{color:#405961;font-size:.78rem;font-variant-numeric:tabular-nums}
.expedition-name{margin:.9rem 0 .15rem;font-size:1.18rem;font-weight:750}.expedition-subtitle,.date-line{margin:.1rem 0;color:var(--muted)}.date-line{font-variant-numeric:tabular-nums}.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin:1rem 0}.stat{padding:.7rem;border:1px solid var(--border);border-radius:9px;background:#f8fbfc}.stat strong,.stat span{display:block}.stat strong{font-size:1.08rem;font-variant-numeric:tabular-nums}.stat span{margin-top:.12rem;color:var(--muted);font-size:.72rem;font-weight:650;text-transform:uppercase}.stat.warning{border-color:#efcf8f;background:var(--warning-bg);color:var(--warning)}.quality-note{margin:.7rem 0;padding:.65rem .75rem;border-left:3px solid var(--warning);border-radius:0 7px 7px 0;background:var(--warning-bg);color:#6d4305}.flag-list{display:flex;flex-wrap:wrap;gap:.4rem;margin:.7rem 0}.badge{padding:.28rem .5rem;border-radius:99px;background:var(--teal-soft);color:#24525c;font-size:.76rem;font-weight:650}.variable-details{margin-top:.8rem;border-top:1px solid var(--border);padding-top:.7rem}.variable-details summary{cursor:pointer;font-weight:700}.table-wrap{overflow-x:auto;margin-top:.65rem}table{width:100%;border-collapse:collapse;font-size:.82rem;white-space:nowrap}th,td{padding:.38rem .5rem;border-bottom:1px solid var(--border);text-align:right;font-variant-numeric:tabular-nums}th{color:var(--muted);font-size:.72rem;text-transform:uppercase}th:first-child,td:first-child{text-align:left}
.charts-section{grid-column:1/-1;display:grid;gap:.8rem;margin-top:.15rem}.section-heading{align-items:end;padding:.2rem}.section-note{margin:.2rem 0 0;color:var(--muted);font-size:.86rem}.button{min-height:40px;padding:.5rem .8rem;border:1px solid #adc4ca;border-radius:8px;background:var(--panel);color:var(--ink);font-weight:680}.button:hover{border-color:var(--teal);background:var(--teal-soft)}.button.primary{border-color:var(--teal);background:var(--teal);color:white}.button:disabled{cursor:not-allowed;opacity:.45}.charts{display:grid;gap:.8rem}.chart-panel{overflow:hidden}.chart-heading{padding:.75rem 1rem .65rem}.chart-controls{flex:1;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.45rem}.line-controls{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:.45rem}.axis-field{display:grid;grid-template-columns:auto minmax(108px,1fr);align-items:center;gap:.35rem;color:var(--muted);font-size:.76rem;font-weight:700}.axis-field select{min-height:40px;padding:.45rem 2rem .45rem .6rem;border:1px solid #b9cbd0;border-radius:7px;background:var(--panel);color:var(--ink)}.line-control{display:flex;align-items:stretch;gap:0;border:1px solid #b9cbd0;border-radius:7px;background:var(--panel);overflow:hidden}.line-control:focus-within{border-color:var(--teal);box-shadow:0 0 0 2px var(--teal-soft)}.line-select{max-width:250px}.line-control .line-select{flex:1;min-width:0;min-height:40px;border:0;border-radius:0;background:transparent}.line-swatch{width:30px;min-height:40px;align-self:stretch;padding:3px;border:0;border-right:1px solid var(--border);border-radius:0;background:transparent;flex:none;cursor:pointer;appearance:none;-webkit-appearance:none}.line-swatch:hover{background:var(--teal-soft)}.line-swatch:focus-visible{outline:2px solid var(--teal);outline-offset:-2px}.line-swatch::-webkit-color-swatch-wrapper{padding:2px}.line-swatch::-webkit-color-swatch{border:none;border-radius:3px}.line-swatch::-moz-color-swatch{border:none;border-radius:3px}.chart-controls.stacked,.chart-controls.stacked .line-controls{flex-direction:column;align-items:stretch}.chart-controls.stacked .line-control,.chart-controls.stacked .axis-field{width:100%}.chart-controls.stacked .line-select{max-width:none;flex:1}.section-actions{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}.charts-heading{justify-content:flex-end;align-items:center}.info-button{width:32px;height:32px;padding:0;border:1px solid #adc4ca;border-radius:99px;background:var(--panel);color:var(--muted);font-size:.9rem;font-weight:750;font-style:italic;line-height:1}.info-button:hover,.info-button:focus-visible{border-color:var(--teal);background:var(--teal-soft);color:var(--teal)}.button.toggle{gap:.5rem;padding:.5rem .75rem;font-weight:680;white-space:nowrap}.button.toggle:has(input:checked){border-color:var(--teal);background:var(--teal-soft);color:var(--teal)}.button.toggle:has(input:disabled){cursor:not-allowed;opacity:.45}.remove-line,.remove-chart{min-height:40px;padding:.4rem .58rem;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--muted)}.remove-line:hover,.remove-chart:hover{border-color:#bf7065;color:#8e2f22}.line-control .remove-line{border:0;border-left:1px solid var(--border);border-radius:0;white-space:nowrap}.line-control .remove-line:hover{background:#bf706526;color:#8e2f22}.chart{width:100%;height:340px;background:linear-gradient(180deg,#f7fbfc,#eef7f8);border-top:1px solid var(--border);border-bottom:10px solid #eef7f8;outline:none}.chart:focus-visible{box-shadow:inset 0 0 0 3px #1b8ea3}.chart .plot-container{height:100%!important}.chart .modebar-container{position:absolute!important;top:auto!important;left:auto!important;right:0!important;bottom:0!important;width:auto!important;height:auto!important;z-index:5}.chart .modebar{position:static!important;top:auto!important;right:auto!important;bottom:auto!important;left:auto!important;transform:none!important;margin:0 6px 4px 0!important;display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;align-items:center!important}.chart .modebar.vertical{flex-direction:row!important}.chart .modebar-group{float:none!important;display:flex!important;flex-direction:row!important}.chart .modebar,.chart .modebar-group{padding:2px!important;border:0!important;background:transparent!important;box-shadow:none!important}.chart .modebar-btn path{fill:#3e5961!important}.chart .modebar-btn:hover path,.chart .modebar-btn.active path{fill:var(--teal)!important}.readout-bar{position:sticky;bottom:0;z-index:900;width:100%;border-top:1px solid var(--border);background:#fbfdfdf5;box-shadow:0 -3px 14px #0b2b3420;backdrop-filter:blur(8px)}.readout{display:flex;justify-content:space-between;align-items:center;gap:1rem;width:100%;min-height:44px;padding:.65rem max(1.25rem,calc((100vw - 1500px)/2));font-variant-numeric:tabular-nums}.readout-time{font-weight:750;white-space:nowrap}.readout-values{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.35rem .8rem;color:var(--muted)}.qc-good{color:#137153;font-weight:700}.qc-flagged{color:#a13f2f;font-weight:700}.page-note{padding:.2rem max(1.25rem,calc((100vw - 1500px)/2)) .9rem;color:var(--muted);font-size:.82rem;line-height:1.5}.page-note p{margin:.35rem 0;max-width:80ch}.page-note strong{color:var(--ink)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:900px){.stat-grid{grid-template-columns:repeat(2,1fr)}.chart-heading{display:grid}.chart-controls{justify-content:flex-start}.line-controls{justify-content:flex-start}.line-select{max-width:min(68vw,300px)}}
@media(max-width:760px){.masthead{align-items:flex-start;padding:1rem}.masthead,.panel-heading{flex-wrap:wrap}main{grid-template-columns:1fr;padding:.7rem}.panel{padding:.85rem}#map{height:300px}.chart{height:295px}.readout{display:grid;gap:.25rem;padding:.6rem 1rem}.readout-values{justify-content:flex-start}.section-heading{align-items:flex-start}.map-legend{justify-content:stretch}.charts-section{min-width:0}}
@media(max-width:460px){.masthead{display:grid}.filters-row{display:grid}.chart-controls,.line-controls{display:grid;grid-template-columns:1fr auto}.axis-field{grid-column:1/-1}.line-control{display:flex;grid-column:1/-1;align-items:stretch;gap:0}.line-select{max-width:none;width:100%}.button.add-line{grid-column:1/-1}.section-heading{display:grid}.section-heading .button{width:100%}.section-actions{width:100%}}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#0d2027;--panel:#17323b;--ink:#edf8fa;--muted:#a8c0c7;--border:#31505a;--sea:#102e3a;--teal-soft:#20454d;--warning:#ffd27c;--warning-bg:#4b381d;--shadow:0 4px 18px #0004}.stat{background:#142d35}.readout-bar{background:#142d35f5;box-shadow:0 -3px 14px #0006}.chart{background:linear-gradient(180deg,#183640,#142e36);border-bottom-color:#142e36}.badge{color:#c7e7ec}.quality-note{color:#ffe4aa}}
"""

SCRIPT = r"""
const S=window.YACHT_DATA, R=window.YACHT_REPORT, q=x=>document.querySelector(x);
// --- Developer-editable settings --------------------------------------------
// 'inline' keeps the line controls on one wrapping row beside the chart (the
// default); 'stacked' gives each its own row. Toggle this to try the taller one.
const LINE_CONTROL_LAYOUT='inline';
const MAX_LINES_PER_CHART=4;
const PHASE_BAND_OPACITY=.16;
// Cycled across phase codes in order, so each phase gets a stable colour that
// the band, the picker pill and the key all agree on.
const PHASE_BAND_COLOURS=['#5e4fa2','#3288bd','#66c2a5','#f46d43','#fdae61','#9e0142','#bd8218','#3f78b5'];
const PHASE_BAND_NEUTRAL='#8a9aa0'; // fill for a code with no label in phase_meta
const MAX_PHASE_BANDS=600; // skip banding rather than hand Plotly this many shapes
// -----------------------------------------------------------------------------
const finite=x=>Number.isFinite(x), extent=a=>{const v=a.filter(finite);return v.length?[Math.min(...v),Math.max(...v)]:[0,1]};
// Colour limits clipped to a central percentile range so a handful of extreme
// values cannot flatten the scale the rest of the track is read against.
const MAP_CLIP=[.025,.975];
// The selected observation is the same red everywhere it is drawn: a dot on
// the map, and a dot on every series of every chart.
const SELECTED_COLOUR='#e6533d', SELECTED_EDGE='#000';
const percentileRange=(a,plo,phi)=>{const v=a.filter(finite).sort((x,y)=>x-y);if(!v.length)return [0,1];
 const at=p=>{const idx=(v.length-1)*p,i=Math.floor(idx),f=idx-i;return i+1<v.length?v[i]+(v[i+1]-v[i])*f:v[i]};
 const lo=at(plo),hi=at(phi);return hi>lo?[lo,hi]:[v[0],v[v.length-1]]};
const spectralR=['#5e4fa2','#3288bd','#66c2a5','#abdda4','#e6f598','#ffffbf','#fee08b','#fdae61','#f46d43','#d53e4f','#9e0142'];
function colorFor(value){const t=Math.min(1,Math.max(0,value))*(spectralR.length-1),i=Math.min(spectralR.length-2,Math.floor(t)),mix=t-i,a=spectralR[i].slice(1).match(/../g).map(x=>parseInt(x,16)),b=spectralR[i+1].slice(1).match(/../g).map(x=>parseInt(x,16));return `rgb(${a.map((v,j)=>Math.round(v+(b[j]-v)*mix)).join(',')})`}
const lineColours=['#007f86','#d2604b','#6f5aa7','#bd8218','#3f78b5','#4f8a67','#b24f78','#526f78'];
const variableColours=new Map();
// A colour picked on a swatch beats the cycled default, and is held per
// variable rather than per line, so the same series reads the same way in
// every chart that draws it.
const colourOverrides=new Map();
const timestamps=S.time.map(Date.parse), good=S.qc.map(x=>x===0);
// The instrument cycles through sampling phases -- seawater, air, gas standards
// -- so the page is filtered by phase as well as by QC, independently.
const phases=S.phase||null, phaseMeta=S.phase_meta||{}, phaseFlag=S.phase_flag||0;
// An empty set means "every phase"; a non-empty one is the phases kept.
let phaseFilter=new Set();
const phaseCodesSorted=phases?[...new Set(phases)].sort((a,b)=>a-b):[];
const phaseColourMap=new Map();
(function assignPhaseColours(){let i=0;for(const code of phaseCodesSorted)phaseColourMap.set(code,code===-1?PHASE_BAND_NEUTRAL:PHASE_BAND_COLOURS[i++%PHASE_BAND_COLOURS.length])})();
function contrastInk(hex){const [r,g,b]=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*r+.7152*g+.0722*b>.42?'#102a33':'#fff'}
function phaseColour(code){return phaseColourMap.has(code)?phaseColourMap.get(code):PHASE_BAND_NEUTRAL}
function phaseName(code){const named=phaseMeta[String(code)];return code===-1?'No phase recorded':named?`${named} (${code})`:`Phase ${code}`}
function phaseOk(i){return !phaseFilter.size||!phases||phaseFilter.has(phases[i])}
// QC flags every phase outside the analysis set, so asking for specific
// phases and for QC-good at once would always be empty. Naming phases is
// itself the statement that their exclusion is the point, so that one bit
// stops counting against them; every other check still does.
function qcOk(i){return !phaseFilter.size?good[i]:(S.qc[i]&~phaseFlag)===0}
function included(i){return (!q('#good').checked||qcOk(i))&&phaseOk(i)}
// Contiguous runs of one phase code, computed once so redraws are cheap.
function computePhaseRuns(){
 if(!phases||!phases.length)return [];
 const runs=[];let start=0;
 for(let i=1;i<=phases.length;i++){if(i===phases.length||phases[i]!==phases[start]){runs.push({code:phases[start],start,end:i-1});start=i}}
 return runs;
}
const phaseRuns=computePhaseRuns();
// The opening view: the raw CO2 reading against water temperature on the
// chart, and the same raw CO2 colouring the track. A campaign that does not
// log these falls back to whatever variable it carries first.
const defaultChartVariables=['raw_co2','raw_watertemp'].filter(name=>S.variables.includes(name));
const defaultMapVariable=S.variables.includes('raw_co2')?'raw_co2':S.variables[0];
let mapVariable=defaultMapVariable, selectedIndex=0, nextChartId=2, activeRangeChartId=null;
let charts=[{id:1,variables:defaultChartVariables.length?defaultChartVariables:[S.variables[0]],x:'time',range:null,y:emptyYLimits()}];

function displayUnit(value){return String(value||'').replaceAll('uatm','µatm')}
function meta(name){return (S.variable_meta&&S.variable_meta[name])||{label:name.replaceAll('_',' '),units:''}}
function label(name){return meta(name).label||name}
function unit(name){return displayUnit(meta(name).units)}
function variableColour(name){if(colourOverrides.has(name))return colourOverrides.get(name);if(!variableColours.has(name))variableColours.set(name,lineColours[variableColours.size%lineColours.length]);return variableColours.get(name)}
const HEX=/^#[0-9a-f]{6}$/i;
function setVariableColour(name,hex){
 if(!HEX.test(hex))return;colourOverrides.set(name,hex.toLowerCase());
 for(const el of document.querySelectorAll('.line-swatch'))if(el.dataset.variable===name)el.value=hex.toLowerCase();
 drawCharts();
}
function normalUnit(name){return unit(name).toLowerCase().replaceAll('μ','µ').replaceAll(' ','').replaceAll('−','-')}
const profileCache=new Map();
function scaleProfile(name){if(profileCache.has(name))return profileCache.get(name);const values=S.data[name].filter((v,i)=>good[i]&&finite(v)).sort((a,b)=>a-b),at=p=>values.length?values[Math.min(values.length-1,Math.floor((values.length-1)*p))]:0,q10=at(.1),q50=at(.5),q90=at(.9),profile={scale:Math.max(Math.abs(q50),Math.abs(q90-q10),1e-12)};profileCache.set(name,profile);return profile}
function axisCompatible(a,b){const ua=normalUnit(a),ub=normalUnit(b);if(ua!==ub)return false;const sa=scaleProfile(a).scale,sb=scaleProfile(b).scale;return Math.max(sa,sb)/Math.min(sa,sb)<=20}
function axisPlan(names){const reps=[],assignments=[];for(const name of names){let axis=reps.findIndex(rep=>axisCompatible(name,rep));if(axis<0&&reps.length<2){reps.push(name);axis=reps.length-1}if(axis<0)axis=1;assignments.push(axis===0?'y':'y2')}return {reps,assignments}}
function allowedForLine(chart,lineIndex){const others=chart.variables.filter((_,i)=>i!==lineIndex),reps=axisPlan(others).reps;if(reps.length<2)return S.variables;return S.variables.filter(name=>reps.some(rep=>axisCompatible(name,rep)))}
function addableVariables(chart){const reps=axisPlan(chart.variables).reps,unused=S.variables.filter(name=>!chart.variables.includes(name));if(reps.length<2)return unused;return unused.filter(name=>reps.some(rep=>axisCompatible(name,rep)))}
function axisLabel(names){const units=[...new Set(names.map(unit).filter(Boolean))];return units.length?units.join(' / '):names.map(label).join(' / ')}
// `allowed` names which of the full variable list may be picked; the rest
// stay in the list but disabled, so a variable explains its own absence
// instead of silently vanishing once the chart's axes are spoken for.
function optionGroups(select,allowed=null){
 const groups=[['Core CO₂',[]],['Water and navigation',[]],['Instrument diagnostics',[]],['Other',[]]];
 for(const name of S.variables){
  let i=name.startsWith('raw_')?2:3;
  if(['fco2_seawater','pco2_seawater','pco2_equilibrator','xco2_dry','xco2_wet','raw_co2'].includes(name))i=0;
  else if(['raw_watertemp','raw_salinity','raw_watercond','raw_chl_a','lat','lon','raw_latitude','raw_longitude','raw_speed','raw_course'].includes(name)||/oxygen|(^|_)o2($|_)/i.test(name)||/^doxy/i.test(name))i=1;
  groups[i][1].push(name);
 }
 select.replaceChildren();
 for(const [title,names] of groups){if(!names.length)continue;const group=document.createElement('optgroup');group.label=title;for(const name of names){const o=document.createElement('option');o.value=name;o.textContent=label(name)+(unit(name)?` (${unit(name)})`:'');const isAllowed=!allowed||allowed.includes(name);o.disabled=!isAllowed;if(!isAllowed)o.title='Needs a third y-axis — this chart supports only two, so pair it with a compatible unit and scale.';group.append(o)}select.append(group)}
}
function eligibleIndices(){return S.time.map((_,i)=>i).filter(included)}
function nearestEligible(i){const eligible=eligibleIndices();if(!eligible.length)return Math.max(0,Math.min(S.time.length-1,i));let lo=0,hi=eligible.length-1;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(eligible[mid]<i)lo=mid+1;else hi=mid}const before=Math.max(0,lo-1);return Math.abs(eligible[before]-i)<=Math.abs(eligible[lo]-i)?eligible[before]:eligible[lo]}
function stepSelection(delta){const eligible=eligibleIndices(),pos=eligible.indexOf(selectedIndex);if(!eligible.length)return;const next=pos<0?(delta>0?0:eligible.length-1):Math.max(0,Math.min(eligible.length-1,pos+delta));move(eligible[next])}
function gapThreshold(){const diffs=[];for(let i=1;i<timestamps.length;i++){const d=timestamps[i]-timestamps[i-1];if(d>0)diffs.push(d)}if(!diffs.length)return Infinity;diffs.sort((a,b)=>a-b);const median=diffs[Math.floor(diffs.length/2)];return Math.max(median*5,10*60*1000)}
const gapLimit=gapThreshold();

const hasMap=typeof L!=='undefined';
let map=null, baseLayers=null, trackLayer=null, posMarker=null, mapHasFit=false;
if(hasMap){
 map=L.map('map',{renderer:L.canvas()});
 // Every basemap here is an open-access tile service that permits third-party
 // embedding. OSM's own tile.openstreetmap.org is deliberately absent: the
 // OSMF policy blocks callers it cannot identify, and a browser page cannot
 // set the Referer or User-Agent it wants, so it answers 403 tiles. Esri's
 // street map carries the same OSM-derived cartography from a host that
 // serves us. The {s} subdomain placeholder is gone everywhere too -- the
 // a/b/c shards it expands to are deprecated.
 baseLayers={
  'Ocean':L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',{maxZoom:16,attribution:'Esri, GEBCO, NOAA, National Geographic, DeLorme, HERE, Geonames.org'}),
  'Satellite':L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Esri, Maxar, Earthstar Geographics, and the GIS User Community'}),
  'Street':L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Esri, HERE, Garmin, OpenStreetMap contributors, and the GIS User Community'})
 };
 baseLayers.Ocean.addTo(map);
 const overlays={'Sea marks':L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; OpenSeaMap contributors'})};
 L.control.layers(baseLayers,overlays,{position:'topright'}).addTo(map);
 // A tile service that stops answering otherwise fails as a blank map with no
 // clue as to why; say it once per layer rather than per tile.
 const warned=new Set();
 for(const [name,layer] of [...Object.entries(baseLayers),...Object.entries(overlays)]){
  if(layer.on)layer.on('tileerror',()=>{if(!warned.has(name)){warned.add(name);console.warn(`Basemap "${name}" could not load its tiles.`)}})
 }
 trackLayer=L.layerGroup().addTo(map);
 posMarker=L.circleMarker([0,0],{radius:7,weight:2,color:'#fff',fillColor:SELECTED_COLOUR,fillOpacity:1}).addTo(map);
 for(const lm of (R&&R.landmarks)||[]){const marker=L.marker([lm.lat,lm.lon],{title:lm.name,alt:lm.name}).addTo(map);marker.bindTooltip(lm.name)}
 setTimeout(()=>map.invalidateSize(),0);
}else{q('#map').textContent='Map unavailable — Leaflet could not be loaded.'}

const hasChart=typeof Plotly!=='undefined';
function xValue(chart,i){return chart.x==='time'?timestamps[i]:chart.x==='lat'?S.lat[i]:S.lon[i]}
function focusedIndices(){const chart=charts.find(c=>c.id===activeRangeChartId);if(!chart||!chart.range)return null;const [lo,hi]=chart.range;return new Set(S.time.map((_,i)=>i).filter(i=>{const v=xValue(chart,i);return finite(v)&&v>=lo&&v<=hi}))}
function trackTooltip(i,value){const el=document.createElement('div');el.className='track-tooltip';const primary=document.createElement('strong'),detail=document.createElement('span');primary.textContent=`${label(mapVariable)}: ${finite(value)?value.toFixed(2):'missing'}${unit(mapVariable)?' '+unit(mapVariable):''}`;detail.textContent=`${fmtTime(S.time[i]).replace('T',' ')} · ${S.lat[i].toFixed(4)}°, ${S.lon[i].toFixed(4)}°`;el.append(primary,detail);return el}
// The opening view sits one zoom level wider than the tightest fit around the
// track, so the route is read against the coastlines and basins either side of
// it rather than filling the frame.
function drawMap(){
 const keep=S.time.map((_,i)=>included(i)),focus=focusedIndices(),values=S.data[mapVariable],scaleValues=values.filter((v,i)=>qcOk(i)&&phaseOk(i)&&finite(v)),[lo,hi]=percentileRange(scaleValues,MAP_CLIP[0],MAP_CLIP[1]);
 if(trackLayer){trackLayer.clearLayers();const bounds=[];S.lon.forEach((lon,i)=>{if(!keep[i]||!finite(lon)||!finite(S.lat[i]))return;bounds.push([S.lat[i],lon]);const v=values[i],t=finite(v)?(v-lo)/(hi-lo||1):null,inFocus=!focus||focus.has(i),outside=focus&&!inFocus,marker=L.circleMarker([S.lat[i],lon],{radius:outside?2.2:3.3,weight:0,fillColor:outside?'#98a7ab':t===null?'#7d8c90':colorFor(t),fillOpacity:outside?.38:.92}).addTo(trackLayer);marker.bindTooltip(trackTooltip(i,v),{direction:'top',offset:[0,-4],opacity:.96})});if(bounds.length&&!mapHasFit){map.fitBounds(L.latLngBounds(bounds),{padding:[18,18]});map.setZoom(Math.max(map.getZoom()-1,map.getMinZoom()),{animate:false});mapHasFit=true}}
 const count=focus?[...focus].filter(i=>keep[i]).length:null,empty=!keep.some(Boolean);
 q('#legend-title').textContent=`Track colour · ${label(mapVariable)}${unit(mapVariable)?` (${unit(mapVariable)})`:''}${count===null?'':` · ${count} observations in chart window`}${empty?' · nothing to show for this phase with the QC filter on':''}`;
 // Observations beyond the clipped limits keep the end colour, so the bound
 // is marked as inclusive rather than read as the extreme of the data.
 const [dataLo,dataHi]=extent(scaleValues);
 q('#legend-min').textContent=finite(lo)?`${lo>dataLo?'≤ ':''}${lo.toFixed(2)}`:'—';q('#legend-max').textContent=finite(hi)?`${hi<dataHi?'≥ ':''}${hi.toFixed(2)}`:'—';
}
function seriesData(name,chart){
 const xs=[],ys=[],ids=[],values=S.data[name];
 for(let i=0;i<S.time.length;i++){
  if(i&&timestamps[i]-timestamps[i-1]>gapLimit){xs.push(null);ys.push(null);ids.push(null)}
  const x=xValue(chart,i);xs.push(chart.x==='time'?S.time[i]:finite(x)?x:null);ys.push(included(i)&&finite(values[i])?values[i]:null);ids.push(i);
 }
 return {xs,ys,ids};
}
function emptyYLimits(){return {yaxis:null,yaxis2:null}}
function dataExtent(names){let lo=Infinity,hi=-Infinity;for(const name of names){const values=S.data[name];for(let i=0;i<values.length;i++){const v=values[i];if(!included(i)||!finite(v))continue;if(v<lo)lo=v;if(v>hi)hi=v}}return lo<=hi?[lo,hi]:null}
// A newly chosen variable fills its axis: the limits are the data min and max
// until the reader zooms or pans that axis themselves.
function applyYLimits(chart,layout,key,names){
 const stored=chart.y[key];if(stored){layout[key].range=stored.slice();layout[key].autorange=false;return}
 const span=dataExtent(names);if(!span)return;
 const [lo,hi]=span,pad=lo===hi?(Math.abs(lo)||1)*.05:0;layout[key].range=[lo-pad,hi+pad];layout[key].autorange=false;
}
// Where the reader clicked, marked on each series that has a value there.
// One trace per y-axis, appended after the series traces in axis order, so
// move() can restyle them by index without redrawing the chart.
function cursorAxes(chart,plan){return ['y','y2'].filter(ax=>chart.variables.some((_,i)=>plan.assignments[i]===ax))}
function cursorPoint(chart,plan,axis,i){
 const x=chart.x==='time'?S.time[i]:xValue(chart,i),ok=finite(chart.x==='time'?Date.parse(x):x)&&included(i);
 const ys=ok?chart.variables.filter((_,k)=>plan.assignments[k]===axis).map(name=>S.data[name][i]).filter(finite):[];
 return {x:ys.map(()=>x),y:ys};
}
function cursorTrace(chart,plan,axis){const p=cursorPoint(chart,plan,axis,selectedIndex);return {x:p.x,y:p.y,yaxis:axis,type:'scattergl',mode:'markers',marker:{color:SELECTED_COLOUR,size:11,line:{color:SELECTED_EDGE,width:2}},hoverinfo:'skip',showlegend:false,name:'Selected observation'}}
// A phase switch, a data gap and a QC drop all look like the same hole in a
// line, so each contiguous phase run gets a shaded band behind the traces --
// but only on a time axis, and only when the runs are few enough to be cheap.
let showPhaseBands=false;
function phaseBandShapes(chart){
 if(!showPhaseBands||chart.x!=='time'||phaseRuns.length<2||phaseRuns.length>MAX_PHASE_BANDS)return [];
 return phaseRuns.map(run=>({type:'rect',xref:'x',yref:'paper',x0:S.time[run.start],x1:S.time[run.end],y0:0,y1:1,layer:'below',line:{width:0},fillcolor:phaseColour(run.code),opacity:PHASE_BAND_OPACITY}));
}
function drawChart(chart){
 const gd=q(`#chart-${chart.id}`);if(!gd||!hasChart)return;
 const plan=axisPlan(chart.variables),traces=chart.variables.map((name,i)=>{const d=seriesData(name,chart),u=unit(name);return {x:d.xs,y:d.ys,customdata:d.ids,yaxis:plan.assignments[i],type:'scattergl',mode:'lines',name:label(name),line:{color:variableColour(name),width:2.8},connectgaps:false,hovertemplate:`<b>${label(name)}</b><br>%{y:.2f}${u?' '+u:''}<extra></extra>`}});
 const styles=getComputedStyle(document.documentElement),ink=getComputedStyle(document.body).color,muted=styles.getPropertyValue('--muted').trim(),border=styles.getPropertyValue('--border').trim();
 const leftNames=chart.variables.filter((_,i)=>plan.assignments[i]==='y'),rightNames=chart.variables.filter((_,i)=>plan.assignments[i]==='y2'),leftColour=variableColour(leftNames[0]),rightColour=rightNames.length?variableColour(rightNames[0]):muted;
 const xTitle=chart.x==='time'?'Time (UTC)':chart.x==='lat'?'Latitude (°N)':'Longitude (°E)',layout={margin:{l:62,r:rightNames.length?68:18,t:12,b:58},modebar:{orientation:'h'},xaxis:{type:chart.x==='time'?'date':'linear',title:{text:xTitle,font:{color:muted}},showgrid:false,zeroline:false,tickfont:{color:muted},showspikes:true,spikemode:'across',spikethickness:1,spikecolor:muted},yaxis:{title:{text:axisLabel(leftNames),font:{color:leftColour}},tickfont:{color:leftColour},tickformat:'.3~g',gridcolor:border,zeroline:false},shapes:phaseBandShapes(chart),paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:ink,size:12},showlegend:false,hoverlabel:{bgcolor:'#fff',bordercolor:'#cfdcdf',font:{color:'#102a33',size:12}},hovermode:'x unified',dragmode:'zoom',uirevision:`chart-${chart.id}-${chart.x}-${chart.variables.join('|')}`};
 if(chart.range)Object.assign(layout.xaxis,{range:chart.range.slice(),autorange:false});
 if(rightNames.length)layout.yaxis2={title:{text:axisLabel(rightNames),font:{color:rightColour}},tickfont:{color:rightColour},tickformat:'.3~g',overlaying:'y',side:'right',showgrid:false,zeroline:false};
 applyYLimits(chart,layout,'yaxis',leftNames);if(rightNames.length)applyYLimits(chart,layout,'yaxis2',rightNames);
 const cursorTraces=cursorAxes(chart,plan).map(ax=>cursorTrace(chart,plan,ax));
 Plotly.react(gd,[...traces,...cursorTraces],layout,{displayModeBar:true,displaylogo:false,responsive:true,scrollZoom:false,modeBarButtonsToRemove:['select2d','lasso2d','autoScale2d','toggleSpikelines','hoverClosestCartesian','hoverCompareCartesian']}).then(()=>bindChart(gd,chart));
}
// When linking is on, a zoom/pan on one chart is echoed to every other chart
// on the same x setting; the guard stops that echo from bouncing back.
let linkXAxes=false, relayoutGuard=false;
function syncLinkedRanges(source){
 if(!linkXAxes||relayoutGuard)return;
 relayoutGuard=true;
 for(const chart of charts){
  if(chart.id===source.id||chart.x!==source.x)continue;
  chart.range=source.range?source.range.slice():null;
  const gd=q(`#chart-${chart.id}`);if(!gd)continue;
  if(chart.range){const [lo,hi]=chart.range,toAxis=v=>chart.x==='time'?new Date(v).toISOString():v;Plotly.relayout(gd,{'xaxis.range':[toAxis(lo),toAxis(hi)],'xaxis.autorange':false})}
  else Plotly.relayout(gd,{'xaxis.autorange':true});
 }
 // Plotly may emit the echoing relayout after this loop returns, so the
 // guard is dropped a tick later rather than here.
 setTimeout(()=>{relayoutGuard=false},0);
}
function bindChart(gd,chart){
 if(gd._scrubBound)return;gd._scrubBound=true;gd.tabIndex=0;gd.setAttribute('role','application');gd.setAttribute('aria-label','Observation chart. Click a point to select it, drag across the plot to zoom, or double click to reset. Use arrow keys for adjacent valid observations.');
 gd.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();stepSelection(e.key==='ArrowRight'?1:-1)}});gd.on('plotly_click',ev=>{const point=ev.points&&ev.points[0],i=point&&point.customdata;if(Number.isInteger(i))move(nearestEligible(i))});gd.on('plotly_relayout',ev=>{if(relayoutGuard)return;const start=ev['xaxis.range[0]'],end=ev['xaxis.range[1]'];if(start!==undefined&&end!==undefined){const convert=v=>chart.x==='time'?Date.parse(v):Number(v),a=convert(start),b=convert(end);if(finite(a)&&finite(b)){chart.range=[Math.min(a,b),Math.max(a,b)];activeRangeChartId=chart.id;drawMap();syncLinkedRanges(chart);writeHash()}}else if(ev['xaxis.autorange']){chart.range=null;if(activeRangeChartId===chart.id)activeRangeChartId=null;drawMap();syncLinkedRanges(chart);writeHash()}
  for(const key of ['yaxis','yaxis2']){const lo=ev[`${key}.range[0]`],hi=ev[`${key}.range[1]`];if(lo!==undefined&&hi!==undefined)chart.y[key]=[Number(lo),Number(hi)];else if(ev[`${key}.autorange`])chart.y[key]=null}});
 bindAxisWheelZoom(gd);
}
// The wheel only bites in the gutter beside an axis, so it scrolls the page
// over the plot itself and zooms just the axis the pointer rests on; the
// cursor switches to a resize glyph over that gutter so the trick is findable.
function bindAxisWheelZoom(gd){
 const zoomKeyAt=(clientX,clientY)=>{
  const full=gd._fullLayout,xa=full&&full.xaxis;if(!xa||xa._offset===undefined)return null;
  const box=gd.getBoundingClientRect(),px=clientX-box.left,py=clientY-box.top;
  const key=px<xa._offset?'yaxis':(px>xa._offset+xa._length&&full.yaxis2?'yaxis2':null);if(!key)return null;
  const ya=full[key];if(!ya||ya._offset===undefined)return null;
  if(py<ya._offset||py>ya._offset+ya._length)return null;
  return key;
 };
 gd.addEventListener('mousemove',e=>{gd.style.cursor=zoomKeyAt(e.clientX,e.clientY)?'ns-resize':''});
 gd.addEventListener('mouseleave',()=>{gd.style.cursor=''});
 gd.addEventListener('wheel',e=>{
  const key=zoomKeyAt(e.clientX,e.clientY);if(!key)return;
  const ya=gd._fullLayout[key],[lo,hi]=(ya.range||[]).map(Number);if(!finite(lo)||!finite(hi))return;
  e.preventDefault();
  const box=gd.getBoundingClientRect(),py=e.clientY-box.top;
  const factor=Math.exp((e.deltaY>0?1:-1)*.12),anchor=ya.p2l(py-ya._offset);
  Plotly.relayout(gd,{[`${key}.range`]:[anchor+(lo-anchor)*factor,anchor+(hi-anchor)*factor],[`${key}.autorange`]:false});
 },{passive:false});
}
function drawCharts(){if(!hasChart){q('#charts').innerHTML='<section class="chart-panel"><p class="quality-note">Charts unavailable — Plotly could not be loaded.</p></section>';return}for(const chart of charts)drawChart(chart)}
function draw(){selectedIndex=nearestEligible(selectedIndex);drawMap();drawCharts();move(selectedIndex);renderInfo();writeHash()}
function fmtTime(iso){const ms=Date.parse(iso.endsWith('Z')?iso:iso+'Z');if(!finite(ms))return iso;return new Date(Math.round(ms/1000)*1000).toISOString().slice(0,19)+'Z'}
function move(i){
 selectedIndex=i;if(posMarker&&finite(S.lon[i])&&finite(S.lat[i]))posMarker.setLatLng([S.lat[i],S.lon[i]]);
 for(const chart of charts){
  const gd=q(`#chart-${chart.id}`);if(!gd||!gd.data)continue;
  const plan=axisPlan(chart.variables),axes=cursorAxes(chart,plan),points=axes.map(ax=>cursorPoint(chart,plan,ax,i));
  const indices=axes.map((_,k)=>chart.variables.length+k);
  if(indices.length&&gd.data.length>indices[indices.length-1])Plotly.restyle(gd,{x:points.map(p=>p.x),y:points.map(p=>p.y)},indices);
 }
 q('#readout-time').textContent=fmtTime(S.time[i]).replace('T',' · ').replace('Z',' UTC');const names=[...new Set(charts.flatMap(c=>c.variables))];q('#readout-values').replaceChildren(...names.map(name=>{const span=document.createElement('span'),v=S.data[name][i];span.textContent=`${label(name)}: ${finite(v)?v.toFixed(2):'missing'}${unit(name)?' '+unit(name):''}`;return span}));const qc=document.createElement('span');qc.className=S.qc[i]===0?'qc-good':'qc-flagged';qc.textContent=S.qc[i]===0?'QC good':`QC flagged · code ${S.qc[i]}`;q('#readout-values').append(qc);
}
function renderInfo(){
 const el=q('#infobody');if(!el)return;if(!R){el.textContent='No report data available.';return}const exp=R.campaign||R.expedition||{},t=R.temporal||{},qc=R.quality||{},flags=Object.entries(qc.flag_counts||{}),coverage=Number(t.coverage_percent),phaseCO2=(R.phases||[]).find(p=>p.co2_variable)||{},phaseRows=(R.phases||[]).map(p=>`<tr><td>${p.label}${p.code===null?'':` (${p.code})`}</td><td>${p.records}</td><td>${p.percent}%</td><td>${p.good_records}</td><td>${p.co2_mean===null||p.co2_mean===undefined?'—':p.co2_mean}${p.co2_std===null||p.co2_std===undefined?'':` ± ${p.co2_std}`}</td></tr>`).join(''),rows=(R.variables||[]).map(v=>`<tr><td>${label(v.name)}</td><td>${displayUnit(v.units)}</td><td>${v.good}/${v.valid}</td><td>${v.min}</td><td>${v.mean}</td><td>${v.max}</td></tr>`).join('');
 el.innerHTML=`<p class="expedition-name">${exp.vessel_name||'Unnamed vessel'}</p><p class="expedition-subtitle">${[exp.vessel_type,exp.instrument,exp.co2_sensor].filter(Boolean).join(' · ')}</p><p class="date-line">${(t.start||'').slice(0,10)} to ${(t.end||'').slice(0,10)}</p><div class="stat-grid"><div class="stat"><strong>${t.days??'—'}</strong><span>Days</span></div><div class="stat"><strong>${t.records??'—'}</strong><span>Records</span></div><div class="stat ${coverage<80?'warning':''}"><strong>${t.coverage_percent??'—'}%</strong><span>Coverage</span></div><div class="stat"><strong>${qc.good_percent??'—'}%</strong><span>QC good</span></div></div>${coverage<80?`<p class="quality-note"><strong>Limited temporal coverage.</strong> ${t.gap_count??0} gap(s), ${t.gap_minutes??'—'} minutes without observations.</p>`:''}<div class="flag-list">${flags.length?flags.map(([name,count])=>`<span class="badge">${name.replaceAll('_',' ')} · ${count}</span>`).join(''):'<span class="badge">No quality flags</span>'}</div>${phaseRows?`<details class="variable-details"><summary>Sampling phases (${(R.phases||[]).length})</summary><div class="table-wrap"><table><thead><tr><th scope="col">Phase</th><th scope="col">Records</th><th scope="col">Share</th><th scope="col">QC good</th><th scope="col">Mean ${phaseCO2.co2_variable?label(phaseCO2.co2_variable):'CO₂'}${phaseCO2.co2_units?` (${displayUnit(phaseCO2.co2_units)})`:''}</th></tr></thead><tbody>${phaseRows}</tbody></table></div><p class="section-note">Mean ± standard deviation over every finite reading in the phase, QC flags included, so a zero or span phase reports what the instrument actually measured.</p></details>`:''}<details class="variable-details"><summary>Variable summary (${(R.variables||[]).length})</summary><div class="table-wrap"><table><thead><tr><th scope="col">Variable</th><th scope="col">Units</th><th scope="col">Good / valid</th><th scope="col">Min</th><th scope="col">Mean</th><th scope="col">Max</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}
function renderChartControls(){
 const root=q('#charts');root.replaceChildren();for(const [chartIndex,chart] of charts.entries()){
  const panel=document.createElement('section');panel.className='chart-panel';panel.dataset.chartId=chart.id;panel.innerHTML=`<div class="chart-heading"><div class="chart-controls"></div></div><div class="chart" id="chart-${chart.id}"></div>`;const controls=panel.querySelector('.chart-controls');controls.classList.add(LINE_CONTROL_LAYOUT);const axisField=document.createElement('label');axisField.className='axis-field';axisField.innerHTML='<span>X-axis</span><select aria-label="Chart x-axis"><option value="time">Time</option><option value="lat">Latitude</option><option value="lon">Longitude</option></select>';const axisSelect=axisField.querySelector('select');axisSelect.value=chart.x;axisSelect.onchange=()=>{chart.x=axisSelect.value;chart.range=null;if(activeRangeChartId===chart.id)activeRangeChartId=null;renderChartControls()};controls.append(axisField);
  const lines=document.createElement('div');lines.className='line-controls';
  // Each line gets a colour swatch matching its trace, so the picker below the
  // chart says which dropdown drew which line.
  chart.variables.forEach((name,lineIndex)=>{const wrap=document.createElement('span');wrap.className='line-control';const swatch=document.createElement('input');swatch.type='color';swatch.className='line-swatch';swatch.value=variableColour(name);swatch.dataset.variable=name;swatch.setAttribute('aria-label',`${label(name)} line colour`);swatch.title=`Change the ${label(name)} line colour`;swatch.oninput=()=>setVariableColour(name,swatch.value);swatch.onchange=()=>{setVariableColour(name,swatch.value);writeHash()};const select=document.createElement('select');select.className='line-select';select.setAttribute('aria-label',`Line ${lineIndex+1} variable`);optionGroups(select,allowedForLine(chart,lineIndex));select.value=name;select.onchange=()=>{chart.variables[lineIndex]=select.value;chart.y=emptyYLimits();renderChartControls()};wrap.append(swatch,select);if(chart.variables.length>1){const remove=document.createElement('button');remove.className='remove-line';remove.type='button';remove.textContent='Remove';remove.setAttribute('aria-label',`Remove ${label(name)} line`);remove.onclick=()=>{chart.variables.splice(lineIndex,1);chart.y=emptyYLimits();renderChartControls()};wrap.append(remove)}lines.append(wrap)});
  const addable=addableVariables(chart),atCap=chart.variables.length>=MAX_LINES_PER_CHART,add=document.createElement('button');add.className='button add-line';add.type='button';add.textContent='Add line';add.disabled=atCap||!addable.length;add.title=atCap?`This chart already shows the maximum of ${MAX_LINES_PER_CHART} lines.`:!addable.length?'Every remaining variable would need a third y-axis — this chart supports two.':'Add a comparison line';add.onclick=()=>{chart.variables.push(addable[0]);chart.y=emptyYLimits();renderChartControls()};lines.append(add);
  if(charts.length>1){const removeChart=document.createElement('button');removeChart.className='remove-chart';removeChart.type='button';removeChart.textContent='Remove chart';removeChart.setAttribute('aria-label',`Remove time series ${chartIndex+1}`);removeChart.onclick=()=>{charts=charts.filter(c=>c.id!==chart.id);if(activeRangeChartId===chart.id)activeRangeChartId=null;renderChartControls()};lines.append(removeChart)}controls.append(lines);root.append(panel)
 }
 draw();
}
const fmtCount=n=>n.toString().replace(/\B(?=(\d{3})+(?!\d))/g,' ');
function renderQcPhaseNote(){
 const el=q('#phase-qc-note');if(!el)return;
 if(phaseFilter.size){el.hidden=false;el.textContent='Picking specific phases ignores the phase-exclusion QC flag for them — naming a phase is the point of looking at it — every other QC check still applies.'}
 else el.hidden=true;
}
// One toggle pill per phase present, coloured to match its band and carrying
// its own record count, rather than a single-choice dropdown.
function buildPhasePicker(){
 const field=q('#phase-field'),container=q('#phase-pills');if(!field||!container||!phases)return;
 if(phaseCodesSorted.length<2)return;
 field.hidden=false;container.replaceChildren();
 const counts=new Map();for(const code of phases)counts.set(code,(counts.get(code)||0)+1);
 const allBtn=document.createElement('button');allBtn.type='button';allBtn.className='phase-pill phase-pill-all';allBtn.setAttribute('aria-pressed',String(phaseFilter.size===0));allBtn.textContent='All phases';allBtn.onclick=()=>{phaseFilter=new Set();buildPhasePicker();draw()};container.append(allBtn);
 for(const code of phaseCodesSorted){
  const btn=document.createElement('button');btn.type='button';btn.className='phase-pill';const fill=phaseColour(code);btn.style.setProperty('--pill-colour',fill);btn.style.setProperty('--pill-ink',contrastInk(fill));
  btn.setAttribute('aria-pressed',String(phaseFilter.has(code)));
  btn.textContent=`${phaseName(code)} · ${fmtCount(counts.get(code)||0)}`;
  btn.onclick=()=>{if(phaseFilter.has(code))phaseFilter.delete(code);else phaseFilter.add(code);buildPhasePicker();draw()};
  container.append(btn);
 }
 renderQcPhaseNote();
}
function renderDensityNote(){
 const el=q('#density-note'),s=S.sampling||{};if(!el)return;
 const total=Number(s.total),shown=Number(s.shown||S.time.length);
 if(!Number.isFinite(total)||!Number.isFinite(shown)){el.remove();return}
 const n=x=>x.toLocaleString('en-GB');
 if(shown>=total){el.textContent=`Showing all ${n(total)} observations of the campaign.`;return}
 const step=Math.round(total/shown);
 el.innerHTML=`Showing <strong>${n(shown)} of ${n(total)} observations</strong> (${(100*shown/total).toFixed(1)}%, about 1 in ${n(step)}): the track is stepped down, within each sampling phase, to keep this page small enough to open and email.`;
}
// The whole view -- phase selection, toggles, map variable and every chart's
// axis/variables/range -- is packed into the URL hash, so a link a colleague
// opens shows the same anomaly, not a fresh default view.
let hashWriteTimer=null;
function serialiseState(){
 return {qc:q('#good').checked?1:0,pb:showPhaseBands?1:0,lx:linkXAxes?1:0,mv:mapVariable,ph:[...phaseFilter],lc:Object.fromEntries(colourOverrides),ch:charts.map(c=>({v:c.variables,x:c.x,r:c.range}))};
}
function writeHash(){
 clearTimeout(hashWriteTimer);
 hashWriteTimer=setTimeout(()=>{
  try{history.replaceState(null,'',`#s=${encodeURIComponent(JSON.stringify(serialiseState()))}`)}catch(e){/* a full track can be large; a failed write just leaves the old hash */}
 },250);
}
// A hash is a link someone else typed or an old bookmark, so every field is
// checked against what this campaign actually has before it is trusted.
function parseHash(){
 const match=/(?:^|[#&])s=([^&]+)/.exec(location.hash);if(!match)return;
 let state;try{state=JSON.parse(decodeURIComponent(match[1]))}catch(e){return}
 if(!state||typeof state!=='object')return;
 if(typeof state.mv==='string'&&S.variables.includes(state.mv))mapVariable=state.mv;
 if(Array.isArray(state.ph))phaseFilter=new Set(state.ph.filter(code=>phaseCodesSorted.includes(code)));
 if(state.lc&&typeof state.lc==='object')for(const [name,hex] of Object.entries(state.lc))if(S.variables.includes(name)&&typeof hex==='string'&&HEX.test(hex))colourOverrides.set(name,hex.toLowerCase());
 if(state.qc===0||state.qc===1)q('#good').checked=!!state.qc;
 if(state.pb===0||state.pb===1)showPhaseBands=!!state.pb;
 if(state.lx===0||state.lx===1)linkXAxes=!!state.lx;
 if(Array.isArray(state.ch)&&state.ch.length){
  const restored=[];
  for(const c of state.ch){
   if(!c||!Array.isArray(c.v))continue;
   const vars=c.v.filter(name=>S.variables.includes(name));if(!vars.length)continue;
   const x=['time','lat','lon'].includes(c.x)?c.x:'time';
   const range=Array.isArray(c.r)&&c.r.length===2&&finite(Number(c.r[0]))&&finite(Number(c.r[1]))?[Number(c.r[0]),Number(c.r[1])]:null;
   restored.push({id:nextChartId++,variables:vars.slice(0,MAX_LINES_PER_CHART),x,range,y:emptyYLimits()});
  }
  if(restored.length)charts=restored;
 }
}
parseHash();
renderDensityNote();buildPhasePicker();optionGroups(q('#map-variable'));q('#map-variable').value=mapVariable;
q('#map-variable').onchange=e=>{mapVariable=e.target.value;drawMap();writeHash()};
q('#good').onchange=()=>{draw()};
const phaseBandsInput=q('#phase-bands');if(phaseBandsInput){
 // Silently drawing nothing would read as a broken toggle, so a track with
 // too many phase switches to shade cheaply says that is why.
 const bandable=phaseRuns.length>1&&phaseRuns.length<=MAX_PHASE_BANDS;
 phaseBandsInput.checked=showPhaseBands&&bandable;phaseBandsInput.disabled=!bandable;
 if(!bandable)phaseBandsInput.closest('.toggle').title=phaseRuns.length>MAX_PHASE_BANDS?`This track switches phase ${phaseRuns.length} times, too often to shade legibly.`:'This track holds a single sampling phase, so there is nothing to shade.';
 phaseBandsInput.onchange=()=>{showPhaseBands=phaseBandsInput.checked;drawCharts();writeHash()}}
const linkXInput=q('#link-x');if(linkXInput){linkXInput.checked=linkXAxes;linkXInput.onchange=()=>{linkXAxes=linkXInput.checked;
 // Linking is asked for to compare what is already on screen, so the charts
 // line up on the window that is open rather than at the next zoom.
 const owner=charts.find(c=>c.id===activeRangeChartId);if(linkXAxes&&owner)syncLinkedRanges(owner);writeHash()}}
// One way back to the opening view, so a reader who has filtered, zoomed and
// recoloured their way into a corner does not have to undo it step by step.
const resetButton=q('#reset-view');if(resetButton)resetButton.onclick=()=>{
 charts=[{id:nextChartId++,variables:defaultChartVariables.length?defaultChartVariables:[S.variables[0]],x:'time',range:null,y:emptyYLimits()}];
 activeRangeChartId=null;phaseFilter=new Set();colourOverrides.clear();
 mapVariable=defaultMapVariable;q('#map-variable').value=mapVariable;mapHasFit=false;
 q('#good').checked=true;
 showPhaseBands=false;if(phaseBandsInput)phaseBandsInput.checked=false;
 linkXAxes=false;if(linkXInput)linkXInput.checked=false;
 buildPhasePicker();renderQcPhaseNote();renderChartControls();writeHash();
};
q('#add-chart').onclick=()=>{charts.push({id:nextChartId++,variables:[mapVariable],x:'time',range:null,y:emptyYLimits()});renderChartControls();writeHash()};
selectedIndex=nearestEligible(0);renderChartControls();
"""
