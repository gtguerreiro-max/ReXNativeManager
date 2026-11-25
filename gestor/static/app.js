'use strict';
// Gestor ReXNative: a página (sem framework). Fala com a API em /api.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const jsq = s => esc(JSON.stringify(String(s ?? '')));
const mcChip = mc => mc == null ? '' : `<span class="chip ${mc >= 75 ? 'ok' : mc >= 50 ? 'warn' : 'bad'}" title="Metacritic score (Xbox 360)">${mc}</span>`;
const genreTxt = i => i && i.genres && i.genres.length ? i.genres.slice(0, 2).join(', ') : '';
const gb = n => n == null ? '-' : (n >= 1e9 ? (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + ' GB' : (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + ' MB');
const when = s => s ? new Date(typeof s === 'number' ? s * 1000 : s).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) : '-';

async function api(path, opts = {}) {
  const o = { headers: {} };
  if (opts.body !== undefined) {
    o.method = opts.method || 'POST';
    o.headers['Content-Type'] = 'application/json';
    o.body = JSON.stringify(opts.body);
  } else if (opts.method) o.method = opts.method;
  if (o.method && o.method !== 'GET') o.headers['X-Gestor'] = '1';
  const r = await fetch(path, o);
  const txt = await r.text();
  let data;
  try { data = JSON.parse(txt); } catch { data = { detail: txt }; }
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

function toast(msg, bad, ms) {
  const t = document.createElement('div');
  t.className = 'toast' + (bad ? ' bad' : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms || (bad ? 7000 : 3500));
}
const fail = e => toast(e.message || String(e), true);

// -- a sessão no GitHub (obrigatória) ---------------------------------------------------------------
// Sem ela a app só mostra isto: entrar com o GitHub CLI (um código para escrever em
// github.com/login/device). A app nunca vê a palavra-passe.
let ghTimer = null;
async function githubGate() {
  let g;
  try { g = await (await fetch('/api/github')).json(); } catch (e) { return; }
  if (g.logged_in) { const el = $('#ghgate'); if (el) { el.remove(); location.reload(); } return; }
  let el = $('#ghgate');
  if (!el) {
    el = document.createElement('div');
    el.id = 'ghgate';
    el.style.cssText = 'position:fixed;inset:0;background:#0b0f0ce6;z-index:999;display:flex;align-items:center;justify-content:center';
    document.body.appendChild(el);
  }
  const f = g.login_flow || {};
  el.innerHTML = `<div class="panel" style="max-width:560px;padding:24px">
    <h2 style="margin-top:0">Sign in with GitHub</h2>
    <p>The ReXNative Manager needs a GitHub account: the fixes the assistant makes to ReXNative are shared as pull requests
      from your account, and your commits carry your GitHub name. The app never sees your password.</p>
    ${!g.installed ? `<p style="color:#f2c46b">The GitHub CLI is not installed. In PowerShell: <code>winget install GitHub.cli</code>, then come back.</p>` : ''}
    ${f.state === 'waiting' && f.code ? `<p>Open <a href="${esc(f.url)}" target="_blank">${esc(f.url)}</a> and enter this code:</p>
      <p style="font-size:30px;letter-spacing:4px;font-weight:700">${esc(f.code)}</p><p class="small muted">Waiting for GitHub…</p>` : ''}
    ${f.state === 'failed' ? `<p style="color:#ff9b94">${esc(f.error || 'the sign-in failed')}</p>` : ''}
    <div class="row" style="gap:8px;margin-top:12px">
      ${g.installed && f.state !== 'waiting' ? '<button class="b p" onclick="githubLogin()">Sign in with GitHub</button>' : ''}
      <button class="b" onclick="githubGate()">Check again</button></div></div>`;
  clearTimeout(ghTimer);
  ghTimer = setTimeout(githubGate, f.state === 'waiting' ? 2000 : 15000);
}
async function githubLogin() {
  try { await fetch('/api/github/login', { method: 'POST', headers: { 'X-Gestor': '1' } }); } catch (e) { /* */ }
  githubGate();
}
githubGate();

function confirmBox(html, okLabel = 'Confirm', danger = false) {
  return new Promise(res => {
    const d = $('#dlg');
    $('#dlgbody').innerHTML = html + `<div class="row" style="margin-top:16px;justify-content:flex-end">
      <button class="b" id="dlgno">Cancel</button><button class="b ${danger ? 'd' : 'p'}" id="dlgok">${esc(okLabel)}</button></div>`;
    d.showModal();
    $('#dlgno').onclick = () => { d.close(); res(false); };
    $('#dlgok').onclick = () => { d.close(); res(true); };
  });
}

// -- separadores ---------------------------------------------------------------------------------
let tab = 'games';
const loaded = {};
document.querySelectorAll('nav button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
function showTab(t) {
  tab = t;
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  document.querySelectorAll('section.tab').forEach(s => s.classList.toggle('on', s.id === 'tab-' + t));
  if (t === 'games') loadGames();
  if (t === 'catalog' && !loaded.catalog) { loadCatalog(false); loadDownloads(); }
  if (t === 'deck') { loadConn(); loadDeck(!loaded.deck); }
  if (t === 'jobs') loadJobs();
  if (t === 'settings') loadSettings();
  if (t === 'compat') loadCompat();
  if (t === 'storage') loadStorage();
  if (t === 'log') loadLog();
  else logBadge();
}

// -- estado no cabeçalho -------------------------------------------------------------------------
let active = [];
async function overview() {
  try {
    const o = await api('/api/overview');
    active = o.active;
    const n = o.active.length;
    const jc = $('#jobcount');
    jc.hidden = !n; jc.textContent = n;
    const dk = o.deck || {};
    const w = dk.watch || {};
    const d = o.disks.work_dir;
    $('#status').innerHTML = `<a href="#" onclick="showTab('jobs');return false" class="${n ? 'chip warn' : 'muted'}">${n ? n + (n === 1 ? ' job running' : ' jobs running') : 'no jobs'}</a>` +
      `<span>D: ${d.free_gb != null ? d.free_gb + ' GB free' : '?'}</span>` +
      `<a href="#" onclick="showTab('deck');return false" class="chip ${w.online ? 'ok' : w.online === false ? 'bad' : ''}" title="${esc(w.host || '')} ${w.since ? '· since ' + when(w.since) : ''}">Deck ${w.online ? 'online' : w.online === false ? 'offline' : '...'}</a>`;
    if (tab === 'jobs') loadJobs(true);
    if (tab === 'catalog') updateCatalogProgress();
    if (tab === 'deck') {
      // O Deck apareceu ou desapareceu, ou a lista foi lida de novo pelo vigia.
      const sig = w.online + '|' + dk.at + '|' + (dk.setup && dk.setup.running);
      if (sig !== lastDeckSig) { if (lastDeckSig !== null) { loadDeck(false); loadConn(); } lastDeckSig = sig; }
      else if (dk.setup && dk.setup.running) renderSetupTimer(dk.setup);
    }
  } catch (e) { $('#status').textContent = 'the app is not responding'; }
}
setInterval(overview, 3000);

// -- versão da app ---------------------------------------------------------------------------------
// A versão a correr no cabeçalho; uma mais nova no disco (um commit por reiniciar) ou no GitHub
// aparece a amarelo, e o diálogo diz o que muda e tem Atualizar / Reiniciar (quando nenhuma tarefa
// estiver a correr).
let ver = null;
let pageVer = null;  // the version whose code this page runs (the first answer after it loaded)
async function versionCheck(fetch) {
  try { ver = await api('/api/version' + (fetch ? '?fetch=true' : '')); } catch (e) { return; }
  if (!pageVer) pageVer = ver.running;
  // The app restarted into another version: this page still runs the old one's code (new options
  // never showed until a reload by hand). It reloads, back where it was.
  if (ver.running !== pageVer) return reloadForUpdate();
  const el = $('#ver');
  const next = ver.restart_needed ? ver.disk : ver.update_available ? ver.remote : null;
  el.textContent = 'v' + ver.running + (ver.restart.pending ? ' · restarting when the running jobs finish' : next ? ' · v' + next + ' available' : '');
  el.className = 'chip ' + (ver.restart.pending ? 'info' : next ? 'warn' : '');
  let seen = null;
  try { seen = localStorage.getItem('gestor-seen-version'); } catch (e) { /* */ }
  if (seen !== ver.running) {
    try { localStorage.setItem('gestor-seen-version', ver.running); } catch (e) { /* */ }
    if (seen) toast(`Updated to v${ver.running}: click the version at the top to see what changed`);
  }
}
// Not while something is being typed, a dialog is open or a text was changed and not saved: then
// as soon as that is done (checked every 5 s).
function typingNow() {
  const a = document.activeElement;
  if (a && (a.tagName === 'TEXTAREA' || a.isContentEditable ||
            (a.tagName === 'INPUT' && !['checkbox', 'radio', 'button', 'submit'].includes(a.type)))) return true;
  if ([...document.querySelectorAll('dialog')].some(d => d.open)) return true;
  return [...document.querySelectorAll('textarea')].some(t => t.value !== t.defaultValue);
}
let reloadWait = null;
function reloadForUpdate() {
  if (typingNow()) {
    if (!reloadWait) {
      toast(`Updated to v${ver.running}: the page reloads as soon as you finish here`);
      reloadWait = setInterval(() => { if (!typingNow()) reloadForUpdate(); }, 5000);
    }
    return;
  }
  try {
    sessionStorage.setItem('gestor-restore', JSON.stringify(
      { tab, slug: cur && cur.slug, sub: curSub, job: jobView, back: jobBack }));
  } catch (e) { /* */ }
  location.reload();
}
function changesHtml(changes, from) {
  return (changes || []).map(([v, date, items]) => `<div style="margin:0 0 12px"><b>v${esc(v)}</b> <span class="small muted">${esc(date)}</span>
    ${verKey(v) > verKey(from) ? '<span class="chip warn">new</span>' : v === from ? '<span class="chip ok">running</span>' : ''}
    <ul style="margin:6px 0 0;padding-left:20px">${items.map(i => `<li class="small">${esc(i)}</li>`).join('')}</ul></div>`).join('');
}
const verKey = v => String(v || '0').split('.').map(n => parseInt(n, 10) || 0).reduce((a, n) => a * 1000 + n, 0);
async function openVersion() {
  await versionCheck(true);
  if (!ver) return;
  const v = ver;
  const kit = v.kit || {}, pl = v.plugin || {};
  const lines = [
    `Running: <b>v${esc(v.running)}</b>` + (v.restart_needed ? ` · on disk: <b>v${esc(v.disk)}</b> (restart to use it)` : ''),
    v.remote ? `GitHub: <b>v${esc(v.remote)}</b>${v.remote_behind ? ` (${v.remote_behind} commit(s) newer than this folder)` : ' (this folder is up to date)'}` : `GitHub: ${esc(v.remote_error || (v.remote_at ? 'no version there yet' : 'not checked yet'))}`,
    `Deck launcher: ${kit.on_deck ? 'v' + esc(kit.on_deck) : 'not installed by the app'}${kit.outdated ? ` · <b>v${esc(kit.latest)}</b> available (Settings › Deck mode › Reinstall, or Update in Deck mode)` : ''}`,
    `Decky plugin on the Deck: ${pl.on_deck ? 'v' + esc(pl.on_deck) + (pl.seen_at ? ' (seen ' + when(new Date(pl.seen_at * 1000).toISOString()) + ')' : '') : 'not seen yet'}${pl.outdated ? ` · <b>v${esc(pl.latest)}</b> available: install it in Decky from ${esc(location.origin.replace('127.0.0.1', 'this PC'))}/static/deck-plugin.zip` : ''}`,
  ];
  const d = $('#dlg');
  $('#dlgbody').innerHTML = `<h3 style="margin-top:0">ReXNative Manager v${esc(v.running)}</h3>
    ${lines.map(l => `<p class="small" style="margin:4px 0">${l}</p>`).join('')}
    ${v.restart.pending ? `<p class="chip info">Restarting when the running jobs finish (${esc(v.restart.reason || '')})</p>
      <p class="small muted">${(v.restart.waits_for || []).length ? 'Waiting for: ' + esc(v.restart.waits_for.join(', ')) + '. ' : ''}${v.restart.later ? esc(String(v.restart.later)) + ' queued job(s) continue after the restart.' : ''}</p>` : ''}
    <h4>What changed</h4><div style="max-height:46vh;overflow:auto">${changesHtml(v.changes, v.running)}</div>
    <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px">
      <a class="small" href="/api/server/log" target="_blank" title="Errors and warnings the app wrote (logs/server.log)" style="margin-right:auto">Server log</a>
      <button class="b" id="vclose">Close</button>
      ${v.update_available ? '<button class="b p" id="vupd">Update from GitHub and restart</button>' : ''}
      ${v.restart_needed && !v.update_available ? '<button class="b p" id="vrst">Restart (after the running jobs)</button>' : ''}
    </div>`;
  d.showModal();
  $('#vclose').onclick = () => d.close();
  if ($('#vupd')) $('#vupd').onclick = async () => { try { const r = await api('/api/version/update', { body: {} }); toast(r.message + (r.restart.pending ? ': restarting when the running jobs finish' : '')); } catch (e) { fail(e); } d.close(); versionCheck(); };
  if ($('#vrst')) $('#vrst').onclick = async () => { try { await api('/api/version/restart', { body: {} }); toast('Restarting when the running jobs finish; queued jobs continue afterwards'); } catch (e) { fail(e); } d.close(); versionCheck(); };
}
versionCheck();
setInterval(() => versionCheck(), 60000);
// Depois de reiniciar, a página volta a ligar-se sozinha (overview falha uns segundos).

// == Compatibilidade ===========================================================================
let compatRows = [], compatSort = { k: 'title', dir: 1 };
const CMPV = { iguais: 'same', nativo_com_erros: 'NATIVE ERRORS', brilho_diferente: 'brightness differs', cenas_diferentes: 'different moments',
  classico_com_erros: 'classic wrong', inconclusivo: 'inconclusive' };
const DPCV = { iguais: 'fine', deck_com_erros: 'ERRORS', cenas_diferentes: 'different moments', inconclusivo: 'inconclusive' };
const COLS = [
  ['title', 'Game', g => g.title],
  ['built_at', 'Built', g => g.built_at || 0, g => g.built ? when(new Date(g.built_at * 1000).toISOString()) : 'not built'],
  ['fresh', 'Fixes', g => g.fresh ? (g.fresh.state === 'atual' ? 0 : g.fresh.missing_count || 1) : -1,
    g => !g.fresh ? '-' : g.fresh.state === 'atual' ? 'up to date' : `${g.fresh.missing_count || 0} missing${g.fresh.sdk_changed ? ' + SDK' : ''}`],
  ['boot', 'Boot', g => g.boot ? (g.boot.ok ? (g.boot.fps || 1) : -1) : -2,
    g => !g.boot ? '-' : g.boot.ok ? `runs${g.boot.fps ? ' · ' + g.boot.fps + ' FPS' : ''}${g.boot.classic_fallback ? ' (classic)' : ''}` : 'FAILS'],
  ['compare', 'Native vs classic', g => g.compare || '', g => CMPV[g.compare] || g.compare || '-'],
  ['deckpc', 'Deck settings', g => g.deckpc || '', g => DPCV[g.deckpc] || g.deckpc || '-'],
  ['classic', 'Renderer PC / Deck', g => (g.classic ? 1 : 0) + (g.classic_deck ? 2 : 0), g => `${g.classic ? 'classic' : 'native'} / ${g.classic_deck ? 'classic' : 'native'}`],
  ['on_deck', 'On Deck', g => g.on_deck ? 1 : 0, g => g.on_deck ? 'yes' : ''],
  ['xdk', 'XDK', g => g.xdk || '', g => g.xdk || '-'],
  ['mc', 'Metacritic', g => g.mc || 0, g => g.mc || ''],
];
async function loadCompat() {
  try { compatRows = (await api('/api/compat')).games; } catch (e) { return fail(e); }
  renderCompat();
}
function compatShown() {
  const q = ($('#cfilter').value || '').toLowerCase();
  const col = COLS.find(c => c[0] === compatSort.k) || COLS[0];
  return compatRows.filter(g => !q || (g.title || '').toLowerCase().includes(q)).sort((a, b) => {
    const x = col[2](a), y = col[2](b);
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * compatSort.dir;
  });
}
function renderCompat() {
  const rows = compatShown();
  const cell = (c, g) => esc(String((c[3] || c[2])(g) ?? ''));
  const bad = g => (g.boot && !g.boot.ok) || g.compare === 'nativo_com_erros' || g.deckpc === 'deck_com_erros';
  $('#compatlist').innerHTML = `<table class="compat"><tr>${COLS.map(c => `<th style="cursor:pointer" onclick="sortCompat('${c[0]}')">${esc(c[1])}${compatSort.k === c[0] ? (compatSort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr>
    ${rows.map(g => `<tr style="${bad(g) ? 'color:#ffb3ad' : ''}">${COLS.map(c => `<td>${c[0] === 'title' ? `<a href="#" onclick="openGame('${esc(g.slug)}');return false">${cell(c, g)}</a>` : cell(c, g)}</td>`).join('')}</tr>`).join('')}</table>
    <p class="small muted">${rows.length} of ${compatRows.length} games</p>`;
}
function sortCompat(k) { compatSort = { k, dir: compatSort.k === k ? -compatSort.dir : 1 }; renderCompat(); }
$('#cfilter').oninput = renderCompat;
function compatCsv() {
  const q = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  const text = [COLS.map(c => q(c[1])).join(',')].concat(compatShown().map(g => COLS.map(c => q((c[3] || c[2])(g))).join(','))).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  a.download = 'rexnative-compatibility.csv';
  a.click();
}

// == Espaço ====================================================================================
let diskData = null;
async function loadStorage() {
  try { diskData = await api('/api/disk'); } catch (e) { return fail(e); }
  const d = diskData;
  $('#drives').innerHTML = d.drives.map(x => `<span class="chip ${x.free < 50e9 ? 'warn' : ''}">${esc(x.drive)} ${gb(x.free)} free of ${gb(x.total)}</span>`).join(' ');
  const meas = d.work.filter(g => g.total != null);
  $('#diskwhen').textContent = meas.length ? `measured ${when(new Date(Math.max(...meas.map(g => g.at)) * 1000).toISOString())} · ${gb(meas.reduce((a, g) => a + g.total, 0))} in ${meas.length} folder(s)` : 'not measured yet';
  const ws = d.work.slice().sort((a, b) => (b.total || 0) - (a.total || 0));
  const v = n => n == null ? '-' : gb(n);
  $('#disklist').innerHTML = `<table class="compat"><tr><th>Game</th><th>Total</th><th>Game files</th><th>Archive copy</th><th>Build</th><th>Run</th><th>Other</th><th>On Deck</th></tr>
    ${ws.map(g => `<tr><td><a href="#" onclick="openGame('${esc(g.slug)}');return false">${esc(g.title)}</a></td><td><b>${v(g.total)}</b></td><td>${v(g.game)}</td><td>${v(g.archive)}</td><td>${v(g.build)}</td><td>${v(g.run)}</td><td>${v(g.other)}</td><td>${g.on_deck ? 'yes' : ''}</td></tr>`).join('')}</table>
    <p class="small muted">Game files: the extracted game (game-data) and its title update. Archive copy: the archive kept inside the game folder. Build: the generated code and the build files.</p>`;
  const fs = d.downloads.files.slice().sort((a, b) => b.size - a.size);
  const prep = fs.filter(f => f.prepared);
  $('#dllist').innerHTML = `<div class="row" style="margin-bottom:8px"><span class="muted small">${esc(d.downloads.dir)} · ${fs.length} file(s), ${gb(fs.reduce((a, f) => a + f.size, 0))}</span>
      ${prep.length ? `<button class="b d" onclick="deletePrepared(${prep.length}, ${prep.reduce((a, f) => a + f.size, 0)})">Delete the ${prep.length} archive(s) already prepared (${gb(prep.reduce((a, f) => a + f.size, 0))})</button>` : ''}</div>
    <table class="compat"><tr><th>Archive</th><th>Size</th><th>Prepared</th></tr>
    ${fs.map(f => `<tr><td>${esc(f.name)}</td><td>${gb(f.size)}</td><td>${f.prepared ? 'yes' : ''}</td></tr>`).join('')}</table>`;
}
async function diskScan() {
  try { const j = await api('/api/disk/scan', { body: {} }); toast('Measuring the game folders (it takes a minute or two)'); openJob(j.id); } catch (e) { fail(e); }
}
async function deletePrepared(n, size) {
  if (!await confirmBox(`<h3 style="margin-top:0">Delete ${n} downloaded archive(s)?</h3>
    <p>They free ${gb(size)}. Those games are already prepared: the extracted game stays in its folder and nothing changes on the Deck.
      Preparing one of them again from scratch would download its archive again.</p>`, 'Delete', true)) return;
  try { const r = await api('/api/downloads/delete-prepared', { body: { confirm: n } }); toast(`Deleted ${r.deleted.length} archive(s), ${gb(r.freed)} freed`); } catch (e) { fail(e); }
  loadStorage();
}

// == Os meus jogos ==============================================================================
let gamesData = [];
async function loadGames() {
  try {
    const r = await api('/api/games');
    gamesData = r.games;
    $('#groots').textContent = 'Folders: ' + r.roots.join(' · ') + ' — ' + r.games.length + ' games';
    renderGames();
  } catch (e) { fail(e); }
}
$('#gfilter').oninput = renderGames;
$('#gsort').onchange = renderGames;
function gameBadges(g) {
  const b = [];
  if (g.unsupported) b.push(`<span class="chip warn" title="Not supported yet: on the roadmap">${esc(g.unsupported)} (later)</span>`);
  if (g.error) b.push(`<span class="chip bad">error</span>`);
  b.push(g.built ? `<span class="chip ok">built</span>` : `<span class="chip warn">${g.prepared ? 'not built' : 'not prepared'}</span>`);
  if (g.boot) b.push(!g.boot.ok ? `<span class="chip bad">boot failed</span>`
    : `<span class="chip ok" title="${esc(g.boot.frames + ' frames, ' + g.boot.frame_ms + ' ms')}">boots</span>`);
  const cv = g.compare && !g.compare.stale && g.compare.verdict;
  if (cv === 'nativo_com_erros') b.push(`<span class="chip bad" title="${esc(g.compare.summary || '')}">native has errors</span>`);
  else if (cv === 'iguais') b.push(`<span class="chip ok" title="${esc(g.compare.summary || '')}">native = classic</span>`);
  else if (cv === 'brilho_diferente') b.push(`<span class="chip warn" title="${esc(g.compare.summary || '')}">different brightness</span>`);
  if (g.deckpc && g.deckpc.verdict === 'deck_com_erros') b.push(`<span class="chip bad" title="${esc(g.deckpc.summary || '')}">Deck: errors</span>`);
  else if (g.deckpc && g.deckpc.verdict === 'iguais') b.push(`<span class="chip ok" title="${esc(g.deckpc.summary || '')}">Deck: ok</span>`);
  if (g.boot && g.boot.ok && g.boot.suspicious && !cv) b.push(`<span class="chip warn" title="The test capture is ${esc(g.boot.suspicious)}">suspicious image</span>`);
  if (g.boot && g.boot.classic_fallback) b.push(`<span class="chip warn" title="${esc('The native renderer failed and no fix was found: ' + (g.boot.native_error || ''))}">classic (native failed)</span>`);
  else if (g.classic && (g.classic.pc || g.classic.deck)) b.push(`<span class="chip" title="Classic renderer (ReXGlue's)">classic${g.classic.pc && g.classic.deck ? '' : g.classic.pc ? ' on PC' : ' on Deck'}</span>`);
  if (g.deck) b.push(`<span class="chip info">Deck${g.deck.where === 'sd' ? ' (SD)' : ''}</span>`);
  if (g.title_update) b.push(`<span class="chip">TU ${g.title_update}</span>`);
  if (g.dlc) b.push(`<span class="chip">DLC ${g.dlc}</span>`);
  if (g.active_job) b.push(`<span class="chip warn">in progress</span>`);
  b.push(freshChip(g.fresh));
  return b.join('');
}
function freshTip(f) {
  if (!f) return '';
  const parts = [];
  if (f.commit) parts.push('Built with ReXNative ' + f.commit + (f.dirty ? ' (with unpublished local changes)' : ''));
  else parts.push('Built before ReXNative recorded its version: estimated from the date');
  if (f.sdk_changed) parts.push('The SDK (ReXGlue) was updated after this build');
  if (f.missing_count) parts.push(f.missing_count + ' ReXNative fix(es) not applied yet:\n' + f.missing.slice(0, 12).map(m => '• ' + m.subject).join('\n'));
  return parts.join('\n');
}
function freshChip(f) {
  if (!f || f.state === '?') return '';
  if (f.state === 'atual') return `<span class="chip ok" title="${esc(freshTip(f))}">up to date</span>`;
  const what = [f.missing_count ? `${f.missing_count} missing` : '', f.sdk_changed ? 'new SDK' : ''].filter(Boolean).join(' · ');
  return `<span class="chip warn" title="${esc(freshTip(f))}">${esc(what)}</span>`;
}
function freshHtml(g) {
  const f = g.fresh;
  if (!f || f.state === '?') return '<span class="muted">-</span>';
  const head = f.state === 'atual' ? '<span class="chip ok">up to date</span> has the published fixes and the current SDK'
    : `<span class="chip warn">outdated</span> ${f.sdk_changed ? 'the SDK (ReXGlue) was updated since' : ''}${f.sdk_changed && f.missing_count ? '; ' : ''}${f.missing_count ? f.missing_count + ' ReXNative fix(es) not applied yet' : ''}`;
  const src = f.commit ? `built with ReXNative <code>${esc(f.commit)}</code>${f.dirty ? ' (with unpublished local changes)' : ''}` : 'built before the version was recorded: estimated from the date';
  const list = f.missing && f.missing.length ? `<ul class="small" style="margin:6px 0 0;padding-left:18px">${f.missing.slice(0, 8).map(m => `<li><code>${esc(m.sha)}</code> ${esc(m.subject)}</li>`).join('')}${f.missing_count > 8 ? `<li class="muted">and ${f.missing_count - 8} more</li>` : ''}</ul>` : '';
  const btn = f.state === 'desatualizado' && !g.active_job ? ` <button class="b s" onclick="rebuildOne('${esc(g.slug)}')">Rebuild${g.deck ? ' and resend to the Deck' : ''}</button>` : '';
  return `${head}${btn}<div class="small muted" style="margin-top:4px">${src}</div>${list}`;
}
async function rebuildOne(slug) {
  try {
    const r = await api('/api/rebuild', { body: { slugs: [slug] } });
    const x = r.jobs[0] || {};
    if (x.error) return toast(x.error);
    toast('Rebuilding' + (x.deck ? ' (then resending to the Deck)' : ''));
    openJob(x.job, slug);
  } catch (e) { fail(e); }
}
async function rebuildOutdated() {
  const old = gamesData.filter(g => g.fresh && g.fresh.state === 'desatualizado' && !g.unsupported);
  const onDeck = old.filter(g => g.deck);
  if (!old.length) return toast('All built games are up to date');
  let tests = false;
  try { tests = !!(await api('/api/config')).rebuild_tests; } catch (e) { /* the text without it */ }
  const pick = await new Promise(res => {
    const d = $('#dlg');
    $('#dlgbody').innerHTML = `<h3 style="margin-top:0">Rebuild outdated games</h3>
      <p>${old.length} outdated game(s), ${onDeck.length} on the Deck: ${esc(onDeck.map(g => g.title).join(', ') || 'none')}.</p>
      <p class="small muted">Each takes about 5 minutes (with a new SDK the game code is generated again), one at a time, ${tests ? 'and is tested on the PC' : 'and is only built: no boot test (Settings, ReXNative turns it on)'}; the ones on the Deck are resent at the end (Steam does not close).</p>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="b" id="rb0">Cancel</button>
        ${onDeck.length ? `<button class="b p" id="rb1">Deck ones only (${onDeck.length})</button>` : ''}<button class="b" id="rb2">All (${old.length})</button></div>`;
    d.showModal();
    const done = v => { d.close(); res(v); };
    $('#rb0').onclick = () => done(null);
    if ($('#rb1')) $('#rb1').onclick = () => done('deck');
    $('#rb2').onclick = () => done('all');
  });
  if (!pick) return;
  try {
    const r = await api('/api/rebuild', { body: { only_deck: pick === 'deck' } });
    toast(r.jobs.filter(x => x.job).length + ' game(s) queued for rebuild');
    showTab('jobs');
  } catch (e) { fail(e); }
}
function renderGames() {
  const f = $('#gfilter').value.toLowerCase();
  let gs = gamesData.filter(g => !f || (g.title + ' ' + g.slug).toLowerCase().includes(f));
  const s = $('#gsort').value;
  const mcOf = g => g.info && g.info.mc != null ? g.info.mc : -1;
  gs.sort((a, b) => s === 'mc' ? (mcOf(b) - mcOf(a)) || a.title.localeCompare(b.title)
    : s === 'built' ? (b.built - a.built) || a.title.localeCompare(b.title)
    : s === 'deck' ? (!!b.deck - !!a.deck) || a.title.localeCompare(b.title) : a.title.localeCompare(b.title));
  $('#gcards').innerHTML = gs.map(g => {
    const art = (g.art || []).includes('portrait') ? `style="background-image:url('/api/games/${encodeURIComponent(g.slug)}/art/portrait.png?v=${Math.round(g.built_at || 0)}')"` : '';
    return `<div class="card" onclick="openGame('${esc(g.slug)}')">
      <div class="art" ${art}>${art ? '' : `<div class="ph">${esc(g.title)}</div>`}
        ${g.built ? `<button class="b p playbtn" title="Play on this PC" onclick="event.stopPropagation();playSlug('${esc(g.slug)}', 'pc')">▶ Play</button>` : ''}</div>
      <div class="meta"><div class="t">${esc(g.title)}</div>
        ${g.info ? `<div class="small muted">${esc([genreTxt(g.info), g.info.year].filter(Boolean).join(' · '))}</div>` : ''}
        <div class="badges">${g.info ? mcChip(g.info.mc) : ''}${gameBadges(g)}</div></div></div>`;
  }).join('') || '<div class="empty">No prepared games in the configured folders.</div>';
}

// -- painel de um jogo ---------------------------------------------------------------------------
let cur = null;      // o jogo aberto
let curSub = 'resumo';
function openDrawer(title) { $('#dtitle').textContent = title; $('#drawer').classList.add('on'); $('#shade').classList.add('on'); }
function closeDrawer() { $('#drawer').classList.remove('on'); $('#shade').classList.remove('on'); cur = null; jobView = null; }

async function openGame(slug, sub) {
  jobView = null;
  try {
    cur = await api('/api/games/' + encodeURIComponent(slug));
  } catch (e) { return fail(e); }
  curSub = sub || curSub || 'resumo';
  openDrawer(cur.title);
  renderGame();
}
// Jogar: o executável compilado neste PC, ou o atalho do Steam no Deck.
const PLAY_KEYS = 'Keyboard: Enter Start, Space A, Backspace B, L X, P Y, W A S D move, arrows look, Q and E triggers, 1 and 3 bumpers, Tab Back';
async function playSlug(slug, where) {
  try {
    const r = await api(`/api/games/${encodeURIComponent(slug)}/play`, { body: { where } });
    if (where === 'deck') { toast('Starting it on the Deck through Steam (follow it in Jobs)'); return; }
    const msg = r.already ? `${r.title} is already open on this PC` : `Starting ${r.title} on this PC`;
    // Sem comando ligado, o teclado é o comando: diz-se que teclas.
    if (r.pads === 0) toast(`${msg}. No controller is connected to this PC: plug one in (it is found while the game runs), or play with the keyboard. ${PLAY_KEYS}.`, false, 14000);
    else toast(msg);
  } catch (e) { fail(e); }
}
function subtabs(names, on, fn) {
  return `<div class="subtabs">${names.map(([k, l]) => `<button class="${k === on ? 'on' : ''}" onclick="${fn}('${k}')">${l}</button>`).join('')}</div>`;
}
function gameSub(k) { curSub = k; renderGame(); }
// -- o topo da página do jogo, como a ficha da loja: o fundo, a caixa, os géneros, as notas, e o que
// se faz com ele (jogar aqui ou no Deck, a página da loja). A ficha vem uma vez por jogo.
const gameCards = {};
function gameHeroHtml(g) {
  const c = gameCards[g.slug] || null;
  const im = (c && c.images) || {};
  const s = encodeURIComponent(g.slug), v = Math.round(g.built_at || 0);
  const bg = c && c.tid && im.background ? storeImg(c.tid, im.background)
    : (g.art || []).includes('hero') ? `/api/games/${s}/art/hero.png?v=${v}` : null;
  const box = (g.art || []).includes('portrait') ? `/api/games/${s}/art/portrait.png?v=${v}`
    : c && c.tid && im.boxart ? storeImg(c.tid, im.boxart) : `/api/remote/cover?t=${encodeURIComponent(g.title)}&slug=${s}`;
  const genres = c && (c.genres || []).length ? c.genres : (g.info && g.info.genres) || [];
  const devs = (c && c.developers) || (g.info && g.info.devs) || [], pubs = (c && c.publishers) || (g.info && g.info.pubs) || [];
  const by = [pubs[0], devs[0] !== pubs[0] ? devs[0] : null, (c && c.year) || (g.info && g.info.year)].filter(Boolean);
  const mc = (c && c.mc) || (g.info && g.info.mc);
  const onDeck = g.deck && g.deck.shortcut && g.deck.shortcut.appid;
  const xbla = /-xbla/.test(g.slug);
  return `<div class="st-hero ghero" id="ghero" ${bg ? `style="--hero:url('${bg}')"` : ''}><div class="st-hin">
    <img class="st-box" src="${box}" alt="" onerror="this.style.visibility='hidden'">
    <div class="st-head">
      <div class="st-kick">${xbla ? 'Xbox Live Arcade' : 'Xbox 360'}${g.title_update ? ' · title update ' + esc(g.title_update) : ''}</div>
      <h1>${esc(g.title)}</h1>
      ${by.length ? `<div class="st-by">${by.map(esc).join(' · ')}</div>` : ''}
      ${genres.length ? `<div class="st-genres">${genres.map(x => `<span>${esc(x)}</span>`).join('')}</div>` : ''}
      <div class="st-scores">
        ${c && c.rating != null ? `<div>${stars(c.rating)} <b>${c.rating.toFixed(1)}</b><span class="muted"> · ${c.ratings.toLocaleString()} player ratings</span></div>` : ''}
        ${mc ? `<div><span class="mc ${mc >= 75 ? 'h' : mc >= 50 ? 'm' : 'l'}">${mc}</span> Metacritic</div>` : ''}
        ${g.info && g.info.wiki ? `<a href="https://en.wikipedia.org/wiki/${encodeURIComponent(g.info.wiki.replace(/ /g, '_'))}" target="_blank" rel="noopener">Wikipedia</a>` : ''}
      </div>
      <div class="row" style="margin-top:12px">${gameBadges(g)}</div>
      <div class="st-acts">
        ${g.built ? `<button class="b p big" onclick="playSlug('${esc(g.slug)}', 'pc')">▶ Play on this PC</button>` : ''}
        ${onDeck ? `<button class="b big" onclick="playSlug('${esc(g.slug)}', 'deck')" title="Through the Deck's Steam, like Play in Deck mode">▶ Play on the Deck</button>` : ''}
        <button class="b big" onclick="openStore({title: ${esc(JSON.stringify(g.title))}, slug: '${esc(g.slug)}', xbla: ${xbla}, cover: '${box}'})">Store page</button>
        <span id="glang">${langSelectHtml(g.slug)}</span>
      </div>
      ${g.built ? `<div class="small muted" style="margin-top:8px">On this PC with the PC settings (F1 in the game opens the settings HUD). A controller or the keyboard: ${PLAY_KEYS}.</div>` : ''}
    </div></div></div>`;
}
// The game's language (the SDK's kernel.user_language, what XGetLanguage tells the game): one of
// the languages its SPA has texts in, for the PC and the Deck together.
const gameLangs = {};
function langSelectHtml(slug) {
  const r = gameLangs[slug];
  if (!r || (r.languages || []).length < 2) return '';
  const now = r.pc || r.deck || '1';
  return `<label class="lang" title="The language the game is played in, on this PC and on the Deck">🌐
    <select onchange="setGameLanguage(this.value)">${r.languages.map(l =>
      `<option value="${esc(l.key)}" ${l.key === now ? 'selected' : ''}>${esc(l.name)}</option>`).join('')}</select></label>`;
}
function loadGameLanguage(slug) {
  api(`/api/games/${encodeURIComponent(slug)}/language`).then(r => {
    gameLangs[slug] = r;
    for (const id of ['#glang', '#glang2']) {
      const el = $(id);
      if (el && cur && cur.slug === slug && langSelectHtml(slug)) el.innerHTML = langSelectHtml(slug);
    }
  }).catch(() => {});
}
async function setGameLanguage(v) {
  const slug = cur.slug;
  try {
    const r = await api(`/api/games/${encodeURIComponent(slug)}/language`, { body: { lang: v } });
    gameLangs[slug] = r;
    for (const id of ['#glang', '#glang2']) { const el = $(id); if (el) el.innerHTML = langSelectHtml(slug); }
    const name = ((r.languages || []).find(l => l.key === v) || {}).name || v;
    toast(`${name}: next time the game starts${r.job ? ' (on the Deck too: its settings go with it when the Deck answers)' : ''}`);
  } catch (e) { fail(e); }
}
function loadGameCard(slug) {
  if (gameCards[slug]) return;
  api('/api/card?slug=' + encodeURIComponent(slug)).then(c => {
    gameCards[slug] = c;
    const el = $('#ghero');
    if (el && cur && cur.slug === slug) el.outerHTML = gameHeroHtml(cur);
  }).catch(() => {});
}
function renderGame() {
  const g = cur;
  loadGameCard(g.slug);
  if (!gameLangs[g.slug]) loadGameLanguage(g.slug);
  let h = gameHeroHtml(g) + subtabs([['resumo', 'Summary'], ['conquistas', 'Achievements'], ['cenas', 'Test scenes'], ['defs', 'Settings'], ['capas', 'Covers'], ['tarefas', 'Jobs']], curSub, 'gameSub');
  if (curSub === 'resumo') h += gameSummary(g);
  if (curSub === 'cenas') h += '<div id="scenebox" class="muted">Loading...</div>';
  if (curSub === 'conquistas') h += '<div id="achbox" class="muted">Loading...</div>';
  if (curSub === 'defs') h += gameSettings(g);
  if (curSub === 'capas') h += '<div id="coverbox" class="muted">Loading...</div>';
  if (curSub === 'tarefas') h += gameJobs(g);
  $('#dbody').innerHTML = h;
  if (curSub === 'capas') loadCovers();
  if (curSub === 'defs') { fillQuickForms(); loadDeckBase(); }
  if (curSub === 'resumo') { loadReports(); loadFpsBoost(); }
  if (curSub === 'cenas') loadScenes();
  if (curSub === 'conquistas') loadAchievements();
}

// -- conquistas: a lista vem do jogo (o SPA na imagem), as desbloqueadas do Deck e deste PC --
async function loadAchievements() {
  const slug = cur && cur.slug;
  if (!slug) return;
  let r;
  try { r = await api(`/api/games/${encodeURIComponent(slug)}/achievements`); } catch (e) { return fail(e); }
  const box = $('#achbox');
  if (!box || !cur || cur.slug !== slug || curSub !== 'conquistas') return;
  box.className = '';
  if (r.none) { box.innerHTML = `<p class="muted">${esc(r.reason)}</p>`; return; }
  const s = encodeURIComponent(slug);
  const WHERE = { deck: 'on the Deck', pc: 'on this PC' };
  const pct = r.count ? 100 * r.unlocked / r.count : 0;
  box.innerHTML = `<div class="row" style="gap:16px;align-items:center;flex-wrap:wrap">
      <b style="font-size:18px">${r.unlocked} of ${r.count} unlocked</b><span class="muted">${r.got_score} of ${r.gamerscore} G</span>
      <div class="progress" style="flex:1;min-width:160px;max-width:360px"><div style="width:${pct.toFixed(1)}%"></div></div></div>
    <p class="small muted">The list comes from the game; the unlocked ones from what the game saved when it gave them (on the Deck, read each time the Manager reaches it${r.deck_at ? ', last ' + esc(when(r.deck_at)) : ''}; and from playing on this PC).</p>
    <div class="achs">${r.items.map(a => `<div class="ach ${a.unlocked ? '' : 'locked'}">
      ${a.image != null ? `<img src="/api/games/${s}/achievements/icon/${a.image}" alt="" loading="lazy">` : '<div class="ph">?</div>'}
      <div><b>${esc(a.name)}</b> <span class="g">${a.gamerscore} G</span>
        <div class="small">${esc(a.description)}</div>
        <div class="small muted">${a.unlocked ? 'Unlocked ' + (a.when ? esc(when(a.when)) + ' ' : '') + a.where.map(w => WHERE[w] || w).join(' and ') : 'Locked'}</div></div></div>`).join('')}</div>`;
}

// -- cenas de teste: frames do jogo gravados (traces do ReXNative), desenhados outra vez depois de cada
// mudança e comparados pixel a pixel com a referência (os mesmos frames: só o renderizador muda) --
const SCENE_SOURCE = { gameplay: 'Gameplay (found by Claude)', boot: 'Where the boot test ends', play: 'Recorded while playing', report: 'From a report', test: 'Test' };
const SCENE_CLS = { same: 'ok', igual: 'ok', melhor: 'ok', pior: 'bad', inconclusivo: 'warn', stale: 'warn', failed: 'bad' };
let sceneTimer = null;
async function loadScenes() {
  clearTimeout(sceneTimer);
  const slug = cur && cur.slug;
  if (!slug) return;
  let r;
  try { r = await api(`/api/games/${encodeURIComponent(slug)}/scenes`); } catch (e) { return fail(e); }
  const box = $('#scenebox');
  if (!box || !cur || cur.slug !== slug || curSub !== 'cenas') return;
  const s = encodeURIComponent(slug);
  const img = (m, which) => `/api/scenes/${s}/${encodeURIComponent(m.id)}/img/${which}?t=${encodeURIComponent((m.last && m.last.at) || m.ref_at || m.at)}`;
  const card = m => {
    const L = m.last || {};
    const state = !m.has_ref ? '<span class="chip warn">pictures when the game closes</span>'
      : L.verdict ? `<span class="chip ${SCENE_CLS[L.verdict] || ''}">${esc(m.word || L.verdict)}</span>` : '<span class="chip">not checked yet</span>';
    return `<div class="scene">
      ${m.has_ref ? `<img src="${img(m, 'ref')}" alt="" onclick="window.open('${img(m, 'ref')}')">` : '<div class="ph">no pictures yet</div>'}
      <div class="sb"><b>${esc(m.label)}</b>
        <div class="small muted">${esc(SCENE_SOURCE[m.source] || m.source)} · ${esc((m.at || '').slice(0, 16).replace('T', ' '))} · reference: ReXNative ${esc(m.ref_rex || '-')}</div>
        <div style="margin-top:6px">${state} ${L.at ? `<span class="small muted">${esc(L.at.slice(0, 16).replace('T', ' '))} with ${esc(L.rex || '?')}</span>` : ''}</div>
        ${L.summary && L.verdict !== 'same' ? `<div class="small" style="margin-top:4px">${esc(L.summary)}</div>` : ''}
        <div class="row" style="margin-top:8px;gap:6px">
          ${m.has_sheet ? `<button class="b s" onclick="window.open('${img(m, 'sheet')}')">Before / after</button>` : ''}
          ${m.has_new && L.verdict && !['same', 'melhor'].includes(L.verdict) && !L.accepted ? `<button class="b s" onclick="sceneDo('${esc(m.id)}','accept')" title="The new pictures become the reference">Accept the new look</button>` : ''}
          ${m.has_prev && L.accepted ? `<button class="b s" onclick="sceneDo('${esc(m.id)}','undo')" title="Back to the reference before it">Undo the accept</button>` : ''}
          <button class="b s d" onclick="sceneDo('${esc(m.id)}','delete')">Delete</button></div></div></div>`;
  };
  const c = r.check;
  box.className = '';
  box.innerHTML = `<p class="small muted" style="margin-top:0">A scene is a few frames of the game recorded as it runs. After every ReXNative change the Manager draws each scene again with the new build and compares the pixels with its reference: the same frames, so a difference is the renderer's, never a slower start. Record the places that matter while you play.</p>
    <div class="row" style="gap:8px;align-items:center">
      <button class="b p" ${r.running ? '' : 'disabled'} onclick="sceneRecord()" title="${r.running ? 'Records the next frames of the game' : 'Start the game with Play on this PC first'}">● Save this scene as a test</button>
      ${r.running ? '<span class="small">The game is open: go where you want to keep, then press it (Alt+Tab to come here).</span>'
        : `<button class="b s" onclick="playSlug('${esc(slug)}','pc');setTimeout(loadScenes,4000)">▶ Play on this PC</button><span class="small muted">to record a scene</span>`}
      <span class="grow"></span>
      ${r.scenes.length ? `<button class="b s" ${r.running || r.busy ? 'disabled' : ''} onclick="scenesCheck()">Check them now</button>` : ''}</div>
    ${c ? `<div class="small muted" style="margin-top:8px">Last check ${esc((c.at || '').slice(0, 16).replace('T', ' '))} with ReXNative ${esc(c.rex || '?')}: ${c.checked} checked${c.worse && c.worse.length ? `, <b style="color:var(--bad)">${c.worse.length} worse</b>` : ''}${c.changed && c.changed.length ? `, ${c.changed.length} changed` : ''}${c.better && c.better.length ? `, ${c.better.length} better` : ''}${c.job ? ` · <a href="#" onclick="openJob('${esc(c.job)}','${esc(slug)}');return false">job</a>` : ''}</div>` : ''}
    <div class="scenes">${r.scenes.map(card).join('') || '<div class="muted">No scenes yet. The next boot test records one of where it ends; record your own while playing.</div>'}</div>`;
  if (r.running || r.busy) sceneTimer = setTimeout(loadScenes, 5000);
}
async function sceneRecord() {
  const label = prompt('A name for this scene (what it shows):', '');
  if (label === null) return;
  toast('Recording the next frames of the game...');
  try { await api(`/api/games/${encodeURIComponent(cur.slug)}/scenes/record`, { body: { label } }); toast('Scene saved: its pictures are made when you close the game'); }
  catch (e) { fail(e); }
  loadScenes();
}
async function scenesCheck() {
  try { const j = await api(`/api/games/${encodeURIComponent(cur.slug)}/scenes/check`, { body: {} }); toast('Checking the scenes (follow it in Jobs)'); }
  catch (e) { fail(e); }
  loadScenes();
}
async function sceneDo(id, what) {
  if (what === 'delete' && !confirm('Delete this test scene? It is not checked any more after ReXNative changes.')) return;
  try { await api(`/api/scenes/${encodeURIComponent(cur.slug)}/${encodeURIComponent(id)}/${what}`, { body: {} }); }
  catch (e) { fail(e); }
  loadScenes();
}

function gameSummary(g) {
  const boot = g.boot;
  const deckTxt = g.deck ? `${g.deck.where === 'sd' ? 'microSD card' : 'internal storage'} — ${gb(g.deck.size)}${g.deck.shortcut ? ', shortcut "' + esc(g.deck.shortcut.name) + '"' : ', no shortcut'}` : 'not installed';
  const pl = g.pipeline;
  const onDeck = g.deck && g.deck.shortcut && g.deck.shortcut.appid;
  return `${g.unsupported ? `<div class="ev fail" style="margin-top:10px">${esc(g.unsupported_why || g.unsupported)}</div>` : ''}
  <div class="kv" style="margin-top:12px">
    <div>Folder</div><div>${esc(g.work)}</div>
    <div>Source</div><div>${esc(g.source || '-')}</div>
    <div>Title ID / version</div><div>${esc(g.title_id || '-')} / ${esc(g.version || '-')}</div>
    <div>Executable</div><div>${esc(g.exe ? g.exe + '.exe' : '-')} ${g.built_at ? '(built ' + when(g.built_at) + ')' : ''}</div>
    <div>Fixes</div><div>${freshHtml(g)}</div>
    <div>Title update / DLC</div><div>${g.title_update ? 'TU ' + g.title_update : 'none'} / ${g.dlc || 0} package(s)</div>
    <div>Steam Deck</div><div>${deckTxt}</div>
    <div>Last pipeline</div><div>${pl ? esc(JOB_STATUS[pl.status] || pl.status) + ' ' + when(pl.at) + (pl.error ? ' — ' + esc(pl.error) : '') + (pl.fixes ? ` (${pl.fixes} fix(es) by Claude)` : '') + (pl.job ? ` <a href="#" onclick="openJob('${pl.job}');return false">view</a>` : '') : '-'}</div>
    ${g.prepare_error ? `<div>Prepare error</div><div style="color:#ff9b94">${esc(g.prepare_error)}</div>` : ''}
  </div>
  ${(g.tunings || []).length ? `<h3>What ReXNative tunes for this game</h3><div class="kv">${g.tunings.map(t => `<div>${esc(t.k)}</div><div>${esc(t.t)}</div>`).join('')}</div>` : ''}
  ${gpuFloorHtml(g)}
  ${linuxHtml(g)}
  <h3>Contribution to ReXNative</h3>
  ${contribHtml(g)}
  <h3>Native vs classic</h3>
  ${compareHtml(g)}
  ${regressHtml(g)}
  <h3>Problems</h3>
  <div class="row">
    <button class="b p" onclick="reportDialog()">Report a problem</button>
    <span class="muted small">Renderer:</span>
    ${['pc', 'deck'].map(w => `<span class="small">${w === 'pc' ? 'PC' : 'Deck'}</span>
      <button class="b s ${g.classic && !g.classic[w] ? 'p' : ''}" onclick="setRenderer('${w}', false)">Native</button>
      <button class="b s ${g.classic && g.classic[w] ? 'p' : ''}" onclick="setRenderer('${w}', true)">Classic</button>`).join('')}
  </div>
  <p class="muted small">Classic is ReXGlue's renderer (Xenia's): slower, but it draws what the native one can't yet; the HUD (F1 / View+Menu) switches at any time. On the Deck it only takes effect after resending with "replace the settings".</p>
  <h3>FPS Boost</h3>
  <div id="fpsbox" class="muted small">Looking for Xenia canary's frame rate patch for this game...</div>
  <div id="reportsbox"></div>
  <h3>PC</h3>
  <div class="row">
    <button class="b p" onclick="runPipeline(['build','boot','compare'])">Build and test</button>
    <button class="b" onclick="runPipeline(['boot','compare'])" ${g.built ? '' : 'disabled'}>Test and compare only</button>
    <button class="b" onclick="runPipeline(['prepare','boot'])">Prepare again and test</button>
    <label class="small"><input type="checkbox" id="thendeck"> send to the Deck at the end</label>
  </div>
  <p class="muted small">If a step fails, Claude Code analyses the log, fixes the problem (in ReXNative or the game folder) and the step runs again.</p>
  ${boot ? `<h3>Last boot test (${when(boot.at)})</h3>
    <div class="row"><span class="chip ${boot.ok ? 'ok' : 'bad'}">${boot.ok ? 'OK' : 'failed'}</span>
    <span>${boot.frames} frames in ${boot.seconds} s · ${boot.draws} draws/frame · ${boot.frame_ms} ms/frame</span></div>
    ${boot.crash && boot.crash.length ? `<div class="log" style="margin-top:8px">${esc(boot.crash.join('\n'))}</div>` : ''}
    ${boot.shot ? `<p><img class="shot" src="/api/games/${encodeURIComponent(g.slug)}/shot?t=${Date.now()}"></p>` : ''}` : ''}
  <h3>Steam Deck</h3>
  <div class="row">
    <select id="deckroot"><option value="">Internal storage</option><option value="sd" ${g.deck && g.deck.where === 'sd' ? 'selected' : ''}>microSD card</option></select>
    <button class="b p" onclick="deckInstall()" ${g.built ? '' : 'disabled'}>${g.deck ? 'Reinstall' : 'Install'} (with test)</button>
    <button class="b" onclick="deckResend(false)" ${g.built && g.deck ? '' : 'disabled'}>Resend files</button>
  </div>
  <p class="muted small">Install closes Steam on the Deck for a moment to add the shortcut and art, then starts the game to test it. Resend sends only what changed (settings, executable).</p>
  <h3>This PC's copy</h3>
  <div class="row"><button class="b d" onclick="pcDeleteDialog('${esc(g.slug)}')">Delete from this PC…</button>
    <span class="small muted">frees the disk: the prepared and built game, and the download if you want; the Deck's copy stays</span></div>`;
}

// Apagar o jogo deste PC: a pasta de trabalho, os saves numa cópia antes, o download se se quiser.
async function pcDeleteDialog(slug) {
  let d;
  try { d = await api(`/api/games/${encodeURIComponent(slug)}/disk`); } catch (e) { return fail(e); }
  if (d.running) return toast('The game is open on this PC: close it first', true);
  if (d.busy && d.busy.length) return toast('The game has jobs queued or running: ' + d.busy.join(', '), true);
  const title = (cur && cur.slug === slug && cur.title) || slug;
  const ok = await confirmBox(`<h3 style="margin-top:0">Delete ${esc(title)} from this PC?</h3>
    <p>The game folder goes (<b>${gb(d.work_bytes)}</b>): the prepared and built game, its PC settings, test scenes and test results. It cannot be undone: to play it here or update the Deck again, it is prepared again (about 5 to 20 minutes, more for big games).</p>
    <p class="small muted">${esc(d.work)}</p>
    ${d.saves ? `<label style="display:block;margin:6px 0"><input type="checkbox" id="pcdsaves" checked> Keep a copy of this PC's saves first (${d.saves} save folder(s), in backups\\pc)</label>` : '<p class="small muted">No saves of this PC.</p>'}
    ${d.download ? `<label style="display:block;margin:6px 0"><input type="checkbox" id="pcddl"> Also delete the downloaded file (<b>${gb(d.download.bytes)}</b>): preparing it again would download it again</label>` : ''}
    ${d.on_deck ? '<p class="small">It stays on the Deck as it is, playable; only its updates from this PC stop until it is prepared again.</p>' : ''}`, 'Delete', true);
  if (!ok) return;
  const body = { backup_saves: !!($('#pcdsaves') && $('#pcdsaves').checked), download: !!($('#pcddl') && $('#pcddl').checked) };
  try {
    await api(`/api/games/${encodeURIComponent(slug)}/delete`, { body });
    toast(`Deleting ${title} from this PC (follow it in Jobs)`);
    closeDrawer();
    setTimeout(loadGames, 4000);
  } catch (e) { fail(e); }
}

// -- comparação, relatórios e renderizador ----------------------------------------------------------
const VERDICT = { iguais: ['ok', 'Native matches classic'], nativo_com_erros: ['bad', 'Native has graphical errors'],
  brilho_diferente: ['warn', 'Different brightness or contrast: check in the game which one is right (F1 switches the renderer)'],
  classico_com_erros: ['warn', 'Classic is the one that is wrong'], cenas_diferentes: ['warn', 'Different moments in the two runs'],
  inconclusivo: ['warn', 'Inconclusive'] };
function capUrl(slug, path) { return `/api/games/${encodeURIComponent(slug)}/capture?path=${encodeURIComponent(path)}`; }
function compareHtml(g) {
  const c = g.compare;
  if (!c) return `<p class="muted small">Not compared yet: "Test and compare only" starts the game with the native and the classic renderer, presses the same buttons (START, A) to get past the title screen and takes captures at the same seconds.</p>`;
  const [cls, label] = VERDICT[c.verdict] || ['', c.verdict];
  if (c.stale) return `<div class="row"><span class="chip">outdated</span><span class="small muted">the last comparison (${when(c.at)}: ${esc(label)}) predates the last test; "Test and compare only" makes a new one</span></div>`;
  return `<div class="row"><span class="chip ${cls}">${esc(label)}</span><span class="small muted">${when(c.at)}</span></div>
    ${c.summary ? `<p class="small">${esc(c.summary)}</p>` : ''}
    ${(c.pairs || []).map(p => `<div class="row" style="align-items:flex-start;margin-bottom:8px">
      <div style="width:48px" class="small muted">${p.t} s</div>
      <div><img class="shot" style="max-width:260px" src="${capUrl(g.slug, p.native)}"><div class="small muted">native ${p.native_ok === false ? '<span class="chip bad">wrong</span>' : p.native_ok ? '<span class="chip ok">right</span>' : ''}</div></div>
      <div><img class="shot" style="max-width:260px" src="${capUrl(g.slug, p.classic)}"><div class="small muted">classic (reference)</div></div>
      <div class="small grow" style="min-width:160px">${esc(p.note || '')}<div class="muted">difference ${p.diff}%</div></div></div>`).join('')}`;
}
// O relógio da GPU enquanto o jogo joga no Deck (o play.sh mantém-na a 1000 MHz ou mais;
// REXNATIVE_GPU_FLOOR=0 no deck.env do jogo deixa o relógio automático do SteamOS).
function gpuFloorHtml(g) {
  if (!g.deck) return '';
  const on = g.deck.gpu_floor !== false;
  return `<h3>GPU clock on the Deck</h3><div class="panel small"><p style="margin-top:0">While a game plays, the Deck's GPU is kept at 1000 MHz or more (up to 1600): the APU shares 15 W between CPU and GPU, and when a game's threads burst at 3.5 GHz SteamOS's automatic clock let the GPU fall to 200-450 MHz in the middle of frames (Forza Horizon: 8-11 frames over 45 ms in 80 s, none with the floor, at the same power). A GPU clock set in Steam's quick menu stays as set. It counts from the game's next start; the automatic clock comes back when the game closes.</p>
    <p>${on ? '<b>Steady</b> (the default): 1000 MHz or more while this game plays' : "<b>SteamOS's automatic clock</b> for this game"}</p>
    <button class="b" onclick="gpuFloorAct('${esc(g.slug)}', ${on ? 'false' : 'true'})">${on ? "Use SteamOS's automatic clock for this game" : 'Keep the GPU steady while it plays'}</button></div>`;
}
async function gpuFloorAct(slug, on) {
  try { const j = await api(`/api/games/${encodeURIComponent(slug)}/gpu-floor`, { body: { on } }); openJob(j.id); } catch (e) { fail(e); }
}
// A build para Linux (experimental): compilar no WSL, enviar para o Deck, escolher o que arranca.
function linuxHtml(g) {
  const l = g.linux;
  if (!l) return '';
  if (!l.enabled) return `<h3>Linux build (experimental)</h3><p class="small muted">${esc(l.why)}. Measured on the Deck it runs, but ReXGlue's Vulkan renderer uses far more GPU than ReXNative under Proton (docs/LINUX.md in ReXNative).</p>`;
  const st = [l.built_at ? 'built ' + when(new Date(l.built_at * 1000).toISOString()) + (l.size ? ' (' + esc(l.size) + ')' : '') : 'not built',
    l.on_deck ? 'on the Deck, ' + (l.runner === 'linux' ? '<b>it is what the Steam shortcut starts</b>' : 'the Windows build is what starts') : (g.deck ? 'not on the Deck' : '')].filter(Boolean).join(' · ');
  return `<h3>Linux build (experimental)</h3><div class="panel small"><p style="margin-top:0">Native Linux, no Proton, drawn by ReXGlue's renderer on Vulkan (ReXNative is D3D12 only): it uses far more GPU on the Deck than the Windows build; for games that run better, or only, this way. Saves are separate from the Windows build's.</p>
    <p>${st}</p><div class="row" style="gap:8px">
    ${g.built ? `<button class="b" onclick="linuxAct('${esc(g.slug)}', 'build')">${l.built_at ? 'Rebuild for Linux' : 'Build for Linux'}</button>` : ''}
    ${l.built_at && g.deck ? `<button class="b" onclick="linuxAct('${esc(g.slug)}', 'deck')">Send to the Deck and use it</button>` : ''}
    ${l.on_deck ? `<button class="b" onclick="linuxAct('${esc(g.slug)}', 'runner', '${l.runner === 'linux' ? 'windows' : 'linux'}')">${l.runner === 'linux' ? 'Start the Windows build on the Deck' : 'Start the Linux build on the Deck'}</button>` : ''}
    </div></div>`;
}
async function linuxAct(slug, what, runner) {
  try { const j = await api(`/api/games/${encodeURIComponent(slug)}/linux/${what}`, { body: { runner } }); openJob(j.id); } catch (e) { fail(e); }
}
function contribHtml(g) {
  const c = g.contrib || { entries: [], commits: 0 };
  const real = c.entries.filter(e => e.commits.length || e.game_files.length);
  const idle = c.entries.length - real.length;
  if (!real.length) return `<p class="small muted">${c.entries.length
    ? `Nothing: Claude analysed it ${idle} time(s) and neither ReXNative nor the game folder needed changes.`
    : 'Nothing so far: this game has needed no fixes (neither automatic nor from reports).'}</p>`;
  return `<p class="small">${c.commits ? `<b>${c.commits} ReXNative commit(s)</b> came from this game.` : 'Only changes in the game folder, none in ReXNative.'}
      ${idle ? `<span class="muted">(plus ${idle} analysis run(s) with no changes)</span>` : ''}</p>
    ${real.map(e => `<div class="ev ${e.commits.length ? 'ok' : 'step'}" style="margin-bottom:6px">
      <span class="t">${esc((e.at || '').slice(0, 16).replace('T', ' '))}</span><b>${esc(e.source)}</b>
      ${e.job ? ` <a href="#" onclick="openJob('${esc(e.job)}','${esc(g.slug)}');return false">view job</a>` : ''}
      ${e.note ? `\n<b>For all games:</b> ${esc(e.note)}` : ''}
      ${e.commits.length ? '\n' + e.commits.map(x => x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.hash)}</a> ${esc(x.subject)}` : `${esc(x.hash)} ${esc(x.subject)}`).join('\n')
        + (e.pushed === true ? '\n<span class="small muted">pushed to main</span>' : e.pushed === false ? '\n<span class="small" style="color:#f2c46b">not pushed yet</span>' : '') : ''}
      ${e.game_files.length ? `\n<b>This game only:</b> ${esc(e.game_files.slice(0, 6).join(', '))}${e.game_files.length > 6 ? '…' : ''}` : ''}</div>`).join('')}`;
}
const REGRESS = { iguais: ['ok', 'Same'], melhorou: ['ok', 'Improved'], piorou: ['bad', 'Got worse'],
  diferentes: ['warn', 'Different moments'], inconclusivo: ['warn', 'Inconclusive'] };
function regressHtml(g) {
  const r = g.regress;
  if (!r) return '';
  const [cls, label] = REGRESS[r.verdict] || ['', r.verdict];
  return `<h3>Before / after the last ReXNative change</h3>
    <div class="row"><span class="chip ${cls}">${esc(label)}</span><span class="small muted">${when(r.at)} · before: ${esc((r.before_rex || '?').slice(0, 60))} · after: ${esc((r.after_rex || '?').slice(0, 60))}</span></div>
    ${r.summary ? `<p class="small">${esc(r.summary)}</p>` : ''}
    ${(r.pairs || []).map(p => `<div class="row" style="align-items:flex-start;margin-bottom:8px">
      <div style="width:48px" class="small muted">${p.t} s</div>
      <div><img class="shot" style="max-width:260px" src="${capUrl(g.slug, p.before)}"><div class="small muted">before</div></div>
      <div><img class="shot" style="max-width:260px" src="${capUrl(g.slug, p.after)}"><div class="small muted">after ${p.change === 'pior' ? '<span class="chip bad">worse</span>' : p.change === 'melhor' ? '<span class="chip ok">better</span>' : ''}</div></div>
      <div class="small grow" style="min-width:160px">${esc(p.note || '')}<div class="muted">difference ${p.diff}%</div></div></div>`).join('')}`;
}
let reportKinds = [];
// Os tipos e o "onde" vão para o servidor tal como estão; aqui só se traduz o que se mostra.
const KIND_LABEL = { 'Gráficos no renderizador nativo': 'Graphics in the native renderer', 'Gráficos no clássico': 'Graphics in the classic renderer',
  'Fecha ou bloqueia': 'Crashes or freezes', 'Lento / FPS': 'Slow / FPS', 'Som': 'Sound', 'Comandos': 'Controls', 'Outro': 'Other' };
const WHERE_LABEL = { 'PC e Steam Deck': 'PC and Steam Deck' };
function reportCls(s) {
  // O estado vem do servidor (em português nos relatórios antigos, talvez em inglês nos novos).
  s = s || '';
  if (/corrigido/.test(s) || (/fixed/i.test(s) && !/not fixed|no fix/i.test(s))) return 'ok';
  if (/sem|falhou/.test(s) || /fail|no fix|not fixed|gave up/i.test(s)) return 'fail';
  return 'step';
}
async function loadReports() {
  const slug = cur.slug;
  let r;
  try { r = await api(`/api/games/${encodeURIComponent(slug)}/reports`); } catch (e) { return; }
  reportKinds = r.kinds;
  const box = $('#reportsbox');
  if (!box || !cur || cur.slug !== slug) return;
  box.innerHTML = r.reports.length ? `<h3>Reports</h3>${r.reports.map(x => `<div class="ev ${reportCls(x.status)}" style="margin-bottom:6px">
    <span class="t">${esc((x.at || '').slice(0, 16).replace('T', ' '))}</span><b>${esc(KIND_LABEL[x.kind] || x.kind)}</b> · ${esc(WHERE_LABEL[x.where] || x.where)} · <span class="chip">${esc(x.status)}</span>
    ${x.job ? `<a href="#" onclick="openJob('${esc(x.job)}','${esc(slug)}');return false">view job</a>` : ''}
    \n${esc(x.text)}${x.summary ? `\n<span style="color:#c9b6dd"><b>Claude:</b> ${esc(x.summary)}</span>` : ''}${x.commits && x.commits.length ? `\n<b>Commits:</b> ${esc(x.commits.join(' · '))}` : ''}</div>`).join('')}` : '';
}
async function reportDialog() {
  const slug = cur.slug, g = cur;
  let caps = [];
  try { caps = (await api(`/api/games/${encodeURIComponent(slug)}/captures`)).captures; } catch (e) { /* sem capturas */ }
  let snaps = [];
  try { snaps = (await api(`/api/games/${encodeURIComponent(slug)}/snapshots`)).snapshots; } catch (e) { /* sem snapshots */ }
  const snapWhen = n => n.length >= 13 ? `${n.slice(0, 4)}-${n.slice(4, 6)}-${n.slice(6, 8)} ${n.slice(9, 11)}:${n.slice(11, 13)}` : n;
  if (!reportKinds.length) reportKinds = ['Gráficos no renderizador nativo', 'Gráficos no clássico', 'Fecha ou bloqueia', 'Lento / FPS', 'Som', 'Comandos', 'Outro'];
  // Com a comparação a dizer que o nativo está mal, os pares vão marcados e o texto já começa.
  const bad = g.compare && g.compare.verdict === 'nativo_com_erros';
  const pairPaths = new Set(bad ? g.compare.pairs.flatMap(p => [p.native, p.classic]) : []);
  const ok = await confirmBox(`<h3 style="margin-top:0">Report a problem: ${esc(g.title)}</h3>
    <div class="form" style="grid-template-columns:110px 1fr">
      <label>Type</label><select id="rpkind">${reportKinds.map(k => `<option value="${esc(k)}">${esc(KIND_LABEL[k] || k)}</option>`).join('')}</select>
      <label>Where</label><select id="rpwhere"><option value="PC">PC</option><option value="Steam Deck">Steam Deck</option><option value="PC e Steam Deck">PC and Steam Deck</option></select>
      <label>What you see</label><textarea id="rptext" style="min-height:110px;font-family:inherit;font-size:13.5px" placeholder="E.g. the main menu screen is all white; in game the terrain is missing, only the buildings show...">${bad ? esc('Automatic comparison: ' + (g.compare.summary || '')) : ''}</textarea>
    </div>
    ${caps.length ? `<p class="small muted" style="margin:10px 0 4px">Captures that show the problem (Claude sees them):</p>
      <div class="picks" style="max-height:230px;overflow:auto">${caps.map((c, i) => `<label class="pick" style="cursor:pointer">
        <img src="${capUrl(slug, c.path)}" style="max-height:90px">
        <span><input type="checkbox" class="rpcap" value="${esc(c.path)}" ${(bad ? pairPaths.has(c.path) : !snaps.length && i === 0) ? 'checked' : ''}> ${esc(c.source)} · ${esc(c.name)}</span></label>`).join('')}</div>` : ''}
    ${snaps.length ? `<p class="small muted" style="margin:10px 0 4px">Snapshots you took on this PC (the last day): the ticked ones go with the report. Claude looks at the picture and replays the frames after it.</p>
      <div class="picks">${snaps.map(s => `<label class="pick" style="cursor:pointer" title="${esc(s.info || '')}">
        ${s.png.length ? `<img src="${capUrl(slug, s.png[0])}" style="max-height:120px">` : ''}
        <span><input type="checkbox" class="rpsnap" value="${esc(s.name)}" checked> ${esc(snapWhen(s.name))}${s.trace.length ? '' : ' · no trace'}</span></label>`).join('')}</div>`
    : `<p class="small muted" style="margin:10px 0 0">Tip: at the place, in the game, open the settings menu (Back + Start or F1; on the Deck View + Menu) and press Y. That moment is saved as a snapshot (the picture and the next frames), and it shows here: the report sends it, so Claude sees what you saw and replays those frames.</p>`}
    <label style="display:block;margin-top:10px"><input type="checkbox" id="rpfix" checked> Ask Claude to investigate and fix it (strong model; opens the game on the PC to look)</label>
    <label style="display:block;margin-top:6px"><input type="checkbox" id="rpcrash"> Just the crash log: Claude starts from this PC's newest log of a crash, and opens the game only if the fix needs it (the fixed game is then built and started once to check it)</label>`, 'Send');
  if (!ok) return;
  const body = { kind: $('#rpkind').value, where: $('#rpwhere').value, text: $('#rptext').value.trim(),
    captures: [...document.querySelectorAll('.rpcap')].filter(c => c.checked).map(c => c.value), fix: $('#rpfix').checked,
    crash_only: $('#rpcrash').checked };
  if (snaps.length) body.snapshots = [...document.querySelectorAll('.rpsnap')].filter(c => c.checked).map(c => c.value);
  if (!body.text && !body.crash_only) return toast('Describe what you see, so Claude knows what to look for', true);
  try {
    const r = await api(`/api/games/${encodeURIComponent(slug)}/report`, { body });
    if (r.id) { toast('Claude will investigate'); openJob(r.id, slug); } else { toast('Report saved'); openGame(slug); }
  } catch (e) { fail(e); }
}
// -- FPS Boost: Xenia canary's frame rate patch (rexnative fps-boost), chosen here, applied by the next build --
async function loadFpsBoost() {
  const slug = cur && cur.slug;
  if (!slug) return;
  let r;
  try { r = await api(`/api/games/${encodeURIComponent(slug)}/fps-boost`); }
  catch (e) { const b = $('#fpsbox'); if (b) b.textContent = e.message; return; }
  const box = $('#fpsbox');
  if (!box || !cur || cur.slug !== slug || curSub !== 'resumo') return;
  box.className = '';
  box.innerHTML = fpsBoostHtml(r);
}
function fpsBoostState(r) {
  return r.on ? (r.needs_build ? 'On: the next build applies it' : 'On, in this build')
    : (r.needs_build ? 'Off: the next build takes it out' : 'Off');
}
function fpsBoostHtml(r) {
  if (!r.available) return `<p class="muted small">Not available: ${esc(r.reason || 'no patch')}.</p>`;
  return `<div class="row">
      <button class="b s ${r.on ? 'p' : ''}" onclick="setFpsBoost(true)">On</button>
      <button class="b s ${r.on ? '' : 'p'}" onclick="setFpsBoost(false)">Off</button>
      <span class="chip ${r.needs_build ? 'warn' : r.on ? 'ok' : ''}">${esc(fpsBoostState(r))}</span>
      ${r.needs_build ? `<button class="b" onclick="runPipeline(['build','boot'])">Build and test now</button>` : ''}
    </div>
    <p class="muted small">Xenia canary's "${esc(r.patch)}" patch${r.author ? ' by ' + esc(r.author) : ''}, made for this version of the game (<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.file)}</a>)${r.desc ? ': ' + esc(r.desc) : '.'}
    Like FPS Boost on the newer Xboxes, it changes how the game paces itself: the build puts it into the game's code, and the boot test shows the frame rate it reaches. Some games run too fast or show glitches somewhere with it (see the patch's notes); the Deck holds 60 FPS only in the lighter games. Nothing is built until you ask: build here, or use Rebuild on the Deck.</p>`;
}
async function setFpsBoost(on) {
  try {
    const r = await api(`/api/games/${encodeURIComponent(cur.slug)}/fps-boost`, { body: { on } });
    const box = $('#fpsbox');
    if (box) box.innerHTML = fpsBoostHtml(r);
    toast(`FPS Boost ${on ? 'on' : 'off'}${r.needs_build ? ': the next build applies it' : ''}`);
  } catch (e) { fail(e); }
}
async function setRenderer(where, classic) {
  try {
    await api(`/api/games/${encodeURIComponent(cur.slug)}/renderer`, { body: { where, classic } });
    toast(`${where === 'pc' ? 'PC' : 'Deck'}: ${classic ? 'classic renderer' : 'native renderer'}${where === 'deck' ? ' (resend with "replace the settings" for it to reach the Deck)' : ''}`);
    openGame(cur.slug, 'resumo');
  } catch (e) { fail(e); }
}

async function runPipeline(steps) {
  const body = { steps };
  if ($('#thendeck') && $('#thendeck').checked) body.deck = { action: 'install', root: $('#deckroot').value || null };
  try {
    const j = await api(`/api/games/${encodeURIComponent(cur.slug)}/pipeline`, { body });
    toast('Job created: ' + j.title);
    openJob(j.id, cur.slug);
  } catch (e) { fail(e); }
}
async function deckInstall() {
  const root = $('#deckroot').value || null;
  if (!await confirmBox(`<p>Install <b>${esc(cur.title)}</b> on the Steam Deck (${root === 'sd' ? 'microSD card' : 'internal storage'})?</p>
    <p class="muted small">Steam on the Deck closes and reopens (for the shortcut) and the game runs for a few seconds as a test. Nobody can be playing.</p>`, 'Install')) return;
  try {
    const j = await api(`/api/games/${encodeURIComponent(cur.slug)}/deck`, { body: { action: 'install', root } });
    openJob(j.id, cur.slug);
  } catch (e) { fail(e); }
}
async function deckResend(steam, force) {
  try {
    const j = await api(`/api/games/${encodeURIComponent(cur.slug)}/deck`, { body: { action: 'resend', steam: !!steam, force_settings: !!force } });
    toast('Resending: ' + j.title);
    openJob(j.id, cur.slug);
  } catch (e) { fail(e); }
}

// -- definições do jogo ---------------------------------------------------------------------------
// The Deck's settings under deck.toml: the PC's file with the kit's Deck settings on it
// (/api/remote/settings: base), what "Default" means in the Deck's form.
let deckBase = {};
// The settings the game has on the Deck now (its own file there: what its menu changed too), null
// when the Deck did not answer (the form then shows deck.toml's).
let deckLive = null;
function parseToml(text) {
  const out = {};
  let sec = '';
  for (const raw of (text || '').split('\n')) {
    const l = raw.replace(/#.*$/, '').trim();
    let m = l.match(/^\[([A-Za-z0-9_.]+)\]$/);
    if (m) { sec = m[1]; continue; }
    m = l.match(/^([A-Za-z0-9_]+)\s*=\s*(.+)$/);
    if (m) out[(sec ? sec + '.' : '') + m[1]] = m[2].trim().replace(/^"(.*)"$/, '$1');
  }
  return out;
}
function gameSettings(g) {
  const parts = [['pc', 'On the PC — run/' + (g.exe || '?') + '.toml', 'The game\'s settings on this PC, as its settings HUD (F1) has them; the HUD writes here too. Default: the renderer\'s own.'],
                 ['deck', 'On the Steam Deck', 'What the game uses on the Deck, its settings menu\'s changes too: a change applied here goes to it at once, also while it runs (games built from 2026-11-25 on; older ones at their next start), and to deck.toml for its next installs. Default: the PC\'s settings with the kit\'s for the Deck (its 1280x800 screen, FSR at native resolution).']];
  const lang = `<h3>Language</h3><p class="muted small">The languages this game is made in, for this PC and the Deck together. Português (Brasil) is Brazil's.</p>
    <div class="row" id="glang2">${langSelectHtml(g.slug) || '<span class="muted small">English only, or the game has no SPA yet.</span>'}</div>`;
  return lang + parts.filter(([k]) => g.settings[k]).map(([k, title, hint]) => `
    <h3>${esc(title)}</h3><p class="muted small">${esc(hint)} <span class="muted">${esc(g.settings[k].path)}</span></p>
    <div class="form setform" id="qf-${k}">${settingsFor(k).map((s, n) => `${n === 0 || settingsFor(k)[n - 1].group !== s.group ? `<div class="setgroup">${esc(s.group)}</div>` : ''}
      <label title="${esc(s.hint)}">${esc(s.label)}</label>
      <select data-id="${s.id}" title="${esc(s.hint)}"></select>`).join('')}</div>
    <div class="row" style="margin:8px 0"><button class="b p" onclick="applyQuick('${k}')">Apply these options</button></div>
    <details><summary class="muted small">Edit the file by hand</summary>
      <textarea id="tx-${k}" spellcheck="false">${esc(g.settings[k].text)}</textarea>
      <div class="row" style="margin-top:6px"><button class="b" onclick="saveText('${k}')">Save the file</button></div></details>
    ${k === 'deck' ? `<div class="row" style="margin-top:10px">
      <button class="b" onclick="deckResend(false, $('#forcedeck').checked)" ${g.deck ? '' : 'disabled'}>Resend to the Deck</button>
      <label class="small"><input type="checkbox" id="forcedeck"> and replace all of its settings with these and the PC's (what was changed in its menu on the Deck is lost)</label></div>
      <p class="muted small">The options above go to the game on the Deck as you apply them; the resend is for the game's files.</p>` : ''}`).join('');
}
function fillQuickForms() {
  for (const k of ['deck', 'pc']) {
    const box = $('#qf-' + k);
    if (!box) continue;
    const vals = k === 'deck' && deckLive ? deckLive : parseToml(cur.settings[k].text);
    const base = k === 'deck' ? deckBase : {};
    box.querySelectorAll('select').forEach(sel => {
      const s = GAME_SETTINGS.find(x => x.id === sel.dataset.id);
      const d = settingIndex(s, base);
      const opts = [['', `Default${d >= 0 ? ` (${s.choices[d][0]})` : ' (the game\'s)'}`]].concat(s.choices.map(([l], i) => [String(i), l]));
      let now = '';
      if (settingSet(s, vals)) {
        const i = settingIndex(s, Object.assign({}, base, vals));
        now = i >= 0 ? String(i) : 'keep';
        if (i < 0) opts.push(['keep', 'As set in the file']);
      }
      sel.innerHTML = opts.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
      sel.value = now;
      sel.dataset.start = now;
    });
  }
}
async function loadDeckBase() {
  if (!cur || !cur.settings || !cur.settings.deck) return;
  try {
    const r = await api(`/api/remote/settings/${encodeURIComponent(cur.slug)}`);
    deckBase = r.base || {};
    deckLive = r.source === 'deck' ? (r.values || {}) : null;
    fillQuickForms();
  } catch (e) { /* the defaults stay the renderer's */ }
}
async function applyQuick(k) {
  const values = {};
  $('#qf-' + k).querySelectorAll('select').forEach(sel => {
    const v = sel.value;
    if (v === sel.dataset.start || v === 'keep') return;
    const s = GAME_SETTINGS.find(x => x.id === sel.dataset.id);
    if (v === '') settingKeys(s).forEach(key => { values[key] = null; });
    else Object.assign(values, s.choices[Number(v)][1]);
  });
  if (!Object.keys(values).length) return toast('Nothing changed');
  try {
    const r = await api(`/api/games/${encodeURIComponent(cur.slug)}/settings`, { method: 'PUT', body: { which: k, values } });
    cur.settings[k].text = r.text; cur.settings[k].exists = true;
    const d = (r.deck || {}).deck;
    toast(k !== 'deck' ? 'Saved to ' + r.path
      : d === 'ok' ? 'On the Deck at once (a running game takes them now), and in deck.toml for its next installs'
      : d === 'not installed' ? 'Saved in deck.toml: the game is not on the Deck'
      : 'Saved in deck.toml: the Deck did not answer, the game gets them at its next install', !!d && d !== 'ok' && d !== 'not installed');
    renderGame();
    if (k === 'deck') loadDeckBase();
  } catch (e) { fail(e); }
}
async function saveText(k) {
  try {
    const r = await api(`/api/games/${encodeURIComponent(cur.slug)}/settings`, { method: 'PUT', body: { which: k, text: $('#tx-' + k).value } });
    cur.settings[k].text = r.text;
    toast('Saved to ' + r.path);
    renderGame();
  } catch (e) { fail(e); }
}

// -- capas --------------------------------------------------------------------------------------
let coverPick = {};
async function loadCovers() {
  let c;
  try { c = await api(`/api/games/${encodeURIComponent(cur.slug)}/covers`); } catch (e) { return fail(e); }
  coverPick = Object.assign({ portrait: null, background: 'blur', logo: null }, c.picked || {});
  const img = (it) => it.thumb ? `<img src="/api/games/${encodeURIComponent(cur.slug)}/covers/img/${it.thumb}">` : '';
  const grid = (kind, items) => items.length ? `<div class="picks">${items.map(it => `
    <button class="pick ${it.id === 'blur' ? 'blur' : ''} ${coverPick[kind] === it.id ? 'on' : ''}" data-kind="${kind}" data-id="${esc(it.id)}" onclick="pickCover(this)">
      ${img(it)}<span title="${esc(it.label)}">${esc(it.label)}</span></button>`).join('')}</div>` : '<p class="muted small">Nothing found.</p>';
  const v = Date.now();
  const art = (c.current || []).filter(n => ['portrait', 'grid', 'hero', 'icon', 'logo'].includes(n));
  $('#coverbox').innerHTML = `
    <div class="row"><button class="b p" onclick="autoCovers()">Pick automatically</button>
      <button class="b" onclick="fetchCovers()">Find official covers</button>
      <span class="muted small">XboxUnity (box scans), Xbox 360 Marketplace${'' }, SteamGridDB if there is a key in Settings, and the game's captures.</span></div>
    <h3>Current art (deck/art)</h3>
    ${art.length ? `<div class="artprev">${art.map(n => `<div><img src="/api/games/${encodeURIComponent(cur.slug)}/art/${n}.png?v=${v}" title="${n}"><div class="muted small">${n}</div></div>`).join('')}</div>` : '<p class="muted small">No art yet.</p>'}
    <h3>Cover (portrait 600x900)</h3>${grid('portrait', c.portrait)}
    <h3>Background (grid 920x430 and hero 1920x620)</h3>${grid('background', c.background)}
    ${c.logo.length ? `<h3>Logo (optional)</h3>${grid('logo', c.logo)}` : ''}
    <div class="row" style="margin-top:14px">
      <button class="b p" onclick="composeCovers()">Generate the art</button>
      <button class="b" onclick="deckResend(true)" ${cur.deck ? '' : 'disabled'}>Send the art to the Deck</button>
      <span class="muted small">Sending the art closes Steam on the Deck for a moment (Steam only reads shortcut art when it starts).</span>
    </div>`;
}
function pickCover(el) {
  const kind = el.dataset.kind;
  coverPick[kind] = (kind === 'logo' && coverPick.logo === el.dataset.id) ? null : el.dataset.id;
  document.querySelectorAll(`.pick[data-kind="${kind}"]`).forEach(p => p.classList.toggle('on', p.dataset.id === coverPick[kind]));
}
async function fetchCovers() {
  try {
    const j = await api(`/api/games/${encodeURIComponent(cur.slug)}/covers/fetch`, { body: {} });
    toast('Looking for covers...');
    const slug = cur.slug;
    const wait = async () => {
      const s = await api('/api/jobs/' + j.id);
      if (s.status === 'running' || s.status === 'queued') return setTimeout(wait, 1500);
      if (s.status !== 'ok') toast('Failed: ' + (s.error || ''), true);
      if (cur && cur.slug === slug && curSub === 'capas') loadCovers();
    };
    setTimeout(wait, 1500);
  } catch (e) { fail(e); }
}
async function autoCovers() {
  try {
    const j = await api(`/api/games/${encodeURIComponent(cur.slug)}/covers/auto`, { body: {} });
    toast('The cheap model is picking the covers...');
    const slug = cur.slug;
    const wait = async () => {
      const s = await api('/api/jobs/' + j.id);
      if (s.status === 'running' || s.status === 'queued') return setTimeout(wait, 1500);
      if (s.status !== 'ok') toast('Failed: ' + (s.error || ''), true);
      else toast(s.result.reason || 'Art generated');
      if (cur && cur.slug === slug && curSub === 'capas') loadCovers();
      loadGames();
    };
    setTimeout(wait, 2000);
  } catch (e) { fail(e); }
}
async function composeCovers() {
  if (!coverPick.portrait) return toast('Pick a cover first', true);
  try {
    await api(`/api/games/${encodeURIComponent(cur.slug)}/covers/compose`, { body: coverPick });
    toast('Art generated in deck/art');
    loadCovers();
    loadGames();
  } catch (e) { fail(e); }
}

function gameJobs(g) {
  return jobTable(g.jobs, g.slug) || '<p class="muted">No jobs for this game.</p>';
}

// == Tarefas ===================================================================================
function jobTable(list, back) {
  if (!list || !list.length) return '';
  return `<table><tr><th>Job</th><th>Status</th><th>Started</th><th>Ended</th><th></th></tr>${list.map(j => `
    <tr><td><a href="#" onclick="openJob('${j.id}'${back ? `,'${esc(back)}'` : ''});return false">${esc(j.title)}</a>
      ${j.error ? `<div class="muted small">${esc(j.error.slice(0, 160))}</div>` : ''}
      ${j.result && j.result.claude && j.result.claude.length ? `<div class="small" style="color:#c9b6dd">${j.result.claude.length} fix(es) by Claude</div>` : ''}</td>
    <td>${statusChip(j)} ${j.progress ? progressBar(j.progress) : ''}${waitLine(j.waiting || (j.progress || {}).waiting)}</td><td class="small">${when(j.started || j.created)}</td>
    <td class="small">${when(j.ended)}</td>
    <td>${j.status === 'running' || j.status === 'queued' ? `<button class="b s d" onclick="cancelJob('${j.id}')">Cancel</button>` : ''}</td></tr>`).join('')}</table>`;
}
const JOB_STATUS = { queued: 'queued', running: 'running', ok: 'done', failed: 'failed', cancelled: 'cancelled', interrupted: 'interrupted' };
function statusChip(j) {
  const cls = { ok: 'ok', failed: 'bad', running: 'info', queued: 'warn', cancelled: '', interrupted: 'warn' }[j.status] || '';
  return `<span class="chip ${cls}">${esc(JOB_STATUS[j.status] || j.status_pt || j.status)}</span>`;
}
// A queued job (or a request whose job is queued): what runs before it in the same lane.
function waitLine(w) {
  if (!w) return '';
  if (w.restart) return '<div class="small muted">continues after the app restarts</div>';
  const n = w.ahead ? `${w.ahead} more job${w.ahead > 1 ? 's' : ''} before it` : '';
  const t = w.title ? `waits for ${esc(w.title)}${w.for_s != null ? ' (running for ' + etaText(w.for_s) + ')' : ''}${n ? ', then ' + n : ''}`
    : 'waits: ' + (n || 'another job runs');
  return `<div class="small muted">${t}</div>`;
}
function etaText(s) {
  if (s == null || !isFinite(s)) return '';
  if (s < 90) return `${Math.max(1, Math.round(s))} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}
function progressBar(p) {
  if (p && !p.total && (p.phase || p.step_pt)) {
    const pc = p.pct != null ? Math.min(100, p.pct) : null;
    const txt = [p.step_pt, p.phase].filter(Boolean).join(' · ');
    return `<div class="progress ${pc == null ? 'ind' : ''}" title="${esc(txt)}"><div style="width:${pc == null ? 30 : pc.toFixed(1)}%"></div></div><span class="small muted">${esc(txt)}${pc != null ? ' · ' + pc.toFixed(0) + '%' : ''}${p.step_elapsed || p.elapsed ? ' · ' + etaText(p.step_elapsed || p.elapsed) : ''}</span>`;
  }
  if (!p || !p.total) return '';
  const pc = Math.min(100, 100 * p.done / p.total);
  const more = p.rate ? ` · ${(p.rate / 1e6).toFixed(1)} MB/s${p.done < p.total ? ' · ' + etaText(p.eta) + ' left' : ''}` : '';
  return `<div class="progress" title="${gb(p.done)} of ${gb(p.total)}"><div style="width:${pc.toFixed(1)}%"></div></div><span class="small muted">${pc.toFixed(0)}% · ${gb(p.done)} of ${gb(p.total)}${more}</span>`;
}
let lastJobsHtml = null;
async function loadJobs(quiet) {
  try {
    const r = await api('/api/jobs');
    // Só se mudou alguma coisa: redesenhar as ~100 linhas de 3 em 3 s tirava o botão Cancelar de
    // debaixo do rato.
    const html = jobTable(r.jobs) || '<div class="empty">No jobs yet.</div>';
    if (html !== lastJobsHtml) { $('#joblist').innerHTML = html; lastJobsHtml = html; }
  } catch (e) { if (!quiet) fail(e); }
}
async function clearJobs(which) {
  if (which === 'finished' && !await confirmBox('<h3 style="margin-top:0">Clear finished jobs?</h3><p>Every finished job leaves the list, the ones that worked too (their logs stay in the logs folder). Queued and running jobs stay.</p>', 'Clear')) return;
  try {
    const r = await api('/api/jobs/clear', { body: { which } });
    toast(r.cleared ? `${r.cleared} job(s) cleared` : 'Nothing to clear');
    lastJobsHtml = null;
    loadJobs();
  } catch (e) { fail(e); }
}
async function testGamesDialog() {
  let gs = [];
  try { gs = (await api('/api/games')).games.filter(g => g.built); } catch (e) { return fail(e); }
  gs.sort((a, b) => a.title.localeCompare(b.title));
  const ok = await confirmBox(`<h3 style="margin-top:0">Test games</h3>
    <p class="small muted">Each one is built, started with the native and the classic renderer, and compared (about 5 minutes per game; the game windows open and close on the PC).</p>
    <div style="max-height:320px;overflow:auto;columns:2">${gs.map(g => `<label style="display:block"><input type="checkbox" class="tgame" value="${esc(g.slug)}"> ${esc(g.title)}</label>`).join('')}</div>`, 'Test');
  if (!ok) return;
  const slugs = [...document.querySelectorAll('.tgame')].filter(c => c.checked).map(c => c.value);
  if (!slugs.length) return toast('No game chosen', true);
  try { const j = await api('/api/test-batch', { body: { slugs, label: 'manual' } }); openJob(j.id); } catch (e) { fail(e); }
}
async function cancelJob(id) {
  if (!await confirmBox('<p>Cancel this job? The running process will be stopped.</p>', 'Cancel the job', true)) return;
  try { await api(`/api/jobs/${id}/cancel`, { body: {} }); toast('Cancelled'); overview(); if (jobView === id) tickJob(); } catch (e) { fail(e); }
}

// A vista de uma tarefa: estado, passos (com o que o Claude faz) e o registo ao vivo. O registo
// segue sozinho o passo que está a correr (prepare-1, build-1, boot-1...), ou o que escolheres.
// Quando um download acaba e a preparação continua noutra tarefa, a vista passa para ela.
let jobView = null, jobBack = null, jobOffset = 0, jobTimer = null, jobStepLog = null;
let jobLogAuto = true, jobEvCount = -1, jobFollowed = {}, jobWasLive = {};
async function openJob(id, back) {
  clearTimeout(jobTimer);
  jobView = id; jobBack = back || null; jobOffset = 0; jobStepLog = null; jobLogAuto = true; jobEvCount = -1;
  openDrawer('Job');
  $('#dbody').innerHTML = `
    <div class="row" id="jobhead"><span class="muted">Loading...</span></div>
    <div id="jobnext"></div><div id="joberr"></div><div id="jobfixes"></div><div id="jobsay"></div>
    <h3>Steps</h3><div class="events" id="jobevents"></div>
    <h3>Live log <span class="small muted" id="joblogname"></span></h3>
    <div class="row" id="jobsteps"></div>
    <div class="log" id="joblog" style="margin-top:8px;max-height:460px"></div>
    <label class="small muted"><input type="checkbox" id="jobfollow" checked> follow the end of the log</label>`;
  tickJob();
}
const EV_LABEL = { step: 'step', ok: 'ok', fail: 'failed', claude: 'Claude', 'claude-text': 'Claude', 'claude-tool': 'Claude uses', 'claude-user': 'You', info: 'note' };
// Escrever ao assistente enquanto trabalha (a mensagem entra no que ele está a fazer).
async function jobSay(id) {
  const box = $('#jobsaytext');
  const text = (box.value || '').trim();
  if (!text) return;
  try { await api(`/api/jobs/${id}/say`, { body: { text } }); box.value = ''; toast('Sent: it reads it in what it is doing now'); tickJob(); }
  catch (e) { fail(e); }
}
function evHtml(e) {
  return `<div class="ev ${esc(e.kind)}"><span class="t">${esc(e.t.slice(11))} ${esc(EV_LABEL[e.kind] || e.kind)}</span>${esc(e.text)}${
    e.commits && e.commits.length ? `\n<b>Commits:</b> ${esc(e.commits.join(' · '))}${e.pushed === true ? ' (pushed)' : e.pushed === false ? ' (not pushed)' : ''}` : ''}${
    e.edited && e.edited.length ? `\n<b>Files changed:</b> ${esc(e.edited.join(', '))}` : ''}${
    e.cost ? `\n<span class="muted small" title="With the Claude subscription session (auth login) this is not billed separately: it counts towards the plan's normal usage.">estimated cost at API prices: ${Number(e.cost).toFixed(3)} USD (not billed with the subscription)</span>` : ''}${
    e.job ? ` <a href="#" onclick="openJob('${esc(e.job)}');return false">open</a>` : ''}</div>`;
}
function autoStepLog(j, names) {
  // O registo do último passo que começou: <passo>-<tentativa mais alta>; sem passos, o da tarefa.
  const last = [...j.events].reverse().find(e => e.kind === 'step' && e.step);
  if (!last) return '';
  const mine = names.filter(n => n.startsWith(last.step + '-'))
    .sort((a, b) => Number(b.split('-').pop()) - Number(a.split('-').pop()));
  return mine[0] || '';
}
async function tickJob() {
  const id = jobView;
  if (!id) return;
  clearTimeout(jobTimer);
  let j, steps;
  try { [j, steps] = await Promise.all([api('/api/jobs/' + id), api(`/api/jobs/${id}/steps`)]); }
  catch (e) { jobTimer = setTimeout(tickJob, 4000); return; }
  if (jobView !== id) return;
  const live = j.status === 'running' || j.status === 'queued';
  $('#dtitle').textContent = j.title;
  $('#jobhead').innerHTML = `${jobBack ? `<button class="b s" onclick="openGame('${esc(jobBack)}','tarefas')">← ${esc(jobBack)}</button>` : ''}
    ${statusChip(j)} ${j.progress ? progressBar(j.progress) : ''}${waitLine(j.waiting || (j.progress || {}).waiting)}
    <span class="muted small">${when(j.started || j.created)} → ${j.ended ? when(j.ended) : (live ? 'running' : '-')}</span><span class="grow"></span>
    ${live ? `<button class="b d" onclick="cancelJob('${j.id}')">Cancel</button>` : ''}
    ${j.game && j.game !== 'selftest' ? `<button class="b s" onclick="openGame('${esc(j.game)}')">Open the game</button>` : ''}`;
  $('#joberr').innerHTML = j.error ? `<div class="ev fail" style="margin-top:10px">${esc(j.error)}</div>` : '';
  // Enquanto o assistente trabalha: uma caixa para lhe escrever (fica o que já se escreveu).
  if (!j.chat) $('#jobsay').innerHTML = '';
  else if (!$('#jobsaytext')) $('#jobsay').innerHTML = `<div class="row" style="margin-top:10px;gap:8px">
    <input id="jobsaytext" style="flex:1" placeholder="Write to the assistant while it works (a hint, what you saw, where to look)" onkeydown="if(event.key==='Enter')jobSay('${j.id}')">
    <button class="b p" onclick="jobSay('${j.id}')">Send</button></div>`;
  const fixes = (j.result && j.result.claude) || [];
  $('#jobfixes').innerHTML = fixes.length ? `<h3>What Claude did</h3>${fixes.map(f => `<div class="ev claude"><b>Attempt ${f.attempt} (${esc(f.step)})</b>\n${esc(f.summary)}${f.commits && f.commits.length ? '\n<b>Commits:</b> ' + esc(f.commits.join(' · ')) : ''}</div>`).join('')}` : '';
  if (j.events.length !== jobEvCount) {
    jobEvCount = j.events.length;
    $('#jobevents').innerHTML = j.events.map(evHtml).join('') || '<span class="muted">—</span>';
  }
  // A tarefa seguinte (a preparação depois do download): a vista passa para ela uma vez.
  const next = [...j.events].reverse().find(e => e.job);
  $('#jobnext').innerHTML = next && !live ? `<div class="ev step" style="margin-top:10px">Continues in the next job.
    <button class="b s p" onclick="openJob('${esc(next.job)}')">View the next job</button></div>` : '';
  if (live) jobWasLive[id] = 1;
  if (next && j.status === 'ok' && jobWasLive[id] && !jobFollowed[id]) { jobFollowed[id] = 1; return openJob(next.job, jobBack); }
  // O registo: o do passo a correr (automático) ou o escolhido.
  const names = steps.steps.filter(s => !s.name.includes('claude')).map(s => s.name);
  if (jobLogAuto) {
    const want = autoStepLog(j, names);
    if (want !== (jobStepLog || '')) { jobStepLog = want || null; jobOffset = 0; $('#joblog').textContent = ''; }
  }
  $('#joblogname').textContent = (jobStepLog || 'job') + (jobLogAuto ? ' (follows the current step)' : '');
  $('#jobsteps').innerHTML = `<button class="b s ${jobLogAuto ? 'p' : ''}" onclick="jobLog(null, true)">Automatic</button>` +
    ['', ...names].map(n => `<button class="b s ${!jobLogAuto && n === (jobStepLog || '') ? 'p' : ''}" onclick="jobLog('${n}')">${n ? esc(n) : 'job'}</button>`).join('');
  await pollJobLog();
  if (live) jobTimer = setTimeout(tickJob, 2000);
}
function jobLog(step, auto) {
  jobLogAuto = !!auto;
  jobStepLog = auto ? null : (step || null);
  jobOffset = 0;
  $('#joblog').textContent = '';
  tickJob();
}
async function pollJobLog() {
  if (!jobView) return;
  try {
    const r = await api(`/api/jobs/${jobView}/log?offset=${jobOffset}${jobStepLog ? '&step=' + encodeURIComponent(jobStepLog) : ''}`);
    const el = $('#joblog');
    if (!el) return;
    if (jobOffset === 0) el.textContent = '';
    if (r.text) {
      el.textContent += r.text;
      if (el.textContent.length > 400000) el.textContent = el.textContent.slice(-300000);
      if (!$('#jobfollow') || $('#jobfollow').checked) el.scrollTop = el.scrollHeight;
    }
    jobOffset = r.offset;
  } catch (e) { /* ainda sem registo */ }
}

// == Catálogo ===================================================================================
let cat = null, catSources = new Set(), catKnown = new Set(), catLimit = 300;
async function loadCatalog(refresh) {
  $('#ctable').innerHTML = '<p class="muted">Reading the catalogue...</p>';
  try {
    cat = await api('/api/catalog' + (refresh ? '?refresh=true' : ''));
    loaded.catalog = true;
    // Uma fonte nova (ou as tuas pastas, acabadas de juntar) aparece ligada.
    cat.sources.forEach(s => { if (!catKnown.has(s.item)) { catKnown.add(s.item); catSources.add(s.item); } });
    fillGenres();
    renderSources();
    renderCatalog();
  } catch (e) { $('#ctable').innerHTML = ''; fail(e); }
}
function renderSources() {
  $('#csources').innerHTML = cat.sources.map(s => `<button class="chip ${catSources.has(s.item) ? 'on' : ''}" onclick="toggleSource(${jsq(s.item)})"
    title="${esc(s.item)}${s.error ? ' — ERROR: ' + esc(s.error) : ''}">${esc(s.label)} ${s.error ? '⚠' : `· ${s.count} · ${gb(s.size)}`}</button>`).join('');
}
function toggleSource(item) {
  catSources.has(item) ? catSources.delete(item) : catSources.add(item);
  renderSources(); renderCatalog();
}
['#cfilter', '#conlynew', '#conlydl', '#cgenre', '#csort', '#chidebad'].forEach(s => $(s).addEventListener('input', () => { catLimit = 300; renderCatalog(); }));
function fillGenres() {
  const count = {};
  cat.entries.forEach(e => (e.info && e.info.genres || []).forEach(g => { count[g] = (count[g] || 0) + 1; }));
  const sel = $('#cgenre'), cur = sel.value;
  sel.innerHTML = '<option value="">All genres</option>' + Object.entries(count).sort((a, b) => b[1] - a[1]).slice(0, 40)
    .map(([g, n]) => `<option value="${esc(g)}">${esc(g)} (${n})</option>`).join('');
  sel.value = cur;
}
function catRows() {
  const f = $('#cfilter').value.toLowerCase().split(/\s+/).filter(Boolean);
  const genre = $('#cgenre').value, sort = $('#csort').value;
  const rows = cat.entries.filter(e => catSources.has(e.item) &&
    (!f.length || f.every(w => (e.title + ' ' + e.name).toLowerCase().includes(w))) &&
    (!$('#conlynew').checked || !e.local) && (!$('#conlydl').checked || e.downloaded) &&
    (!genre || (e.info && e.info.genres.includes(genre))) &&
    (!$('#chidebad').checked || !e.unsupported));
  const mc = e => e.info && e.info.mc != null ? e.info.mc : -1;
  const yr = e => e.info && e.info.year ? e.info.year : 0;
  // The players' rating weighed by how many rated (as stores rank): few ratings pull it to 3.5, so
  // 5.0 from 68 players is not above 4.5 from 300 000.
  const rt = e => e.info && e.info.rating != null ? (e.info.rating * (e.info.ratings || 0) + 3.5 * 2000) / ((e.info.ratings || 0) + 2000) : -1;
  if (sort === 'rating') rows.sort((a, b) => rt(b) - rt(a) || a.title.localeCompare(b.title));
  else if (sort === 'mc') rows.sort((a, b) => mc(b) - mc(a) || a.title.localeCompare(b.title));
  else if (sort === 'year') rows.sort((a, b) => yr(b) - yr(a) || a.title.localeCompare(b.title));
  else if (sort === 'size') rows.sort((a, b) => a.size - b.size);
  return rows;
}
function entryState(e) {
  const b = [];
  if (e.unsupported) b.push(`<span class="chip warn" title="The game code is .NET (XNA): ReXGlue cannot run it yet. On the roadmap, for later.">${esc(e.unsupported)} (later)</span>`);
  if (e.local) b.push(`<a href="#" class="chip ok" onclick="openGame('${esc(e.local)}');return false">prepared</a>`);
  if (e.own) b.push(`<span class="chip info" title="${esc(e.path)}">your file · ${esc(OWN_KIND[e.kind] || e.kind)}</span>`);
  else if (e.downloaded === 'sim') b.push('<span class="chip info">downloaded</span>');
  if (e.downloaded === 'parcial') b.push('<span class="chip warn">partial download</span>');
  if (e.job) b.push(`<span data-job="${e.job}"></span>`);
  return b.join(' ');
}
function entryActions(e) {
  if (e.job) return `<button class="b s" onclick="openJob('${e.job}')">View</button>`;
  if (e.unsupported) return `<span class="small muted" title="The game code is .NET, which the console compiles at run time; ReXGlue only runs code recompiled before it starts">for later</span>`;
  const a = [];
  if (e.own) a.push(`<button class="b s p" onclick="preparePath(${jsq(e.path)},${jsq(e.title)})">Prepare</button>`);
  else if (e.downloaded === 'sim') a.push(`<button class="b s p" onclick="prepareDownloaded(${jsq(e.item)},${jsq(e.name)})">Prepare</button>`);
  else {
    a.push(`<button class="b s p" onclick="download(${jsq(e.item)},${jsq(e.name)},${e.size},'prepare')">${e.downloaded ? 'Resume' : 'Download'} and prepare</button>`);
    a.push(`<button class="b s" onclick="download(${jsq(e.item)},${jsq(e.name)},${e.size},null)">Download only</button>`);
  }
  return a.join(' ');
}
// O catálogo em capas (como no Deck) ou em lista; um clique abre a ficha do jogo (openCatStore).
let catView = (() => { try { return localStorage.getItem('gestor-catview') || 'grid'; } catch (e) { return 'grid'; } })();
let catShown = [];
function setCatView(v) {
  catView = v;
  try { localStorage.setItem('gestor-catview', v); } catch (e) { /* */ }
  renderCatalog();
}
function catTile(e, i) {
  const b = [];
  if (e.unsupported) b.push(`<span class="r">${esc(e.unsupported)}</span>`);
  if (e.local) b.push('<span class="g">In My games</span>');
  else if (e.own) b.push('<span class="b">Your file</span>');
  else if (e.downloaded === 'sim') b.push('<span class="b">Downloaded</span>');
  else if (e.downloaded === 'parcial') b.push('<span class="w">Partial</span>');
  if (e.job) b.push(`<span class="w" data-job="${e.job}">Working…</span>`);
  const mc = e.info && e.info.mc;
  const g = (e.info && e.info.genres || []).slice(0, 2).join(', ');
  return `<div class="ctile" tabindex="0" onclick="openCatStore(${i})" onkeydown="if(event.key==='Enter')openCatStore(${i})" title="${esc(e.name)}">
    <div class="cv"><img loading="lazy" src="${catCover(e)}" alt=""><div class="badges">${b.join('')}</div>
      ${mc ? `<div class="mcb ${mc >= 75 ? 'h' : mc >= 50 ? 'm' : 'l'}">${mc}</div>` : ''}</div>
    <div class="nm">${esc(e.title)}</div>
    <div class="sub">${[e.info && e.info.year, g].filter(Boolean).map(esc).join(' · ') || '&nbsp;'}</div>
    ${e.info && e.info.rating != null ? `<div class="sub"><span class="stars sm">★</span> ${e.info.rating.toFixed(1)} <span class="muted">· ${(e.info.ratings || 0).toLocaleString()} ratings</span></div>` : ''}
    <div class="sub">${esc([gb(e.size), (e.tags || []).join(' ')].filter(Boolean).join(' · '))}</div></div>`;
}
function renderCatalog() {
  if (!cat) return;
  const rows = catRows();
  catShown = rows;
  const x = cat.xna || {};
  const head = `<div class="row" style="justify-content:space-between;margin-top:6px"><p class="muted small" style="margin:0">${rows.length} of ${cat.entries.length} files
    · ${x.count || 0} XNA game(s), flagged${$('#chidebad').checked ? ' and hidden' : ''} (${x.scanned || 0} XBLA archives checked)
    <a href="#" onclick="xnaScan();return false">scan for XNA</a> · click a game for its page</p>
    <span class="seg"><button class="${catView === 'grid' ? 'on' : ''}" onclick="setCatView('grid')">Covers</button><button class="${catView === 'list' ? 'on' : ''}" onclick="setCatView('list')">List</button></span></div>`;
  const more = rows.length > catLimit ? `<div class="row" style="margin-top:14px"><button class="b" onclick="catLimit+=${catView === 'grid' ? 240 : 500};renderCatalog()">Show more</button></div>` : '';
  if (catView === 'grid') {
    $('#ctable').innerHTML = head + `<div class="cgrid">${rows.slice(0, catLimit).map(catTile).join('')}</div>` + more;
    updateCatalogProgress();
    return;
  }
  $('#ctable').innerHTML = head + `
    <table><tr><th>Game</th><th>Genre</th><th class="num">Year</th><th class="num">Score</th><th>Region</th><th>Source</th><th class="num">Size</th><th>Status</th><th></th></tr>
    ${rows.slice(0, catLimit).map((e, i) => `<tr><td title="${esc(e.name)}"><a class="tlink" onclick="openCatStore(${i})">${esc(e.title)}</a></td>
      <td class="small">${esc(genreTxt(e.info))}</td><td class="num small">${e.info && e.info.year || ''}</td>
      <td class="num">${e.info ? mcChip(e.info.mc) : ''}</td>
      <td>${e.tags.map(t => `<span class="chip">${esc(t)}</span>`).join(' ')}</td><td class="small muted">${esc(e.source)}</td>
      <td class="num">${gb(e.size)}</td><td>${entryState(e)}</td><td>${entryActions(e)}</td></tr>`).join('')}</table>
    ${more}`;
  updateCatalogProgress();
}
async function updateCatalogProgress() {
  const spans = document.querySelectorAll('#ctable [data-job]');
  if (!spans.length) return;
  const byId = Object.fromEntries(active.map(j => [j.id, j]));
  let gone = false;
  spans.forEach(s => {
    const j = byId[s.dataset.job];
    if (j) s.innerHTML = j.progress ? progressBar(j.progress) : statusChip(j);
    else gone = true;
  });
  if (gone) { const c = await api('/api/catalog'); cat.entries = c.entries; renderCatalog(); loadDownloads(); }
}
// -- a ficha do jogo, como a da loja (market.py: o Marketplace da Xbox 360 e a Wikidata) ------------
// Abre-se no catálogo (um jogo dos ficheiros) e em Os meus jogos (um jogo preparado): o fundo, a
// caixa, os géneros, as notas, a descrição, as capturas e os modos de jogo.
let storeShots = [], storeShot = 0;
const storeImg = (tid, n) => `/api/market/img/${encodeURIComponent(tid)}/${encodeURIComponent(n)}`;
function stars(r) {
  if (r == null) return '';
  const full = Math.floor(r), half = r - full >= 0.25 && r - full < 0.75 ? 1 : 0, up = r - full >= 0.75 ? 1 : 0;
  const n = full + up;
  return '<span class="stars" aria-label="' + r + ' of 5">' + '★'.repeat(n) + (half ? '<span class="half">★</span>' : '') +
    '<span class="off">' + '★'.repeat(Math.max(0, 5 - n - half)) + '</span></span>';
}
function fmtDate(d) {
  if (!d) return '';
  const t = new Date(d + 'T00:00:00');
  return isNaN(t) ? d : t.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
}
// o: {title, xbla, slug, entry (do catálogo), acts (HTML dos botões)}
async function openStore(o) {
  const d = $('#store');
  d.innerHTML = `<div class="st-wrap"><button class="st-x" onclick="closeStore()" title="Close (Esc)">✕</button>
    <div class="st-hero st-loading"><div class="st-hin"><img class="st-box" src="${o.cover || ''}" alt="">
    <div class="st-head"><div class="st-kick">${o.xbla ? 'Xbox Live Arcade' : 'Xbox 360'}</div><h1>${esc(o.title)}</h1>
    <div class="muted">Reading the game's page…</div></div></div></div></div>`;
  d.showModal();
  const q = new URLSearchParams();
  if (o.title) q.set('title', o.title);
  if (o.slug) q.set('slug', o.slug);
  if (o.xbla != null) q.set('xbla', o.xbla ? 1 : 0);
  let c;
  try { c = await api('/api/card?' + q); } catch (e) { c = { title: o.title, genres: [], screens: [], modes: [], features: [], images: {} }; }
  if (!d.open) return;
  d.innerHTML = storeHtml(c, o);
}
function storeHtml(c, o) {
  const e = o.entry || {};
  const im = c.images || {};
  const bg = c.tid && im.background ? storeImg(c.tid, im.background) : null;
  const box = c.tid && im.boxart ? storeImg(c.tid, im.boxart) : o.cover;
  storeShots = (c.screens || []).map(n => storeImg(c.tid, n));
  const by = [(c.publishers || [])[0], (c.developers || [])[0] !== (c.publishers || [])[0] ? (c.developers || [])[0] : null, c.year].filter(Boolean);
  const facts = [];
  if ((c.developers || []).length) facts.push(['Developer', c.developers.join(', ')]);
  if ((c.publishers || []).length) facts.push(['Publisher', c.publishers.join(', ')]);
  if (c.released) facts.push(['Released', fmtDate(c.released)]);
  else if (c.year) facts.push(['Released', String(c.year)]);
  if (e.size) facts.push([e.own ? 'Size' : 'Download', gb(e.size)]);
  if ((e.tags || []).length) facts.push(['Region', e.tags.join(', ')]);
  if (e.source) facts.push(['Source', e.own ? 'Your files' : e.source]);
  if (e.name) facts.push(['File', e.name]);
  if ((c.languages || []).length) facts.push(['Languages', c.languages.join(', ')]);
  if (c.achievements && c.achievements.count) facts.push(['Achievements', `${c.achievements.count} · ${c.achievements.gamerscore} G${c.achievements.unlocked ? ` (${c.achievements.unlocked} unlocked)` : ''}`]);
  if (c.tid) facts.push(['Title ID', c.tid]);
  storeMore = similarGames(c.genres || [], [c.title, o.title, e.title]);
  const desc = (c.description || '').split(/\n{2,}/).map(p => `<p>${esc(p.trim())}</p>`).join('');
  return `<div class="st-wrap"><button class="st-x" onclick="closeStore()" title="Close (Esc)">✕</button>
    <div class="st-hero" ${bg ? `style="--hero:url('${bg}')"` : ''}><div class="st-hin">
      <img class="st-box" src="${box || ''}" alt="" onerror="this.style.visibility='hidden'">
      <div class="st-head">
        <div class="st-kick">${o.xbla ? 'Xbox Live Arcade' : 'Xbox 360'}${c.store ? ' · Xbox 360 Marketplace' : ''}</div>
        <h1>${esc(c.title || o.title)}</h1>
        ${by.length ? `<div class="st-by">${by.map(esc).join(' · ')}</div>` : ''}
        ${(c.genres || []).length ? `<div class="st-genres">${c.genres.map(g => `<span>${esc(g)}</span>`).join('')}</div>` : ''}
        <div class="st-scores">
          ${c.rating != null ? `<div>${stars(c.rating)} <b>${c.rating.toFixed(1)}</b><span class="muted"> · ${c.ratings.toLocaleString()} player ratings</span></div>` : ''}
          ${c.mc ? `<div><span class="mc ${c.mc >= 75 ? 'h' : c.mc >= 50 ? 'm' : 'l'}">${c.mc}</span> Metacritic</div>` : ''}
        </div>
        <div class="st-acts">${o.acts || ''}</div>
      </div></div></div>
    <div class="st-body">
      <div class="st-main">
        ${desc ? `<div class="st-desc">${desc}<div class="small muted">${c.description_from === 'store' ? 'From the Xbox 360 Marketplace' : 'From Wikipedia'}${c.wiki ? ` · <a href="${esc(c.wiki)}" target="_blank" rel="noopener">Wikipedia</a>` : ''}</div></div>`
          : `<p class="muted">No description${c.pending ? ' yet: the Marketplace list is still being read, try again in a minute' : ''}.</p>`}
        ${storeShots.length ? `<h3>Screenshots</h3><div class="st-shots">${storeShots.slice(0, 6).map((u, i) => `<button onclick="storeView(${i})"><img loading="lazy" src="${u}" alt="">${i === 5 && storeShots.length > 6 ? `<span class="st-plus">+${storeShots.length - 6}</span>` : ''}</button>`).join('')}</div>` : ''}
        ${storeMore.length ? `<h3>More like this</h3><div class="st-more">${storeMore.map((x, i) => `<button onclick="openStoreMore(${i})" title="${esc(x.title)}">
          <img loading="lazy" src="${catCover(x)}" alt=""><span>${esc(x.title)}</span></button>`).join('')}</div>` : ''}
      </div>
      <aside class="st-side">
        ${(c.modes || []).length ? `<h3>Play</h3><div class="kv">${c.modes.map(([k, v]) => `<div>${esc(k)}</div><div>${esc(v)}</div>`).join('')}</div>` : ''}
        ${(c.features || []).length ? `<h3>Features</h3><div class="st-feats">${c.features.map(f => `<span>${esc(f)}</span>`).join('')}</div>` : ''}
        ${facts.length ? `<h3>Details</h3><div class="kv">${facts.map(([k, v]) => `<div>${esc(k)}</div><div style="overflow-wrap:anywhere">${esc(v)}</div>`).join('')}</div>` : ''}
      </aside>
    </div>
    <div class="st-view" id="stview" onclick="if(event.target===this)storeViewClose()"><button class="st-x" onclick="storeViewClose()">✕</button>
      <button class="st-nav l" onclick="storeView(storeShot-1)">‹</button><img id="stvimg" alt=""><button class="st-nav r" onclick="storeView(storeShot+1)">›</button></div>
  </div>`;
}
// More like this: the catalogue's games with the most genres in common (then the best rated).
let storeMore = [];
function similarGames(genres, not) {
  if (!cat || !(genres || []).length) return [];
  const want = new Set(genres.map(x => x.toLowerCase()));
  const skip = new Set(not.filter(Boolean).map(x => x.toLowerCase()));
  const seen = new Set();
  return cat.entries.filter(x => x.info && !skip.has(x.title.toLowerCase()) && !x.unsupported)
    .map(x => ({ x, n: (x.info.genres || []).filter(g => want.has(g.toLowerCase())).length }))
    .filter(r => r.n > 0)
    .sort((a, b) => b.n - a.n || ((b.x.info.rating || 0) * 20 + (b.x.info.mc || 0)) - ((a.x.info.rating || 0) * 20 + (a.x.info.mc || 0)))
    .map(r => r.x).filter(x => !seen.has(x.title.toLowerCase()) && seen.add(x.title.toLowerCase())).slice(0, 8);
}
function openStoreMore(i) {
  const e = storeMore[i];
  if (!e) return;
  const acts = entryActions(e).replace(/class="b s( p)?"/g, (m, p) => `class="b${p ? ' p' : ''} big"`) +
    (e.local ? ` <button class="b big" onclick="closeStore();openGame('${esc(e.local)}')">Open in My games</button>` : '');
  openStore({ title: e.title, xbla: e.xbla, slug: e.local || null, entry: e, acts, cover: catCover(e) });
}
function storeView(i) {
  const v = $('#stview');
  if (!v || !storeShots.length) return;
  storeShot = (i + storeShots.length) % storeShots.length;
  $('#stvimg').src = storeShots[storeShot];
  v.classList.add('on');
}
function storeViewClose() { const v = $('#stview'); if (v) v.classList.remove('on'); }
function closeStore() { const d = $('#store'); if (d.open) d.close(); }
document.addEventListener('keydown', ev => {
  const d = $('#store'), v = $('#stview');
  if (!d || !d.open || !v || !v.classList.contains('on')) return;
  if (ev.key === 'ArrowRight') { storeView(storeShot + 1); ev.preventDefault(); }
  else if (ev.key === 'ArrowLeft') { storeView(storeShot - 1); ev.preventDefault(); }
  else if (ev.key === 'Escape') { storeViewClose(); ev.preventDefault(); }
});
// um jogo do catálogo (as ações do catálogo: descarregar, preparar, ver a tarefa)
function openCatStore(i) {
  const e = catShown[i];
  if (!e) return;
  const acts = entryActions(e).replace(/class="b s( p)?"/g, (m, p) => `class="b${p ? ' p' : ''} big"`) +
    (e.local ? ` <button class="b big" onclick="closeStore();openGame('${esc(e.local)}')">Open in My games</button>` : '');
  openStore({ title: e.title, xbla: e.xbla, slug: e.local || null, entry: e, acts, cover: catCover(e) });
}
const catCover = e => '/api/remote/cover?t=' + encodeURIComponent(e.title) + (e.local ? '&slug=' + encodeURIComponent(e.local) : '') + (e.xbla ? '&a=1' : '');
async function xnaScan() {
  try { const j = await api('/api/xna/scan', { body: {} }); toast('Scanning for XNA games (without downloading)'); openJob(j.id); } catch (e) { fail(e); }
}
async function download(item, name, size, then) {
  if (!await confirmBox(`<p>Download <b>${esc(name)}</b> (${gb(size)}) from <i>${esc(item)}</i>?</p>
      <p class="muted small">It goes to the downloads folder (Settings). It resumes if interrupted and checks the MD5.${then === 'prepare' ? ' Then it is prepared: extraction, title update, DLC, codegen, build and boot test.' : ''}</p>`, 'Download')) return;
  try {
    const j = await api('/api/download', { body: { item, name, then } });
    toast('Download queued: ' + j.title);
    overview();
    openJob(j.id);
    const e = cat && cat.entries.find(x => x.item === item && x.name === name);
    if (e) { e.job = j.id; renderCatalog(); }
  } catch (e) { fail(e); }
}
async function prepareDownloaded(item, name) {
  const files = (await api('/api/downloads')).files;
  const f = files.find(x => x.item === item && x.name === name.split('/').pop());
  if (!f) return toast('Could not find the downloaded file', true);
  return preparePath(f.path, name);
}
async function preparePath(path, name) {
  if (!await confirmBox(`<p>Prepare <b>${esc(name || path)}</b>?</p><p class="muted small">Extraction, title update (XboxUnity), DLC, codegen, layer, build and boot test on the PC; if something fails, the assistant tries to fix it.</p>`, 'Prepare')) return;
  try { const j = await api('/api/prepare', { body: { path } }); toast('Queued: ' + j.title); openJob(j.id); } catch (e) { fail(e); }
}

// -- os teus jogos: um dump numa pasta, um .iso, um .7z/.zip/.rar, um pacote do Xbox Live ----------
const OWN_KIND = { folder: 'dump folder', iso: 'disc image', archive: 'archive', package: 'Xbox Live package' };
function addOwnGame() {
  const d = $('#dlg');
  $('#dlgbody').innerHTML = `<h3 style="margin-top:0">Add your own game</h3>
    <p class="small muted">A game as you have it: a <b>dump folder</b> (with <code>default.xex</code>), a <b>disc image</b> (.iso),
      an <b>archive</b> (.7z, .zip, .rar) or an <b>Xbox Live package</b>. The app prepares, builds and tests it like a game from the
      catalogue (nothing is downloaded but its title update, and DLC from your DLC sources in the Settings); then install it on the Deck from My games.</p>
    <input id="ownpath" style="width:100%" placeholder="The file or folder (paste its path, or choose it)" oninput="ownCheckSoon()">
    <div class="row" style="margin-top:8px"><button class="b" onclick="ownPick('file')">Choose a file…</button>
      <button class="b" onclick="ownPick('folder')">Choose a folder…</button></div>
    <p id="ownwhat" class="small" style="min-height:18px;margin:10px 0 0"></p>
    <p class="small" style="margin:14px 0 6px"><b>Its DLC</b> <span class="muted">(optional): Xbox Live packages, archives (.rar, .7z, .zip) or folders with them, one per line.
      Only the packages for this game are installed.</span></p>
    <textarea id="owndlc" style="width:100%;min-height:54px" placeholder="Paste their paths, or choose them"></textarea>
    <div class="row" style="margin-top:6px"><button class="b" onclick="ownPickDlc('dlc')">Choose DLC files…</button>
      <button class="b" onclick="ownPickDlc('dlc-folder')">Choose a DLC folder…</button></div>
    <p class="small muted" style="margin-top:14px">A folder with many games? <a href="#" onclick="ownAddDir();return false">Add it to your game folders</a>:
      its games show in the catalogue, here and in Deck mode (where Install takes them straight to the Deck).</p>
    <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="b" id="ownno">Cancel</button>
      <button class="b p" id="ownok" disabled>Prepare, build and test</button></div>`;
  d.showModal();
  $('#ownno').onclick = () => d.close();
  $('#ownok').onclick = async () => {
    const dlc = $('#owndlc').value.split('\n').map(l => l.trim()).filter(Boolean);
    try { const j = await api('/api/prepare', { body: { path: $('#ownpath').value, dlc } }); d.close(); toast('Queued: ' + j.title); openJob(j.id); } catch (e) { fail(e); }
  };
}
async function ownPickDlc(what) {
  try {
    const r = await api('/api/own/pick?what=' + what);
    if (!r.path) return;
    const box = $('#owndlc');
    const have = box.value.split('\n').map(l => l.trim()).filter(Boolean);
    box.value = have.concat(r.path.split('\n').filter(p => p && !have.includes(p))).join('\n');
  } catch (e) { fail(e); }
}
async function ownPick(what) {
  $('#ownwhat').innerHTML = '<span class="muted">The Windows window is open (it may be behind the browser)…</span>';
  try {
    const r = await api('/api/own/pick?what=' + what);
    if (r.path) { $('#ownpath').value = r.path; ownCheck(); } else $('#ownwhat').textContent = '';
  } catch (e) { $('#ownwhat').textContent = e.message; }
}
let ownTimer = null;
function ownCheckSoon() { clearTimeout(ownTimer); ownTimer = setTimeout(ownCheck, 400); }
async function ownCheck() {
  const p = $('#ownpath').value.trim();
  const ok = $('#ownok');
  if (!p) { $('#ownwhat').textContent = ''; ok.disabled = true; return; }
  try {
    const r = await api('/api/own/check', { body: { path: p } });
    ok.disabled = !r.ok;
    $('#ownwhat').innerHTML = r.ok ? `<span style="color:#9be27d">✓ ${esc(r.what)}: <b>${esc(r.title)}</b></span>${r.path !== p ? ` <span class="muted">(${esc(r.path)})</span>` : ''}`
      : `<span style="color:#f2c46b">${esc(r.why)}</span>`;
  } catch (e) { ok.disabled = true; $('#ownwhat').textContent = e.message; }
}
async function ownAddDir() {
  let p = $('#ownpath') ? $('#ownpath').value.trim() : '';
  if (!p) { const r = await api('/api/own/pick?what=folder').catch(fail); p = r && r.path; }
  if (!p) return;
  try {
    const r = await api('/api/own/dirs', { body: { path: p } });
    toast(`${r.found} game(s) in that folder: they are in the catalogue (Your files)`);
    $('#dlg').close();
    loadCatalog(false);
  } catch (e) { fail(e); }
}
async function loadDownloads() {
  try {
    const r = await api('/api/downloads');
    $('#dlfiles').innerHTML = `<p class="muted small">${esc(r.dir)} — ${r.free_gb.toFixed(1)} GB free</p>` + (r.files.length ? `<table>
      <tr><th>File</th><th>Item</th><th class="num">Size</th><th></th></tr>
      ${r.files.map(f => `<tr><td>${esc(f.name)}</td><td class="small muted">${esc(f.item)}</td><td class="num">${gb(f.size)}</td>
        <td>${f.prepared ? `<a class="chip ok" href="#" onclick="openGame('${esc(f.slug)}');return false">prepared</a>` : `<button class="b s p" onclick="preparePath(${jsq(f.path)},${jsq(f.name)})">Prepare</button>`}
        <button class="b s d" onclick="deleteDownload(${jsq(f.path)},${jsq(f.name)})">Delete</button></td></tr>`).join('')}</table>` : '<p class="muted">Nothing downloaded yet.</p>');
  } catch (e) { fail(e); }
}
async function deleteDownload(path, name) {
  if (!await confirmBox(`<p>Delete the archive <b>${esc(name)}</b> from disk?</p><p class="muted small">Only the downloaded archive; the prepared game (work folder) stays.</p>`, 'Delete', true)) return;
  try { await api('/api/downloads/delete', { body: { path, confirm: name } }); toast('Deleted'); loadDownloads(); } catch (e) { fail(e); }
}

// -- pesquisa no Internet Archive ------------------------------------------------------------------
$('#iaq').addEventListener('keydown', e => { if (e.key === 'Enter') iaSearch(); });
async function iaSearch() {
  const q = $('#iaq').value.trim();
  if (!q) return;
  $('#iaresults').innerHTML = '<p class="muted">Searching...</p>';
  try {
    const r = await api(`/api/search?q=${encodeURIComponent(q)}&xbox=${$('#iaxbox').checked}`);
    $('#iaresults').innerHTML = r.results.length ? `<table><tr><th>Item</th><th class="num">Size</th><th class="num">Downloads</th><th></th></tr>
      ${r.results.map(x => `<tr><td><b>${esc(x.title)}</b><div class="small muted">${esc(x.identifier)}</div><div id="ia-${esc(x.identifier)}"></div></td>
        <td class="num">${gb(x.item_size)}</td><td class="num">${x.downloads ?? '-'}</td>
        <td><button class="b s" onclick="iaItem(${jsq(x.identifier)})">View files</button></td></tr>`).join('')}</table>` : '<p class="muted">Nothing found.</p>';
  } catch (e) { $('#iaresults').innerHTML = ''; fail(e); }
}
async function iaItem(id) {
  const box = document.getElementById('ia-' + id);
  box.innerHTML = '<p class="muted small">Reading the item...</p>';
  try {
    const r = await api('/api/item/' + encodeURIComponent(id));
    box.innerHTML = `${r.restricted ? '<p class="small" style="color:#f2c46b">Restricted item: needs the archive.org keys (already set up for downloads).</p>' : ''}
      ${r.files.length ? `<table>${r.files.map(f => `<tr><td class="small">${esc(f.name)}</td><td class="num small">${gb(f.size)}</td>
        <td>${f.downloaded === 'sim' ? '<span class="chip info">downloaded</span>' : `<button class="b s p" onclick="download(${jsq(id)},${jsq(f.name)},${f.size},'prepare')">Download and prepare</button>
        <button class="b s" onclick="download(${jsq(id)},${jsq(f.name)},${f.size},null)">Download only</button>`}</td></tr>`).join('')}</table>` : '<p class="muted small">No game files (.rar, .7z, .zip, .iso).</p>'}
      <button class="b s" onclick="addSource(${jsq(id)})">Add this item to the catalogue sources</button>`;
  } catch (e) { box.innerHTML = ''; fail(e); }
}
async function addSource(item) {
  try {
    const cfg = await api('/api/config');
    if (cfg.sources.some(s => s.item === item)) return toast('Already a source');
    cfg.sources.push({ item, label: item });
    await api('/api/config', { method: 'PUT', body: { sources: cfg.sources } });
    toast('Source added');
    catSources.add(item);
    loadCatalog(false);
  } catch (e) { fail(e); }
}

// == Steam Deck =================================================================================
let deckData = null, conn = null, lastDeckSig = null, diag = null, found = null;

async function loadConn() {
  try { conn = await api('/api/deck/connection'); } catch (e) { return fail(e); }
  renderConn();
}
function renderSetupTimer(s) {
  const el = $('#setuptimer');
  if (el && s && s.until) el.textContent = Math.max(0, Math.round((s.until * 1000 - Date.now()) / 60000)) + ' min';
}
function renderConn() {
  const c = conn, w = c.watch || {};
  const s = c.setup || {};
  const ok = w.online;
  const diagHtml = diag ? `<div style="margin-top:12px">${diag.steps.map(st => `<div>${st.ok ? '✅' : '❌'} <b>${esc(st.name)}</b> <span class="muted">${esc(st.text)}</span></div>`).join('')}
    ${diag.ok ? `<div class="kv" style="margin-top:8px"><div>Deck</div><div>${esc(diag.info.host)} · ${esc(diag.info.os)}</div>
      <div>Battery</div><div>${esc(diag.info.battery || '?')}% ${esc(diag.info.charging || '')}</div><div>Uptime</div><div>${esc(diag.info.uptime)}</div>
      <div>IP</div><div>${esc(diag.info.ip)}</div><div>Playing</div><div>${diag.info.playing ? '<span class="chip warn">yes</span> ' + esc(diag.info.playing) : 'no'}</div>
      <div>Steam</div><div>${diag.info.steam ? 'open' : 'closed'}</div></div>` : ''}
    ${diag.fix ? `<div class="ev info" style="margin-top:8px">${esc(diag.fix)}</div>` : ''}
    <div class="row" style="margin-top:8px">
      ${diag.trust === 'new' ? `<button class="b p" onclick="trustDeck(false)">Trust this Deck</button>` : ''}
      ${diag.trust === 'changed' ? `<button class="b d" onclick="trustDeck(true)">Forget the old key and trust</button>` : ''}
      ${diag.needs_setup && !s.running ? `<button class="b p" onclick="setupSsh()">Turn on SSH on the Deck</button>` : ''}
    </div>
    ${diag.public_key ? `<p class="small muted">The PC's public key (to add by hand to the Deck's ~/.ssh/authorized_keys):</p><div class="log">${esc(diag.public_key)}</div>` : ''}</div>` : '';
  const foundHtml = found ? `<h3>On the network (${found.scanned} addresses in ${esc(found.networks.join(', '))})</h3>
    ${found.found.length ? `<table><tr><th>Address</th><th>Name</th><th>Key login</th><th></th></tr>${found.found.map(f => `<tr>
      <td>${esc(f.addr)}:${f.port}<div class="small muted">${esc(f.banner)}</div></td>
      <td>${esc(f.hostname || f.name || '-')} ${f.steamos ? '<span class="chip ok">SteamOS</span>' : ''}</td>
      <td>${f.login ? '<span class="chip ok">yes</span>' : `<span class="chip warn">no</span> <span class="small muted">${esc(f.error || '')}</span>`}</td>
      <td><button class="b s ${f.login ? 'p' : ''}" onclick="useHost(${jsq(f.host)})">Use</button></td></tr>`).join('')}</table>`
      : '<p class="muted">No SSH server found (is the Deck on and on the same network? Is its SSH turned on?)</p>'}` : '';
  $('#deckconn').innerHTML = `
    <div class="row"><b>Deck connection</b>
      <span class="chip ${ok ? 'ok' : ok === false ? 'bad' : ''}">${ok ? 'online' : ok === false ? 'offline' : 'checking...'}</span>
      <span class="small muted">${w.since ? 'since ' + when(w.since) : ''} · checked every 20 s</span></div>
    <div class="form" style="margin-top:10px">
      <label>Address (user@IP:port)</label><input id="cnhost" value="${esc(c.host)}">
      <label>SSH key</label><input id="cnkey" value="${esc(c.key)}">
      <label>Save as (optional)</label><input id="cnname" placeholder="e.g. Deck at home">
    </div>
    <div class="row" style="margin-top:10px">
      <button class="b p" onclick="testDeck()">Test the connection</button>
      <button class="b" onclick="useHost($('#cnhost').value, $('#cnkey').value, $('#cnname').value)">Save and use</button>
      <button class="b" onclick="discoverDeck()">Search the network</button>
      ${s.running ? `<button class="b d" onclick="setupSsh('stop')">Stop the SSH helper</button>` : `<button class="b" onclick="setupSsh()">Turn on SSH on the Deck</button>`}
    </div>
    ${s.running ? `<div class="ev step" style="margin-top:10px">On the Deck: Desktop Mode → Konsole, and run (the PC serves the script for another <span id="setuptimer"></span>):
<div class="row" style="margin-top:6px"><code class="log" style="flex:1;margin:0">${esc(s.command)}</code><button class="b s" onclick="navigator.clipboard.writeText(${jsq(s.command)});toast('Copied')">Copy</button></div>
<span class="small muted">Starts an SSH server as the deck user on the port of the address above, which only accepts this PC's key (no sudo; it stops when the Deck restarts). If Windows asks whether Python may accept connections on the private network, that is your call.</span></div>` : ''}
    ${(c.profiles || []).length ? `<h3>Saved connections</h3><table>${c.profiles.map(p => `<tr><td><b>${esc(p.name)}</b></td><td>${esc(p.host)}</td><td class="small muted">${esc(p.key)}</td>
      <td>${p.host === c.host ? '<span class="chip ok">in use</span>' : `<button class="b s" onclick="useHost(${jsq(p.host)}, ${jsq(p.key)})">Use</button>`}
      <button class="b s d" onclick="delProfile(${jsq(p.name)})">Delete</button></td></tr>`).join('')}</table>` : ''}
    <div id="diagbox">${diagHtml}</div>${foundHtml}`;
  renderSetupTimer(s);
}
async function testDeck() {
  $('#diagbox').innerHTML = '<p class="muted">Testing...</p>';
  try { diag = await api('/api/deck/test', { body: { host: $('#cnhost').value, key: $('#cnkey').value } }); } catch (e) { diag = null; fail(e); }
  renderConn();
}
async function useHost(host, key, name) {
  try {
    const body = { host };
    if (key !== undefined) body.key = key;
    if (name) body.name = name;
    conn = await api('/api/deck/use', { body });
    toast('Using ' + host);
    diag = null; renderConn(); testDeck();
  } catch (e) { fail(e); }
}
async function delProfile(name) {
  try { conn = await api('/api/deck/profiles/delete', { body: { name } }); renderConn(); } catch (e) { fail(e); }
}
async function discoverDeck() {
  found = null;
  $('#diagbox').innerHTML = '<p class="muted">Looking for SSH servers on the local network (a few seconds)...</p>';
  try { found = await api('/api/deck/discover', { body: {} }); } catch (e) { fail(e); }
  renderConn();
}
async function trustDeck(forget) {
  if (forget && !await confirmBox('<p>The host key for this address has changed. Only continue if you are sure it is your Deck (for example, it was reinstalled): any other device with this IP would then be accepted.</p>', 'Forget and trust', true)) return;
  try {
    const r = await api('/api/deck/trust', { body: { host: $('#cnhost').value, forget_old: !!forget } });
    toast(r.ok ? 'Deck key saved' : 'Did not work: ' + r.text, !r.ok);
    testDeck();
  } catch (e) { fail(e); }
}
async function setupSsh(action) {
  try {
    const s = await api('/api/deck/setup', { body: { action: action || 'start' } });
    conn.setup = s; renderConn();
  } catch (e) { fail(e); }
}
async function deckBatch(mode) {
  const rebuild = mode === 'rebuild';
  if (!await confirmBox(`<h3 style="margin-top:0">${rebuild ? 'Rebuild' : 'Update'} all the games on the Deck</h3>
    <p>${rebuild ? 'Every Deck game without the latest ReXNative fixes is built again, tested (also with the Deck settings) and sent, one after the other (about 5 minutes per game).'
      : 'Every Deck game with a newer build on the PC (or an unfinished send) gets it, one after the other.'} One job, one notice at the end.</p>`,
    rebuild ? 'Rebuild all' : 'Update all')) return;
  try { const j = await api('/api/deck/' + (rebuild ? 'rebuild-all' : 'update-all'), { body: {} }); openJob(j.id); } catch (e) { fail(e); }
}
// -- a ligação com o Deck num relance: responde?, o que espera por ele, versões do lançador e do plugin --
let linkTimer = null;
async function loadLink() {
  clearTimeout(linkTimer);
  let r;
  try { r = await api('/api/deck/link'); } catch (e) { return; }
  const box = $('#decklink');
  if (!box) return;
  const kit = r.kit || {}, pl = r.plugin || {};
  const ago = t => t ? when(t) : '-';
  const KIND = { deck: 'Send', 'deck-batch': 'Batch', 'deck-report': 'Report', order: 'Request', 'deck-gestor': 'Launcher',
    'deck-plugin': 'Plugin', 'deck-flush': 'Steam shortcuts', 'deck-play': 'Play', 'deck-delete': 'Delete', 'deck-restore': 'Restore' };
  const waits = r.jobs || [];
  box.innerHTML = `<div class="link">
    <div class="lk ${r.online ? 'on' : r.online === false ? 'off' : ''}">
      <div class="dot"></div><div><b>${r.online ? 'The Deck answers' : r.online === false ? 'The Deck does not answer' : 'Checking the Deck…'}</b>
      <div class="small muted">${r.online ? 'since ' + ago(r.since) : r.online === false ? (r.since ? 'since ' + ago(r.since) + ' · ' : '') + 'asleep, off or on another network: what needs it waits and goes on by itself when it is back' : ''}</div>
      ${!r.online && r.detail ? `<div class="small" style="color:#ff9b94;margin-top:2px">${esc(r.detail)}</div>` : ''}</div></div>
    <div class="lk"><div><b>${waits.length ? waits.length + ' waiting for the Deck' : 'Nothing waiting'}</b>
      ${waits.slice(0, 4).map(j => `<div class="small"><a href="#" onclick="openJob('${j.id}');return false">${esc(KIND[j.kind] || j.kind)}: ${esc(j.title)}</a>
        <span class="muted">${esc(j.status === 'queued' ? 'queued' : j.phase || 'running')}</span></div>`).join('')}
      ${waits.length > 4 ? `<div class="small muted">and ${waits.length - 4} more (Jobs)</div>` : ''}
      ${(r.add || []).length || (r.remove || []).length ? `<div class="small muted">Steam library: ${[(r.add || []).length ? (r.add.length + ' to add') : '', (r.remove || []).length ? (r.remove.length + ' to remove') : ''].filter(Boolean).join(', ')} when the Manager closes on the Deck</div>` : ''}</div></div>
    <div class="lk"><div><b>On the Deck</b>
      <div class="small">Launcher ${kit.on_deck ? 'v' + esc(kit.on_deck) : '<span class="muted">unknown</span>'}${kit.outdated ? ` <span class="chip warn">v${esc(kit.latest)} ready</span> <a href="#" onclick="linkUpdate('kit');return false">Update</a>` : kit.on_deck ? ' <span class="chip ok">latest</span>' : ''}</div>
      <div class="small">Decky plugin ${pl.on_deck ? 'v' + esc(pl.on_deck) : '<span class="muted">not seen</span>'}${pl.outdated ? ` <span class="chip warn">v${esc(pl.latest)} ready</span> <a href="#" onclick="linkUpdate('plugin');return false">Update</a>` : pl.on_deck ? ' <span class="chip ok">latest</span>' : ''}</div>
      <div class="small muted">This PC: Manager v${esc(r.running || '?')}</div></div></div></div>`;
  if (tab === 'deck') linkTimer = setTimeout(loadLink, 20000);
}
async function linkUpdate(what) {
  try { const j = await api('/api/deck/link/update', { body: { what } }); toast(j.title + ': it runs when the Deck answers'); loadLink(); } catch (e) { fail(e); }
}
async function loadDeck(refresh) {
  loadLink();
  $('#deckwhen').textContent = refresh ? 'Reading the Deck over SSH...' : '';
  try {
    deckData = await api('/api/deck' + (refresh ? '?refresh=true' : ''));
    loaded.deck = true;
    renderDeck();
  } catch (e) { fail(e); }
}
function renderDeck() {
  const d = deckData || {};
  $('#deckwhen').textContent = d.at ? 'Read ' + when(d.at) + (d.cached ? ' (cache)' : '') : 'Not read yet';
  const sp = d.space || {};
  const bars = Object.entries(sp).map(([k, s]) => `<div style="min-width:260px" class="grow"><div class="row"><b>${k === 'sd' ? 'microSD card' : 'Internal storage'}</b><span class="grow"></span>
      <span>${gb(s.free)} free of ${gb(s.total)}</span></div><div class="bar"><div style="width:${(100 * (1 - s.free / s.total)).toFixed(1)}%"></div></div></div>`).join('');
  const work = Object.fromEntries(gamesData.map(g => [g.slug, g]));
  const rows = (d.games || []).map(g => `<tr><td><input type="checkbox" class="dsel" value="${esc(g.slug)}" onchange="deckSelChanged()"></td>
    <td><b>${esc(g.shortcut ? g.shortcut.name : g.slug)}</b><div class="small muted">${esc(g.path)}</div></td>
    <td>${g.where === 'sd' ? 'microSD' : 'internal'}</td><td class="num" title="${g.size_old ? 'measured in an earlier read (the Deck is not measured while a game is open)' : ''}">${gb(g.size)}${g.size_old ? '*' : ''}</td>
    <td>${g.saves && g.saves.length ? `${g.saves.length} (${gb(g.saves_size)})` : '<span class="muted">none</span>'}</td>
    <td class="small">${g.last_played ? when(g.last_played) : '-'}</td>
    <td>${g.shortcut ? `<span class="chip ok" title="appid ${g.shortcut.appid}">yes</span>` : '<span class="chip warn">no</span>'}
      ${g.complete === false ? '<span class="chip bad" title="play.sh is missing: the transfer did not finish">incomplete transfer</span>' : ''}
      ${g.removed_mark ? '<span class="chip warn" title="deleted by the app, then another program sent it again (no shortcut)">back after deletion</span>' : ''}</td>
    <td>${work[g.slug] && work[g.slug].active_job ? `<button class="b s" onclick="openJob('${work[g.slug].active_job}')">View job</button>`
        : work[g.slug] && (!g.shortcut || g.complete === false) ? `<button class="b s" title="sends what is missing and adds the Steam shortcut" onclick="deckComplete(${jsq(g.slug)})">Complete</button>` : ''}
      ${work[g.slug] ? `<button class="b s" onclick="openGame('${esc(g.slug)}')">Open</button>` : ''}
      <button class="b s d" onclick="deckDelete('${esc(g.slug)}')">Delete</button></td></tr>`).join('');
  $('#deckstate').innerHTML = `
    <div class="panel"><div class="row">
      <span class="chip ${d.reachable ? 'ok' : 'bad'}">${d.reachable ? 'online' : 'unreachable'}</span>
      ${d.reachable ? `<span class="chip ${d.playing ? 'warn' : ''}">${d.playing ? 'playing: ' + esc(d.playing_title || 'AppId ' + d.playing_appid) : 'nobody playing'}</span>
      <span class="chip">${d.steam ? 'Steam open' : 'Steam closed'}</span>` : ''}
      ${d.sd ? `<span class="chip info">microSD at ${esc(d.sd)}</span>` : '<span class="chip">no microSD card</span>'}
      ${d.error ? `<span class="small" style="color:#ff9b94">${esc(d.error)}</span>` : ''}</div>
      <div class="row" style="margin-top:12px;gap:24px">${bars}</div></div>
    ${(d.foreign || []).length ? `<div class="ev fail" style="margin:10px 0">Another program on the PC is sending games to the Deck (${esc([...new Set(d.foreign.map(f => f.game || 'pid ' + f.pid))].join(', '))}). This app's Deck jobs wait for it to finish; a game deleted here is marked and <code>rexnative deck</code> will not send it again.</div>` : ''}
    ${d.measured === false ? '<p class="small muted">* While a game is open on the Deck, sizes are not measured (so as not to load the disk while someone plays): these are from the previous read.</p>' : ''}
    <h2>Installed games (${(d.games || []).length})</h2>
    <div class="row" style="margin-bottom:8px"><button class="b d" id="dseldel" onclick="deckDeleteSelected()" disabled>Delete selected</button>
      <span class="small muted">Steam closes and reopens only once for all of them</span></div>
    ${rows ? `<table><tr><th><input type="checkbox" title="all" onchange="document.querySelectorAll('.dsel').forEach(c => c.checked = this.checked); deckSelChanged()"></th><th>Game</th><th>Where</th><th class="num">Size</th><th>Saves</th><th>Last played</th><th>Steam shortcut</th><th></th></tr>${rows}</table>` : '<p class="muted">None (or the Deck has not been read yet).</p>'}
    <h2>Backups</h2><div id="backups" class="muted small">Reading...</div>`;
  loadBackups();
}
async function loadBackups() {
  let r;
  try { r = await api('/api/deck/backups'); } catch (e) { return; }
  const installed = new Set(((deckData || {}).games || []).map(g => g.slug));
  $('#backups').innerHTML = r.backups.length ? `<p class="small muted">${esc(r.dir)}</p><table>
    <tr><th>Game</th><th>Created</th><th class="num">Size</th><th>Contents</th><th></th></tr>${r.backups.map(b => `<tr>
      <td>${esc(b.slug)}</td><td class="small">${when(b.at)}</td><td class="num">${gb(b.size)}</td>
      <td class="small">${b.entries} entries · ${b.saves} save file(s)${b.settings.length ? ' · ' + esc(b.settings.join(', ')) : ''}</td>
      <td><button class="b s" ${installed.has(b.slug) ? '' : 'disabled title="install the game on the Deck first"'} onclick="restoreBackup(${jsq(b.slug)}, ${jsq(b.file)})">Restore to the Deck</button></td></tr>`).join('')}</table>`
    : '<p class="muted">None yet (they are made when a game is deleted from the Deck).</p>';
}
async function restoreBackup(slug, file) {
  if (!await confirmBox(`<p>Restore <b>${esc(file)}</b> into the ${esc(slug)} folder on the Deck?</p><p class="muted small">The saves and settings in the backup replace any files there with the same name.</p>`, 'Restore')) return;
  try { const j = await api('/api/deck/restore', { body: { slug, file } }); openJob(j.id); } catch (e) { fail(e); }
}
function deckSelChanged() {
  const n = document.querySelectorAll('.dsel:checked').length;
  const b = $('#dseldel');
  if (b) { b.disabled = !n; b.textContent = n ? `Delete selected (${n})` : 'Delete selected'; }
}
async function deckDeleteSelected() {
  const slugs = [...document.querySelectorAll('.dsel:checked')].map(c => c.value);
  const gs = (deckData.games || []).filter(g => slugs.includes(g.slug));
  if (!gs.length) return;
  const withSaves = gs.filter(g => g.saves && g.saves.length);
  const total = gs.reduce((a, g) => a + (g.size || 0), 0);
  const ok = await confirmBox(`<h3 style="margin-top:0">Delete ${gs.length} game(s) from the Steam Deck</h3>
    <div style="max-height:220px;overflow:auto">${gs.map(g => `<div>${esc(g.shortcut ? g.shortcut.name : g.slug)} <span class="muted small">— ${gb(g.size)}${g.saves && g.saves.length ? ', <b style="color:#f2c46b">' + g.saves.length + ' save(s)</b>' : ''}</span></div>`).join('')}</div>
    <p>${total ? gb(total) + ' in total. ' : ''}${withSaves.length ? `<b style="color:#f2c46b">${withSaves.length} have saves</b>, which are inside the folders and go with them.` : 'No saves found.'}
      The Steam shortcuts are removed too (Steam on the Deck closes and reopens once).</p>
    <label><input type="checkbox" id="delbackupm" checked> First back up each game's saves and settings to the PC</label>
    <p class="small muted">This cannot be undone.</p>`, `Delete ${gs.length}`, true);
  if (!ok) return;
  try {
    const j = await api('/api/deck/delete-many', { body: { slugs: gs.map(g => g.slug), confirm: gs.length, backup: $('#delbackupm').checked } });
    openJob(j.id);
  } catch (e) { fail(e); }
}
async function deckComplete(slug) {
  const g = (deckData.games || []).find(x => x.slug === slug) || {};
  if (!await confirmBox(`<p>Complete <b>${esc(slug)}</b> on the Deck?</p><p class="muted small">Sends only what is missing${g.shortcut ? '' : ' and adds the Steam shortcut (Steam on the Deck closes and reopens)'}.</p>`, 'Complete')) return;
  try {
    const j = await api(`/api/games/${encodeURIComponent(slug)}/deck`, { body: { action: 'install', root: g.where === 'sd' ? 'sd' : null, try: 0 } });
    openJob(j.id, slug);
  } catch (e) { fail(e); }
}
async function deckDelete(slug) {
  const g = (deckData.games || []).find(x => x.slug === slug);
  if (!g) return;
  const ok = await confirmBox(`<h3 style="margin-top:0">Delete from the Steam Deck</h3>
    <p><b>${esc(g.shortcut ? g.shortcut.name : slug)}</b> — ${gb(g.size)} in <code>${esc(g.path)}</code></p>
    <p>${g.saves && g.saves.length ? `<b style="color:#f2c46b">It has ${g.saves.length} save(s)</b> (${gb(g.saves_size)}), which are inside the game folder (userdata/) and go with it.` : 'No saves found.'}
      ${g.shortcut ? ' The Steam shortcut is removed too (Steam on the Deck closes and reopens).' : ''}</p>
    <label><input type="checkbox" id="delbackup" checked> First back up the saves and settings to the PC</label>
    <p class="small muted">This cannot be undone (the backup restores the saves after you reinstall the game).</p>`, 'Delete', true);
  if (!ok) return;
  try {
    // A janela confirmada é a confirmação; a API pede o nome da pasta para nada apagar por engano.
    const j = await api('/api/deck/delete', { body: { slug, confirm: slug, backup: $('#delbackup').checked } });
    openJob(j.id);
  } catch (e) { fail(e); }
}

// == Definições =================================================================================
const SETTINGS = [
  ['Sources and folders', [
    ['sources', 'Catalogue sources (item | label, one per line)', 'sources'],
    ['own_dirs', 'Your game folders: dumps (a folder with default.xex), .iso, .7z/.zip/.rar or Xbox Live packages (one folder per line)', 'lines'],
    ['dlc_sources', 'DLC sources: a folder with an archive per game (.rar, .7z, .zip), or an archive.org item (its id or address), one per line. None: games are prepared without DLC', 'lines'],
    ['download_dir', 'Downloads folder'], ['work_dir', 'Folder for new games (prepare --work)'],
    ['work_roots', 'Folders with prepared games (one per line)', 'lines'],
    ['data_dir', 'App data (logs, covers, backups)'],
    ['max_downloads', 'Simultaneous downloads (restart the app)', 'int']]],
  ['ReXNative', [
    ['channel', 'Updates of ReXNative and of this app: stable (the releases, tested) or dev (every change, for testing them)', 'select:stable,dev'],
    ['rexnative_dir', 'ReXNative copy to build with (worktree)'], ['python', 'Python (empty: the one the app uses)'],
    ['report_lane', 'Reports run beside the builds, in a ReXNative copy of their own', 'bool'],
    ['report_rexnative_dir', 'ReXNative copy for reports (empty: the one above with -reports)'],
    ['prepare_lane', 'New games are prepared beside the builds, in a ReXNative copy of their own', 'bool'],
    ['prepare_rexnative_dir', 'ReXNative copy for new games (empty: the one above with -prepare)'],
    ['env', 'Environment variables (NAME=value, one per line)', 'env'],
    ['prepare_args', 'Prepare options', 'args'],
    ['boot_seconds', 'Boot test: seconds', 'int'], ['boot_seconds_max', 'Boot test: maximum without stats', 'int'],
    ['boot_min_frames', 'Boot test: minimum frames', 'int'],
    ['rebuild_tests', 'Rebuilds also open the game to test it (the boot test, and the Deck settings test for games on the Deck)', 'bool'],
    ['compare_enabled', 'Compare native with classic after the test', 'bool'],
    ['compare_route', 'Buttons in both runs (sec:buttons, to get past the title screen)'],
    ['compare_auto_report', 'If native has errors, ask Claude (strong model) to investigate', 'bool'],
    ['test_suspects_after_fix', 'After a ReXNative fix, test the suspect games Claude points out', 'bool']]],
  ['AI assistant', [
    ['linux_enabled', 'Linux builds (experimental): a native Linux build per game, on request, in WSL', 'bool'],
    ['linux_wsl_distro', 'WSL distribution for Linux builds (empty: the default one)'],
    ['linux_sdk', 'ReXGlue SDK built for Linux (its install folder, a path inside WSL)'],
    ['agent', 'Assistant that fixes and investigates (Claude Code, OpenAI Codex with a ChatGPT account, Gemini CLI, Antigravity CLI, or a local model)', 'select:claude,codex,gemini,antigravity,local'],
    ['local_provider', 'Local model server (agent = local)', 'select:ollama,lmstudio'],
    ['local_url', 'Local server address (empty: http://127.0.0.1:11434 for Ollama, :1234 for LM Studio)'],
    ['agent_exe', 'Its program (empty: search for it; for Claude Code use the field below)'],
    ['agent_model', 'Model for fixing games (Codex, Gemini, Antigravity, local; empty: the default, gpt-oss:20b for local)'],
    ['agent_cheap_model', 'Model for comparing captures and picking covers: it must see images (empty: the default, gemma3 for local)'],
    ['agent_trailer', 'Co-author line of the commits the assistant makes (empty: its own)'],
    ['agent_rules', 'Extra rules for the assistant on this PC (one per line)', 'lines']]],
  ['Claude Code', [
    ['claude_enabled', 'Fix failures with the assistant', 'bool'], ['claude_exe', 'claude.exe (empty: search for it)'],
    ['claude_model', 'Model for fixing games (opus recommended)'],
    ['claude_effort', 'Effort for fixing games', 'select:high,xhigh,max,medium,low'],
    ['claude_cheap_model', 'Cheap model (covers, self-test)'],
    ['claude_permission_mode', 'Permission mode', 'select:auto,acceptEdits,dontAsk,bypassPermissions'],
    ['claude_max_attempts', 'Attempts per job', 'int'], ['claude_push', 'Push the ReXNative fixes', 'bool'],
    ['claude_budget_usd', 'Cost limit per fix in USD (empty: no limit)']]],
  ['Steam Deck and covers', [
    ['deck_host', 'Deck (user@address:port)'], ['deck_key', 'SSH key'],
    ['deck_try_seconds', 'Deck test: seconds', 'int'], ['steamgriddb_key', 'SteamGridDB API key (optional)', 'secret']]],
];
let cfg = null;
// -- Modo Deck: o Gestor no Steam Deck ------------------------------------------------------------
let lanTimer = null;
async function loadLan() {
  let d;
  try { d = await api('/api/lan'); } catch (e) { return; }
  const s = d.servers, g = d.gestor || {};
  const devs = d.devices.map(x => `<tr><td>${esc(x.name)}</td><td class="small">${x.kind === 'deck' ? 'the Manager on the Deck' : 'paired with a code'}</td>
    <td class="small">${x.last_seen ? when(new Date(x.last_seen * 1000).toISOString()) + ' (' + esc(x.ip || '') + ')' : 'not connected yet'}</td>
    <td><button class="b s d" onclick="lanRevoke('${x.id}')">Revoke</button></td></tr>`).join('');
  const pend = d.pending || { add: {}, remove: {} };
  const np = Object.keys(pend.add).length + Object.keys(pend.remove).length;
  $('#lanpanel').innerHTML = `<h2>Deck mode</h2><div class="panel">
    <p style="margin-top:0">The <b>Manager on the Steam Deck</b>: a shortcut in the Steam library that opens this app full screen on the Deck,
      so you can pick games from the catalogue with the controller. The PC does the work (download, prepare, build, test) and the game goes to the Deck.</p>
    <div class="row" style="gap:10px;flex-wrap:wrap">
      <label class="row" style="gap:8px"><input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="lanEnable(this.checked)"> Accept connections from the home network (paired devices only)</label>
      <span class="chip ${s.listening.length ? 'ok' : ''}">${s.listening.length ? 'on the network: ' + esc(s.urls.join(' · ')) : 'this PC only'}</span>
      ${s.error ? `<span class="chip bad">${esc(s.error)}</span>` : ''}
    </div>
    <div class="row" style="gap:10px;margin-top:12px;flex-wrap:wrap">
      <button class="b p" onclick="lanInstallDeck()">${g.appid ? 'Reinstall the Manager on the Deck' : 'Install the Manager on the Deck'}</button>
      <span class="small muted">${g.appid ? `Installed ${when(new Date(g.at * 1000).toISOString())} (shortcut ${g.appid}, in ${esc(g.dir || '')})` : 'Opens the app to the network, writes the access on the Deck over SSH and adds the Manager shortcut to the library (Steam closes once).'}</span>
      ${ver && ver.kit && ver.kit.outdated ? `<span class="chip warn">launcher v${esc(ver.kit.on_deck)} on the Deck: v${esc(ver.kit.latest)} available (Reinstall updates it)</span>` : ''}
      ${ver && ver.plugin && ver.plugin.outdated ? `<span class="chip warn">Decky plugin v${esc(ver.plugin.on_deck)} on the Deck: v${esc(ver.plugin.latest)} available</span>` : ''}
    </div>
    <div class="row" style="gap:10px;margin-top:12px;flex-wrap:wrap">
      <button class="b" onclick="pluginToDeck()">${ver && ver.plugin && ver.plugin.on_deck ? 'Update the Decky plugin on the Deck' : 'Install the Decky plugin on the Deck'}</button>
      <span class="small muted">Copies it to ~/Downloads on the Deck and Decky installs it. Plugin here: v${esc((ver && ver.plugin && ver.plugin.latest) || '?')}${ver && ver.plugin && ver.plugin.on_deck ? ', on the Deck: v' + esc(ver.plugin.on_deck) : ''}.</span>
    </div>
    <div class="row" style="gap:10px;margin-top:12px;flex-wrap:wrap">
      <button class="b" onclick="lanPair()">Pair another device</button>
      ${d.pairing.code ? `<span class="chip warn" style="font-size:18px;letter-spacing:3px">${d.pairing.code}</span><span class="small muted">valid for ${Math.ceil(d.pairing.left / 60)} min: open ${esc((s.urls[0] || '') + '/deck')} on that device and enter the code</span>` : '<span class="small muted">a phone or another PC, through the network address</span>'}
    </div>
    <div class="row" style="gap:10px;margin-top:12px;flex-wrap:wrap">
      <label class="row" style="gap:8px"><input type="checkbox" ${d.autostart ? 'checked' : ''} onchange="lanAutostart(this.checked)"> Start the Manager with Windows (minimised), so the Deck can always find it</label>
    </div>
    ${np ? `<div class="row" style="gap:10px;margin-top:12px"><span class="chip warn">${np} shortcut(s) waiting for Steam on the Deck to close</span>
      <button class="b s" onclick="lanFlush()">Add to the library now</button><span class="small muted">Steam on the Deck closes and reopens</span></div>` : ''}
    ${devs ? `<table style="margin-top:14px"><tr><th>Device</th><th>How</th><th>Last connection</th><th></th></tr>${devs}</table>` : ''}
  </div>`;
  clearTimeout(lanTimer);
  if (d.pairing.code) lanTimer = setTimeout(() => { if ($('#tab-settings').classList.contains('on')) loadLan(); }, 10000);
}
async function lanEnable(on) { try { await api('/api/lan/enable', { body: { on } }); } catch (e) { fail(e); } loadLan(); }
async function lanPair() { try { await api('/api/lan/pair', { body: {} }); } catch (e) { fail(e); } loadLan(); }
async function lanRevoke(id) {
  if (!await confirmBox('<p>Revoke this device? It will not be able to open the Manager until it is paired again.</p>', 'Revoke', true)) return;
  try { await api('/api/lan/revoke', { body: { id } }); } catch (e) { fail(e); } loadLan();
}
async function lanAutostart(on) { try { await api('/api/autostart', { body: { on } }); } catch (e) { fail(e); } loadLan(); }
async function lanInstallDeck() {
  if (!await confirmBox(`<h3 style="margin-top:0">Install the Manager on the Steam Deck</h3>
    <p>The app starts accepting connections from the home network, from paired devices only. The Deck is paired
      right away (access goes over SSH), gets the launcher in ~/.local/share/gestor-rexnative and the Manager shortcut is added to the library:
      Steam on the Deck closes and reopens once. Nobody can be playing.</p>`, 'Install')) return;
  try { const j = await api('/api/lan/install-deck', { body: {} }); openJob(j.id); } catch (e) { fail(e); }
}
async function pluginToDeck() {
  if (!await confirmBox(`<h3 style="margin-top:0">Decky plugin on the Deck</h3>
    <p>Copies the plugin (v${esc((ver && ver.plugin && ver.plugin.latest) || '?')}) to ~/Downloads on the Deck and Decky installs it
      (it replaces the one there and reloads it: a few seconds). Not while a game is open.</p>`, 'Install')) return;
  try { const j = await api('/api/deck/plugin', { body: { prompt: true } }); openJob(j.id); } catch (e) { fail(e); }
}
async function lanFlush() { try { const j = await api('/api/deck/flush', { body: {} }); openJob(j.id); } catch (e) { fail(e); } }

async function loadSettings() {
  loadLan();
  try { cfg = await api('/api/config'); } catch (e) { return fail(e); }
  const field = ([k, label, kind]) => {
    const v = cfg[k];
    let input;
    if (kind === 'sources') input = `<textarea data-k="${k}" data-kind="sources" style="min-height:150px">${esc(v.map(s => s.item + (s.label && s.label !== s.item ? ' | ' + s.label : '')).join('\n'))}</textarea>`;
    else if (kind === 'lines') input = `<textarea data-k="${k}" data-kind="lines" style="min-height:70px">${esc(v.join('\n'))}</textarea>`;
    else if (kind === 'env') input = `<textarea data-k="${k}" data-kind="env" style="min-height:150px">${esc(Object.entries(v).map(([a, b]) => a + '=' + b).join('\n'))}</textarea>`;
    else if (kind === 'args') input = `<input data-k="${k}" data-kind="args" value="${esc(v.join(' '))}">`;
    else if (kind === 'bool') input = `<input type="checkbox" data-k="${k}" data-kind="bool" ${v ? 'checked' : ''}>`;
    else if (kind === 'int') input = `<input type="number" data-k="${k}" data-kind="int" value="${esc(v)}">`;
    else if (kind && kind.startsWith('select:')) input = `<select data-k="${k}">${kind.slice(7).split(',').map(o => `<option ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
    else input = `<input data-k="${k}" ${kind === 'secret' ? 'type="password"' : ''} value="${esc(v)}">`;
    return `<label>${esc(label)}</label>${input}`;
  };
  $('#settingsform').innerHTML = SETTINGS.map(([title, fields]) => `<h2>${esc(title)}</h2><div class="form panel">${fields.map(field).join('')}</div>`).join('') + `
    <div class="row" style="margin-top:14px"><button class="b p" onclick="saveSettings()">Save</button>
      <button class="b" onclick="claudeCheck()">Test the assistant</button>
      <button class="b" onclick="claudeSelftest()">Fixing self-test</button><span id="claudecheck" class="small muted"></span></div>
    <p class="muted small">claude.exe found: ${esc(cfg._claude_exe || 'none')} · Settings in ${esc(cfg._config_path)}</p>
    <h2>ReXNative (the app's copy)</h2><div class="panel"><div class="row"><span id="rexstatus" class="small muted">...</span><span class="grow"></span>
      <button class="b" onclick="rexSync()">Update now</button></div>
      <p class="small muted">A worktree just for this app: other sessions work in other copies, so Claude's commits don't get mixed up and builds don't pick up half-finished work. Before each job it moves to the latest published version of main (if it has no uncommitted changes).</p></div>
    <h2>ReXGlue SDK</h2><div class="panel" id="sdkpanel"><span class="small muted">Reading…</span></div>
    <h2>Game information</h2><div class="panel"><div class="row"><span id="infostatus" class="small muted">...</span><span class="grow"></span>
      <button class="b" onclick="infoRefresh()">Update now</button></div>
      <p class="small muted">Genre, year, developer and Metacritic score, from Wikidata (free data) and the review tables of the English Wikipedia; refreshed automatically every 14 days.</p></div>`;
  api('/api/rexnative?fetch=true').then(r => { $('#rexstatus').innerHTML = r.exists ? `${esc(r.dir)} · <b>${esc(r.head)}</b>${
      r.behind ? ` · <span style="color:#f2c46b">${r.behind} published commit(s) to pull</span>` : ' · up to date'}${
      r.ahead ? ` · ${r.ahead} to push` : ''}${r.dirty && r.dirty.length ? ` · <span style="color:#f2c46b">${r.dirty.length} uncommitted file(s)</span>` : ''}`
    : `<span style="color:#ff9b94">${esc(r.dir)} does not exist</span>`; }).catch(() => {});
  loadSdk(false);
  api('/api/info').then(i => { $('#infostatus').textContent = i.fetched ? `${i.games} Xbox 360 games, ${i.with_genre} with a genre, ${i.with_mc} with a Metacritic score · read ${when(i.fetched)}${i.refreshing ? ' · updating...' : ''}` : (i.refreshing ? 'Reading for the first time...' : 'Not read yet'); });
}
async function saveSettings() {
  const out = {};
  document.querySelectorAll('#settingsform [data-k]').forEach(el => {
    const k = el.dataset.k, kind = el.dataset.kind;
    if (kind === 'sources') out[k] = el.value.split('\n').map(l => l.trim()).filter(Boolean).map(l => { const [item, label] = l.split('|').map(s => s.trim()); return { item, label: label || item }; });
    else if (kind === 'lines') out[k] = el.value.split('\n').map(l => l.trim()).filter(Boolean);
    else if (kind === 'env') out[k] = Object.fromEntries(el.value.split('\n').map(l => l.trim()).filter(l => l.includes('=')).map(l => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));
    else if (kind === 'args') out[k] = el.value.split(/\s+/).filter(Boolean);
    else if (kind === 'bool') out[k] = el.checked;
    else if (kind === 'int') out[k] = Number(el.value);
    else out[k] = el.value;
  });
  try { await api('/api/config', { method: 'PUT', body: out }); toast('Settings saved'); loaded.catalog = false; loadSettings(); } catch (e) { fail(e); }
}
async function loadSdk(fetch) {
  let s;
  try { s = await api('/api/sdk' + (fetch ? '?fetch=true' : '')); } catch (e) { return; }
  const r = s.releases || {};
  const rel = (x, label) => x ? `<div class="small"><b>${label}: ${esc(x.tag)}</b> <span class="muted">${esc((x.date || '').slice(0, 10))}</span>
      ${x.notes && x.notes.length ? `<div class="muted" style="white-space:pre-wrap;max-height:110px;overflow:auto;margin:4px 0 8px">${esc(x.notes.join('\n'))}</div>` : ''}</div>` : '';
  $('#sdkpanel').innerHTML = `<div class="row"><span class="small">Installed <b>${esc(s.version || '?')}</b> · ${esc(s.describe || '')}
      · ${(s.ours || []).length} change(s) of ours on top of the official SDK
      ${s.new_count ? ` · <span style="color:#f2c46b">${s.new_count} new official commit(s)</span>` : ' · nothing new in the official SDK'}${!s.new_count && (s.release_marks || []).length ? ` <span class="small muted" title="${esc(s.release_marks.join('\n'))}">(${s.release_marks.length} release mark(s) that change no file)</span>` : ''}</span>
      <span class="grow"></span><button class="b" onclick="loadSdk(true)">Check now</button>
      ${s.new_count ? '<button class="b p" onclick="sdkUpdate()">Update and rebuild the SDK</button>' : ''}</div>
    ${(s.new || []).length ? `<div class="small muted" style="max-height:120px;overflow:auto;margin:6px 0">${s.new.map(esc).join('<br>')}</div>` : ''}
    ${rel(r.stable, 'Latest release')}${rel(r.nightly, 'Latest nightly')}
    <p class="small muted">${esc(s.source || '')} → ${esc(s.install || '')}. Updating brings the official commits, puts our changes back on top and builds the SDK
      (the state before stays in a backup/sdk-… branch; on a conflict nothing changes). The games then show "new SDK" to rebuild.</p>`;
}
async function sdkUpdate() {
  if (!await confirmBox(`<h3 style="margin-top:0">Update and rebuild the ReXGlue SDK?</h3>
    <p>Brings the new official commits, puts our changes back on top and builds the SDK (this takes a while; no game builds meanwhile,
      and it waits for builds of other sessions). If our changes conflict with the new ones, nothing changes.
      Afterwards every game shows "new SDK" and needs a rebuild.</p>`, 'Update the SDK')) return;
  try { const j = await api('/api/sdk/update', { body: {} }); openJob(j.id); } catch (e) { fail(e); }
}
async function rexSync() {
  try { const j = await api('/api/rexnative/sync', { body: {} }); openJob(j.id); } catch (e) { fail(e); }
}
async function infoRefresh() {
  try { const j = await api('/api/info/refresh', { body: {} }); openJob(j.id); } catch (e) { fail(e); }
}
async function claudeSelftest() {
  try { const j = await api('/api/claude/selftest', { body: {} }); openJob(j.id); } catch (e) { fail(e); }
}
async function claudeCheck() {
  $('#claudecheck').textContent = 'Asking Claude...';
  try {
    const r = await api('/api/claude/check');
    $('#claudecheck').innerHTML = `<span style="color:${r.ok ? '#9be27d' : '#ff9b94'}">${esc(r.message)}</span>`;
  } catch (e) { $('#claudecheck').textContent = e.message; }
}

// -- o registo do ReXNative (Changelog) -----------------------------------------------------------
// Os commits do main, por dia: a área, os jogos de que falam (os de cá com o que a compilação do PC
// e a do Deck já têm), a descrição ao abrir. Ao lado, os jogos de cá e quantas mudanças lhes faltam.
let logData = null, logSeenAt = null;
const logF = { q: '', area: 'all', game: null, mode: 'mentions' };
const logOpen = new Set(), logBranchOpen = new Set();
async function loadLog(refresh) {
  if (refresh) $('#logsub').textContent = 'Asking GitHub…';
  try {
    const d = await api('/api/rexlog' + (refresh ? '?refresh=true' : ''));
    logData = d;
    if (logSeenAt === null) logSeenAt = RL.seen() || d.head;  // o que era novo quando se abriu
    renderLog();
    if (tab === 'log') { RL.markSeen(d); logBadge(); }
    if (refresh) toast('ReXNative changelog up to date');
  } catch (e) { $('#logsub').textContent = 'Could not read the changelog: ' + e.message; }
}
function logBadge() {
  const n = tab === 'log' ? 0 : RL.newCount(logData);
  const el = $('#logcount');
  el.hidden = !n; el.textContent = n;
}
async function logPeek() {
  try { logData = await api('/api/rexlog'); logBadge(); } catch (e) { /* */ }
}
let logTimer = null;
function logSearch() { clearTimeout(logTimer); logTimer = setTimeout(() => { logF.q = $('#logq').value; renderLog(); }, 180); }
function setLogArea(a) { logF.area = a; renderLog(); }
function setLogGame(gi, mode) {
  logF.game = gi; logF.mode = mode || 'mentions';
  renderLog();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function toggleLog(sha) {
  if (logOpen.has(sha)) logOpen.delete(sha); else logOpen.add(sha);
  const el = document.getElementById('e-' + sha);
  if (el) el.classList.toggle('open');
}
function toggleBranch(n) { if (logBranchOpen.has(n)) logBranchOpen.delete(n); else logBranchOpen.add(n); renderLog(); }
function logChip(d, gi, inSubj, c, i) {
  const n = d.names[gi], g = RL.mineOf(d, gi);
  const st = g && i != null ? RL.state(g, c, i, RL.index(d)) : null;
  const cls = st ? RL.STATE[st][0] : g ? '' : 'other';
  const tip = n.t + (st ? ': ' + RL.STATE[st][1] : g ? '' : ': not in your library') + (inSubj ? '' : ' (mentioned in the description)');
  return `<span class="gchip ${cls} ${inSubj ? '' : 'body'}" title="${esc(tip)}" onclick="event.stopPropagation();setLogGame(${gi}, 'mentions')"><span class="dt"></span>${esc(n.n)}</span>`;
}
function logReach(d, c, i) {
  if (c.build && i != null) {
    const idx = RL.index(d);
    const deckGames = d.mine.filter(g => g.on_deck);
    const lack = deckGames.filter(g => { const s = RL.state(g, c, i, idx); return s === 'rebuild' || s === 'update'; }).length;
    return deckGames.length ? (lack ? `not yet on the Deck in ${lack} of your ${deckGames.length} Deck games` : 'in all your Deck games') : 'in the game builds';
  }
  if (c.build) return 'in the game builds once it is merged into main';
  return c.area === 'sdk' ? 'in the games once the SDK is rebuilt' : 'not in the game builds (tools, docs)';
}
function logEntry(d, c, i, isNew) {
  const idx = RL.index(d);
  const chips = c.games.map(([gi, s]) => logChip(d, gi, s, c, i)).join('');
  const mine = c.games.map(([gi]) => [gi, RL.mineOf(d, gi)]).filter(([, g]) => g);
  const forg = mine.length && i != null ? `<div class="forg">${mine.map(([gi, g]) => {
    const s = RL.state(g, c, i, idx);
    return `<div><span class="gchip ${s ? RL.STATE[s][0] : ''}" onclick="setLogGame(${gi}, 'mentions')"><span class="dt"></span>${esc(d.names[gi].n)}</span> <span class="muted">${s ? esc(RL.STATE[s][1]) : g.built ? '' : 'not built on the PC'}</span></div>`;
  }).join('')}</div>` : '';
  const more = c.files > c.paths.length ? `<br>and ${c.files - c.paths.length} more` : '';
  return `<div class="ent ${isNew ? 'new' : ''} ${logOpen.has(c.sha) ? 'open' : ''}" id="e-${c.sha}">
    <div class="eh" onclick="toggleLog('${c.sha}')"><span class="tm">${RL.hm(c.at)}</span>
      <div class="em"><div class="l1"><span class="ar a-${c.area}">${esc(d.areas[c.area] || c.area)}</span><span class="sj">${RL.inline(c.subject)}</span>${isNew ? '<span class="newtag">NEW</span>' : ''}</div>
        ${c.body ? `<div class="pv">${RL.firstLine(c.body)}</div>` : ''}
        ${chips ? `<div class="gs">${chips}</div>` : ''}</div></div>
    <div class="eb">${RL.bodyHtml(c.body) || '<p class="muted">No description.</p>'}${forg}
      <div class="ef"><span>${esc(c.sha.slice(0, 7))}</span><span>${new Date(c.at * 1000).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</span>
        <span>${esc(logReach(d, c, i))}</span>${d.repo ? `<a href="${esc(d.repo)}/commit/${esc(c.sha)}" target="_blank" rel="noopener">View on GitHub</a>` : ''}</div>
      ${c.paths.length ? `<div class="files">${c.paths.map(esc).join('<br>')}${more}</div>` : ''}</div></div>`;
}
function renderLog() {
  const d = logData;
  if (!d) return;
  const newest = d.commits[0];
  $('#logsub').innerHTML = d.commits.length ? `${d.commits.length} changes on main · the newest ${esc(RL.ago(newest.at))}${d.checked_at ? ' · checked with GitHub ' + esc(RL.ago(d.checked_at)) : ''}${d.repo ? ` · <a href="${esc(d.repo)}/commits/main" target="_blank" rel="noopener">GitHub</a>` : ''}`
    : 'No ReXNative commits read yet (the app clones ReXNative the first time it builds).';
  // as áreas
  const cnt = RL.counts(d);
  const areas = [['all', 'All'], ['build', 'Reaches the games']].concat(RL.AREA_ORDER.filter(a => cnt[a]).map(a => [a, d.areas[a]]));
  $('#logareas').innerHTML = areas.map(([k, t]) => `<button class="chip ${logF.area === k ? 'on' : ''}" onclick="setLogArea('${k}')">${k !== 'all' && k !== 'build' ? `<span class="ar a-${k}" style="border:0;padding:0">●</span> ` : ''}${esc(t)}<b>${cnt[k] || 0}</b></button>`).join('');
  // os jogos (os de cá primeiro, depois os outros de que o ReXNative fala)
  const mentioned = {};
  d.commits.forEach(c => c.games.forEach(([gi]) => { mentioned[gi] = (mentioned[gi] || 0) + 1; }));
  const opt = gi => `<option value="${gi}" ${logF.game === gi ? 'selected' : ''}>${esc(d.names[gi].t)}${mentioned[gi] ? ' (' + mentioned[gi] + ')' : ''}</option>`;
  const byTitle = (a, b) => d.names[a].t.localeCompare(d.names[b].t);
  const mineIdx = d.names.map((n, gi) => gi).filter(gi => d.names[gi].s).sort(byTitle);
  const others = d.names.map((n, gi) => gi).filter(gi => !d.names[gi].s && mentioned[gi]).sort(byTitle);
  $('#loggame').innerHTML = `<option value="">Every game</option><optgroup label="Your games">${mineIdx.map(opt).join('')}</optgroup>
    ${others.length ? `<optgroup label="Other games ReXNative mentions">${others.map(opt).join('')}</optgroup>` : ''}`;
  // o jogo escolhido
  const pend = RL.pending(d);
  const gbar = $('#loggamebar');
  if (logF.game != null) {
    const n = d.names[logF.game], g = RL.mineOf(d, logF.game);
    const p = g ? pend.find(x => x.slug === g.slug) : null;
    const modes = [['mentions', 'Mentions it', mentioned[logF.game] || 0]];
    if (g && g.built) modes.push(['notbuilt', 'Not in its PC build', p.missing_build]);
    if (g && g.on_deck) modes.push(['notdeck', 'Not on the Deck yet', p.missing_deck]);
    const where = !g ? 'not in your library' : g.on_deck ? (p.missing_deck ? `on your Deck, ${p.missing_deck} change(s) behind` : 'on your Deck, up to date')
      : g.built ? (p.missing_build ? `built on the PC, ${p.missing_build} change(s) behind` : 'built on the PC, up to date') : 'prepared, not built';
    gbar.innerHTML = `<div class="panel gamebar"><b>${esc(n.t)}</b><span class="muted small">${esc(where)}</span>
      <span class="row chips" style="gap:6px">${modes.map(([k, t, c]) => `<button class="chip ${logF.mode === k ? 'on' : ''}" style="cursor:pointer" onclick="setLogGame(${logF.game}, '${k}')">${t} <b>${c}</b></button>`).join('')}</span>
      <span class="grow"></span>${g ? `<button class="b s" onclick="openGame('${esc(g.slug)}')">Open the game</button>` : ''}
      <button class="b s" onclick="setLogGame(null)">Every game</button></div>`;
  } else gbar.innerHTML = '';
  // a lista, por dia
  const seenIdx = logSeenAt ? d.commits.findIndex(c => c.sha === logSeenAt) : 0;
  const rows = RL.filter(d, logF);
  const perDay = {};
  rows.forEach(r => { const k = RL.dayKey(r.c.at); perDay[k] = (perDay[k] || 0) + 1; });
  let html = '', day = null;
  for (const { c, i } of rows) {
    const k = RL.dayKey(c.at);
    if (k !== day) {
      day = k;
      html += `<div class="logday"><h3>${esc(RL.day(c.at))}</h3><span class="muted small">${perDay[k]} change${perDay[k] === 1 ? '' : 's'}</span></div>`;
    }
    html += logEntry(d, c, i, seenIdx > 0 && i < seenIdx);
  }
  // os ramos ainda fora do main
  const br = (d.branches || []).map(b => {
    const bl = RL.filter(d, Object.assign({}, logF, { mode: 'mentions' }), b.commits);
    if (!bl.length && (logF.q || logF.game != null || logF.area !== 'all')) return '';
    const open = logBranchOpen.has(b.name);
    return `<div class="branch"><div class="bh" onclick="toggleBranch('${esc(b.name)}')"><b>🧪 ${esc(b.name)}</b>
      <span class="muted small">${b.commits.length} change(s) not in main yet, so not in the game builds · the newest ${esc(RL.ago(b.at))}</span>
      <span class="grow"></span><a href="#" class="small" onclick="return false">${open ? 'Hide' : 'Show'}</a></div>
      ${open ? `<div class="bl">${bl.map(({ c }) => logEntry(d, c, null, false)).join('') || '<p class="muted small">Nothing here matches the filter.</p>'}</div>` : ''}</div>`;
  }).join('');
  $('#loglist').innerHTML = br + (html || '<div class="empty">No changes match. Clear the search or pick another area.</div>');
  // ao lado: os jogos de cá e o que lhes falta
  const onDeck = pend.filter(g => g.on_deck).sort((a, b) => b.missing_deck - a.missing_deck || a.title.localeCompare(b.title));
  const pcOnly = pend.filter(g => !g.on_deck && g.built).sort((a, b) => b.missing_build - a.missing_build || a.title.localeCompare(b.title));
  const giOf = slug => d.names.findIndex(n => n.s === slug);
  const row = (g, n, mode) => `<div class="mg" onclick="setLogGame(${giOf(g.slug)}, '${n ? mode : 'mentions'}')" title="${esc(g.title)}"><span>${esc(g.title)}</span>
    <span style="color:${n ? 'var(--warn)' : 'var(--muted)'}">${n ? n + ' behind' : 'up to date'}</span></div>`;
  $('#logside').innerHTML = `<div class="panel">
    <h3>Your Deck games</h3>${onDeck.map(g => row(g, g.missing_deck, 'notdeck')).join('') || '<p class="muted small">None on the Deck.</p>'}
    ${pcOnly.length ? `<h3 style="margin-top:14px">Built on the PC only</h3>${pcOnly.map(g => row(g, g.missing_build, 'notbuilt')).join('')}` : ''}
    <div class="legend"><b style="color:var(--text);margin-top:10px">The game tags</b>
      <span><span class="gchip ok"><span class="dt"></span>game</span> has the change (on the Deck, or in the PC build)</span>
      <span><span class="gchip info"><span class="dt"></span>game</span> built on the PC: update the Deck</span>
      <span><span class="gchip warn"><span class="dt"></span>game</span> not built in yet: rebuild</span>
      <span><span class="gchip other"><span class="dt"></span>game</span> not in your library</span></div></div>`;
}

// -- arranque -------------------------------------------------------------------------------------
// http://127.0.0.1:8360/#deck abre logo num separador (games, catalog, deck, jobs, settings).
window.addEventListener('hashchange', () => showTab(location.hash.slice(1) || 'games'));
overview();
if (['catalog', 'deck', 'jobs', 'settings', 'compat', 'storage', 'log'].includes(location.hash.slice(1))) showTab(location.hash.slice(1));
else loadGames();
api('/api/deck').then(d => { deckData = d; }).catch(() => {});
// Quantas mudanças novas no ReXNative desde a última visita ao Changelog (no separador).
setTimeout(() => { if (tab !== 'log') logPeek(); }, 4000);
setInterval(() => { if (tab !== 'log') logPeek(); }, 600000);
// Reloaded for an update (reloadForUpdate): the tab, game or job that was open.
(function restoreAfterUpdate() {
  let r = null;
  try { r = JSON.parse(sessionStorage.getItem('gestor-restore') || 'null'); sessionStorage.removeItem('gestor-restore'); }
  catch (e) { return; }
  if (!r) return;
  if (r.tab && r.tab !== tab) showTab(r.tab);
  if (r.job) openJob(r.job, r.back);
  else if (r.slug) openGame(r.slug, r.sub);
})();
