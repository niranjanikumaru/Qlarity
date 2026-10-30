const $=s=>document.querySelector(s),form=$('#form');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>(100*x).toFixed(2)+'%',num=x=>Number(x).toLocaleString(undefined,{maximumFractionDigits:3});
let defaults,active=null,data=null,selected=0,busy=false,angle=-.6,inspect=0;
async function api(url,opts={}){const r=await fetch(url,opts);if(!r.ok){let b=await r.text();try{b=JSON.stringify(JSON.parse(b).detail)}catch{}throw Error(b)}return r.json()}
function error(e){$('#error').hidden=!e;$('#error').textContent=e?.message||''}
function fill(s){for(const k of ['sigma_L_nm','sigma_tox_nm','sigma_vth_mV','temperature_K','reduction','epsilon','scale','bins','samples','shots','seed'])form.elements[k].value=s[k];form.elements.limit_nA.value=+(s.I_limit_A*1e9).toFixed(6);form.elements.yield_pct.value=100*(1-s.max_failure_probability);form.elements.confidence.value=100*(1-s.alpha);form.elements.quantum.checked=s.quantum;form.elements.adaptive.checked=s.adaptive;$('#reduction-value').textContent=pct(s.reduction)}
function read(){const o={...defaults};for(const k of ['sigma_L_nm','sigma_tox_nm','sigma_vth_mV','temperature_K','reduction','epsilon','scale','bins','samples','shots','seed'])o[k]=+form.elements[k].value;o.I_limit_A=+form.elements.limit_nA.value*1e-9;o.max_failure_probability=1-(+form.elements.yield_pct.value)/100;o.alpha=1-(+form.elements.confidence.value)/100;o.quantum=form.elements.quantum.checked;o.adaptive=form.elements.adaptive.checked;o.compare=true;return o}
function setBusy(v){busy=v;$('#run').disabled=v;$('#recorded').disabled=v;$('#cancel').hidden=!v;for(const e of form.elements)if(!['cancel','run','recorded'].includes(e.id))e.disabled=v}
function dirty(){if(data&&!busy)$('#status').textContent='Settings changed. Results below retain their executed scenario; run again to apply changes.'}
form.addEventListener('input',()=>{$('#reduction-value').textContent=pct(+form.elements.reduction.value);dirty()});
$('#preset').onchange=e=>{const s={...defaults};if(e.target.value==='wafer'){s.sigma_L_nm=1.156;s.sigma_tox_nm=0.030;s.sigma_vth_mV=21.0;s.I_limit_A=3.0e-8;s.max_failure_probability=0.182;s.temperature_K=300;}if(e.target.value==='hot')s.temperature_K=350;if(e.target.value==='tight'){s.sigma_L_nm=2;s.sigma_vth_mV=10}fill(s);dirty()};
form.onsubmit=async e=>{e.preventDefault();error(null);if(!form.reportValidity())return;const s=read();if(s.quantum&&s.bins!==4){error(Error('IQAE supports 4 bins per input. Select 4, or disable IQAE for a classical resolution study.'));return}if(s.adaptive&&!s.quantum){error(Error('Adaptive mode requires IQAE.'));return}setBusy(true);try{const key=crypto.randomUUID();const j=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(s)});active=j.id;localStorage.setItem('qlarity-active',active);await poll()}catch(e){error(e);setBusy(false)}};
async function poll(){let failures=0;while(active&&busy){try{const j=await api('/api/runs/'+active);failures=0;$('#status').textContent=j.progress;if(j.status==='completed'){data=j.result;selected=0;setBusy(false);localStorage.removeItem('qlarity-active');render();history();break}if(['failed','cancelled'].includes(j.status)){setBusy(false);localStorage.removeItem('qlarity-active');if(j.error)error(Error(j.error));break}}catch(e){if(++failures>=3){setBusy(false);error(Error('Connection interrupted. Reload to reconnect to this run.'));break}$('#status').textContent='Reconnecting…'}await new Promise(r=>setTimeout(r,700))}}
$('#cancel').onclick=async()=>{try{await api('/api/runs/'+active,{method:'DELETE'});$('#status').textContent='Cancelled; worker stopped.';setBusy(false);localStorage.removeItem('qlarity-active');history()}catch(e){error(e)}};
$('#recorded').onclick=async()=>{try{data=await api('/evidence/example.json');active=null;selected=0;data.execution='recorded';fill(data.request);render();$('#status').textContent='Recorded execution loaded. This is not a new quantum run.';error(null)}catch(e){error(e)}};
function badge(d){return `<span class="status-pill ${d.startsWith('meets')?'meets':d.startsWith('misses')?'misses':'unresolved'}">${esc(d)}</span>`}
function render(){if(!data)return;$('#provenance').textContent=(data.execution==='recorded'?'RECORDED EXECUTION':'FRESH EXECUTION');$('#comparison').classList.remove('empty');$('#comparison').innerHTML=data.scenarios.map((s,i)=>{const base=data.scenarios[0].scenario;const diffs=['sigma_L_nm','sigma_tox_nm','sigma_vth_mV'].filter(k=>base[k]!==s.scenario[k]).map(k=>`${k}: ${base[k]} → ${s.scenario[k]}`);return `<article class="scenario"><div class="scenario-title"><h3>${esc(s.scenario.label)}</h3><button data-select="${i}">${selected===i?'Inspecting':'Inspect evidence'}</button></div><p class="change">${diffs.length?esc(diffs.join(' · ')):'Baseline; no tolerance changes'} · target yield ≥ ${pct(1-s.scenario.max_failure_probability)}</p><div class="table-wrap"><table><thead><tr><th>Estimator</th><th>Encoded yield</th><th>Encoded failure CI</th><th>Modeled decision</th></tr></thead><tbody>${s.results.map(r=>`<tr><td>${esc(r.method)}</td><td>${pct(r.yield_estimate)}</td><td>${pct(r.ci[0])}–${pct(r.ci[1])}</td><td>${badge(r.decision)}</td></tr>`).join('')}</tbody></table></div></article>`}).join('');document.querySelectorAll('[data-select]').forEach(b=>b.onclick=()=>{selected=+b.dataset.select;render();$('#evidence').scrollIntoView({behavior:'smooth'})});renderEvidence();draw();for(const id of ['json','csv','zip'])$('#'+id).disabled=false}
function metric(k,v){return `<div class="metric-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`}
function renderEvidence(){const s=data.scenarios[selected],q=s.results.find(x=>x.method==='IQAE')?.quantum;$('#evidence-body').classList.remove('empty');$('#evidence-body').innerHTML=`<h3>${esc(s.scenario.label)} · ${esc(s.target_id)}</h3><div class="evidence-grid"><div><h3>Approximation ledger</h3>${metric('Original discrete-model failure',pct(s.reference.discrete_float))}${metric('Encoded-model failure',pct(s.reference.encoded))}${metric('Classification disagreement',pct(s.approximation.disagreement_mass))}${metric('Signed probability difference',(100*s.reference.signed_encoding_difference).toFixed(3)+' percentage points')}${metric('Log-score rounding bound',num(s.approximation.score_error_bound))}${metric('Omitted Gaussian mass',pct(s.approximation.omitted_tail_mass))}<p class="muted">${esc(s.approximation.bound_scope)} Discretization and physical-model error are not covered by the displayed decision intervals.</p></div><div><h3>Execution resources</h3>${q?`${metric('Logical qubits',q.n_total_qubits)}${metric('A / A-inverse calls',q.NA_our_count)}${metric('Total shots',q.resources.total_shots)}${metric('A two-qubit gates',q.resources.A.two_qubit_gates)}${metric('Maximum executed depth',q.resources.max_executed_depth)}${metric('Shot-weighted two-qubit gates',q.resources.total_two_qubit_gate_executions)}${metric('IQAE simulator time',num(q.elapsed_s)+' s')}${metric('Evidence compilation time',num(q.resources.compilation_s)+' s')}`:'<p>IQAE was not executed for this run.</p>'}<p class="muted">${esc(data.runtime)} Shared reference preprocessing: ${num(s.reference.preprocessing_s)} s and ${s.reference.reference_evaluations} model evaluations.</p></div></div><h3>Matched-target estimator comparison</h3><div class="table-wrap"><table><thead><tr><th>Method</th><th>Classical evaluations</th><th>Quantum calls</th><th>Time (s)</th><th>Decision interval</th><th>Interval method</th></tr></thead><tbody>${s.results.map(r=>`<tr><td>${esc(r.method)}</td><td>${num(r.model_evaluations||0)}</td><td>${num(r.oracle_calls||0)}</td><td>${num(r.elapsed_s)}</td><td>${pct(r.decision_ci[0])}–${pct(r.decision_ci[1])}</td><td>${esc(r.interval_method)}</td></tr>`).join('')}</tbody></table></div><p class="muted">Conditional CDF also performs ${s.scenario.bins**2} conditional queries and per-axis preprocessing. Query types are not equivalent execution costs.</p>${q?`<h3>Actual amplification rounds</h3><div class="table-wrap"><table><thead><tr><th>Round</th><th>k</th><th>Shots</th><th>Counts 0 / 1</th><th>Failure interval</th><th>Depth</th><th>2Q gates</th><th>Circuit</th></tr></thead><tbody>${q.executed_rounds.map(r=>`<tr><td>${esc(r.circuit_id)}</td><td>${r.k}</td><td>${r.shots}</td><td>${r.counts['0']||0} / ${r.counts['1']||0}</td><td>${pct(r.probability_interval[0])}–${pct(r.probability_interval[1])}</td><td>${r.depth}</td><td>${r.two_qubit_gates}</td><td><button data-circuit="${esc(r.circuit_id)}">QASM</button></td></tr>`).join('')}</tbody></table></div><p class="muted">${esc(q.resources.query_convention)}. ${esc(q.resources.hardware_connectivity)}.</p>`:''}${s.adaptive?`<h3>Adaptive checks</h3><p class="muted">${esc(s.adaptive.stopping)} · cumulative oracle calls ${s.adaptive.total_oracle_calls}</p>${s.adaptive.attempts.map(a=>metric('Check '+a.step, a.reason+' · scale '+a.result.scenario.scale)).join('')}`:''}<details><summary>Continuous reference · separate mathematical target</summary><pre>${esc(JSON.stringify(data.continuous_reference,null,2))}</pre></details><details><summary>Executed scenario & probability distributions</summary><pre>${esc(JSON.stringify({scenario:s.scenario,distribution:s.distribution},null,2))}</pre></details>`;document.querySelectorAll('[data-circuit]').forEach(b=>b.onclick=()=>download(b.dataset.circuit+'.qasm',q.circuits[b.dataset.circuit],'text/plain'))}
function download(name,text,type){const u=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
$('#json').onclick=()=>download('qlarity-result.json',JSON.stringify(data,null,2),'application/json');
$('#csv').onclick=()=>{const rows=[['scenario','method','target_id','p_fail','ci_lower','ci_upper','decision','model_evaluations','oracle_calls','elapsed_s']];for(const s of data.scenarios)for(const r of s.results)rows.push([s.scenario.label,r.method,r.target_id,r.p_fail,...r.ci,r.decision,r.model_evaluations||0,r.oracle_calls||0,r.elapsed_s]);download('qlarity-results.csv',rows.map(row=>row.map(x=>'"'+String(x).replaceAll('"','""')+'"').join(',')).join('\n'),'text/csv')};$('#zip').onclick=()=>{location.href=active?'/api/runs/'+active+'/export/zip':'/api/recorded/export'};
async function history(){try{const jobs=await api('/api/runs');$('#history').innerHTML=jobs.map(j=>`<button data-history="${esc(j.id)}">${esc(j.status)} · ${new Date(j.queued_at*1000).toLocaleTimeString()}</button>`).join('');document.querySelectorAll('[data-history]').forEach(b=>b.onclick=async()=>{try{const j=await api('/api/runs/'+b.dataset.history);if(j.result){active=j.id;data=j.result;selected=0;fill(data.request);render()}else $('#status').textContent=j.progress}catch(e){error(e)}})}catch{}}
const canvas=$('#population'),ctx=canvas.getContext('2d');let points=[];
function draw(){const rect=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);const states=data?.scenarios[selected]?.population;if(!states){ctx.fillStyle='#a9bc9f';ctx.font='14px system-ui';ctx.fillText('Your process space will appear here.',25,h/2);return}const n=Math.round(Math.cbrt(states.length)),scale=Math.min(w/(n*2.3),h/(n*1.9));points=states.map((s,i)=>{const x=(Math.floor(i/(n*n))-(n-1)/2)*scale,y=(Math.floor(i/n)%n-(n-1)/2)*scale,z=(i%n-(n-1)/2)*scale;return {s,i,x:w/2+x*Math.cos(angle)-y*Math.sin(angle),y:h/2+(x*Math.sin(angle)+y*Math.cos(angle))*.35-z*.65,depth:x*Math.sin(angle)+y*Math.cos(angle)}}).sort((a,b)=>a.depth-b.depth);for(const p of points){ctx.fillStyle=p.s.float_failure?'#f58a60':'#a8c58c';ctx.globalAlpha=p.i===inspect?1:.75;const r=Math.max(2,Math.min(8,scale*.17));ctx.fillRect(p.x-r,p.y-r,r*2,r*2);if(p.i===inspect){ctx.strokeStyle='#fff';ctx.strokeRect(p.x-r-3,p.y-r-3,r*2+6,r*2+6)}}ctx.globalAlpha=1;$('#population-label').textContent=states.length+' weighted configurations';const s=states[inspect%states.length];$('#state-detail').textContent=`State ${inspect+1} · Ioff ${(s.current_A*1e9).toFixed(4)} nA · δL ${s.delta_L_nm.toFixed(2)} nm · δtox ${s.delta_tox_nm.toFixed(3)} nm · δVth ${s.delta_vth_mV.toFixed(2)} mV · weight ${pct(s.weight)} · ${s.float_failure?'FAIL':'PASS'}`}
let dragging=false,lastX=0;canvas.onpointerdown=e=>{dragging=true;lastX=e.clientX;canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(dragging){angle+=(e.clientX-lastX)*.008;lastX=e.clientX;draw()}};canvas.onpointerup=e=>{dragging=false;canvas.releasePointerCapture(e.pointerId);const rect=canvas.getBoundingClientRect();if(points.length){const p=points.reduce((a,b)=>Math.hypot(a.x-e.clientX+rect.left,a.y-e.clientY+rect.top)<Math.hypot(b.x-e.clientX+rect.left,b.y-e.clientY+rect.top)?a:b);inspect=p.i;draw()}};canvas.onpointercancel=()=>dragging=false;canvas.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const n=data?.scenarios[selected]?.population.length||1;inspect=(inspect+(e.key==='ArrowRight'?1:n-1))%n;draw()}};new ResizeObserver(draw).observe(canvas);

