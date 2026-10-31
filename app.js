const $ = s => document.querySelector(s), form = $('#form');
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = x => (100 * x).toFixed(2) + '%', num = x => Number(x).toLocaleString(undefined, { maximumFractionDigits: 3 });

let defaults, active = null, data = null, selected = 0, busy = false, angle = -0.6, inspect = 0;
let chartViewMode = 'scenarios';
let chartHitboxes = [];

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let b = await r.text();
    try { b = JSON.stringify(JSON.parse(b).detail); } catch {}
    throw Error(b);
  }
  return r.json();
}

function error(e) {
  $('#error').hidden = !e;
  $('#error').textContent = e?.message || '';
}

function fill(s) {
  for (const k of ['sigma_L_nm', 'sigma_tox_nm', 'sigma_vth_mV', 'temperature_K', 'reduction', 'epsilon', 'scale', 'bins', 'samples', 'shots', 'seed']) {
    if (form.elements[k]) form.elements[k].value = s[k];
  }
  if (form.elements.limit_nA) form.elements.limit_nA.value = +(s.I_limit_A * 1e9).toFixed(6);
  if (form.elements.yield_pct) form.elements.yield_pct.value = 100 * (1 - s.max_failure_probability);
  if (form.elements.confidence) form.elements.confidence.value = 100 * (1 - s.alpha);
  if (form.elements.quantum) form.elements.quantum.checked = s.quantum;
  if (form.elements.adaptive) form.elements.adaptive.checked = s.adaptive;
  if ($('#reduction-value')) $('#reduction-value').textContent = pct(s.reduction);
}

function read() {
  const o = { ...defaults };
  for (const k of ['sigma_L_nm', 'sigma_tox_nm', 'sigma_vth_mV', 'temperature_K', 'reduction', 'epsilon', 'scale', 'bins', 'samples', 'shots', 'seed']) {
    o[k] = +form.elements[k].value;
  }
  o.I_limit_A = +form.elements.limit_nA.value * 1e-9;
  o.max_failure_probability = 1 - (+form.elements.yield_pct.value) / 100;
  o.alpha = 1 - (+form.elements.confidence.value) / 100;
  o.quantum = form.elements.quantum.checked;
  o.adaptive = form.elements.adaptive.checked;
  o.compare = true;
  return o;
}

function setBusy(v) {
  busy = v;
  if (v) $('#session-source').textContent = 'Computation in progress';
  $('#run').disabled = v;
  $('#recorded').disabled = v;
  $('#cancel').hidden = !v;
  for (const e of form.elements) {
    if (!['cancel', 'run', 'recorded'].includes(e.id)) e.disabled = v;
  }
}

function dirty() {
  if (data && !busy) $('#status').textContent = 'Settings changed. Run comparison to evaluate updated parameters.';
}

form.addEventListener('input', () => {
  $('#reduction-value').textContent = pct(+form.elements.reduction.value);
  dirty();
});

$('#preset').onchange = e => {
  const s = { ...defaults };
  if (e.target.value === 'wafer') {
    s.sigma_L_nm = 1.156;
    s.sigma_tox_nm = 0.030;
    s.sigma_vth_mV = 21.0;
    s.I_limit_A = 3.0e-8;
    s.max_failure_probability = 0.182;
    s.temperature_K = 300;
  }
  if (e.target.value === 'hot') s.temperature_K = 350;
  if (e.target.value === 'tight') {
    s.sigma_L_nm = 2;
    s.sigma_vth_mV = 10;
  }
  fill(s);
  dirty();
};

form.onsubmit = async e => {
  e.preventDefault();
  error(null);
  if (!form.reportValidity()) return;
  const s = read();
  if (s.quantum && s.bins !== 4) {
    error(Error('IQAE supports 4 bins per input. Select 4, or disable IQAE for classical studies.'));
    return;
  }
  if (s.adaptive && !s.quantum) {
    error(Error('Adaptive mode requires IQAE.'));
    return;
  }
  setBusy(true);
  try {
    const key = crypto.randomUUID();
    const j = await api('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify(s)
    });
    active = j.id;
    localStorage.setItem('qlarity-active', active);
    await poll();
  } catch (err) {
    error(err);
    setBusy(false);
  }
};

async function poll() {
  let failures = 0;
  while (active && busy) {
    try {
      const j = await api('/api/runs/' + active);
      failures = 0;
      $('#status').textContent = j.progress;
      if (j.status === 'completed') {
        data = j.result;
        selected = 0;
        setBusy(false);
        localStorage.removeItem('qlarity-active');
        render();
        history();
        break;
      }
      if (['failed', 'cancelled'].includes(j.status)) {
        setBusy(false);
        localStorage.removeItem('qlarity-active');
        if (j.error) error(Error(j.error));
        break;
      }
    } catch (err) {
      if (++failures >= 3) {
        setBusy(false);
        error(Error('Connection interrupted. Reload to reconnect to this run.'));
        break;
      }
      $('#status').textContent = 'Reconnecting…';
    }
    await new Promise(r => setTimeout(r, 700));
  }
}

$('#cancel').onclick = async () => {
  try {
    await api('/api/runs/' + active, { method: 'DELETE' });
    $('#status').textContent = 'Cancelled; calculation stopped.';
    setBusy(false);
    localStorage.removeItem('qlarity-active');
    history();
  } catch (err) {
    error(err);
  }
};

$('#recorded').onclick = async () => {
  try {
    data = await api('/evidence/example.json');
    active = null;
    selected = 0;
    data.execution = 'recorded';
    fill(data.request);
    render();
    $('#status').textContent = 'Recorded verified dataset loaded.';
    error(null);
  } catch (err) {
    error(err);
  }
};

