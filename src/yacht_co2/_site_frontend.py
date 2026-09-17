"""Frontend assets for the static campaign explorer."""

STYLE = """
:root{color-scheme:light;font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--bg:#f3f7f8;--panel:#fff;--ink:#102a33;--muted:#587079;--border:#dbe6e9;--sea:#e4f1f4;--accent:#e6533d;--teal:#087e8b;--teal-soft:#e8f5f6;--warning:#9b5700;--warning-bg:#fff4dc;--shadow:0 4px 18px #0b2b3412}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}button,select{font:inherit}button,select,input{accent-color:var(--teal)}button{cursor:pointer}
.masthead{display:flex;justify-content:space-between;align-items:end;gap:1.5rem;padding:1.15rem max(1.25rem,calc((100vw - 1500px)/2));background:#073b4c;color:white}.masthead h1{margin:.05rem 0 0;font-size:clamp(1.65rem,2vw,2.15rem);line-height:1.15}.eyebrow{margin:0;color:var(--muted);font-size:.72rem;font-weight:750;letter-spacing:.09em;text-transform:uppercase}.masthead .eyebrow{color:#b9d6de}.masthead-controls{display:flex;align-items:center;gap:1.1rem;flex-wrap:wrap}.phase-field{color:#b9d6de}.phase-field select{min-height:40px;padding:.45rem 2rem .45rem .6rem;border:1px solid #3d6d80;border-radius:7px;background:#0d4a5e;color:#fff}.toggle-wrap{position:relative}.toggle{display:inline-flex;align-items:center;gap:.55rem;min-height:44px;font-weight:650;white-space:nowrap}.toggle input{width:1.15rem;height:1.15rem}.qc-popover{position:absolute;z-index:1001;top:calc(100% + .45rem);right:0;width:min(620px,calc(100vw - 2rem));padding:.8rem;border:1px solid #cfdcdf;border-radius:9px;background:#fff;color:#29454e;box-shadow:0 8px 24px #062a3540;font-size:.78rem;font-weight:500;line-height:1.35;white-space:normal;opacity:0;pointer-events:none;transform:translateY(-3px);transition:opacity .15s,transform .15s}.toggle-wrap:hover .qc-popover,.toggle-wrap:focus-within .qc-popover{opacity:1;pointer-events:auto;transform:translateY(0)}.qc-popover>strong,.qc-intro{display:block}.qc-popover>strong{margin-bottom:.15rem;font-size:.86rem}.qc-intro{margin-bottom:.55rem;color:#587079}.qc-table-wrap{display:block;max-height:min(58vh,390px);overflow:auto}.qc-popover table{font-size:.74rem;white-space:normal}.qc-popover th,.qc-popover td{padding:.34rem .42rem;text-align:left;color:#29454e;vertical-align:top}.qc-popover thead th{color:#587079}.qc-popover tbody th{font-size:.74rem;text-transform:none;letter-spacing:0}
main{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:1rem;max-width:1532px;margin:auto;padding:1rem}.panel,.chart-panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow)}.panel{padding:1.1rem}.panel-heading,.section-heading,.chart-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem}.panel-heading h2,.section-heading h2,.chart-heading h3{margin:.12rem 0 0;line-height:1.2}.panel-heading h2,.section-heading h2{font-size:1.3rem}.chart-heading h3{font-size:1.05rem}
#map{width:100%;height:390px;margin-top:.9rem;background:var(--sea);border:1px solid var(--border);border-radius:9px;overflow:hidden}.compact-field{display:grid;gap:.2rem;color:var(--muted);font-size:.78rem;font-weight:650}.compact-field select,.line-select{min-height:40px;padding:.45rem 2.2rem .45rem .65rem;border:1px solid #b9cbd0;border-radius:7px;background:var(--panel);color:var(--ink)}
.map-legend{display:grid;grid-template-columns:auto minmax(90px,170px) auto;align-items:center;justify-content:end;gap:.5rem;margin-top:.65rem;color:var(--muted);font-size:.78rem;font-variant-numeric:tabular-nums}.colour-bar{height:.45rem;border-radius:99px;background:linear-gradient(90deg,#5e4fa2,#3288bd,#66c2a5,#abdda4,#e6f598,#ffffbf,#fee08b,#fdae61,#f46d43,#d53e4f,#9e0142)}.legend-title{grid-column:1/-1;text-align:right;font-weight:650;color:var(--ink)}.track-tooltip strong,.track-tooltip span{display:block}.track-tooltip strong{margin-bottom:.12rem}.track-tooltip span{color:#405961;font-size:.78rem;font-variant-numeric:tabular-nums}
.expedition-name{margin:.9rem 0 .15rem;font-size:1.18rem;font-weight:750}.expedition-subtitle,.date-line{margin:.1rem 0;color:var(--muted)}.date-line{font-variant-numeric:tabular-nums}.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin:1rem 0}.stat{padding:.7rem;border:1px solid var(--border);border-radius:9px;background:#f8fbfc}.stat strong,.stat span{display:block}.stat strong{font-size:1.08rem;font-variant-numeric:tabular-nums}.stat span{margin-top:.12rem;color:var(--muted);font-size:.72rem;font-weight:650;text-transform:uppercase}.stat.warning{border-color:#efcf8f;background:var(--warning-bg);color:var(--warning)}.quality-note{margin:.7rem 0;padding:.65rem .75rem;border-left:3px solid var(--warning);border-radius:0 7px 7px 0;background:var(--warning-bg);color:#6d4305}.flag-list{display:flex;flex-wrap:wrap;gap:.4rem;margin:.7rem 0}.badge{padding:.28rem .5rem;border-radius:99px;background:var(--teal-soft);color:#24525c;font-size:.76rem;font-weight:650}.variable-details{margin-top:.8rem;border-top:1px solid var(--border);padding-top:.7rem}.variable-details summary{cursor:pointer;font-weight:700}.table-wrap{overflow-x:auto;margin-top:.65rem}table{width:100%;border-collapse:collapse;font-size:.82rem;white-space:nowrap}th,td{padding:.38rem .5rem;border-bottom:1px solid var(--border);text-align:right;font-variant-numeric:tabular-nums}th{color:var(--muted);font-size:.72rem;text-transform:uppercase}th:first-child,td:first-child{text-align:left}
.charts-section{grid-column:1/-1;display:grid;gap:.8rem;margin-top:.15rem}.section-heading{align-items:end;padding:.2rem}.section-note{margin:.2rem 0 0;color:var(--muted);font-size:.86rem}.button{min-height:40px;padding:.5rem .8rem;border:1px solid #adc4ca;border-radius:8px;background:var(--panel);color:var(--ink);font-weight:680}.button:hover{border-color:var(--teal);background:var(--teal-soft)}.button.primary{border-color:var(--teal);background:var(--teal);color:white}.button:disabled{cursor:not-allowed;opacity:.45}.charts{display:grid;gap:.8rem}.chart-panel{overflow:hidden}.chart-heading{padding:.85rem 1rem .7rem}.chart-controls{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:.45rem}.axis-field{display:grid;grid-template-columns:auto minmax(108px,1fr);align-items:center;gap:.35rem;color:var(--muted);font-size:.76rem;font-weight:700}.axis-field select{min-height:40px;padding:.45rem 2rem .45rem .6rem;border:1px solid #b9cbd0;border-radius:7px;background:var(--panel);color:var(--ink)}.line-control{display:flex;align-items:center;gap:.25rem}.line-select{max-width:250px}.remove-line,.remove-chart{min-height:40px;padding:.4rem .58rem;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--muted)}.remove-line:hover,.remove-chart:hover{border-color:#bf7065;color:#8e2f22}.chart{width:100%;height:330px;background:linear-gradient(180deg,#f7fbfc,#eef7f8);border-top:1px solid var(--border);outline:none}.chart:focus-visible{box-shadow:inset 0 0 0 3px #1b8ea3}.chart .modebar,.chart .modebar-group{padding:2px!important;border:0!important;background:transparent!important;box-shadow:none!important}.chart .modebar-btn path{fill:#3e5961!important}.chart .modebar-btn:hover path,.chart .modebar-btn.active path{fill:var(--teal)!important}.readout{display:flex;justify-content:space-between;gap:1rem;min-height:44px;padding:.65rem 1rem;border:1px solid var(--border);border-radius:10px;background:#fbfdfd;font-variant-numeric:tabular-nums}.readout-time{font-weight:750}.readout-values{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.35rem .8rem;color:var(--muted)}.qc-good{color:#137153;font-weight:700}.qc-flagged{color:#a13f2f;font-weight:700}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:900px){.stat-grid{grid-template-columns:repeat(2,1fr)}.chart-heading{display:grid}.chart-controls{justify-content:flex-start}.line-select{max-width:min(68vw,300px)}}
@media(max-width:760px){.masthead{align-items:flex-start;padding:1rem}.masthead,.panel-heading{flex-wrap:wrap}main{grid-template-columns:1fr;padding:.7rem}.panel{padding:.85rem}#map{height:300px}.chart{height:285px}.readout{display:grid}.readout-values{justify-content:flex-start}.section-heading{align-items:flex-start}.map-legend{justify-content:stretch}.charts-section{min-width:0}}
@media(max-width:460px){.masthead{display:grid}.chart-controls{display:grid;grid-template-columns:1fr auto}.axis-field{grid-column:1/-1}.line-control{display:contents}.line-select{max-width:none;width:100%}.button.add-line{grid-column:1/-1}.section-heading{display:grid}.section-heading .button{width:100%}}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#0d2027;--panel:#17323b;--ink:#edf8fa;--muted:#a8c0c7;--border:#31505a;--sea:#102e3a;--teal-soft:#20454d;--warning:#ffd27c;--warning-bg:#4b381d;--shadow:0 4px 18px #0004}.stat,.readout{background:#142d35}.chart{background:linear-gradient(180deg,#183640,#142e36)}.badge{color:#c7e7ec}.quality-note{color:#ffe4aa}}
"""