/* --- WAFER MAP INTERACTIVE CONTROLLER --- */
let waferData=null,waferMode='yield',waferHoverIndex=-1;
const waferCanvas=$('#wafer-canvas'),wCtx=waferCanvas?.getContext('2d'),waferTooltip=$('#wafer-tooltip');

function colorForValue(val,min,max,colormap='plasma'){
  const t=Math.max(0,Math.min(1,(val-min)/(max-min||1)));
  if(colormap==='plasma'){
    const r=Math.round(255*(0.1+0.9*t)), g=Math.round(255*(0.8*(1-Math.abs(t-0.5)*2))), b=Math.round(255*(0.9*(1-t)+0.1));
    return `rgb(${r},${g},${b})`;
  }
  const r=Math.round(255*t), b=Math.round(255*(1-t));
  return `rgb(${r},70,${b})`;
}

function drawWafer(){
  if(!wCtx||!waferData) return;
  const dpr=devicePixelRatio||1, rect=waferCanvas.getBoundingClientRect();
  waferCanvas.width=rect.width*dpr; waferCanvas.height=rect.height*dpr;
  wCtx.setTransform(dpr,0,0,dpr,0,0);
  const w=rect.width, h=rect.height, cx=w/2, cy=h/2, R=Math.min(cx,cy)-14;
  wCtx.clearRect(0,0,w,h);

  // Outer silicon wafer border (300mm standard)
  wCtx.strokeStyle='#445b4c'; wCtx.lineWidth=2;
  wCtx.beginPath(); wCtx.arc(cx,cy,R,0,Math.PI*2); wCtx.stroke();

  // Wafer notch at bottom (6 o'clock orientation notch)
  wCtx.fillStyle='#27382d';
  wCtx.beginPath(); wCtx.arc(cx,cy+R,6,Math.PI,0); wCtx.fill();

  const pts=waferData.sampled_dies, scale=R/150.0;
  for(let i=0;i<pts.length;i++){
    const [id,x_mm,y_mm,Lg,Tox,Vth,Ileak,pass]=pts[i];
    const px=cx+x_mm*scale, py=cy+y_mm*scale;
    if(waferMode==='yield') wCtx.fillStyle=pass?'#5cb85c':'#d9534f';
    else if(waferMode==='vth') wCtx.fillStyle=colorForValue(Vth,0.28,0.38,'plasma');
    else if(waferMode==='lg') wCtx.fillStyle=colorForValue(Lg,24.0,30.0,'cool');
    else wCtx.fillStyle=colorForValue(Math.log10(Ileak),0.2,2.4,'plasma');
    wCtx.fillRect(px-1.8,py-1.8,3.6,3.6);
  }

  // Highlight hovered die
  if(waferHoverIndex>=0 && waferHoverIndex<pts.length){
    const [id,x_mm,y_mm,Lg,Tox,Vth,Ileak,pass]=pts[waferHoverIndex];
    const px=cx+x_mm*scale, py=cy+y_mm*scale;
    wCtx.strokeStyle='#ffffff'; wCtx.lineWidth=2.5;
    wCtx.strokeRect(px-4.5,py-4.5,9,9);
  }
}