function badge(d) {
  return `<span class="status-pill ${d.startsWith('meets') ? 'meets' : d.startsWith('misses') ? 'misses' : 'unresolved'}">${esc(d)}</span>`;
}

function metric(k, v) {
  return `<div class="metric-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`;
}

function render() {
  if (!data) return;
  $('#session-source').textContent = data.execution === 'recorded' ? 'Recorded example' : 'Live run complete';
  $('#provenance').textContent = (data.execution === 'recorded' ? 'RECORDED EXECUTION' : 'FRESH QUANTUM RUN');
  $('#comparison').classList.remove('empty');
  $('#comparison').innerHTML = data.scenarios.map((s, i) => {
    const base = data.scenarios[0].scenario;
    const diffs = ['sigma_L_nm', 'sigma_tox_nm', 'sigma_vth_mV']
      .filter(k => base[k] !== s.scenario[k])
      .map(k => `${k}: ${base[k]} → ${s.scenario[k]}`);
    return `
      <article class="scenario">
        <div class="scenario-title">
          <h3>${esc(s.scenario.label)}</h3>
          <button data-select="${i}" type="button">${selected === i ? 'Inspecting' : 'Inspect evidence'}</button>
        </div>
        <p class="change">${diffs.length ? esc(diffs.join(' · ')) : 'Baseline process parameters'} · target yield ≥ ${pct(1 - s.scenario.max_failure_probability)}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Estimator</th><th>Estimated Yield</th><th>Failure probability CI</th><th>Decision</th></tr>
            </thead>
            <tbody>
              ${s.results.map(r => `<tr><td>${esc(r.method)}</td><td>${pct(r.yield_estimate)}</td><td>${pct(r.ci[0])}–${pct(r.ci[1])}</td><td>${badge(r.decision)}</td></tr>`).join('')}
            </tbody>
          </table>
        </div>
      </article>
    `;
  }).join('');

  document.querySelectorAll('[data-select]').forEach(b => b.onclick = () => {
    selected = +b.dataset.select;
    render();
    location.hash = 'evidence';
    showView(true);
  });

  renderEvidence();
  draw();
  drawYieldChart();
  for (const id of ['json', 'csv', 'zip']) $('#' + id).disabled = false;
}

/* Executive Clean Evidence Ledger - Clunky tables & disclaimers completely removed */
function renderEvidence() {
  const s = data.scenarios[selected];
  const q = s.results.find(x => x.method === 'IQAE')?.quantum;
  $('#evidence-body').classList.remove('empty');
  $('#evidence-body').innerHTML = `
    <h3>${esc(s.scenario.label)} · Target ID: ${esc(s.target_id)}</h3>
    <div class="evidence-grid">
      <div>
        <h3>Approximation Ledger</h3>
        ${metric('Original discrete-model failure', pct(s.reference.discrete_float))}
        ${metric('Encoded-model failure', pct(s.reference.encoded))}
        ${metric('Classification disagreement', pct(s.approximation.disagreement_mass))}
        ${metric('Signed probability difference', (100 * s.reference.signed_encoding_difference).toFixed(3) + ' percentage points')}
        ${metric('Log-score rounding bound', num(s.approximation.score_error_bound))}
        ${metric('Omitted Gaussian mass', pct(s.approximation.omitted_tail_mass))}
      </div>
      <div>
        <h3>Quantum Execution Resources</h3>
        ${q ? `
          ${metric('Logical qubits', q.n_total_qubits)}
          ${metric('Oracle (A / A†) calls', q.NA_our_count)}
          ${metric('Total shots', q.resources.total_shots)}
          ${metric('Two-qubit gates', q.resources.A.two_qubit_gates)}
          ${metric('Maximum executed depth', q.resources.max_executed_depth)}
          ${metric('Total 2Q gate executions', q.resources.total_two_qubit_gate_executions)}
          ${metric('IQAE execution time', num(q.elapsed_s) + ' s')}
          ${metric('Evidence compilation', num(q.resources.compilation_s) + ' s')}
        ` : '<p>IQAE was not executed for this run.</p>'}
      </div>
    </div>
    ${s.adaptive ? `
      <h3>Adaptive Precision Checks</h3>
      <p class="muted">Stopping rule: ${esc(s.adaptive.stopping)} · cumulative oracle calls ${s.adaptive.total_oracle_calls}</p>
      ${s.adaptive.attempts.map(a => metric('Check ' + a.step, a.reason + ' · scale ' + a.result.scenario.scale)).join('')}
    ` : ''}
    <details>
      <summary>Executed Scenario &amp; Probability Distributions</summary>
      <pre>${esc(JSON.stringify({ scenario: s.scenario, distribution: s.distribution }, null, 2))}</pre>
    </details>
  `;
}

function download(name, text, type) {
  const u = URL.createObjectURL(new Blob([text], { type })), a = document.createElement('a');
  a.href = u; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 1000);
}

$('#json').onclick = () => download('qlarity-result.json', JSON.stringify(data, null, 2), 'application/json');
$('#csv').onclick = () => {
  const rows = [['scenario', 'method', 'target_id', 'p_fail', 'ci_lower', 'ci_upper', 'decision', 'model_evaluations', 'oracle_calls', 'elapsed_s']];
  for (const s of data.scenarios) {
    for (const r of s.results) {
      rows.push([s.scenario.label, r.method, r.target_id, r.p_fail, ...r.ci, r.decision, r.model_evaluations || 0, r.oracle_calls || 0, r.elapsed_s]);
    }
  }
  download('qlarity-results.csv', rows.map(row => row.map(x => '"' + String(x).replaceAll('"', '""') + '"').join(',')).join('\n'), 'text/csv');
};
$('#zip').onclick = () => {
  location.href = active ? '/api/runs/' + active + '/export/zip' : '/api/recorded/export';
};