SCRIPT = r"""
const S=window.YACHT_DATA, R=window.YACHT_REPORT, q=x=>document.querySelector(x);
const finite=x=>Number.isFinite(x), extent=a=>{const v=a.filter(finite);return v.length?[Math.min(...v),Math.max(...v)]:[0,1]};
// Colour limits clipped to a central percentile range so a handful of extreme
// values cannot flatten the scale the rest of the track is read against.
const MAP_CLIP=[.025,.975];
const percentileRange=(a,plo,phi)=>{const v=a.filter(finite).sort((x,y)=>x-y);if(!v.length)return [0,1];
 const at=p=>{const idx=(v.length-1)*p,i=Math.floor(idx),f=idx-i;return i+1<v.length?v[i]+(v[i+1]-v[i])*f:v[i]};
 const lo=at(plo),hi=at(phi);return hi>lo?[lo,hi]:[v[0],v[v.length-1]]};
const spectralR=['#5e4fa2','#3288bd','#66c2a5','#abdda4','#e6f598','#ffffbf','#fee08b','#fdae61','#f46d43','#d53e4f','#9e0142'];
function colorFor(value){const t=Math.min(1,Math.max(0,value))*(spectralR.length-1),i=Math.min(spectralR.length-2,Math.floor(t)),mix=t-i,a=spectralR[i].slice(1).match(/../g).map(x=>parseInt(x,16)),b=spectralR[i+1].slice(1).match(/../g).map(x=>parseInt(x,16));return `rgb(${a.map((v,j)=>Math.round(v+(b[j]-v)*mix)).join(',')})`}
const lineColours=['#007f86','#d2604b','#6f5aa7','#bd8218','#3f78b5','#4f8a67','#b24f78','#526f78'];
const variableColours=new Map();
const timestamps=S.time.map(Date.parse), good=S.qc.map(x=>x===0);
// The instrument cycles through sampling phases -- seawater, air, gas standards
// -- so the page is filtered by phase as well as by QC, independently: a phase
// the QC excludes is still viewable with the QC filter off.
const phases=S.phase||null, phaseMeta=S.phase_meta||{};
let phaseFilter='all';
function phaseName(code){const named=phaseMeta[String(code)];return code===-1?'No phase recorded':named?`${named} (${code})`:`Phase ${code}`}
function phaseOk(i){return phaseFilter==='all'||!phases||phases[i]===phaseFilter}
function included(i){return (!q('#good').checked||good[i])&&phaseOk(i)}
let mapVariable=S.variables[0], selectedIndex=0, nextChartId=2, activeRangeChartId=null;
const defaultChartVariables=['fco2_seawater','raw_watertemp'].filter(name=>S.variables.includes(name));
let charts=[{id:1,variables:defaultChartVariables.length?defaultChartVariables:[S.variables[0]],x:'time',range:null}];

function displayUnit(value){return String(value||'').replaceAll('uatm','µatm')}
function meta(name){return (S.variable_meta&&S.variable_meta[name])||{label:name.replaceAll('_',' '),units:''}}
function label(name){return meta(name).label||name}
function unit(name){return displayUnit(meta(name).units)}
function variableColour(name){if(!variableColours.has(name))variableColours.set(name,lineColours[variableColours.size%lineColours.length]);return variableColours.get(name)}
function normalUnit(name){return unit(name).toLowerCase().replaceAll('μ','µ').replaceAll(' ','').replaceAll('−','-')}
const profileCache=new Map();
function scaleProfile(name){if(profileCache.has(name))return profileCache.get(name);const values=S.data[name].filter((v,i)=>good[i]&&finite(v)).sort((a,b)=>a-b),at=p=>values.length?values[Math.min(values.length-1,Math.floor((values.length-1)*p))]:0,q10=at(.1),q50=at(.5),q90=at(.9),profile={scale:Math.max(Math.abs(q50),Math.abs(q90-q10),1e-12)};profileCache.set(name,profile);return profile}
function axisCompatible(a,b){const ua=normalUnit(a),ub=normalUnit(b);if(ua!==ub)return false;const sa=scaleProfile(a).scale,sb=scaleProfile(b).scale;return Math.max(sa,sb)/Math.min(sa,sb)<=20}
function axisPlan(names){const reps=[],assignments=[];for(const name of names){let axis=reps.findIndex(rep=>axisCompatible(name,rep));if(axis<0&&reps.length<2){reps.push(name);axis=reps.length-1}if(axis<0)axis=1;assignments.push(axis===0?'y':'y2')}return {reps,assignments}}
function allowedForLine(chart,lineIndex){const others=chart.variables.filter((_,i)=>i!==lineIndex),reps=axisPlan(others).reps;if(reps.length<2)return S.variables;return S.variables.filter(name=>reps.some(rep=>axisCompatible(name,rep)))}
function addableVariables(chart){const reps=axisPlan(chart.variables).reps,unused=S.variables.filter(name=>!chart.variables.includes(name));if(reps.length<2)return unused;return unused.filter(name=>reps.some(rep=>axisCompatible(name,rep)))}
function axisLabel(names){const units=[...new Set(names.map(unit).filter(Boolean))];return units.length?units.join(' / '):names.map(label).join(' / ')}
function optionGroups(select,allowed=S.variables){
 const groups=[['Core CO₂',[]],['Water and navigation',[]],['Instrument diagnostics',[]],['Other',[]]];
 for(const name of allowed){
  let i=name.startsWith('raw_')?2:3;
  if(['fco2_seawater','pco2_seawater','pco2_equilibrator','xco2_dry','xco2_wet','raw_co2'].includes(name))i=0;
  else if(['raw_watertemp','raw_salinity','raw_watercond','raw_chl_a','lat','lon','raw_latitude','raw_longitude','raw_speed','raw_course'].includes(name)||/oxygen|(^|_)o2($|_)/i.test(name)||/^doxy/i.test(name))i=1;
  groups[i][1].push(name);
 }
 select.replaceChildren();
 for(const [title,names] of groups){if(!names.length)continue;const group=document.createElement('optgroup');group.label=title;for(const name of names){const o=document.createElement('option');o.value=name;o.textContent=label(name)+(unit(name)?` (${unit(name)})`:'');group.append(o)}select.append(group)}
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
 baseLayers={
  'Sea':L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',{maxZoom:16,attribution:'Esri, GEBCO, NOAA, National Geographic, DeLorme, HERE, Geonames.org'}),
  'Nautical chart':L.layerGroup([
   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}),
   L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; OpenSeaMap contributors'})
  ]),
  'Night':L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors &copy; CARTO'})
 };
 baseLayers.Sea.addTo(map);L.control.layers(baseLayers,null,{position:'topright'}).addTo(map);trackLayer=L.layerGroup().addTo(map);
 posMarker=L.circleMarker([0,0],{radius:7,weight:2,color:'#fff',fillColor:'#e6533d',fillOpacity:1}).addTo(map);
 for(const lm of (R&&R.landmarks)||[]){const marker=L.marker([lm.lat,lm.lon],{title:lm.name,alt:lm.name}).addTo(map);marker.bindTooltip(lm.name)}
 setTimeout(()=>map.invalidateSize(),0);
}else{q('#map').textContent='Map unavailable — Leaflet could not be loaded.'}

const hasChart=typeof Plotly!=='undefined';
function xValue(chart,i){return chart.x==='time'?timestamps[i]:chart.x==='lat'?S.lat[i]:S.lon[i]}
function focusedIndices(){const chart=charts.find(c=>c.id===activeRangeChartId);if(!chart||!chart.range)return null;const [lo,hi]=chart.range;return new Set(S.time.map((_,i)=>i).filter(i=>{const v=xValue(chart,i);return finite(v)&&v>=lo&&v<=hi}))}
function trackTooltip(i,value){const el=document.createElement('div');el.className='track-tooltip';const primary=document.createElement('strong'),detail=document.createElement('span');primary.textContent=`${label(mapVariable)}: ${finite(value)?value.toFixed(2):'missing'}${unit(mapVariable)?' '+unit(mapVariable):''}`;detail.textContent=`${fmtTime(S.time[i]).replace('T',' ')} · ${S.lat[i].toFixed(4)}°, ${S.lon[i].toFixed(4)}°`;el.append(primary,detail);return el}
function drawMap(){
 const keep=S.time.map((_,i)=>included(i)),focus=focusedIndices(),values=S.data[mapVariable],scaleValues=values.filter((v,i)=>good[i]&&phaseOk(i)&&finite(v)),[lo,hi]=percentileRange(scaleValues,MAP_CLIP[0],MAP_CLIP[1]);
 if(trackLayer){trackLayer.clearLayers();const bounds=[];S.lon.forEach((lon,i)=>{if(!keep[i]||!finite(lon)||!finite(S.lat[i]))return;bounds.push([S.lat[i],lon]);const v=values[i],t=finite(v)?(v-lo)/(hi-lo||1):null,inFocus=!focus||focus.has(i),outside=focus&&!inFocus,marker=L.circleMarker([S.lat[i],lon],{radius:outside?2.2:3.3,weight:0,fillColor:outside?'#98a7ab':t===null?'#7d8c90':colorFor(t),fillOpacity:outside?.38:.92}).addTo(trackLayer);marker.bindTooltip(trackTooltip(i,v),{direction:'top',offset:[0,-4],opacity:.96})});if(bounds.length&&!mapHasFit){map.fitBounds(L.latLngBounds(bounds),{padding:[18,18]});mapHasFit=true}}
 const count=focus?[...focus].filter(i=>keep[i]).length:null,empty=!keep.some(Boolean);
 q('#legend-title').textContent=`Track colour · ${label(mapVariable)}${unit(mapVariable)?` (${unit(mapVariable)})`:''}${count===null?'':` · ${count} observations in chart window`}${empty?' · nothing to show; the QC filter and the phase exclude each other':''}`;
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
function cursorShape(chart){const x=chart.x==='time'?S.time[selectedIndex]:xValue(chart,selectedIndex);return {type:'line',x0:x,x1:x,y0:0,y1:1,yref:'paper',line:{color:'rgba(70,91,99,.52)',width:2,dash:'dot'}}}
function drawChart(chart){
 const gd=q(`#chart-${chart.id}`);if(!gd||!hasChart)return;
 const plan=axisPlan(chart.variables),traces=chart.variables.map((name,i)=>{const d=seriesData(name,chart),u=unit(name);return {x:d.xs,y:d.ys,customdata:d.ids,yaxis:plan.assignments[i],type:'scattergl',mode:'lines',name:label(name),line:{color:variableColour(name),width:2.8},connectgaps:false,hovertemplate:`<b>${label(name)}</b><br>%{y:.2f}${u?' '+u:''}<extra></extra>`}});
 const styles=getComputedStyle(document.documentElement),ink=getComputedStyle(document.body).color,muted=styles.getPropertyValue('--muted').trim(),border=styles.getPropertyValue('--border').trim();
 const leftNames=chart.variables.filter((_,i)=>plan.assignments[i]==='y'),rightNames=chart.variables.filter((_,i)=>plan.assignments[i]==='y2'),leftColour=variableColour(leftNames[0]),rightColour=rightNames.length?variableColour(rightNames[0]):muted;
 const xTitle=chart.x==='time'?'Time (UTC)':chart.x==='lat'?'Latitude (°N)':'Longitude (°E)',layout={margin:{l:62,r:rightNames.length?68:18,t:12,b:52},xaxis:{type:chart.x==='time'?'date':'linear',title:{text:xTitle,font:{color:muted}},showgrid:false,zeroline:false,tickfont:{color:muted},showspikes:true,spikemode:'across',spikethickness:1,spikecolor:muted},yaxis:{title:{text:axisLabel(leftNames),font:{color:leftColour}},tickfont:{color:leftColour},tickformat:'.3~g',gridcolor:border,zeroline:false},shapes:[cursorShape(chart)],paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:ink,size:12},showlegend:true,legend:{orientation:'h',x:0,y:1.02,xanchor:'left',yanchor:'bottom'},hovermode:'x unified',dragmode:'zoom',uirevision:`chart-${chart.id}-${chart.x}`};
 if(rightNames.length)layout.yaxis2={title:{text:axisLabel(rightNames),font:{color:rightColour}},tickfont:{color:rightColour},tickformat:'.3~g',overlaying:'y',side:'right',showgrid:false,zeroline:false};
 Plotly.react(gd,traces,layout,{displayModeBar:true,displaylogo:false,responsive:true,scrollZoom:false,modeBarButtonsToRemove:['select2d','lasso2d','autoScale2d','toggleSpikelines','hoverClosestCartesian','hoverCompareCartesian']}).then(()=>bindChart(gd,chart));
}
function bindChart(gd,chart){
 if(gd._scrubBound)return;gd._scrubBound=true;gd.tabIndex=0;gd.setAttribute('role','application');gd.setAttribute('aria-label','Observation chart. Click a point to select it, drag across the plot to zoom, or double click to reset. Use arrow keys for adjacent valid observations.');
 gd.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();stepSelection(e.key==='ArrowRight'?1:-1)}});gd.on('plotly_click',ev=>{const point=ev.points&&ev.points[0],i=point&&point.customdata;if(Number.isInteger(i))move(nearestEligible(i))});gd.on('plotly_relayout',ev=>{const start=ev['xaxis.range[0]'],end=ev['xaxis.range[1]'];if(start!==undefined&&end!==undefined){const convert=v=>chart.x==='time'?Date.parse(v):Number(v),a=convert(start),b=convert(end);if(finite(a)&&finite(b)){chart.range=[Math.min(a,b),Math.max(a,b)];activeRangeChartId=chart.id;drawMap()}}else if(ev['xaxis.autorange']){chart.range=null;if(activeRangeChartId===chart.id)activeRangeChartId=null;drawMap()}});
}
function drawCharts(){if(!hasChart){q('#charts').innerHTML='<section class="chart-panel"><p class="quality-note">Charts unavailable — Plotly could not be loaded.</p></section>';return}for(const chart of charts)drawChart(chart)}
function draw(){selectedIndex=nearestEligible(selectedIndex);drawMap();drawCharts();move(selectedIndex);renderInfo()}
function fmtTime(iso){const ms=Date.parse(iso.endsWith('Z')?iso:iso+'Z');if(!finite(ms))return iso;return new Date(Math.round(ms/1000)*1000).toISOString().slice(0,19)+'Z'}
function move(i){
 selectedIndex=i;if(posMarker&&finite(S.lon[i])&&finite(S.lat[i]))posMarker.setLatLng([S.lat[i],S.lon[i]]);
 for(const chart of charts){const gd=q(`#chart-${chart.id}`),x=chart.x==='time'?S.time[i]:xValue(chart,i);if(gd&&gd.data&&finite(chart.x==='time'?Date.parse(x):x))Plotly.relayout(gd,{'shapes[0].x0':x,'shapes[0].x1':x})}
 q('#readout-time').textContent=fmtTime(S.time[i]).replace('T',' · ').replace('Z',' UTC');const names=[...new Set(charts.flatMap(c=>c.variables))];q('#readout-values').replaceChildren(...names.map(name=>{const span=document.createElement('span'),v=S.data[name][i];span.textContent=`${label(name)}: ${finite(v)?v.toFixed(2):'missing'}${unit(name)?' '+unit(name):''}`;return span}));const qc=document.createElement('span');qc.className=S.qc[i]===0?'qc-good':'qc-flagged';qc.textContent=S.qc[i]===0?'QC good':`QC flagged · code ${S.qc[i]}`;q('#readout-values').append(qc);
}
function renderInfo(){
 const el=q('#infobody');if(!el)return;if(!R){el.textContent='No report data available.';return}const exp=R.campaign||R.expedition||{},t=R.temporal||{},qc=R.quality||{},flags=Object.entries(qc.flag_counts||{}),coverage=Number(t.coverage_percent),rows=(R.variables||[]).map(v=>`<tr><td>${label(v.name)}</td><td>${displayUnit(v.units)}</td><td>${v.good}/${v.valid}</td><td>${v.min}</td><td>${v.mean}</td><td>${v.max}</td></tr>`).join('');
 el.innerHTML=`<p class="expedition-name">${exp.vessel_name||'Unnamed vessel'}</p><p class="expedition-subtitle">${[exp.vessel_type,exp.instrument,exp.co2_sensor].filter(Boolean).join(' · ')}</p><p class="date-line">${(t.start||'').slice(0,10)} to ${(t.end||'').slice(0,10)}</p><div class="stat-grid"><div class="stat"><strong>${t.days??'—'}</strong><span>Days</span></div><div class="stat"><strong>${t.records??'—'}</strong><span>Records</span></div><div class="stat ${coverage<80?'warning':''}"><strong>${t.coverage_percent??'—'}%</strong><span>Coverage</span></div><div class="stat"><strong>${qc.good_percent??'—'}%</strong><span>QC good</span></div></div>${coverage<80?`<p class="quality-note"><strong>Limited temporal coverage.</strong> ${t.gap_count??0} gap(s), ${t.gap_minutes??'—'} minutes without observations.</p>`:''}<div class="flag-list">${flags.length?flags.map(([name,count])=>`<span class="badge">${name.replaceAll('_',' ')} · ${count}</span>`).join(''):'<span class="badge">No quality flags</span>'}</div><details class="variable-details"><summary>Variable summary (${(R.variables||[]).length})</summary><div class="table-wrap"><table><thead><tr><th scope="col">Variable</th><th scope="col">Units</th><th scope="col">Good / valid</th><th scope="col">Min</th><th scope="col">Mean</th><th scope="col">Max</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}
function renderChartControls(){
 const root=q('#charts');root.replaceChildren();for(const [chartIndex,chart] of charts.entries()){
  const panel=document.createElement('section');panel.className='chart-panel';panel.dataset.chartId=chart.id;panel.innerHTML=`<div class="chart-heading"><div><p class="eyebrow">Time series ${chartIndex+1}</p><h3>${label(chart.variables[0])}</h3></div><div class="chart-controls"></div></div><div class="chart" id="chart-${chart.id}"></div>`;const controls=panel.querySelector('.chart-controls'),axisField=document.createElement('label');axisField.className='axis-field';axisField.innerHTML='<span>X-axis</span><select aria-label="Chart x-axis"><option value="time">Time</option><option value="lat">Latitude</option><option value="lon">Longitude</option></select>';const axisSelect=axisField.querySelector('select');axisSelect.value=chart.x;axisSelect.onchange=()=>{chart.x=axisSelect.value;chart.range=null;if(activeRangeChartId===chart.id)activeRangeChartId=null;renderChartControls()};controls.append(axisField);
  chart.variables.forEach((name,lineIndex)=>{const wrap=document.createElement('span');wrap.className='line-control';const select=document.createElement('select');select.className='line-select';select.setAttribute('aria-label',`Line ${lineIndex+1} variable`);optionGroups(select,allowedForLine(chart,lineIndex));select.value=name;select.onchange=()=>{chart.variables[lineIndex]=select.value;renderChartControls()};wrap.append(select);if(chart.variables.length>1){const remove=document.createElement('button');remove.className='remove-line';remove.type='button';remove.textContent='Remove';remove.setAttribute('aria-label',`Remove ${label(name)} line`);remove.onclick=()=>{chart.variables.splice(lineIndex,1);renderChartControls()};wrap.append(remove)}controls.append(wrap)});
  const addable=addableVariables(chart),add=document.createElement('button');add.className='button add-line';add.type='button';add.textContent='Add line';add.disabled=!addable.length||chart.variables.length>=4;add.title=chart.variables.length>=4?'Use another chart for additional variables':'Add a comparison line';add.onclick=()=>{chart.variables.push(addable[0]);renderChartControls()};controls.append(add);
  if(charts.length>1){const removeChart=document.createElement('button');removeChart.className='remove-chart';removeChart.type='button';removeChart.textContent='Remove chart';removeChart.setAttribute('aria-label',`Remove time series ${chartIndex+1}`);removeChart.onclick=()=>{charts=charts.filter(c=>c.id!==chart.id);if(activeRangeChartId===chart.id)activeRangeChartId=null;renderChartControls()};controls.append(removeChart)}root.append(panel)
 }
 draw();
}
function buildPhasePicker(){
 const field=q('#phase-field'),select=q('#phase');if(!field||!select||!phases)return;
 const codes=[...new Set(phases)].sort((a,b)=>a-b);if(codes.length<2)return;
 field.hidden=false;select.replaceChildren();
 const all=document.createElement('option');all.value='all';all.textContent='All phases';select.append(all);
 for(const code of codes){const o=document.createElement('option');o.value=String(code);o.textContent=phaseName(code);select.append(o)}
 select.value='all';select.onchange=()=>{phaseFilter=select.value==='all'?'all':Number(select.value);draw()};
}
buildPhasePicker();optionGroups(q('#map-variable'));q('#map-variable').value=mapVariable;q('#map-variable').onchange=e=>{mapVariable=e.target.value;drawMap()};q('#good').onchange=draw;q('#add-chart').onclick=()=>{charts.push({id:nextChartId++,variables:[mapVariable],x:'time',range:null});renderChartControls()};selectedIndex=nearestEligible(0);renderChartControls();
"""