async function initWafer(){
  try{
    waferData=await api('/api/wafer/summary');
    if(!waferData) return;
    $('#wafer-yield-badge').textContent=waferData.overall_yield_pct+'% WAFER YIELD';
    const m=waferData.regional, c=waferData.clusters, st=waferData.stats;
    $('#wafer-metrics').innerHTML=`
      <div class="wafer-metric-card"><small>Overall Wafer Yield</small><strong>${waferData.overall_yield_pct}%</strong><small>${waferData.passed_dies.toLocaleString()} / ${waferData.total_dies.toLocaleString()} dies</small></div>
      <div class="wafer-metric-card"><small>Inner Core (ρ &lt; 0.60)</small><strong>${m.core_yield_pct}%</strong><small>${m.core_count.toLocaleString()} dies</small></div>
      <div class="wafer-metric-card"><small>Mid-Wafer (0.60 ≤ ρ &lt; 0.85)</small><strong>${m.mid_yield_pct}%</strong><small>${m.mid_count.toLocaleString()} dies</small></div>
      <div class="wafer-metric-card"><small>Outer Edge (ρ ≥ 0.85)</small><strong>${m.edge_yield_pct}%</strong><small>${m.edge_count.toLocaleString()} dies [Edge Roll-off]</small></div>
      <div class="wafer-metric-card"><small>Cluster 1 (Particle Pinhole)</small><strong>${c.c1_yield_pct}%</strong><small>${c.c1_count} dies affected</small></div>
      <div class="wafer-metric-card"><small>Cluster 2 (Litho Defocus)</small><strong>${c.c2_yield_pct}%</strong><small>${c.c2_count} dies affected</small></div>
      <div class="wafer-metric-card"><small>Cluster 3 (Thermal Slip)</small><strong>${c.c3_yield_pct}%</strong><small>${c.c3_count} dies affected</small></div>
      <div class="wafer-metric-card"><small>Median Standby Leakage</small><strong>${st.Ileak_median_nA} nA</strong><small>Spec Limit: 30.0 nA</small></div>
    `;

    ['yield','vth','lg','leak'].forEach(mode=>{
      const btn=$('#btn-mode-'+mode);
      if(btn){
        btn.onclick=()=>{
          document.querySelectorAll('.button-group button').forEach(b=>b.classList.remove('active'));
          btn.classList.add('active');
          waferMode=mode;
          drawWafer();
        };
      }
    });

    waferCanvas.onmousemove=e=>{
      const rect=waferCanvas.getBoundingClientRect();
      const mx=e.clientX-rect.left, my=e.clientY-rect.top;
      const cx=rect.width/2, cy=rect.height/2, scale=(Math.min(cx,cy)-14)/150.0;
      const pts=waferData.sampled_dies;
      let closest=-1, minDist=99999;
      for(let i=0;i<pts.length;i++){
        const px=cx+pts[i][1]*scale, py=cy+pts[i][2]*scale;
        const d=Math.hypot(px-mx,py-my);
        if(d<minDist){ minDist=d; closest=i; }
      }
      if(minDist<15 && closest>=0){
        waferHoverIndex=closest;
        const [id,x,y,Lg,Tox,Vth,Ileak,pass]=pts[closest];
        waferTooltip.hidden=false;
        waferTooltip.style.left=mx+'px';
        waferTooltip.style.top=my+'px';
        waferTooltip.innerHTML=`<strong>Die #${id}</strong> (${x}, ${y} mm)<br>L<sub>g</sub>: ${Lg} nm | T<sub>ox</sub>: ${Tox} nm<br>V<sub>th</sub>: ${Vth} V | I<sub>leak</sub>: ${Ileak} nA<br><span style="color:${pass?'#7bd87b':'#ff7a7a'};font-weight:bold">${pass?'PASSED (≤30 nA)':'FAILED (>30 nA)'}</span>`;
        $('#wafer-die-detail').textContent=`Die #${id} · Coordinates: (${x}, ${y}) mm · Gate Length: ${Lg} nm · Oxide: ${Tox} nm · Threshold Vth: ${Vth} V · Standby Leakage: ${Ileak} nA · Status: ${pass?'PASS':'FAIL'}`;
      } else {
        waferHoverIndex=-1; waferTooltip.hidden=true;
      }
      drawWafer();
    };

    waferCanvas.onmouseleave=()=>{ waferHoverIndex=-1; waferTooltip.hidden=true; drawWafer(); };
    new ResizeObserver(drawWafer).observe(waferCanvas);
    drawWafer();
  }catch(err){ console.warn('Wafer summary error', err); }
}