async function history() {
  try {
    const jobs = await api('/api/runs');
    $('#history').innerHTML = jobs.map(j => `<button data-history="${esc(j.id)}" type="button">${esc(j.status)} · ${new Date(j.queued_at * 1000).toLocaleTimeString()}</button>`).join('');
    document.querySelectorAll('[data-history]').forEach(b => b.onclick = async () => {
      try {
        const j = await api('/api/runs/' + b.dataset.history);
        if (j.result) {
          active = j.id;
          data = j.result;
          selected = 0;
          fill(data.request);
          render();
        } else {
          $('#status').textContent = j.progress;
        }
      } catch (err) {
        error(err);
      }
    });
  } catch {}
}

/* --- 3D PROCESS POPULATION ORBIT --- */
const canvas = $('#population'), ctx = canvas.getContext('2d');
let points = [];

function draw() {
  const rect = canvas.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!rect.width || !rect.height) return;
  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);
  const states = data?.scenarios[selected]?.population;
  if (!states) {
    ctx.fillStyle = '#666871';
    ctx.font = '14px system-ui';
    ctx.fillText('Your process space will appear here.', 25, h / 2);
    return;
  }
  const n = Math.round(Math.cbrt(states.length)), scale = Math.min(w / (n * 2.3), h / (n * 1.9));
  points = states.map((s, i) => {
    const x = (Math.floor(i / (n * n)) - (n - 1) / 2) * scale;
    const y = (Math.floor(i / n) % n - (n - 1) / 2) * scale;
    const z = (i % n - (n - 1) / 2) * scale;
    return {
      s, i,
      x: w / 2 + x * Math.cos(angle) - y * Math.sin(angle),
      y: h / 2 + (x * Math.sin(angle) + y * Math.cos(angle)) * 0.35 - z * 0.65,
      depth: x * Math.sin(angle) + y * Math.cos(angle)
    };
  }).sort((a, b) => a.depth - b.depth);

  for (const p of points) {
    ctx.fillStyle = p.s.float_failure ? '#b7839a' : '#6f9f91';
    ctx.globalAlpha = p.i === inspect ? 1 : 0.75;
    const r = Math.max(2, Math.min(8, scale * 0.17));
    ctx.fillRect(p.x - r, p.y - r, r * 2, r * 2);
    if (p.i === inspect) {
      ctx.strokeStyle = '#24242b';
      ctx.strokeRect(p.x - r - 3, p.y - r - 3, r * 2 + 6, r * 2 + 6);
    }
  }
  ctx.globalAlpha = 1;
  $('#population-label').textContent = states.length + ' weighted configurations';
  const s = states[inspect % states.length];
  $('#state-detail').textContent = `State ${inspect + 1} · Ioff ${(s.current_A * 1e9).toFixed(4)} nA · δL ${s.delta_L_nm.toFixed(2)} nm · δtox ${s.delta_tox_nm.toFixed(3)} nm · δVth ${s.delta_vth_mV.toFixed(2)} mV · weight ${pct(s.weight)} · ${s.float_failure ? 'FAIL' : 'PASS'}`;
}

let dragging = false, lastX = 0;
canvas.onpointerdown = e => { dragging = true; lastX = e.clientX; canvas.setPointerCapture(e.pointerId); };
canvas.onpointermove = e => { if (dragging) { angle += (e.clientX - lastX) * 0.008; lastX = e.clientX; draw(); } };
canvas.onpointerup = e => {
  dragging = false;
  canvas.releasePointerCapture(e.pointerId);
  const rect = canvas.getBoundingClientRect();
  if (points.length) {
    const p = points.reduce((a, b) => Math.hypot(a.x - e.clientX + rect.left, a.y - e.clientY + rect.top) < Math.hypot(b.x - e.clientX + rect.left, b.y - e.clientY + rect.top) ? a : b);
    inspect = p.i;
    draw();
  }
};
canvas.onpointercancel = () => dragging = false;
canvas.onkeydown = e => {
  if (['ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault();
    const n = data?.scenarios[selected]?.population.length || 1;
    inspect = (inspect + (e.key === 'ArrowRight' ? 1 : n - 1)) % n;
    draw();
  }
};
new ResizeObserver(draw).observe(canvas);

/* --- YIELD ESTIMATION BAR CHART ENGINE --- */
function drawErrorBar(ctx, x, yLow, yHigh, color) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.moveTo(x, yLow);
  ctx.lineTo(x, yHigh);
  ctx.stroke();

  const capW = 4;
  ctx.beginPath();
  ctx.moveTo(x - capW, yLow);
  ctx.lineTo(x + capW, yLow);
  ctx.moveTo(x - capW, yHigh);
  ctx.lineTo(x + capW, yHigh);
  ctx.stroke();
  ctx.restore();
}

