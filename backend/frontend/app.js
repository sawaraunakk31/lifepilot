/* LifePilot SPA — vanilla JS, same-origin API. No build step, no keys. Data stays local. */
'use strict';

// ───────── helpers ─────────
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const RING_CIRC = 2 * Math.PI * 52; // 326.7

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const fmtINR = (n) => '₹' + Math.round(n || 0).toLocaleString('en-IN');

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return r.status === 204 ? null : r.json();
}

function parseAmount(text) {
  if (!text) return 0;
  const nums = [...text.matchAll(/₹\s*([\d,]+)/g)].map((m) => +m[1].replace(/,/g, ''));
  if (!nums.length) return 0;
  let v = Math.max(...nums);
  if (/month/i.test(text)) v *= 12;
  return v;
}

function daysLeft(d) {
  if (!d) return null;
  return Math.ceil((new Date(d) - new Date()) / 86400000);
}

function toast(msg, type = 'info') {
  const colors = { info: 'var(--accent-2)', good: 'var(--good)', bad: 'var(--bad)', warn: 'var(--warn)' };
  const el = document.createElement('div');
  el.className = 'toast glass rounded-xl px-4 py-3 text-sm flex items-center gap-2 max-w-xs';
  el.style.borderLeft = `3px solid ${colors[type]}`;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(30px)'; el.style.transition = '.4s'; setTimeout(() => el.remove(), 400); }, 3200);
}