async function init(){try{const m=await api('/api/model');defaults=m.default_scenario;fill(defaults);$('#model').innerHTML=`<p><strong>${esc(m.id)}</strong> · ${esc(m.provenance)}</p><p>${esc(m.distribution)}</p><p>${esc(m.validation)}</p><details><summary>Formula, operating conditions & limitations</summary><pre>${esc(JSON.stringify({formula:m.formula,device:m.device,operating:m.operating,limitations:m.limitations},null,2))}</pre></details>`;$('#status').textContent='Local service ready. All comparisons execute the same encoded target.';history();initWafer();const old=localStorage.getItem('qlarity-active');if(old){active=old;setBusy(true);poll()}}catch(e){error(Error('Start the Python service using the README command. '+e.message));$('#run').disabled=true}try{const b=await api('/evidence/benchmark.json');$('#benchmark-summary').textContent=`Recorded suite: ${b.runs.length} experiments. ${b.description}`;const summary=await api('/evidence/benchmark-summary.json');$('#benchmark-summary').insertAdjacentHTML('beforeend',`<div class="table-wrap"><table><thead><tr><th>Method</th><th>Within requested error</th><th>CI half-width target</th><th>Coverage</th><th>Coverage interval</th><th>Mean absolute error</th></tr></thead><tbody>${summary.rows.map(r=>`<tr><td>${esc(r.method)}</td><td>${r.within_accuracy_target}/${r.runs}</td><td>${r.interval_half_width_target}/${r.runs}</td><td>${r.covered}/${r.runs}</td><td>${pct(r.coverage_binomial_interval[0])}–${pct(r.coverage_binomial_interval[1])}</td><td>${r.mean_absolute_error.toFixed(5)}</td></tr>`).join('')}</tbody></table></div><p class="muted">${esc(summary.note)}</p>`) }catch{$('#benchmark-summary').textContent='No recorded benchmark dataset is available. Run scripts/benchmark.py.'}}
init();