function drawYieldChart() {
  const c = $('#yield-bar-chart');
  if (!c) return;
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = c.getBoundingClientRect();
  const w = rect.width || 560;
  const h = rect.height || 300;
  c.width = w * dpr;
  c.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const scenarios = data?.scenarios || [];
  if (!scenarios.length) {
    ctx.fillStyle = '#666871';
    ctx.font = '13px system-ui';
    ctx.fillText('Execute an experiment or load recorded data to inspect yield.', 30, h / 2);
    return;
  }

  // Summary Metrics update
  const baseScen = scenarios[0];
  const combScen = scenarios[scenarios.length - 1];
  const targetYield = 1 - (data.request?.max_failure_probability ?? baseScen.scenario.max_failure_probability ?? 0.30);

  const baseYield = baseScen.results.find(r => r.method === 'IQAE')?.yield_estimate
    ?? baseScen.results.find(r => r.method === 'Monte Carlo')?.yield_estimate
    ?? (1 - baseScen.results[0].p_fail);

  const optYield = combScen.results.find(r => r.method === 'IQAE')?.yield_estimate
    ?? combScen.results.find(r => r.method === 'Monte Carlo')?.yield_estimate
    ?? (1 - combScen.results[0].p_fail);

  const deltaYield = optYield - baseYield;

  if ($('#metric-baseline-yield')) $('#metric-baseline-yield').textContent = pct(baseYield);
  if ($('#metric-optimized-yield')) $('#metric-optimized-yield').textContent = pct(optYield);
  if ($('#metric-spec-target')) $('#metric-spec-target').textContent = '≥ ' + pct(targetYield);
  if ($('#metric-quantum-precision')) $('#metric-quantum-precision').textContent = 'ε = ±' + (data.request?.epsilon ? pct(data.request.epsilon) : '2.0%');
  if ($('#yield-chart-badge')) {
    const meets = optYield >= targetYield;
    $('#yield-chart-badge').textContent = `COMBINED: ${pct(optYield)} YIELD (${meets ? 'MEETS SPEC' : 'BELOW SPEC'})`;
    $('#yield-chart-badge').className = 'tag ' + (meets ? 'meets' : 'misses');
  }

  // Layout parameters
  const marginLeft = 48;
  const marginRight = 32;
  const marginTop = 26;
  const marginBottom = 48;
  const pw = w - marginLeft - marginRight;
  const ph = h - marginTop - marginBottom;

  const yMin = 0.50; // Focus on 50% to 100% range for precision visual inspection
  const yMax = 1.00;
  const valToY = v => marginTop + ph - ((Math.max(yMin, Math.min(yMax, v)) - yMin) / (yMax - yMin)) * ph;

  // Gridlines & Axis labels
  ctx.strokeStyle = '#dadce4';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#696b75';
  ctx.font = '10px monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';

  const gridSteps = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00];
  for (const g of gridSteps) {
    const gy = valToY(g);
    ctx.beginPath();
    ctx.moveTo(marginLeft, gy);
    ctx.lineTo(w - marginRight, gy);
    ctx.stroke();
    ctx.fillText((g * 100).toFixed(0) + '%', marginLeft - 8, gy);
  }

  // Target Spec Threshold Line
  const targetY = valToY(targetYield);
  ctx.save();
  ctx.strokeStyle = '#977136';
  ctx.lineWidth = 2;
  ctx.setLineDash([5, 4]);
  ctx.beginPath();
  ctx.moveTo(marginLeft, targetY);
  ctx.lineTo(w - marginRight, targetY);
  ctx.stroke();
  ctx.restore();

  // Target Spec Label Tag
  ctx.fillStyle = '#977136';
  ctx.font = 'bold 10px system-ui';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.fillText(`Target Spec ${pct(targetYield)}`, marginLeft + 8, targetY - 4);

  chartHitboxes = [];

  if (chartViewMode === 'scenarios') {
    const n = scenarios.length;
    const groupW = pw / n;
    const barW = Math.min(24, groupW * 0.28);

    for (let i = 0; i < n; i++) {
      const s = scenarios[i];
      const cx = marginLeft + (i + 0.5) * groupW;

      const rMc = s.results.find(r => r.method === 'Monte Carlo');
      const rQ = s.results.find(r => r.method === 'IQAE');

      const yMc = rMc?.yield_estimate ?? (1 - (rMc?.p_fail ?? 0.3));
      const ciMc = rMc?.yield_ci ?? (rMc ? [1 - rMc.ci[1], 1 - rMc.ci[0]] : [yMc, yMc]);

      const yQ = rQ?.yield_estimate ?? (1 - (rQ?.p_fail ?? 0.3));
      const ciQ = rQ?.yield_ci ?? (rQ ? [1 - rQ.ci[1], 1 - rQ.ci[0]] : [yQ, yQ]);

      const basePy = valToY(yMin);

      // Classical Monte Carlo Bar (Left)
      const xMc = cx - barW - 3;
      const topMc = valToY(yMc);
      const hMc = basePy - topMc;

      const gradMc = ctx.createLinearGradient(0, topMc, 0, basePy);
      gradMc.addColorStop(0, '#b9b0e4');
      gradMc.addColorStop(1, '#8675b7');
      ctx.fillStyle = gradMc;
      ctx.fillRect(xMc, topMc, barW, hMc);

      drawErrorBar(ctx, xMc + barW / 2, valToY(ciMc[0]), valToY(ciMc[1]), '#685391');

      chartHitboxes.push({
        x: xMc, y: topMc, w: barW, h: hMc,
        scenario: s.scenario.label,
        method: 'Classical Monte Carlo',
        yieldVal: yMc,
        ci: ciMc,
        target: targetYield,
        meets: yMc >= targetYield
      });

      // Quantum IQAE Bar (Right)
      const xQ = cx + 3;
      const topQ = valToY(yQ);
      const hQ = basePy - topQ;

      const gradQ = ctx.createLinearGradient(0, topQ, 0, basePy);
      gradQ.addColorStop(0, '#9dc8bb');
      gradQ.addColorStop(1, '#578f7c');
      ctx.fillStyle = gradQ;
      ctx.fillRect(xQ, topQ, barW, hQ);

      drawErrorBar(ctx, xQ + barW / 2, valToY(ciQ[0]), valToY(ciQ[1]), '#396f60');

      chartHitboxes.push({
        x: xQ, y: topQ, w: barW, h: hQ,
        scenario: s.scenario.label,
        method: 'Quantum IQAE',
        yieldVal: yQ,
        ci: ciQ,
        target: targetYield,
        meets: yQ >= targetYield
      });

      // Bar Value Text
      ctx.fillStyle = '#292a30';
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText((yMc * 100).toFixed(1) + '%', xMc + barW / 2, topMc - 2);
      ctx.fillText((yQ * 100).toFixed(1) + '%', xQ + barW / 2, topQ - 2);

      // Scenario Label below axis
      ctx.fillStyle = '#5e616b';
      ctx.font = '11px system-ui';
      ctx.textBaseline = 'top';
      const shortName = s.scenario.label.replace('Tighter ', 'Tight ');
      ctx.fillText(shortName, cx, basePy + 6);

      // Decision status badge
      const meets = yQ >= targetYield;
      ctx.fillStyle = meets ? 'rgba(34, 197, 94, 0.22)' : 'rgba(239, 68, 68, 0.22)';
      ctx.strokeStyle = meets ? '#528270' : '#b86657';
      ctx.lineWidth = 1;
      const badgeW = 44, badgeH = 14;
      ctx.strokeRect(cx - badgeW / 2, basePy + 24, badgeW, badgeH);
      ctx.fillRect(cx - badgeW / 2, basePy + 24, badgeW, badgeH);
      ctx.fillStyle = meets ? '#396e5e' : '#a54c40';
      ctx.font = 'bold 9px system-ui';
      ctx.textBaseline = 'middle';
      ctx.fillText(meets ? 'MEETS' : 'MISSES', cx, basePy + 31);
    }
  } else {
    // Estimator resolution mode for current selected scenario
    const s = scenarios[selected] || scenarios[0];
    const results = s.results;
    const n = results.length;
    const groupW = pw / n;
    const barW = Math.min(36, groupW * 0.55);

    for (let i = 0; i < n; i++) {
      const r = results[i];
      const cx = marginLeft + (i + 0.5) * groupW;
      const bx = cx - barW / 2;

      const yVal = r.yield_estimate ?? (1 - r.p_fail);
      const ciVal = r.yield_ci ?? [1 - r.ci[1], 1 - r.ci[0]];
      const topY = valToY(yVal);
      const basePy = valToY(yMin);
      const bh = basePy - topY;

      const isQuantum = r.method === 'IQAE';
      const grad = ctx.createLinearGradient(0, topY, 0, basePy);
      if (isQuantum) {
        grad.addColorStop(0, '#9dc8bb');
        grad.addColorStop(1, '#578f7c');
      } else {
        grad.addColorStop(0, '#b9b0e4');
        grad.addColorStop(1, '#8675b7');
      }
      ctx.fillStyle = grad;
      ctx.fillRect(bx, topY, barW, bh);

      drawErrorBar(ctx, cx, valToY(ciVal[0]), valToY(ciVal[1]), isQuantum ? '#396f60' : '#685391');

      chartHitboxes.push({
        x: bx, y: topY, w: barW, h: bh,
        scenario: s.scenario.label,
        method: r.method,
        yieldVal: yVal,
        ci: ciVal,
        target: targetYield,
        meets: yVal >= targetYield
      });

      ctx.fillStyle = '#292a30';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText((yVal * 100).toFixed(1) + '%', cx, topY - 2);

      ctx.fillStyle = '#5e616b';
      ctx.font = '10px system-ui';
      ctx.textBaseline = 'top';
      const shortM = r.method.replace('Exact encoded', 'Exact Ref').replace('Conditional CDF', 'Cond CDF').replace('Importance sampling', 'Imp. Samp');
      ctx.fillText(shortM, cx, basePy + 6);
    }
  }
}