function animateCount(el, to, fmt = fmtINR) {
  const from = 0, dur = 900, t0 = performance.now();
  function step(t) {
    const p = Math.min((t - t0) / dur, 1);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function setRing(ring, pctEl, pct) {
  if (ring) ring.style.strokeDashoffset = RING_CIRC * (1 - pct / 100);
  if (pctEl) {
    let cur = 0; const t0 = performance.now();
    const step = (t) => { const p = Math.min((t - t0) / 900, 1); pctEl.textContent = Math.round(pct * (1 - Math.pow(1 - p, 3))) + '%'; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
}

const icons = () => window.lucide && window.lucide.createIcons();

// ───────── state ─────────
const state = {
  profileId: localStorage.getItem('lp_pid') ? +localStorage.getItem('lp_pid') : null,
  profile: JSON.parse(localStorage.getItem('lp_profile') || 'null'),
  run: null,
  ownedDocs: new Set(JSON.parse(localStorage.getItem('lp_docs') || '[]')),
  discoverFilter: 'all',
  charts: {},
  baseline: { eligible: 0, benefit: 0 },
};

const saveDocs = () => localStorage.setItem('lp_docs', JSON.stringify([...state.ownedDocs]));

// ───────── navigation ─────────
const PAGE_META = {
  dashboard: ['Dashboard', 'Your personalised opportunity cockpit'],
  discover: ['Discover', 'Every scheme matched to your profile'],
  simulator: ['What-If Simulator', 'Model scenarios without saving anything'],
  assistant: ['AI Assistant', 'Ask anything about your matches'],
  documents: ['Documents', 'Your combined readiness checklist'],
  activity: ['Agent Activity', 'How the agents reasoned'],
  profile: ['Profile & Settings', 'Tune your matches'],
};

function switchView(name) {
  $$('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === name));
  $$('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.nav === name));
  const [title, sub] = PAGE_META[name] || ['', ''];
  $('#pageTitle').textContent = title;
  $('#pageSub').textContent = sub;
  const mob = $('#mobileNav'); if (mob) mob.value = name;
  window.scrollTo({ top: 0, behavior: 'smooth' });
  icons();
}

document.addEventListener('click', (e) => {
  const nav = e.target.closest('[data-nav]');
  if (nav) { switchView(nav.dataset.nav); }
});
$('#mobileNav')?.addEventListener('change', (e) => switchView(e.target.value));

// ───────── health ─────────
async function checkHealth() {
  const el = $('#health');
  try {
    const h = await api('/api/health');
    const label = h.llm_provider === 'mock' ? 'offline engine · no keys' : `${h.llm_provider}${h.llm_available ? '' : ' (fallback)'}`;
    el.innerHTML = `<span class="w-2 h-2 rounded-full pulse" style="background:var(--good)"></span> API online · ${esc(label)}`;
  } catch {
    el.innerHTML = `<span class="w-2 h-2 rounded-full" style="background:var(--bad)"></span> API offline`;
  }
}

// ───────── overlay ─────────
const OVERLAY_STEPS = ['Planning your search', 'Researching schemes', 'Checking eligibility', 'Building document checklist', 'Tracking deadlines', 'Writing your roadmap'];
let overlayTimer;
function showOverlay() {
  $('#overlay').style.display = 'flex';
  let i = 0; $('#overlayStep').textContent = OVERLAY_STEPS[0];
  overlayTimer = setInterval(() => { i = (i + 1) % OVERLAY_STEPS.length; $('#overlayStep').textContent = OVERLAY_STEPS[i]; }, 500);
}
function hideOverlay() { clearInterval(overlayTimer); $('#overlay').style.display = 'none'; }

// ───────── profile form ─────────
$('#exampleBtn')?.addEventListener('click', () => {
  const f = $('#profileForm');
  f.name.value = 'Aisha Kumar'; f.age.value = 21; f.gender.value = 'Female'; f.state.value = 'Karnataka';
  f.category.value = 'OBC'; f.education_level.value = 'Undergraduate'; f.field_of_study.value = 'Engineering';
  f.annual_income.value = 300000; f.goals.value = 'Finish B.Tech and later start a company';
  toast('Example profile loaded — hit Save & run', 'info');
});

$('#profileForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = {
    name: fd.get('name'), age: fd.get('age') ? +fd.get('age') : null, gender: fd.get('gender') || null,
    state: fd.get('state') || null, category: fd.get('category') || null,
    education_level: fd.get('education_level') || null, field_of_study: fd.get('field_of_study') || null,
    annual_income: fd.get('annual_income') ? +fd.get('annual_income') : null,
    disability: fd.get('disability') === 'on', goals: fd.get('goals') || null,
  };
  showOverlay();
  try {
    const profile = await api('/api/profiles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    state.profileId = profile.id; state.profile = payload;
    localStorage.setItem('lp_pid', profile.id);
    localStorage.setItem('lp_profile', JSON.stringify(payload));
    await runAgents(true);
    switchView('dashboard');
    toast('LifePilot finished scanning your opportunities', 'good');
  } catch (err) {
    toast('Error: ' + err.message, 'bad');
  } finally { hideOverlay(); }
});

// ───────── run agents ─────────
async function runAgents(celebrate = false) {
  if (!state.profileId) return;
  const data = await api(`/api/agent/run/${state.profileId}`, { method: 'POST' });
  state.run = data;
  state.baseline = { eligible: data.insights.eligible_count, benefit: data.insights.estimated_annual_benefit };
  $('#rerunBtn').classList.remove('hidden'); $('#rerunBtn').classList.add('flex');
  renderAll();
  if (celebrate && data.insights.eligible_count > 0) setTimeout(fireConfetti, 350);
}

$('#rerunBtn')?.addEventListener('click', async () => {
  showOverlay();
  try { await runAgents(true); toast('Refreshed', 'good'); } catch (e) { toast(e.message, 'bad'); } finally { hideOverlay(); }
});

// ───────── render orchestration ─────────
function renderAll() {
  renderDashboard();
  renderDiscover();
  renderDocuments();
  renderActivity();
  seedSimulatorFromProfile();
}

// ───────── DASHBOARD ─────────
function computeReadiness() {
  const docs = state.run?.insights?.master_documents || [];
  const total = docs.length;
  const owned = docs.filter((d) => state.ownedDocs.has(d.document.toLowerCase())).length;
  return { total, owned, pct: total ? Math.round((100 * owned) / total) : 0 };
}

function renderDashboard() {
  if (!state.run) return;
  $('#dashEmpty').classList.add('hidden');
  $('#dashContent').classList.remove('hidden');
  const ins = state.run.insights;

  animateCount($('#heroBenefit'), ins.estimated_annual_benefit);
  $('#heroSub').textContent = `across ${ins.eligible_count} eligible scheme${ins.eligible_count === 1 ? '' : 's'} · ${ins.avg_confidence * 100 | 0}% avg confidence`;

  const rd = computeReadiness();
  setRing($('#readyRing'), $('#readyPct'), rd.pct);
  $('#readySub').textContent = `${rd.owned} of ${rd.total} documents ready`;

  // stat tiles
  const tiles = [
    ['check-circle-2', ins.eligible_count, 'Eligible', 'var(--good)'],
    ['circle-dashed', ins.partial_count, 'Partial', 'var(--warn)'],
    ['door-open', ins.open_count, 'Open now', 'var(--accent-2)'],
    ['alarm-clock', ins.critical_count, 'Closing ≤14d', 'var(--bad)'],
  ];
  $('#statTiles').innerHTML = tiles.map(([ic, val, label, col]) => `
    <div class="glass glass-hover rounded-2xl p-4">
      <div class="flex items-center justify-between">
        <i data-lucide="${ic}" class="w-5 h-5" style="color:${col}"></i>
        <span class="font-display text-3xl font-bold">${val}</span>
      </div>
      <p class="text-xs text-[var(--muted)] mt-1">${label}</p>
    </div>`).join('');

  renderCharts(ins);

  // top pick
  const tp = ins.top_pick;
  $('#topPick').innerHTML = tp ? `
    <div class="flex items-center gap-2 mb-2">
      <span class="chip ${tp.eligible ? 'badge-good' : 'badge-warn'}">${tp.eligible ? 'Top match' : 'Closest match'}</span>
      <span class="text-xs text-[var(--muted)]">${Math.round(tp.score * 100)}% fit</span>
    </div>
    <h3 class="font-display font-bold text-lg leading-snug">${esc(tp.title)}</h3>
    <p class="text-xs text-[var(--muted)] mt-1">${esc(tp.provider || '')}</p>
    <div class="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-[var(--muted)]">
      <span>💰 ${esc(tp.amount || '—')}</span><span>📅 ${esc(tp.deadline || 'see portal')}</span>
    </div>
    <div class="flex gap-2 mt-4">
      ${tp.url ? `<a href="${esc(tp.url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary px-4 py-2 text-xs flex items-center gap-1.5"><i data-lucide="external-link" class="w-3.5 h-3.5"></i> Apply on portal</a>` : ''}
      <button class="btn btn-ghost px-4 py-2 text-xs" data-nav="discover">See all</button>
    </div>` : '<p class="text-sm text-[var(--muted)]">No matches yet.</p>';

  // deadlines
  const open = ins.urgency.filter((u) => u.days_left != null && u.days_left >= 0).slice(0, 6);
  $('#deadlineList').innerHTML = open.length ? open.map((u) => {
    const cls = u.level === 'critical' ? 'badge-bad' : u.level === 'soon' ? 'badge-warn' : 'badge-good';
    return `<div class="flex items-center justify-between gap-3 glass rounded-xl px-3 py-2">
      <div class="min-w-0"><p class="text-xs font-medium truncate">${esc(u.title)}</p><p class="text-[11px] text-[var(--muted)]">${esc(u.deadline)}</p></div>
      <span class="chip ${cls} shrink-0">${u.days_left}d left</span></div>`;
  }).join('') : '<p class="text-xs text-[var(--muted)]">No open deadlines found.</p>';

  icons();
  applyPostEffects();
}

function renderCharts(ins) {
  const grid = getComputedStyle(document.body).getPropertyValue('--muted');
  Chart.defaults.color = '#8b90a6'; Chart.defaults.font.family = 'Inter';

  // mix donut
  state.charts.mix?.destroy();
  state.charts.mix = new Chart($('#chartMix'), {
    type: 'doughnut',
    data: { labels: ['Eligible', 'Partial'], datasets: [{ data: [ins.eligible_count, ins.partial_count], backgroundColor: ['#34d399', '#fbbf24'], borderWidth: 0, hoverOffset: 6 }] },
    options: { cutout: '68%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14 } } } },
  });

  // benefit bar (eligible only)
  const elig = state.run.matches.filter((m) => m.eligible).map((m) => ({ t: m.title, v: parseAmount(m.amount) })).filter((x) => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 6);
  state.charts.benefit?.destroy();
  state.charts.benefit = new Chart($('#chartBenefit'), {
    type: 'bar',
    data: {
      labels: elig.map((x) => x.t.length > 26 ? x.t.slice(0, 24) + '…' : x.t),
      datasets: [{ data: elig.map((x) => x.v), backgroundColor: (c) => { const g = c.chart.ctx.createLinearGradient(0, 0, c.chart.width, 0); g.addColorStop(0, '#7c5cff'); g.addColorStop(1, '#22d3ee'); return g; }, borderRadius: 6, barThickness: 16 }],
    },
    options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(255,255,255,.06)' }, ticks: { callback: (v) => '₹' + (v / 1000) + 'k' } }, y: { grid: { display: false } } } },
  });
}

// ───────── DISCOVER ─────────
const DISCOVER_FILTERS = [['all', 'All'], ['eligible', 'Eligible'], ['partial', 'Partial'], ['open', 'Open now']];
function renderDiscover() {
  const chips = $('#discoverChips');
  chips.innerHTML = DISCOVER_FILTERS.map(([k, l]) => `<span class="chip ${state.discoverFilter === k ? 'active' : ''}" data-filter="${k}">${l}</span>`).join('');
  $$('[data-filter]', chips).forEach((c) => c.addEventListener('click', () => { state.discoverFilter = c.dataset.filter; renderDiscover(); }));
  drawDiscoverGrid();
}

function drawDiscoverGrid() {
  const grid = $('#discoverGrid'), empty = $('#discoverEmpty');
  if (!state.run) { grid.innerHTML = ''; empty.classList.remove('hidden'); return; }
  empty.classList.add('hidden');
  const q = ($('#discoverSearch').value || '').toLowerCase();
  let items = state.run.matches.filter((m) => {
    if (state.discoverFilter === 'eligible' && !m.eligible) return false;
    if (state.discoverFilter === 'partial' && m.eligible) return false;
    if (state.discoverFilter === 'open' && !((daysLeft(m.deadline) ?? -1) >= 0)) return false;
    if (q && !(`${m.title} ${m.provider}`.toLowerCase().includes(q))) return false;
    return true;
  });
  grid.innerHTML = items.map(matchCard).join('') || `<div class="glass rounded-2xl p-6 text-sm text-[var(--muted)] md:col-span-2">No schemes match this filter.</div>`;
  icons();
}

$('#discoverSearch')?.addEventListener('input', drawDiscoverGrid);

function matchCard(m) {
  const dl = daysLeft(m.deadline);
  const badge = m.eligible ? `<span class="chip badge-good">Eligible</span>` : `<span class="chip badge-warn">Partial</span>`;
  const dlTxt = m.deadline ? (dl < 0 ? `<span style="color:var(--bad)">Closed</span>` : `${esc(m.deadline)} · ${dl}d`) : 'See portal';
  const col = m.eligible ? 'var(--good)' : 'var(--warn)';
  const reasons = (m.reasons || []).map((r) => `<li class="flex gap-1.5"><i data-lucide="check" class="w-3.5 h-3.5 mt-0.5" style="color:var(--good)"></i><span>${esc(r)}</span></li>`).join('');
  const unmet = (m.unmet || []).map((r) => `<li class="flex gap-1.5"><i data-lucide="dot" class="w-3.5 h-3.5 mt-0.5" style="color:var(--warn)"></i><span>${esc(r)}</span></li>`).join('');
  const docs = (m.documents || []).map((d) => `<li class="flex gap-1.5 text-[var(--muted)]"><i data-lucide="file" class="w-3.5 h-3.5 mt-0.5"></i>${esc(d)}</li>`).join('');
  const road = (m.roadmap || []).map((s, i) => `<li class="flex gap-2"><span class="w-5 h-5 shrink-0 rounded-full text-[10px] font-bold flex items-center justify-center" style="background:rgba(124,92,255,.2);color:#c4b5fd">${i + 1}</span><span>${esc(s)}</span></li>`).join('');

  return `<div class="glass glass-hover rounded-2xl p-5">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0"><div class="flex items-center gap-2 flex-wrap mb-1">${badge}<span class="text-[11px] text-[var(--muted)]">${Math.round(m.confidence * 100)}% confidence</span></div>
        <h3 class="font-semibold text-sm leading-snug">${esc(m.title)}</h3>
        <p class="text-[11px] text-[var(--muted)] mt-0.5">${esc(m.provider || '')}</p></div>
      <div class="text-right shrink-0"><div class="font-display text-2xl font-bold" style="color:${col}">${Math.round(m.score * 100)}%</div><div class="text-[10px] text-[var(--muted)]">fit</div></div>
    </div>
    <div class="h-1 rounded-full mt-3 overflow-hidden" style="background:rgba(255,255,255,.07)"><div style="width:${Math.round(m.score * 100)}%;height:100%;background:linear-gradient(90deg,#7c5cff,#22d3ee)"></div></div>
    <div class="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-[var(--muted)]"><span>💰 ${esc(m.amount || '—')}</span><span>📅 ${dlTxt}</span></div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3 text-xs">
      ${reasons ? `<div><p class="font-semibold mb-1">Why you qualify</p><ul class="space-y-1">${reasons}</ul></div>` : ''}
      ${unmet ? `<div><p class="font-semibold mb-1">Gaps to check</p><ul class="space-y-1">${unmet}</ul></div>` : ''}
    </div>
    <details class="mt-3">
      <summary class="cursor-pointer text-xs font-semibold flex items-center gap-1" style="color:#a78bfa"><i data-lucide="list-checks" class="w-3.5 h-3.5"></i> Documents & roadmap</summary>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3 text-xs">
        <div><p class="font-semibold mb-1">Documents</p><ul class="space-y-1">${docs}</ul></div>
        <div><p class="font-semibold mb-1">Roadmap</p><ol class="space-y-1.5">${road}</ol></div>
      </div>
    </details>
    ${m.url ? `<a href="${esc(m.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 mt-3 text-xs font-semibold" style="color:#67e8f9">Open official portal <i data-lucide="external-link" class="w-3 h-3"></i></a>` : ''}
  </div>`;
}

// ───────── SIMULATOR ─────────
let simTimer;
function seedSimulatorFromProfile() {
  const p = state.profile; if (!p) return;
  if (p.annual_income != null) { $('#simIncome').value = Math.min(p.annual_income, 1500000); }
  if (p.category) $('#simCategory').value = p.category;
  if (p.education_level) $('#simEducation').value = p.education_level;
  if (p.gender) $('#simGender').value = p.gender;
  if (p.state) $('#simState').value = p.state;
  if (p.field_of_study) $('#simField').value = p.field_of_study;
  $('#simDisability').checked = !!p.disability;
  updateSliderFill(); runSimulation();
}
function updateSliderFill() {
  const s = $('#simIncome'); const pct = (s.value / s.max) * 100; s.style.setProperty('--pct', pct + '%');
  $('#simIncomeLabel').textContent = fmtINR(+s.value);
}
async function runSimulation() {
  const payload = {
    name: 'Simulation', annual_income: +$('#simIncome').value, category: $('#simCategory').value,
    education_level: $('#simEducation').value, gender: $('#simGender').value, state: $('#simState').value,
    field_of_study: $('#simField').value, disability: $('#simDisability').checked, goals: state.profile?.goals || null,
    owned_documents: [],
  };
  try {
    const res = await api('/api/agent/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const ins = res.insights;
    animateCount($('#simEligible'), ins.eligible_count, (n) => Math.round(n));
    animateCount($('#simBenefit'), ins.estimated_annual_benefit);
    const dE = ins.eligible_count - state.baseline.eligible;
    const dB = ins.estimated_annual_benefit - state.baseline.benefit;
    const sign = (x) => (x > 0 ? '+' : '');
    const col = dE > 0 || dB > 0 ? 'var(--good)' : dE < 0 || dB < 0 ? 'var(--bad)' : 'var(--muted)';
    $('#simDelta').style.color = col;
    $('#simDelta').textContent = state.baseline.eligible || state.baseline.benefit ? `${sign(dE)}${dE} · ${sign(dB)}${fmtINR(Math.abs(dB)).replace('₹', dB < 0 ? '-₹' : '₹')}` : '—';
    const elig = res.matches.filter((m) => m.eligible);
    $('#simList').innerHTML = (elig.length ? elig : res.matches.slice(0, 5)).map((m) => `
      <div class="flex items-center justify-between gap-3 glass rounded-xl px-3 py-2">
        <div class="min-w-0"><p class="text-xs font-medium truncate">${esc(m.title)}</p><p class="text-[11px] text-[var(--muted)]">${esc(m.amount || '')}</p></div>
        <span class="chip ${m.eligible ? 'badge-good' : 'badge-warn'} shrink-0">${Math.round(m.score * 100)}%</span></div>`).join('') || '<p class="text-xs text-[var(--muted)]">No eligible schemes for this scenario.</p>';
  } catch (e) { toast(e.message, 'bad'); }
}
['simCategory', 'simEducation', 'simGender', 'simState', 'simField', 'simDisability'].forEach((id) =>
  $('#' + id)?.addEventListener('input', () => { clearTimeout(simTimer); simTimer = setTimeout(runSimulation, 220); }));
$('#simIncome')?.addEventListener('input', () => { updateSliderFill(); clearTimeout(simTimer); simTimer = setTimeout(runSimulation, 220); });

// ───────── ASSISTANT ─────────
const SUGGESTIONS = ['How much can I get?', 'Which schemes am I eligible for?', 'What documents do I need?', 'Show me the deadlines'];
function renderSuggestions() {
  $('#chatSuggest').innerHTML = SUGGESTIONS.map((s) => `<span class="chip" data-suggest="${esc(s)}">${esc(s)}</span>`).join('');
  $$('[data-suggest]').forEach((c) => c.addEventListener('click', () => { $('#chatInput').value = c.dataset.suggest; $('#chatForm').requestSubmit(); }));
}
function addBubble(text, who) {
  const el = document.createElement('div');
  el.className = `bubble ${who}`;
  el.textContent = text;
  $('#chatLog').appendChild(el);
  $('#chatLog').scrollTop = $('#chatLog').scrollHeight;
  return el;
}
$('#chatForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = $('#chatInput').value.trim(); if (!q) return;
  if (!state.profileId) { toast('Create a profile first', 'warn'); switchView('profile'); return; }
  addBubble(q, 'user'); $('#chatInput').value = '';
  const typing = addBubble('…', 'bot');
  try {
    const res = await api('/api/agent/assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_id: state.profileId, question: q }) });
    typing.textContent = res.answer;
  } catch (err) { typing.textContent = 'Sorry — ' + err.message; }
  $('#chatLog').scrollTop = $('#chatLog').scrollHeight;
});

// ───────── DOCUMENTS ─────────
function renderDocuments() {
  const list = $('#docList');
  const docs = state.run?.insights?.master_documents || [];
  if (!docs.length) { list.innerHTML = '<p class="text-xs text-[var(--muted)]">Run LifePilot from your profile to build a checklist.</p>'; updateDocRing(); return; }
  list.innerHTML = docs.map((d) => {
    const key = d.document.toLowerCase(); const owned = state.ownedDocs.has(key);
    return `<label class="flex items-center gap-3 glass rounded-xl px-3 py-2.5 cursor-pointer glass-hover">
      <input type="checkbox" class="accent-[#7c5cff] w-4 h-4" data-doc="${esc(key)}" ${owned ? 'checked' : ''} />
      <div class="flex-1 min-w-0"><p class="text-sm ${owned ? 'line-through text-[var(--muted)]' : ''}">${esc(d.document)}</p>
      <p class="text-[11px] text-[var(--muted)]">Needed by ${d.used_by} scheme${d.used_by === 1 ? '' : 's'}</p></div>
      ${owned ? '<i data-lucide="check-circle-2" class="w-4 h-4" style="color:var(--good)"></i>' : ''}
    </label>`;
  }).join('');
  $$('[data-doc]', list).forEach((cb) => cb.addEventListener('change', () => {
    cb.checked ? state.ownedDocs.add(cb.dataset.doc) : state.ownedDocs.delete(cb.dataset.doc);
    saveDocs(); renderDocuments(); updateDocRing();
    const rd = computeReadiness(); setRing($('#readyRing'), $('#readyPct'), rd.pct); $('#readySub').textContent = `${rd.owned} of ${rd.total} documents ready`;
  }));
  updateDocRing();
  icons();
}
function updateDocRing() {
  const rd = computeReadiness();
  setRing($('#docRing'), $('#docPct'), rd.pct);
  $('#docCount').textContent = `${rd.owned} of ${rd.total} collected`;
}

// ───────── ACTIVITY ─────────
const AGENT_ICON = { PlannerAgent: 'route', ResearchAgent: 'telescope', EligibilityAgent: 'scale', DocumentAgent: 'folder-check', TrackingAgent: 'alarm-clock', RoadmapAgent: 'map', InsightAgent: 'sparkles' };
function renderActivity() {
  const list = $('#activityList');
  if (!state.run) { list.innerHTML = '<p class="text-xs text-[var(--muted)]">No agent runs yet.</p>'; return; }
  list.innerHTML = `<div class="absolute left-[10px] top-1 bottom-1 w-px" style="background:linear-gradient(var(--accent),transparent)"></div>` +
    state.run.logs.map((l) => {
      const conf = Math.round((l.confidence || 0) * 100);
      return `<div class="relative">
        <div class="absolute -left-[22px] top-1 w-5 h-5 rounded-full glass flex items-center justify-center"><i data-lucide="${AGENT_ICON[l.agent] || 'bot'}" class="w-3 h-3" style="color:#a78bfa"></i></div>
        <div class="glass rounded-xl p-3">
          <div class="flex items-center justify-between"><span class="text-xs font-bold">${esc(l.agent)}</span><span class="text-[11px] text-[var(--muted)]">${conf}%</span></div>
          <p class="text-xs text-[var(--muted)] mt-1">${esc(l.message)}</p>
          <div class="h-1 rounded-full mt-2 overflow-hidden" style="background:rgba(255,255,255,.07)"><div style="width:${conf}%;height:100%;background:linear-gradient(90deg,#7c5cff,#22d3ee)"></div></div>
        </div></div>`;
    }).join('');
  icons();
}

// ───────── premium UX: confetti, tilt, magnetic ─────────
function fireConfetti() {
  const c = document.createElement('canvas'); c.id = 'confetti'; document.body.appendChild(c);
  const ctx = c.getContext('2d'); const W = c.width = innerWidth, H = c.height = innerHeight;
  const colors = ['#7c5cff', '#22d3ee', '#f472b6', '#34d399', '#fbbf24'];
  const parts = Array.from({ length: 150 }, (_, i) => ({
    x: W / 2 + (Math.random() - .5) * 260, y: H * 0.28,
    vx: (Math.random() - .5) * 11, vy: Math.random() * -9 - 4,
    r: Math.random() * 6 + 3, col: colors[i % colors.length],
    rot: Math.random() * 6, vr: (Math.random() - .5) * .5, life: 0,
  }));
  const t0 = performance.now();
  function frame(t) {
    ctx.clearRect(0, 0, W, H); let alive = false;
    for (const p of parts) {
      p.vy += 0.25; p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.life += 0.008;
      if (p.y < H + 30 && p.life < 1) alive = true;
      ctx.save(); ctx.globalAlpha = Math.max(0, 1 - p.life); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
      ctx.fillStyle = p.col; ctx.fillRect(-p.r / 2, -p.r / 2, p.r, p.r * 0.6); ctx.restore();
    }
    if (alive && t - t0 < 2800) requestAnimationFrame(frame); else c.remove();
  }
  requestAnimationFrame(frame);
}

function setupTilt() {
  $$('[data-tilt]').forEach((el) => {
    if (el._tilt) return; el._tilt = true; el.classList.add('tilt');
    el.addEventListener('mousemove', (e) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - .5, py = (e.clientY - r.top) / r.height - .5;
      el.style.transform = `perspective(900px) rotateX(${(-py * 4).toFixed(2)}deg) rotateY(${(px * 5).toFixed(2)}deg)`;
    });
    el.addEventListener('mouseleave', () => { el.style.transform = ''; });
  });
}

function setupMagnetic() {
  $$('.btn-primary').forEach((b) => {
    if (b._mag) return; b._mag = true;
    b.addEventListener('mousemove', (e) => {
      const r = b.getBoundingClientRect();
      b.style.transform = `translate(${((e.clientX - r.left) / r.width - .5) * 6}px, ${((e.clientY - r.top) / r.height - .5) * 6}px)`;
    });
    b.addEventListener('mouseleave', () => { b.style.transform = ''; });
  });
}

function applyPostEffects() { setupTilt(); setupMagnetic(); }

// ───────── calendar (.ics) + print action plan ─────────
function downloadCalendar() {
  if (!state.profileId) { toast('Create a profile first', 'warn'); switchView('profile'); return; }
  const a = document.createElement('a');
  a.href = `/api/agent/calendar/${state.profileId}`; a.download = 'lifepilot-deadlines.ics';
  document.body.appendChild(a); a.click(); a.remove();
  toast('Calendar file downloading — import it into Google/Apple/Outlook', 'good');
}

function printActionPlan() {
  if (!state.run) { toast('Run LifePilot first', 'warn'); switchView('profile'); return; }
  const ins = state.run.insights;
  const elig = state.run.matches.filter((m) => m.eligible);
  const docs = ins.master_documents || [];
  const scheme = (m) => `
    <div class="p-scheme">
      <strong>${esc(m.title)}</strong> — <span class="p-meta">${esc(m.amount || '')}</span><br/>
      <span class="p-muted">${esc(m.provider || '')} · Deadline: ${esc(m.deadline || 'see portal')} · ${esc(m.url || '')}</span>
      <div><em>Roadmap:</em><ol>${(m.roadmap || []).map((s) => `<li>${esc(s)}</li>`).join('')}</ol></div>
    </div>`;
  $('#printArea').innerHTML = `
    <h1>LifePilot — Personalised Action Plan</h1>
    <div class="p-muted">Prepared for ${esc(state.profile?.name || 'you')} · Generated ${new Date().toLocaleDateString()}</div>
    <div class="p-meta" style="margin-top:8px">Estimated potential value: <strong>${esc(ins.estimated_benefit_label)}/year</strong>
      · ${ins.eligible_count} eligible scheme(s) · Readiness ${computeReadiness().pct}%</div>
    <h2>Eligible opportunities (${elig.length})</h2>
    ${elig.map(scheme).join('') || '<p class="p-muted">No fully-eligible schemes yet.</p>'}
    <h2>Combined document checklist</h2>
    <ul>${docs.map((d) => `<li>${esc(d.document)} — needed by ${d.used_by} scheme(s)</li>`).join('')}</ul>
    <div class="p-muted" style="margin-top:14px">Generated locally by LifePilot. No data left your device.</div>`;
  window.print();
}

$('#calBtn')?.addEventListener('click', downloadCalendar);
$('#printBtn')?.addEventListener('click', printActionPlan);

// ───────── command palette ─────────
const PALETTE = [
  { icon: 'layout-dashboard', label: 'Go to Dashboard', keys: 'home overview', run: () => switchView('dashboard') },
  { icon: 'compass', label: 'Go to Discover', keys: 'opportunities schemes', run: () => switchView('discover') },
  { icon: 'sliders-horizontal', label: 'Open What-If Simulator', keys: 'simulate income', run: () => switchView('simulator') },
  { icon: 'sparkles', label: 'Open AI Assistant', keys: 'chat ask', run: () => switchView('assistant') },
  { icon: 'folder-check', label: 'Go to Documents', keys: 'checklist readiness', run: () => switchView('documents') },
  { icon: 'activity', label: 'Go to Agent Activity', keys: 'logs agents', run: () => switchView('activity') },
  { icon: 'user-round-cog', label: 'Edit Profile', keys: 'settings profile', run: () => switchView('profile') },
  { icon: 'refresh-cw', label: 'Re-run agents', keys: 'refresh update', run: () => $('#rerunBtn').click() },
  { icon: 'calendar-plus', label: 'Add deadlines to calendar', keys: 'ics reminder', run: downloadCalendar },
  { icon: 'printer', label: 'Print action plan', keys: 'pdf export', run: printActionPlan },
  { icon: 'wand-2', label: 'Load example profile', keys: 'demo sample', run: () => { switchView('profile'); $('#exampleBtn').click(); } },
];
let paletteIdx = 0, paletteItems = [];
function openPalette() {
  $('#palette').style.display = 'block'; const inp = $('#paletteInput'); inp.value = ''; renderPalette(''); inp.focus();
}
function closePalette() { $('#palette').style.display = 'none'; }
function renderPalette(q) {
  q = q.toLowerCase();
  paletteItems = PALETTE.filter((p) => !q || (p.label + ' ' + p.keys).toLowerCase().includes(q));
  paletteIdx = 0;
  $('#paletteList').innerHTML = paletteItems.map((p, i) => `
    <div class="palette-item ${i === 0 ? 'active' : ''}" data-i="${i}">
      <i data-lucide="${p.icon}" class="w-4 h-4"></i><span>${esc(p.label)}</span>
    </div>`).join('') || '<div class="palette-item">No matching commands</div>';
  icons();
  $$('#paletteList .palette-item[data-i]').forEach((el) => {
    el.addEventListener('click', () => { paletteItems[+el.dataset.i]?.run(); closePalette(); });
    el.addEventListener('mousemove', () => { paletteIdx = +el.dataset.i; highlightPalette(); });
  });
}
function highlightPalette() {
  $$('#paletteList .palette-item[data-i]').forEach((el) => el.classList.toggle('active', +el.dataset.i === paletteIdx));
}
$('#paletteInput')?.addEventListener('input', (e) => renderPalette(e.target.value));
$('#paletteBtn')?.addEventListener('click', openPalette);
$('#palette')?.addEventListener('click', (e) => { if (e.target.id === 'palette') closePalette(); });
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#palette').style.display === 'block' ? closePalette() : openPalette(); return; }
  if ($('#palette').style.display !== 'block') return;
  if (e.key === 'Escape') closePalette();
  else if (e.key === 'ArrowDown') { e.preventDefault(); paletteIdx = Math.min(paletteIdx + 1, paletteItems.length - 1); highlightPalette(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); paletteIdx = Math.max(paletteIdx - 1, 0); highlightPalette(); }
  else if (e.key === 'Enter') { paletteItems[paletteIdx]?.run(); closePalette(); }
});

// ───────── boot ─────────
async function boot() {
  icons();
  renderSuggestions();
  updateSliderFill();
  setupMagnetic();
  checkHealth();
  if (state.profileId) {
    showOverlay();
    try { await runAgents(); addBubble(`Hi! I'm your LifePilot assistant. Ask me anything about your ${state.run.insights.eligible_count} eligible schemes.`, 'bot'); }
    catch { toast('Could not restore last session', 'warn'); localStorage.removeItem('lp_pid'); }
    finally { hideOverlay(); }
  } else {
    addBubble("Hi! I'm your LifePilot assistant. Create a profile and I'll help you claim every benefit you're entitled to.", 'bot');
  }
}
boot();