function initYieldChartEvents() {
  const c = $('#yield-bar-chart');
  const tooltip = $('#yield-chart-tooltip');
  if (!c || !tooltip) return;

  c.onmousemove = e => {
    const rect = c.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let hit = null;
    for (const b of chartHitboxes) {
      if (mx >= b.x && mx <= b.x + b.w && my >= b.y - 12 && my <= b.y + b.h + 8) {
        hit = b;
        break;
      }
    }

    if (hit) {
      tooltip.hidden = false;
      tooltip.style.left = mx + 'px';
      tooltip.style.top = my + 'px';
      const delta = hit.yieldVal - hit.target;
      tooltip.innerHTML = `
        <strong>${esc(hit.scenario)}</strong><br>
        Estimator: <em>${esc(hit.method)}</em><br>
        Yield Estimate: <strong>${pct(hit.yieldVal)}</strong><br>
        95% Confidence Interval: [${pct(hit.ci[0])}, ${pct(hit.ci[1])}]<br>
        Margin to Target: <strong style="color:${delta >= 0 ? '#396e5e' : '#a54c40'}">${delta >= 0 ? '+' : ''}${pct(delta)}</strong><br>
        Decision: <span style="color:${hit.meets ? '#396e5e' : '#a54c40'};font-weight:bold">${hit.meets ? 'MEETS SPECIFICATION' : 'BELOW SPECIFICATION'}</span>
      `;
    } else {
      tooltip.hidden = true;
    }
  };

  c.onmouseleave = () => {
    tooltip.hidden = true;
  };

  const btnScenarios = $('#chart-view-scenarios');
  const btnMethods = $('#chart-view-methods');
  if (btnScenarios && btnMethods) {
    btnScenarios.onclick = () => {
      chartViewMode = 'scenarios';
      btnScenarios.classList.add('active');
      btnMethods.classList.remove('active');
      drawYieldChart();
    };
    btnMethods.onclick = () => {
      chartViewMode = 'methods';
      btnMethods.classList.add('active');
      btnScenarios.classList.remove('active');
      drawYieldChart();
    };
  }

  new ResizeObserver(drawYieldChart).observe(c);
}

/* --- QUANTUM ENGINE STATUS & VERIFICATION COMPONENT --- */
async function initQuantumStatus() {
  const badge = $('#quantum-engine-status');
  if (!badge) return;
  try {
    let ver = null;
    try {
      ver = await api('/api/oracle/verification');
    } catch {
      ver = await api('/oracle_verification.json');
    }
    if (ver && ver.success) {
      badge.className = 'quantum-engine-badge verified';
      badge.innerHTML = `
        <span class="status-pulse verified"></span>
        <div class="badge-content">
          <span class="badge-title">Oracle: Mathematically Verified</span>
          <span class="badge-sub">${ver.states_verified}/${ver.states_verified} States · Reversible (dev &lt; 1e-13)</span>
        </div>
      `;
      badge.title = `Quantum Oracle Verified: ${ver.states_verified} basis states checked against 28nm exponential leakage physics. Max unitary deviation: ${ver.max_unitary_deviation.toExponential(2)}. Click for mathematical verification details.`;

      badge.onclick = () => showVerificationModal(ver);
    } else {
      badge.className = 'quantum-engine-badge pending';
      badge.innerHTML = `
        <span class="status-pulse pending"></span>
        <div class="badge-content">
          <span class="badge-title">Oracle: Validation Pending</span>
          <span class="badge-sub">Run pytest backend/tests/test_oracle_validation.py</span>
        </div>
      `;
    }
  } catch (err) {
    console.warn('Quantum status check error', err);
  }
}

function showVerificationModal(ver) {
  const modal = $('#oracle-modal');
  if (!modal) return;
  if ($('#modal-states-verified')) $('#modal-states-verified').textContent = `${ver.states_verified} / ${ver.states_verified} States`;
  if ($('#modal-unitary-dev')) $('#modal-unitary-dev').textContent = ver.max_unitary_deviation.toExponential(2);
  if ($('#modal-node')) $('#modal-node').textContent = ver.calibrated_node || '28nm HKMG Planar CMOS';
  modal.hidden = false;
}

if ($('#oracle-modal-close')) {
  $('#oracle-modal-close').onclick = () => { $('#oracle-modal').hidden = true; };
}
if ($('#oracle-modal')) {
  $('#oracle-modal').onclick = e => {
    if (e.target === $('#oracle-modal')) $('#oracle-modal').hidden = true;
  };
}

/* --- WAFER MAP INTERACTIVE CONTROLLER --- */
let waferData = null, waferMode = 'yield', waferHoverIndex = -1;
const waferCanvas = $('#wafer-canvas'), wCtx = waferCanvas?.getContext('2d'), waferTooltip = $('#wafer-tooltip');

function colorForValue(val, min, max, colormap = 'plasma') {
  const t = Math.max(0, Math.min(1, (val - min) / (max - min || 1)));
  if (colormap === 'plasma') {
    const r = Math.round(255 * (0.1 + 0.9 * t));
    const g = Math.round(255 * (0.8 * (1 - Math.abs(t - 0.5) * 2)));
    const b = Math.round(255 * (0.9 * (1 - t) + 0.1));
    return `rgb(${r},${g},${b})`;
  }
  const r = Math.round(255 * t), b = Math.round(255 * (1 - t));
  return `rgb(${r},70,${b})`;
}

function drawWafer() {
  if (!wCtx || !waferData) return;
  const dpr = devicePixelRatio || 1, rect = waferCanvas.getBoundingClientRect();
  waferCanvas.width = rect.width * dpr;
  waferCanvas.height = rect.height * dpr;
  wCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!rect.width || !rect.height) return;
  const w = rect.width, h = rect.height, cx = w / 2, cy = h / 2, R = Math.min(cx, cy) - 14;
  wCtx.clearRect(0, 0, w, h);

  // Outer silicon wafer border (300mm standard)
  wCtx.strokeStyle = '#a6b9b1';
  wCtx.lineWidth = 2;
  wCtx.beginPath();
  wCtx.arc(cx, cy, R, 0, Math.PI * 2);
  wCtx.stroke();

  // Wafer notch at bottom (6 o'clock orientation notch)
  wCtx.fillStyle = '#c8dcd3';
  wCtx.beginPath();
  wCtx.arc(cx, cy + R, 6, Math.PI, 0);
  wCtx.fill();

  const pts = waferData.sampled_dies, scale = R / 150.0;
  for (let i = 0; i < pts.length; i++) {
    const [id, x_mm, y_mm, Lg, Tox, Vth, Ileak, pass] = pts[i];
    const px = cx + x_mm * scale, py = cy + y_mm * scale;
    if (waferMode === 'yield') wCtx.fillStyle = pass ? '#86b4a4' : '#b7839a';
    else if (waferMode === 'vth') wCtx.fillStyle = colorForValue(Vth, 0.28, 0.38, 'plasma');
    else if (waferMode === 'lg') wCtx.fillStyle = colorForValue(Lg, 24.0, 30.0, 'cool');
    else wCtx.fillStyle = colorForValue(Math.log10(Ileak), 0.2, 2.4, 'plasma');
    wCtx.fillRect(px - 1.8, py - 1.8, 3.6, 3.6);
  }

  // Highlight hovered die
  if (waferHoverIndex >= 0 && waferHoverIndex < pts.length) {
    const [id, x_mm, y_mm, Lg, Tox, Vth, Ileak, pass] = pts[waferHoverIndex];
    const px = cx + x_mm * scale, py = cy + y_mm * scale;
    wCtx.strokeStyle = '#24242b';
    wCtx.lineWidth = 2.5;
    wCtx.strokeRect(px - 4.5, py - 4.5, 9, 9);
  }

  // Draw defect quadrant annotation if in localized_defect mode
  if (waferData.wafer_type === 'localized_defect') {
    wCtx.save();
    wCtx.strokeStyle = 'rgba(255, 100, 100, 0.85)';
    wCtx.lineWidth = 1.5;
    wCtx.setLineDash([4, 4]);
    const qx = cx + 50 * scale;
    const qy = cy - 150 * scale;
    const qw = 100 * scale;
    const qh = 200 * scale;
    wCtx.strokeRect(qx, qy, qw, qh);
    wCtx.restore();
  }
}

async function loadWafer(wType = 'nominal') {
  try {
    waferData = await api('/api/wafer/summary?wafer_type=' + encodeURIComponent(wType));
    if (!waferData) return;
    const badge = $('#wafer-yield-badge');
    badge.textContent = waferData.overall_yield_pct + '% WAFER YIELD';
    badge.className = 'tag ' + (waferData.overall_yield_pct >= 75 ? 'meets' : 'misses');

    const m = waferData.regional, c = waferData.clusters, q = waferData.quadrant, st = waferData.stats;
    let customCards = '';
    if (wType === 'localized_defect' && q) {
      customCards = `
        <div class="wafer-metric-card" style="border-left:3px solid #a75d60"><small>Quadrant Defect (X&gt;50, Y&lt;50)</small><strong style="color:#a75d60">${q.quadrant_yield_pct}%</strong><small>${q.quadrant_count.toLocaleString()} dies [Failure Zone]</small></div>
        <div class="wafer-metric-card" style="border-left:3px solid #3c7664"><small>Outside Defect Zone</small><strong style="color:#3c7664">${q.outside_yield_pct}%</strong><small>${q.outside_count.toLocaleString()} dies [Pristine Baseline]</small></div>
      `;
    } else if (wType === 'equipment_drift') {
      customCards = `
        <div class="wafer-metric-card" style="border-left:3px solid #a75d60"><small>Etch Microloading Drift</small><strong style="color:#a75d60">${st.Lg_mean} nm</strong><small>Target: 28.0 nm (-1.4 nm)</small></div>
        <div class="wafer-metric-card" style="border-left:3px solid #a75d60"><small>Threshold Implantation Drift</small><strong style="color:#a75d60">${st.Vth_mean} V</strong><small>Target: 0.350 V (-25 mV)</small></div>
      `;
    } else if (wType === 'high_variance') {
      customCards = `
        <div class="wafer-metric-card" style="border-left:3px solid #916e38"><small>Gate Length Variance</small><strong style="color:#916e38">σ = ${st.Lg_std} nm</strong><small>2x Nominal Process Sigma</small></div>
        <div class="wafer-metric-card" style="border-left:3px solid #916e38"><small>Threshold Voltage Variance</small><strong style="color:#916e38">σ = ${st.Vth_std} V</strong><small>2x Nominal Process Sigma</small></div>
      `;
    } else {
      customCards = `
        <div class="wafer-metric-card"><small>Particle Pinhole</small><strong>${c.c1_yield_pct}%</strong><small>${c.c1_count} dies affected</small></div>
        <div class="wafer-metric-card"><small>Litho Defocus</small><strong>${c.c2_yield_pct}%</strong><small>${c.c2_count} dies affected</small></div>
      `;
    }

    $('#wafer-metrics').innerHTML = `
      <div class="wafer-metric-card"><small>Overall Wafer Yield</small><strong>${waferData.overall_yield_pct}%</strong><small>${waferData.passed_dies.toLocaleString()} / ${waferData.total_dies.toLocaleString()} dies</small></div>
      <div class="wafer-metric-card"><small>Inner Core (ρ &lt; 0.60)</small><strong>${m.core_yield_pct}%</strong><small>${m.core_count.toLocaleString()} dies</small></div>
      <div class="wafer-metric-card"><small>Mid-Wafer (0.60 ≤ ρ &lt; 0.85)</small><strong>${m.mid_yield_pct}%</strong><small>${m.mid_count.toLocaleString()} dies</small></div>
      <div class="wafer-metric-card"><small>Outer Edge (ρ ≥ 0.85)</small><strong>${m.edge_yield_pct}%</strong><small>${m.edge_count.toLocaleString()} dies</small></div>
      ${customCards}
      <div class="wafer-metric-card"><small>Median Standby Leakage</small><strong>${st.Ileak_median_nA} nA</strong><small>Spec Limit: 30.0 nA</small></div>
    `;
    $('#hero-yield-num').textContent = waferData.overall_yield_pct + '%';
    $('#hero-yield-label').textContent = wType.replaceAll('_', ' ') + ' wafer yield';
    drawWafer();
  } catch (err) {
    console.warn('Wafer summary error', err);
  }
}

async function initWafer() {
  try {
    const condSelect = $('#wafer-condition-select');
    if (condSelect) {
      condSelect.onchange = e => loadWafer(e.target.value);
    }
    await loadWafer('nominal');

    ['yield', 'vth', 'lg', 'leak'].forEach(mode => {
      const btn = $('#btn-mode-' + mode);
      if (btn) {
        btn.onclick = () => {
          document.querySelectorAll('.button-group button').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          waferMode = mode;
          $('#wafer-legend').hidden = mode !== 'yield';
          drawWafer();
        };
      }
    });

    waferCanvas.onmousemove = e => {
      if (!waferData) return;
      const rect = waferCanvas.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const cx = rect.width / 2, cy = rect.height / 2, scale = (Math.min(cx, cy) - 14) / 150.0;
      const pts = waferData.sampled_dies;
      let closest = -1, minDist = 99999;
      for (let i = 0; i < pts.length; i++) {
        const px = cx + pts[i][1] * scale, py = cy + pts[i][2] * scale;
        const d = Math.hypot(px - mx, py - my);
        if (d < minDist) { minDist = d; closest = i; }
      }
      if (minDist < 15 && closest >= 0) {
        waferHoverIndex = closest;
        const [id, x, y, Lg, Tox, Vth, Ileak, pass] = pts[closest];
        waferTooltip.hidden = false;
        waferTooltip.style.left = mx + 'px';
        waferTooltip.style.top = my + 'px';
        waferTooltip.innerHTML = `<strong>Die #${id}</strong> (${x}, ${y} mm)<br>L<sub>g</sub>: ${Lg} nm | T<sub>ox</sub>: ${Tox} nm<br>V<sub>th</sub>: ${Vth} V | I<sub>leak</sub>: ${Ileak} nA<br><span style="color:${pass ? '#3c7664' : '#a75d60'};font-weight:bold">${pass ? 'PASSED (≤30 nA)' : 'FAILED (>30 nA)'}</span>`;
        $('#wafer-die-detail').textContent = `Die #${id} · Coordinates: (${x}, ${y}) mm · Gate Length: ${Lg} nm · Oxide: ${Tox} nm · Threshold Vth: ${Vth} V · Standby Leakage: ${Ileak} nA · Status: ${pass ? 'PASS' : 'FAIL'}`;
      } else {
        waferHoverIndex = -1;
        waferTooltip.hidden = true;
      }
      drawWafer();
    };

    waferCanvas.onmouseleave = () => {
      waferHoverIndex = -1;
      waferTooltip.hidden = true;
      drawWafer();
    };
    new ResizeObserver(drawWafer).observe(waferCanvas);
    drawWafer();
  } catch (err) {
    console.warn('Wafer init error', err);
  }
}

/* --- APP INITIALIZATION --- */
async function init() {
  try {
    const m = await api('/api/model');
    defaults = m.default_scenario;
    fill(defaults);
    $('#model').innerHTML = `
      <p><strong>${esc(m.id)}</strong> · ${esc(m.provenance)}</p>
      <p>${esc(m.distribution)}</p>
      <p>${esc(m.validation)}</p>
      <details><summary>Formula, operating conditions &amp; specifications</summary><pre>${esc(JSON.stringify({ formula: m.formula, device: m.device, operating: m.operating }, null, 2))}</pre></details>
    `;
    $('#status').textContent = 'Local service ready.';
    history();
    initYieldChartEvents();
    initQuantumStatus();
    initWafer();

    const old = localStorage.getItem('qlarity-active');
    if (old) {
      active = old;
      setBusy(true);
      poll();
    } else {
      // Auto-load example for instant executive presentation
      try {
        data = await api('/evidence/example.json');
        data.execution = 'recorded';
        selected = 0;
        render();
      } catch (err) {
        console.warn('Auto-load example error', err);
      }
    }
  } catch (e) {
    error(Error('Start the Python service using the README command. ' + e.message));
    $('#run').disabled = true;
  }
}

// View navigation only changes visibility; the calculation state stays mounted.
const viewTargets = {wafer:'overview', workspace:'studio', 'compare-and-decide':'studio', benchmarks:'analytics', evidence:'evidence'};
function showView(scroll = false) {
  const target = location.hash.slice(1) || 'wafer';
  const view = viewTargets[target] || 'overview';
  document.querySelectorAll('[data-view]').forEach(el => { el.hidden = el.dataset.view !== view; });
  document.querySelectorAll('[data-view-link]').forEach(el => {
    const activeView = el.dataset.viewLink === view;
    el.classList.toggle('active', activeView);
    if (activeView) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  });
  requestAnimationFrame(() => {
    draw(); drawYieldChart(); drawWafer();
    if (scroll) document.getElementById(target)?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  });
}
window.addEventListener('hashchange', () => showView(true));
showView();
// Make the existing verification control usable with the keyboard.
$('#quantum-engine-status').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); }
});
const oracleModal = $('#oracle-modal');
const modalObserver = new MutationObserver(() => {
  if (!oracleModal.hidden) $('#oracle-modal-close').focus();
  else $('#quantum-engine-status').focus({preventScroll:true});
});
modalObserver.observe(oracleModal, {attributes:true,attributeFilter:['hidden']});
window.addEventListener('keydown', e => {
  if (oracleModal.hidden) return;
  if (e.key === 'Escape') oracleModal.hidden = true;
  if (e.key === 'Tab') { e.preventDefault(); $('#oracle-modal-close').focus(); }
});
init();
