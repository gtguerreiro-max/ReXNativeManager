'use strict';
// Modo Deck: o Gestor no Steam Deck (Firefox em ecrã inteiro, Game Mode). Comando: cruz/analógico
// mexem, A escolhe, B volta, X e Y fazem o que a barra de baixo diz, L1/R1 mudam de separador, Menu
// sai. Também toque e teclado (setas, Enter, Esc, Q/E).
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const gb = b => b == null ? '?' : b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : Math.max(1, Math.round(b / 1e6)) + ' MB';
const eta = s => s == null || !isFinite(s) ? '' : s < 90 ? Math.max(1, Math.round(s)) + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : Math.floor(s / 3600) + ' h ' + Math.round((s % 3600) / 60) + ' min';
const ago = t => { if (!t) return '-'; const d = (Date.now() / 1000 - (typeof t === 'number' ? t : Date.parse(t) / 1000)); if (d < 3600) return Math.max(1, Math.round(d / 60)) + ' min ago'; if (d < 86400) return Math.round(d / 3600) + ' h ago'; const n = Math.round(d / 86400); return n + (n === 1 ? ' day ago' : ' days ago'); };

const S = {
  tab: 'deck', home: null, cat: null, online: false,
  f: { q: '', kind: 'all', sort: 'name', genre: '' }, shown: 60,
  layers: [], cur: null, lastFocus: {}, seen: {}, sig: {},
};
// Quem faz o trabalho: a app do PC ('pc') ou este Deck (o modo Sem PC, 'local'), como diz home.mode.
// Até o /home responder, a morada (o serviço do Deck está em 127.0.0.1:8370).
const LOCAL = 'http://127.0.0.1:8370';
S.mode = location.port === '8370' && ['127.0.0.1', 'localhost'].includes(location.hostname) ? 'local' : 'pc';
const isLocal = () => S.mode === 'local';
// Where the work is done, in the texts: "Build on the PC" / "Build on this Deck".
const side = () => isLocal() ? 'this Deck' : 'the PC';
const Side = () => isLocal() ? 'This Deck' : 'The PC';

// -- API ------------------------------------------------------------------------------------------
async function api(path, opts = {}) {
  const o = { method: opts.method || (opts.body ? 'POST' : 'GET'), headers: {}, credentials: 'same-origin' };
  if (o.method !== 'GET') o.headers['X-Gestor'] = '1';
  if (opts.body) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(opts.body); }
  // Sem resposta em pouco tempo (o PC a dormir, o Wi-Fi caiu): erro, em vez de esperar os 300 s do
  // Firefox com o ponto verde aceso e os pedidos a acumular.
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), opts.timeout || 10000);
  o.signal = ctl.signal;
  let r;
  try { r = await fetch(path, o); }
  catch (e) {
    if (isLocal()) throw new Error(e.name === 'AbortError' ? 'The Manager on this Deck did not answer' : 'No connection to the Manager on this Deck');
    throw new Error(e.name === 'AbortError' ? 'The PC did not answer' : 'No connection to the PC');
  }
  finally { clearTimeout(timer); }
  if (r.status === 401 && !isLocal()) { if (S.tab !== 'pair') showPair(); throw new Error('emparelhar'); }
  if (r.status === 428) throw new Error('Sign in with GitHub on the PC first (the ReXNative Manager page)');
  const t = await r.text();
  let d;
  try { d = JSON.parse(t); } catch (e) { d = { detail: t }; }
  if (!r.ok) throw new Error(d.detail || r.statusText);
  return d;
}
const cover = (title, slug, xbla) => '/api/remote/cover?t=' + encodeURIComponent(title) + (slug ? '&slug=' + encodeURIComponent(slug) : '') + (xbla ? '&a=1' : '');
// As capas que já carregaram aparecem logo, sem o fade outra vez, quando a vista se redesenha.
const loaded = new Set();
function coverLoaded(el) { loaded.add(el.getAttribute('src')); el.classList.add('ok'); if (el.nextElementSibling) el.nextElementSibling.classList.add('hide'); }
function img(title, slug, xbla) {
  const src = cover(title, slug, xbla);
  if (loaded.has(src)) return `<img class="ok" decoding="async" src="${src}" onerror="this.remove()"><div class="ph hide" style="background:${tint(title)}">${esc(title)}</div>`;
  return `<img loading="lazy" decoding="async" src="${src}" onload="coverLoaded(this)" onerror="this.remove()"><div class="ph" style="background:${tint(title)}">${esc(title)}</div>`;
}
function tint(s) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `linear-gradient(160deg, hsl(${h} 35% 26%), hsl(${(h + 40) % 360} 30% 12%))`;
}

// -- avisos ---------------------------------------------------------------------------------------
function toast(text, bad) {
  const d = document.createElement('div');
  d.className = 'toast' + (bad ? ' bad' : '');
  d.textContent = text;
  $('#toasts').appendChild(d);
  setTimeout(() => d.remove(), bad ? 9000 : 5500);
}

// -- foco e navegação -----------------------------------------------------------------------------
function scope() { return S.layers.length ? S.layers[S.layers.length - 1].el : $('#v-' + S.tab); }
function visible(el) { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
function focusables(root) { return $$('.f', root || scope()).filter(el => !el.disabled && visible(el)); }

function focus(el, scroll = true) {
  if (!el) return;
  if (S.cur && S.cur !== el) S.cur.classList.remove('focus');
  S.cur = el;
  el.classList.add('focus');
  try { el.focus({ preventScroll: true }); } catch (e) { /* */ }
  if (scroll) reveal(el);
  if (!S.layers.length && el.dataset.id) S.lastFocus[S.tab] = el.dataset.id;
  if (el.dataset.cover) backdrop(el.dataset.cover);
  if (S.tab === 'catalog' && !S.layers.length && el.classList.contains('tile')) maybeMore(el);
  hints();
}
function reveal(el) {
  const box = el.closest('.scrollbox, .view, .sheet');  // .scrollbox: a list that scrolls inside a sheet
  if (!box) return;
  const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
  const m = 70;
  if (r.top < b.top + m) box.scrollTop -= (b.top + m - r.top);
  else if (r.bottom > b.bottom - m) box.scrollTop += (r.bottom - (b.bottom - m));
}
function move(dir) {
  const cur = S.cur;
  if (cur && cur.classList.contains('opt') && (dir === 'left' || dir === 'right')) { cycle(cur, dir === 'right' ? 1 : -1); return; }
  const g = cur && cur.classList.contains('tile') && cur.parentElement && cur.parentElement.classList.contains('grid') ? gridMove(cur, dir) : undefined;
  if (g) { focus(g); return; }
  const items = focusables();
  if (!items.length) return;
  if (!cur || !items.includes(cur)) { focus(items[0]); return; }
  const a = cur.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best = null, bs = Infinity;
  for (const el of items) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    let main, cross;
    if (dir === 'down') { main = b.top - a.bottom + a.height / 2; cross = Math.abs(bx - ax); if (by <= ay + 2) continue; }
    else if (dir === 'up') { main = a.top - b.bottom + a.height / 2; cross = Math.abs(bx - ax); if (by >= ay - 2) continue; }
    else if (dir === 'right') { main = b.left - a.right + a.width / 2; cross = Math.abs(by - ay); if (bx <= ax + 2) continue; }
    else { main = a.left - b.right + a.width / 2; cross = Math.abs(by - ay); if (bx >= ax - 2) continue; }
    const sc = Math.max(main, 0) + cross * 2.4;
    if (sc < bs) { bs = sc; best = el; }
  }
  if (best) { focus(best); sfx(); }
}
// Numa grelha de capas: a vizinha pela posição (colunas = capas na primeira fila). undefined quando
// sai da grelha (a procura pela geometria trata disso).
function gridMove(cur, dir) {
  const tiles = [...cur.parentElement.children].filter(e => e.classList.contains('f'));
  const i = tiles.indexOf(cur);
  if (i < 0) return undefined;
  const top = tiles[0].offsetTop;
  let cols = tiles.findIndex(e => e.offsetTop !== top);
  if (cols < 0) cols = tiles.length;
  const row = Math.floor(i / cols), rows = Math.ceil(tiles.length / cols);
  let j;
  if (dir === 'left') j = i % cols ? i - 1 : -1;
  else if (dir === 'right') j = (i % cols < cols - 1 && i + 1 < tiles.length) ? i + 1 : -1;
  else if (dir === 'up') j = row > 0 ? i - cols : -1;
  else j = row < rows - 1 ? Math.min(i + cols, tiles.length - 1) : -1;
  return j >= 0 ? tiles[j] : undefined;
}
function restoreFocus() {
  const root = scope();
  const id = S.layers.length ? null : S.lastFocus[S.tab];
  const el = (id && $$('.f', root).find(e => e.dataset.id === id)) || focusables(root)[0];
  if (el) focus(el, true);
  else { S.cur = null; hints(); }
}
function sfx() { /* sem som: o Deck já faz o seu */ }
function activate() { if (S.cur) S.cur.click(); }

// -- camadas (detalhe, confirmar, teclado) -----------------------------------------------------
function openLayer(html, opts = {}) {
  const el = document.createElement('div');
  el.className = 'layer';
  el.innerHTML = html;
  document.body.appendChild(el);
  const layer = { el, back: opts.back, actions: opts.actions || {}, prev: S.cur, hint: opts.hint };
  S.layers.push(layer);
  el.addEventListener('click', e => { if (e.target === el) closeLayer(); });
  const first = opts.focus ? $(opts.focus, el) : focusables(el)[0];
  focus(first);
  return layer;
}
function closeLayer() {
  const l = S.layers.pop();
  if (!l) return;
  l.el.remove();
  if (l.onclose) l.onclose();
  if (l.prev && document.body.contains(l.prev)) focus(l.prev);
  else restoreFocus();
}
function closeAll() { while (S.layers.length) { const l = S.layers.pop(); l.el.remove(); if (l.onclose) l.onclose(); } restoreFocus(); }
function back() {
  const l = S.layers[S.layers.length - 1];
  if (l) { if (l.back) l.back(); else closeLayer(); return; }
}

// -- barra de ajuda -----------------------------------------------------------------------------
function actions() {
  const l = S.layers[S.layers.length - 1];
  if (l) return l.actions;
  const el = S.cur;
  if (S.tab === 'catalog') return { x: ['Search', () => openSearch()], y: ['Sort', () => cycleSort()] };
  if (S.tab === 'orders' && el && el.dataset.order) {
    const o = (S.home.orders || []).find(x => x.id === el.dataset.order);
    if (o && (o.status === 'running' || o.status === 'queued')) return { x: ['Cancel request', () => cancelOrder(o)] };
    if (o && o.kind === 'order' && (o.status === 'failed' || o.status === 'cancelled' || o.status === 'interrupted')) return { y: ['Try again', () => retryOrder(o)] };
  }
  if (S.tab === 'deck') return { y: ['Rescan the Deck', () => refreshHome(true, true)] };
  if (S.tab === 'log') return { x: ['Search', () => openLogSearch()], y: ['Show: next', () => cycleLogArea(1)] };
  return {};
}
function hints() {
  const a = actions();
  const parts = [];
  if (S.cur) parts.push(['a', S.cur.dataset.hint || 'Choose']);
  if (S.layers.length) parts.push(['b', 'Back']);
  if (a.x) parts.push(['x', a.x[0]]);
  if (a.y) parts.push(['y', a.y[0]]);
  if (!S.layers.length && GRID_TABS.includes(S.tab) && $('.grid', $('#v-' + S.tab))) parts.push(['j', gridByName() ? 'Next letter' : 'Jump']);
  if (!S.layers.length) parts.push(['m', 'Exit']);
  $('#hints').innerHTML = parts.map(([k, t]) => k === 'j' ? `<span><span class="glyph">L2</span><span class="glyph">R2</span>${esc(t)}</span>`
    : `<span><span class="k ${k}">${k === 'm' ? '☰' : k.toUpperCase()}</span>${esc(t)}</span>`).join('');
}

// -- fundo -----------------------------------------------------------------------------------
let bdi = 0, bdUrl = null, bdTimer = null;
// O fundo muda só quando o foco pára um bocadinho: com a cruz carregada, cada passo recomeçava a
// transição de duas camadas desfocadas do tamanho do ecrã.
function backdrop(url) {
  if (url === bdUrl) return;
  clearTimeout(bdTimer);
  bdTimer = setTimeout(() => backdropNow(url), 250);
}
function backdropNow(url) {
  if (url === bdUrl) return;
  bdUrl = url;
  const ds = $$('#backdrop div');
  const next = ds[bdi ^ 1];
  const im = new Image();
  im.onload = () => {
    if (bdUrl !== url) return;
    next.style.backgroundImage = `url("${url}")`;
    next.classList.add('on');
    ds[bdi].classList.remove('on');
    bdi ^= 1;
  };
  im.src = url;
}

// -- separadores ------------------------------------------------------------------------------
const TABS = ['deck', 'pc', 'catalog', 'log', 'orders', 'settings'];
// The tabs on the bar (L1/R1 go through these): without the PC there is no "On PC".
const tabs = () => isLocal() ? TABS.filter(t => t !== 'pc') : TABS;
const TAB_KEY = 'gestor-tab';
function switchTab(t) {
  if (S.layers.length || S.tab === 'pair') return;
  S.tab = t;
  try { localStorage.setItem(TAB_KEY, t); } catch (e) { /* no storage: it opens on the Deck tab */ }
  for (const v of TABS) $('#v-' + v).classList.toggle('hide', v !== t);
  $$('#tabs .tab').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  render(t);
  nowStrip();
  restoreFocus();
}
// The tab the Manager was left on, when it opens again.
function firstTab() {
  let t = null;
  try { t = localStorage.getItem(TAB_KEY); } catch (e) { /* */ }
  if (tabs().includes(t)) return t;
  return (S.home && (S.home.games || []).length) ? 'deck' : 'catalog';
}
// The mode changed (home.mode, or the address at the start): the tab bar and the texts follow.
function applyMode() {
  const pcTab = $('#tabs .tab[data-tab="pc"]');
  if (pcTab) pcTab.classList.toggle('hide', isLocal());
  if (isLocal()) { const p = $('#v-boot p'); if (p) p.textContent = 'Opening the Manager on this Deck…'; }
  S.sig = {};
  if (isLocal() && S.tab === 'pc' && !S.layers.length) switchTab('deck');
}

// -- saltar nas grelhas (L2 / R2) ---------------------------------------------------------------
// With 2000 games in the catalogue the D-pad alone takes minutes: L2 and R2 go to the previous and
// the next letter in a list sorted by name, and three rows at a time in any other order.
const GRID_TABS = ['deck', 'pc', 'catalog'];
function gridByName() {
  if (S.tab === 'catalog') return S.f.sort === 'name';
  return (((S.tab === 'deck' ? S.dv : S.pv) || {}).sort || 'name') === 'name';
}
const letterOf = t => { const c = String(t || '').trim().charAt(0).toUpperCase(); return c >= 'A' && c <= 'Z' ? c : '#'; };
let jumpTimer = null;
function showJump(text) {
  const el = $('#jump');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('small', text.length > 2);
  el.classList.add('on');
  clearTimeout(jumpTimer);
  jumpTimer = setTimeout(() => el.classList.remove('on'), 800);
}
function jumpGrid(dir) {
  if (S.layers.length || !GRID_TABS.includes(S.tab)) return;
  const grid = $('.grid', $('#v-' + S.tab));
  if (!grid) return;
  let tiles = $$('.tile', grid);
  if (!tiles.length) return;
  // The catalogue draws its tiles as you go down: its names come from the whole list, and its order
  // by name is the order of each game's key (the title's words: "A Kingdom for Keflings" is under K).
  const names = S.tab === 'catalog' ? filtered().map(g => g.key || g.title) : tiles.map(t => ($('.nm', t) || t).textContent);
  let i = tiles.indexOf(S.cur);
  if (i < 0) i = 0;
  let j, label;
  if (gridByName()) {
    const k = letterOf(names[i]);
    if (dir > 0) {
      j = names.findIndex((n, x) => x > i && letterOf(n) !== k);
      if (j < 0) j = names.length - 1;
    } else {
      // the first of this letter, or of the letter before when already on it
      j = i;
      while (j > 0 && letterOf(names[j - 1]) === k) j--;
      if (j === i && i > 0) { const p = letterOf(names[i - 1]); j = i - 1; while (j > 0 && letterOf(names[j - 1]) === p) j--; }
    }
    label = letterOf(names[j]);
  } else {
    const cols = Math.max(1, tiles.filter(t => t.offsetTop === tiles[0].offsetTop).length);
    j = Math.min(names.length - 1, Math.max(0, i + dir * cols * 3));
    label = `${j + 1} / ${names.length}`;
  }
  if (S.tab === 'catalog' && j >= tiles.length) {
    S.shown = Math.min(names.length, j + 60);
    grid.insertAdjacentHTML('beforeend', filtered().slice(tiles.length, S.shown).map(catTile).join(''));
    const note = grid.nextElementSibling;
    if (note) note.textContent = S.shown < names.length ? `Showing ${S.shown} of ${names.length}: scroll down for more` : '';
    tiles = $$('.tile', grid);
  }
  if (!tiles[j]) return;
  // At once, with the tile near the top (what follows it is what was jumped to): the smooth scroll
  // of one step is too slow over thousands of pixels.
  focus(tiles[j], false);
  const box = tiles[j].closest('.view');
  if (box) {
    const top = box.scrollTop + tiles[j].getBoundingClientRect().top - box.getBoundingClientRect().top - 24;
    box.style.scrollBehavior = 'auto';
    box.scrollTop = Math.max(0, top);
    box.style.scrollBehavior = '';
  }
  showJump(label);
}

// -- o pedido em curso, em todos os separadores ---------------------------------------------------
// The request the PC is working on (or the first one waiting), its stage and its progress, under
// the top bar on every tab but Requests: no need to go there to see how it is going.
function nowStrip() {
  const el = $('#now');
  if (!el) return;
  const act = ((S.home || {}).orders || []).filter(o => o.status === 'running' || o.status === 'queued')
    .sort((a, b) => (a.status === 'running' ? 0 : 1) - (b.status === 'running' ? 0 : 1) || String(a.created).localeCompare(String(b.created)));
  if (!act.length || !S.online || S.tab === 'orders' || !TABS.includes(S.tab)) { el.classList.add('hide'); return; }
  const o = act[0], p = o.progress || {};
  const pc = p.total ? 100 * p.done / p.total : p.pct;
  const waits = o.status === 'queued' || (p.waiting && o.status === 'running');
  el.classList.remove('hide');
  el.onclick = () => switchTab('orders');
  // One line: while the assistant fixes a step, that, not the command it is running.
  // (pstep in a request that follows a pipeline; step in a rebuild asked from the Deck, which is one)
  const fixing = p.pstep === 'claude' || (o.kind === 'pipeline' && p.step === 'claude');
  const text = fixing && !waits ? 'Claude is fixing a step that failed on ' + side() : stageText(o);
  el.innerHTML = `<span class="pulse ${waits ? 'q' : ''}"></span><span class="t">${esc(otitle(o))}</span><span class="s">${esc(text)}</span>
    ${pc != null && o.status === 'running' && !waits ? `<span class="pb"><span style="width:${Math.max(0, Math.min(100, pc)).toFixed(1)}%"></span></span>` : ''}
    ${act.length > 1 ? `<span class="more">+${act.length - 1} more</span>` : ''}`;
}
// What the PC is doing now (the build lane and the report lane), for the Requests tab: why a
// request waits. From 1.19 (pc_work); nothing with an older app on the PC.
function pcWorkText(h) {
  const w = (h || {}).pc_work;
  if (!w) return '';
  const run = (w.running || []).map(r => `${r.title}${r.for_s != null ? ' (' + eta(r.for_s) + ')' : ''}`);
  const parts = [run.length ? Side() + ' is working on ' + run.join(' and ') : Side() + ' is free'];
  if (w.queued) parts.push(`${w.queued} job${w.queued > 1 ? 's' : ''} waiting`);
  if (w.restart) parts.push('it restarts after the running jobs, the queue continues afterwards');
  return parts.join(' · ');
}
function pcWork(h) {
  const t = pcWorkText(h);
  const busy = (((h || {}).pc_work || {}).running || []).length;
  return t ? `<div class="pcw" id="pcw"><span class="dot ${busy ? 'ok' : ''}"></span><span>${esc(t)}</span></div>` : '';
}
function nextTab(d) { const ts = tabs(); switchTab(ts[(ts.indexOf(S.tab) + d + ts.length) % ts.length]); }

function render(t) {
  if (t === 'deck') renderDeck();
  else if (t === 'pc') { renderPc(); loadPc(); }
  else if (t === 'catalog') renderCatalog();
  else if (t === 'orders') renderOrders();
  else if (t === 'log') { renderLog(); loadLog(); }
  else if (t === 'settings') { renderSettings(); loadMode(); loadAccounts(); }
  logBadge();
}

// -- estado do PC e do Deck ---------------------------------------------------------------------
// O que, mudando, obriga a desenhar a vista outra vez (o progresso dos pedidos muda a cada passo e
// atualiza-se no sítio: ordersShape deixa-o de fora).
const deckSig = h => JSON.stringify([h.games, h.pending, h.deck.space, h.deck.reachable]);
const ordersShape = h => JSON.stringify([(h.orders || []).map(o => [o.id, o.status, o.stage, o.kind, o.error, !!(o.progress || {}).step_pt, (o.report || {}).status]), h.pending]);
async function refreshHome(readDeck, manual) {
  if (S.tab === 'pair' || S.leaving) return;  // leaving: the launcher is opening the other side
  try {
    const h = await api('/api/remote/home' + (readDeck ? '?refresh=true' : ''), { timeout: readDeck ? 60000 : 10000 });
    S.online = true;
    if (!h.deck) h.deck = {};
    const prev = S.home;
    S.home = h;
    const mode = h.mode === 'local' ? 'local' : 'pc';
    if (mode !== S.mode) { S.mode = mode; applyMode(); }
    notifyOrders(prev, h);
    notifyAchievements(h);
    notifySnapshots(h);
    status();
    const n = (h.orders || []).filter(o => o.status === 'running' || o.status === 'queued').length;
    $('#ordn').textContent = n;
    $('#ordn').classList.toggle('hide', !n);
    // Volta a desenhar o separador à vista só se mudou alguma coisa (o foco fica onde estava).
    const sig = S.tab === 'orders' ? ordersShape(h) : S.tab === 'deck' ? deckSig(h) : null;
    if (sig !== S.sig[S.tab] && !S.layers.length && S.tab !== 'catalog' && S.tab !== 'log' && S.tab !== 'settings') {
      const id = S.cur && S.cur.dataset.id;
      const view = $('#v-' + S.tab), top = view.scrollTop;
      render(S.tab);
      view.scrollTop = top;
      const el = id && $$('.f', view).find(e => e.dataset.id === id);
      if (el) focus(el, false); else restoreFocus();
    } else if (S.tab === 'orders') updateOrders(h);
    if (manual) {
      if (h.deck.reachable === false) toast('The Deck did not answer the PC: showing the last scan', true);
      else toast('Deck scanned: ' + (h.games || []).length + ' game(s)');
    }
  } catch (e) {
    if (e.message === 'emparelhar') return;
    S.online = false;
    status();
  }
}
function notifyOrders(prev, h) {
  const good = [], bad = [];
  for (const o of h.orders || []) {
    const before = S.seen[o.id];
    S.seen[o.id] = o.status;
    if (!before || before === o.status || !prev) continue;
    const name = o.name || otitle(o);
    if (o.status === 'ok') {
      if (o.kind === 'order') {
        good.push(o.stage === 'library' ? `${name} is on the Deck: it joins the library when you exit the Manager` : `${name} is in the Deck's library`);
        loadCatalog();
      } else if (o.kind === 'deck-report') good.push(`Report on ${name}: ${(o.report || {}).status || 'done'}`);
      else if (o.kind === 'deck-batch') good.push(`${otitle(o).split(':')[0]}: ${o.last || 'done'}`);
      else good.push(`${name}: ${(KIND_LABEL[o.kind] || 'done').toLowerCase()} done`);
    } else if (o.status === 'failed') bad.push(`${name}: ${o.error || 'failed'}`);
  }
  // Vários ao mesmo tempo: um aviso só.
  if (good.length === 1) toast(good[0]);
  else if (good.length > 1) toast(`${good.length} requests finished: ${good.map(t => t.split(':')[0]).join(', ')}`);
  if (bad.length === 1) toast(bad[0], true);
  else if (bad.length > 1) toast(`${bad.length} requests failed: ${bad.map(t => t.split(':')[0]).join(', ')}`, true);
}
function status() {
  const h = S.home || {};
  const sp = ((h.deck || {}).space || {}).interno;
  const who = isLocal() ? (S.online ? 'This Deck does the work' : 'No connection to the Manager on this Deck')
    : S.online ? 'PC ' + esc(h.pc || '') : 'No connection to the PC';
  $('#status').innerHTML = `<span class="pcn"><span class="dot ${S.online ? 'ok' : 'bad'}"></span>${who}</span>
    ${S.online && h.ssh === false && !isLocal() ? '<span class="chip" title="The PC cannot reach the Deck (SSH): sending waits">Deck unreachable: sending waits</span>' : ''}
    ${sp ? `<span>· ${gb(sp.free)} free</span>` : ''}${h.version ? `<span>· v${esc(h.version)}</span>` : ''}`;
  nowStrip();
}

// -- versão --------------------------------------------------------------------------------------
// A versão da app (a do PC), o que mudou, e o lançador deste Deck: uma vez por versão, depois de o
// PC atualizar, abre-se "What's new".
async function loadVersion(show) {
  try { S.ver = await api('/api/remote/version'); } catch (e) { return; }
  let seen = null;
  try { seen = localStorage.getItem('gestor-seen-version'); } catch (e) { /* */ }
  if (seen !== S.ver.running) {
    try { localStorage.setItem('gestor-seen-version', S.ver.running); } catch (e) { /* */ }
    if (seen && !S.layers.length) show = true;
  }
  if (S.tab === 'deck' && !S.layers.length) { S.sig.deck = null; refreshHome(); }
  if (show) openWhatsNew(seen);
}
function openWhatsNew(since) {
  const v = S.ver;
  if (!v) return;
  const vk = x => String(x || '0').split('.').map(n => parseInt(n, 10) || 0).reduce((a, n) => a * 1000 + n, 0);
  const list = (v.changes || []).filter(c => !since || vk(c[0]) > vk(since)).slice(0, 4);
  const shown = list.length ? list : (v.changes || []).slice(0, 1);
  // The launcher and the plugin come from the PC (over SSH): nothing to offer without it.
  const kit = !isLocal() && v.kit && v.kit.outdated, plug = isLocal() ? null : v.plugin;
  openLayer(`<div class="sheet confirm" style="width:980px"><h3>What's new in the Manager v${esc(v.running)}</h3>
    <div style="max-height:470px;overflow:auto">${shown.map(([ver, date, items]) => `<div class="hist f" tabindex="-1"><b>v${esc(ver)} · ${esc(date)}</b>
      ${items.map(i => `<div class="chg">• ${esc(i)}</div>`).join('')}</div>`).join('')}</div>
    ${kit ? `<div class="note">A newer launcher for this Deck is ready (v${esc(v.kit.latest)}; this one is v${esc(v.kit.on_deck)}).</div>` : ''}
    ${plug && plug.outdated ? `<div class="note">The Decky plugin here is v${esc(plug.on_deck)}: v${esc(plug.latest)} is on the PC.</div>` : ''}
    <div class="acts">${kit ? '<button class="btn p f" onclick="updateKit()">Update the launcher</button>' : ''}
      ${plug && (plug.outdated || !plug.on_deck) ? `<button class="btn ${kit ? '' : 'p '}f" onclick="updatePlugin()">${plug.on_deck ? 'Update' : 'Install'} the Decky plugin</button>` : ''}
      <button class="btn f" onclick="closeLayer()">Close</button></div></div>`, { focus: '.btn' });
}
async function updatePlugin() {
  try {
    const j = await api('/api/remote/plugin-update', { body: {} });
    S.seen[j.id] = j.status;
    toast('Installing the Decky plugin: Decky reloads it in a few seconds (follow it in Requests)');
    closeAll();
  } catch (e) { toast(e.message, true); }
}
async function updateKit() {
  try {
    const j = await api('/api/remote/kit-update', { body: {} });
    S.seen[j.id] = j.status;
    toast('Updating the launcher on this Deck (only files: Steam does not restart)');
    closeAll();
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}

// -- Changelog: o registo do ReXNative ----------------------------------------------------------------
// Os commits do main, por dia, com a área e os jogos de que falam (os do Deck com um ponto: verde já
// tem, azul está no PC, amarelo falta compilar). A abre a mudança inteira; X procura, Y muda o que se
// mostra. Fica guardado no Firefox do Gestor: abre logo, e atualiza quando o PC responde.
const LOG_KEY = 'gestor-rexlog';
const LOG_AREAS = ['all', 'build', 'upscaling', 'renderer', 'sdk', 'tool', 'deck', 'debug', 'docs'];
const LOG_MODES = [['mentions', 'Mentions it'], ['notdeck', 'Not on the Deck yet'], ['notbuilt', 'Not in its PC build']];
S.lf = { q: '', area: 'all', game: null, mode: 'mentions' };
async function loadLog() {
  if (!S.log) {
    try { const t = localStorage.getItem(LOG_KEY); if (t) { S.log = JSON.parse(t); S.logText = t; } } catch (e) { /* */ }
    if (S.log && S.logSeenAt === undefined) S.logSeenAt = RL.seen() || S.log.head;
    if (S.log && S.tab === 'log' && !S.layers.length) { renderLog(); restoreFocus(); }
  }
  let d;
  try { d = await api('/api/remote/rexlog', { timeout: 30000 }); } catch (e) {
    if (S.tab === 'log' && !S.log) $('#v-log').innerHTML = `<div class="empty"><b>Could not read the changelog</b>${esc(e.message)}</div>`;
    return;
  }
  const text = JSON.stringify(d);
  if (S.logSeenAt === undefined) S.logSeenAt = RL.seen() || d.head;
  if (text !== S.logText) {
    S.log = d; S.logText = text;
    try { localStorage.setItem(LOG_KEY, text); } catch (e) { /* cheio: só em memória */ }
    if (S.tab === 'log' && !S.layers.length) {
      const id = S.cur && S.cur.dataset.id, view = $('#v-log'), top = view.scrollTop;
      renderLog();
      view.scrollTop = top;
      const el = id && $$('.f', view).find(e => e.dataset.id === id);
      if (el) focus(el, false); else restoreFocus();
    }
  }
  if (S.tab === 'log') RL.markSeen(S.log);
  logBadge();
}
function logBadge() {
  const n = S.tab === 'log' ? 0 : RL.newCount(S.log);
  $('#logn').textContent = n;
  $('#logn').classList.toggle('hide', !n);
}
function logChip(d, gi, c, i, button) {
  const n = d.names[gi], g = RL.mineOf(d, gi);
  const st = g && i != null ? RL.state(g, c, i, RL.index(d)) : null;
  const cls = st ? RL.STATE[st][0] : g ? '' : 'other';
  if (!button) return `<span class="gch ${cls}"><span class="dt"></span>${esc(n.n)}</span>`;
  const what = st ? RL.STATE[st][1] : g ? (g.built ? 'your game' : 'not built on the PC') : 'not in your library';
  return `<button class="gch ${cls} f" data-hint="Its changes" onclick="logPickGame(${gi})"><span class="dt"></span>${esc(n.t)}<span class="w">· ${esc(what)}</span></button>`;
}
function logRow(d, c, i, isNew) {
  const chips = c.games.slice(0, 6).map(([gi]) => logChip(d, gi, c, i)).join('') + (c.games.length > 6 ? `<span class="gch other">+${c.games.length - 6}</span>` : '');
  return `<button class="lent f ${isNew ? 'new' : ''}" data-id="${esc(c.sha)}" data-hint="Read" onclick="openLogEntry('${esc(c.sha)}')">
    <span class="lt">${RL.hm(c.at)}</span>
    <span class="lb"><span class="l1"><span class="ar a-${c.area}">${esc(d.areas[c.area] || c.area)}</span>${RL.inline(c.subject)}${isNew ? '<span class="newtag">NEW</span>' : ''}</span>
      ${c.body ? `<span class="lp">${RL.firstLine(c.body)}</span>` : ''}
      ${chips ? `<span class="lg">${chips}</span>` : ''}</span></button>`;
}
function logAreaName(d, a) { return a === 'all' ? 'Everything' : a === 'build' ? 'Reaches the games' : d.areas[a] || a; }
function renderLog() {
  const v = $('#v-log'), d = S.log;
  if (!d) { v.innerHTML = '<div class="center"><div class="spin"></div><p>Reading the ReXNative changelog…</p></div>'; return; }
  const f = S.lf;
  const g = f.game != null ? RL.mineOf(d, f.game) : null;
  if (f.game != null && (!g || (f.mode === 'notdeck' && !g.on_deck) || (f.mode === 'notbuilt' && !g.built))) f.mode = 'mentions';
  const rows = RL.filter(d, f);
  const seenIdx = S.logSeenAt ? d.commits.findIndex(c => c.sha === S.logSeenAt) : 0;
  const nNew = seenIdx > 0 ? seenIdx : 0;
  const perDay = {};
  rows.forEach(r => { const k = RL.dayKey(r.c.at); perDay[k] = (perDay[k] || 0) + 1; });
  let list = '', day = null;
  for (const { c, i } of rows) {
    const k = RL.dayKey(c.at);
    if (k !== day) {
      if (day !== null) list += '</div>';
      day = k;
      list += `<div class="lday">${esc(RL.day(c.at))}<span>${perDay[k]} change${perDay[k] === 1 ? '' : 's'}</span></div><div class="lents">`;
    }
    list += logRow(d, c, i, i < nNew);
  }
  if (day !== null) list += '</div>';
  const n = f.game != null ? d.names[f.game] : null;
  let banner = '';
  if (n) {
    const p = g ? RL.pending(d).find(x => x.slug === g.slug) : null;
    const where = !g ? 'not in your library' : g.on_deck ? (p.missing_deck ? `on your Deck, ${p.missing_deck} change(s) behind` : 'on your Deck, up to date')
      : g.built ? (p.missing_build ? `built on the PC, ${p.missing_build} change(s) behind` : 'built on the PC, up to date') : 'prepared on the PC, not built';
    banner = `<div class="banner lbanner"><b>${esc(n.t)}</b> · ${esc(where)}
      ${g ? `<button class="btn f" style="margin-left:14px" onclick="logOpenGame('${esc(g.slug)}')">Open the game</button>` : ''}
      <button class="btn f" onclick="logPickGame(null)">Every game</button></div>`;
  }
  const brs = d.branches || [];
  const modes = g ? LOG_MODES.filter(([k]) => k === 'mentions' || (k === 'notdeck' && g.on_deck) || (k === 'notbuilt' && g.built)) : [];
  v.innerHTML = `<div class="vhead"><div><h2>ReXNative changelog</h2><div class="sub">${d.commits.length} changes on main · the newest ${esc(RL.ago((d.commits[0] || {}).at))}${nNew ? ` · <b style="color:var(--accent)">${nNew} new</b> since you last looked` : ''}</div></div></div>
    <div class="tools">
      <button class="pill search f" data-hint="Search" onclick="openLogSearch()">🔍 <span class="${f.q ? 'q' : ''}">${f.q ? esc(f.q) : 'Search'}</span></button>
      <button class="pill f ${f.area !== 'all' ? 'on' : ''}" data-hint="Change" data-id="pill-area" onclick="cycleLogArea(1)">Show: ${esc(logAreaName(d, f.area))}</button>
      <button class="pill f ${n ? 'on' : ''}" data-hint="Choose" data-id="pill-game" onclick="openLogGames()">Game: ${n ? esc(n.n) : 'every game'}</button>
      ${modes.length > 1 ? `<button class="pill f on" data-hint="Change" data-id="pill-mode" onclick="cycleLogMode()">${esc(LOG_MODES.find(m => m[0] === f.mode)[1])}</button>` : ''}
      ${brs.map(b => `<button class="pill f" data-hint="Open" onclick="openLogBranch('${esc(b.name)}')">🧪 ${esc(b.name)} (${b.commits.length})</button>`).join('')}</div>
    ${banner}
    ${list || `<div class="empty"><b>No changes here</b>${f.q || f.area !== 'all' || n ? 'Change the search, what is shown or the game.' : 'ReXNative has not been read yet.'}</div>`}`;
}
function logFind(sha) {
  const d = S.log;
  const i = d.commits.findIndex(c => c.sha === sha);
  if (i >= 0) return { c: d.commits[i], i, branch: null };
  for (const b of d.branches || []) { const c = b.commits.find(x => x.sha === sha); if (c) return { c, i: null, branch: b.name }; }
  return null;
}
function openLogEntry(sha) {
  const d = S.log, r = d && logFind(sha);
  if (!r) return;
  const { c, i, branch } = r;
  const idx = RL.index(d);
  let reach;
  if (branch) reach = `On the ${branch} branch: not in main yet, so not in the game builds.`;
  else if (c.build) {
    const dg = d.mine.filter(g => g.on_deck);
    const lack = dg.filter(g => { const s = RL.state(g, c, i, idx); return s === 'rebuild' || s === 'update'; }).length;
    reach = dg.length ? (lack ? `Reaches the games when they are built: not yet on the Deck in ${lack} of your ${dg.length} Deck games.` : 'Reaches the games when they are built: already in all your Deck games.') : 'Reaches the games when they are built.';
  } else reach = c.area === 'sdk' ? 'Reaches the games once the SDK is rebuilt (on the PC, Settings).' : 'Does not change the game builds (tools, docs).';
  const blocks = RL.blocks(c.body);
  const more = c.files > c.paths.length ? ` and ${c.files - c.paths.length} more` : '';
  openLayer(`<div class="sheet logsheet">
    <div class="lm"><span class="ar a-${c.area}">${esc(d.areas[c.area] || c.area)}</span>${esc(new Date(c.at * 1000).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }))}
      · ${esc(c.sha.slice(0, 7))} · ${c.files} file(s)${branch ? ` · 🧪 ${esc(branch)}` : ''}</div>
    <h3>${RL.inline(c.subject)}</h3>
    ${c.games.length ? `<div class="lgames">${c.games.map(([gi]) => logChip(d, gi, c, i, true)).join('')}</div>` : ''}
    ${blocks.map(b => `<div class="lbk ${b.kind} f" tabindex="-1" data-hint="Scroll">${b.html}</div>`).join('') || '<div class="lbk f dim" tabindex="-1">No description.</div>'}
    <div class="lfoot f" tabindex="-1" data-hint="Scroll">${esc(reach)}${c.paths.length ? `<div class="lfiles">${c.paths.map(esc).join(' · ')}${more}</div>` : ''}</div>
    <div class="acts" style="display:flex;justify-content:flex-end;margin-top:16px"><button class="btn f" onclick="closeLayer()">Close</button></div></div>`,
  { focus: c.games.length ? '.gch' : '.lbk' });
}
function logPickGame(gi) {
  S.lf.game = gi;
  S.lf.mode = 'mentions';
  closeAll();
  if (S.tab !== 'log') switchTab('log');
  renderLog();
  const el = $$('.f', $('#v-log')).find(e => e.dataset.id === 'pill-game');
  $('#v-log').scrollTop = 0;
  if (el) focus(el); else restoreFocus();
}
async function logOpenGame(slug) {
  if (deckGame(slug)) { openDeckGame(slug); return; }
  if (isLocal()) { toast('That game is not on this Deck', true); return; }
  if (!pcGame(slug)) await loadPc();
  if (pcGame(slug)) openPcGame(slug);
  else toast('That game is not on the PC list yet', true);
}
function openLogGames() {
  const d = S.log;
  if (!d) return;
  const pend = RL.pending(d);
  const mentioned = {};
  d.commits.forEach(c => c.games.forEach(([gi]) => { mentioned[gi] = (mentioned[gi] || 0) + 1; }));
  const giOf = slug => d.names.findIndex(n => n.s === slug);
  const mine = pend.filter(g => g.on_deck || g.built).sort((a, b) => (b.on_deck - a.on_deck) || ((b.on_deck ? b.missing_deck : b.missing_build) - (a.on_deck ? a.missing_deck : a.missing_build)) || a.title.localeCompare(b.title));
  const others = d.names.map((x, gi) => gi).filter(gi => !d.names[gi].s && mentioned[gi]).sort((a, b) => d.names[a].t.localeCompare(d.names[b].t));
  const row = (gi, title, right) => `<button class="opt f" data-hint="Choose" onclick="logPickGame(${gi})"><span class="l">${esc(title)}</span><span style="color:var(--muted);font-size:14.5px">${right}</span></button>`;
  openLayer(`<div class="sheet confirm" style="width:820px"><h3>Changes for one game</h3>
    <p>Your games first, the ones furthest behind on the Deck at the top.</p>
    <div class="opts" style="max-height:520px;overflow:auto">
      ${row('null', 'Every game', d.commits.length + ' changes')}
      ${mine.map(g => row(giOf(g.slug), g.title, g.on_deck ? (g.missing_deck ? `<span style="color:var(--warn)">on the Deck · ${g.missing_deck} behind</span>` : 'on the Deck · up to date') : (g.missing_build ? `PC · ${g.missing_build} not built in` : 'PC · up to date'))).join('')}
      ${others.length ? `<div class="sub2" style="margin-top:12px">Other games ReXNative mentions</div>${others.map(gi => row(gi, d.names[gi].t, (mentioned[gi] || 0) + ' change(s)')).join('')}` : ''}
    </div><div class="acts"><button class="btn f" onclick="closeLayer()">Close</button></div></div>`, { focus: '.opt' });
}
function openLogBranch(name) {
  const d = S.log, b = (d.branches || []).find(x => x.name === name);
  if (!b) return;
  openLayer(`<div class="sheet confirm" style="width:1040px"><h3>🧪 ${esc(b.name)}</h3>
    <p>${b.commits.length} change(s) being tried on this branch: not in main yet, so not in the game builds.</p>
    <div class="lents" style="max-height:540px;overflow:auto;margin:0">${b.commits.map(c => logRow(d, c, null, false)).join('')}</div>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Close</button></div></div>`, { focus: '.lent' });
}
function openLogSearch() {
  openKeyboard(S.lf.q || '', { live: t => { S.lf.q = t; renderLog(); }, done: () => restoreFocus(), clear: true });
}
function cycleLogArea(dir) {
  const d = S.log;
  if (!d) return;
  const cnt = RL.counts(d);
  const list = LOG_AREAS.filter(a => a === 'all' || cnt[a]);
  S.lf.area = list[(list.indexOf(S.lf.area) + dir + list.length) % list.length];
  renderLog();
  const el = $$('.f', $('#v-log')).find(e => e.dataset.id === 'pill-area');
  if (el) focus(el); else restoreFocus();
}
function cycleLogMode() {
  const d = S.log, g = d && S.lf.game != null ? RL.mineOf(d, S.lf.game) : null;
  if (!g) return;
  const modes = LOG_MODES.filter(([k]) => k === 'mentions' || (k === 'notdeck' && g.on_deck) || (k === 'notbuilt' && g.built)).map(m => m[0]);
  S.lf.mode = modes[(modes.indexOf(S.lf.mode) + 1) % modes.length];
  renderLog();
  const el = $$('.f', $('#v-log')).find(e => e.dataset.id === 'pill-mode');
  if (el) focus(el); else restoreFocus();
}

// -- No Deck ------------------------------------------------------------------------------------
function storage(sp) {
  if (!sp) return '';
  const used = 1 - sp.free / sp.total;
  return `<div class="storage"><div class="t"><span>Internal storage</span><span>${gb(sp.free)} free of ${gb(sp.total)}</span></div>
    <div class="bar"><div style="width:${(used * 100).toFixed(1)}%"></div></div></div>`;
}
function pendingBanner(h) {
  const p = (h || {}).pending || {};
  if (!p.add && !p.remove) return '';
  const what = [p.add ? `${p.add} game(s) join the library` : '', p.remove ? `${p.remove} shortcut(s) are removed` : ''].filter(Boolean).join(' and ');
  return `<div class="banner">${esc(what)} when you exit the Manager (Steam on the Deck restarts for a few seconds).</div>`;
}
function renderDeck() {
  const h = S.home;
  const v = $('#v-deck');
  if (!h) { v.innerHTML = ''; return; }
  S.sig.deck = deckSig(h);
  const all0 = h.games || [];
  const gs = sortSearch(all0, S.dv || {}, DSORTS);
  const sp = (h.deck.space || {}).interno;
  const tiles = gs.map(g => {
    const b = [];
    if (g.update) b.push('<span class="bd g">Update</span>');
    else if (g.fresh && g.fresh.state === 'desatualizado') b.push('<span class="bd w">New fixes</span>');
    if (g.pending_add) b.push('<span class="bd i">Joining the library</span>');
    else if (!g.in_library) b.push('<span class="bd w">No shortcut</span>');
    if (!g.complete) b.push('<span class="bd b">Incomplete</span>');
    if (g.runner === 'linux') b.push('<span class="bd i">Linux</span>');
    return `<button class="tile f" data-id="${esc(g.slug)}" data-cover="${esc(cover(g.title, g.slug))}" onclick="openDeckGame('${esc(g.slug)}')">
      <div class="cv">${img(g.title, g.slug)}<div class="badges">${b.join('')}</div>${g.job ? '<div class="busy"><div class="spin"></div></div>' : ''}</div>
      <div class="nm">${esc(g.title)}</div></button>`;
  }).join('');
  const upd = isLocal() ? [] : batchGames('update'), reb = isLocal() ? [] : batchGames('rebuild');  // the PC's
  const dv = S.dv || {};
  const low = sp && (sp.free < 20e9 || sp.free < sp.total * 0.1);
  const all = `<div class="tools" style="margin:0 0 14px">
      <button class="pill search f" data-hint="Search" onclick="openListSearch('dv')">🔍 <span class="${dv.q ? 'q' : ''}">${dv.q ? esc(dv.q) : 'Search'}</span></button>
      <button class="pill f" data-hint="Change" onclick="cycleListSort('dv')">Sort: ${(DSORTS.find(x => x[0] === (dv.sort || 'name')) || DSORTS[0])[1]}</button>
      <button class="pill f ${low ? 'on' : ''}" data-hint="Free space" onclick="openFreeSpace()">🗑 Free space</button>
      ${upd.length ? `<button class="pill f" data-hint="Update all" onclick="confirmBatch('update')">⟳ Update all (${upd.length})</button>` : ''}
      ${reb.length ? `<button class="pill f" data-hint="Rebuild all" onclick="confirmBatch('rebuild')">⚒ Rebuild all (${reb.length})</button>` : ''}</div>`;
  v.innerHTML = `<div class="vhead"><div><h2>On your Deck</h2><div class="sub">${dv.q ? gs.length + ' of ' : ''}${all0.length} ReXNative game(s)${h.deck.reachable !== false ? '' : ' · the Deck did not respond: showing the last scan'}</div></div>
      <div class="grow"></div>${storage(sp)}</div>
    ${all}
    ${low ? `<div class="banner">The Deck is running out of space (${gb(sp.free)} free): Free space shows the biggest games and the ones you have not played for a while.</div>` : ''}
    ${pendingBanner(h)}
    ${!isLocal() && S.ver && S.ver.kit && S.ver.kit.outdated ? `<div class="banner">A newer launcher for this Deck is ready (v${esc(S.ver.kit.latest)}). <button class="btn f" style="margin-left:10px" onclick="updateKit()">Update</button></div>` : ''}
    ${gs.length ? `<div class="grid">${tiles}</div>` : `<div class="empty"><b>No games on the Deck yet</b>Go to the Catalogue (R1), choose a game and press Install.</div>`}`;
}
// Procura e ordem nas listas "On Deck" (S.dv) e "On PC" (S.pv).
const DSORTS = [['name', 'Name'], ['played', 'Last played'], ['size', 'Size'], ['added', 'Recently sent']];
const PSORTS = [['name', 'Name'], ['built', 'Recently built'], ['mc', 'Metacritic']];
function sortSearch(list, st, sorts) {
  const q = (st.q || '').trim().toLowerCase();
  let gs = q ? list.filter(g => (g.title || '').toLowerCase().includes(q)) : list.slice();
  const k = st.sort || 'name';
  const num = (a, b, f) => (f(b) || 0) - (f(a) || 0);
  if (k === 'played') gs.sort((a, b) => num(a, b, g => g.last_played));
  else if (k === 'size') gs.sort((a, b) => num(a, b, g => g.size));
  else if (k === 'added') gs.sort((a, b) => num(a, b, g => g.mtime));
  else if (k === 'built') gs.sort((a, b) => num(a, b, g => g.built_at));
  else if (k === 'mc') gs.sort((a, b) => num(a, b, g => g.mc));
  else gs.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'en-GB'));
  return gs;
}
function listRender(which) { if (which === 'dv') renderDeck(); else renderPc(); }
function openListSearch(which) {
  const st = S[which] = S[which] || {};
  openKeyboard(st.q || '', { live: t => { st.q = t; listRender(which); }, done: () => restoreFocus(), clear: true });
}
function cycleListSort(which) {
  const st = S[which] = S[which] || {};
  const sorts = which === 'dv' ? DSORTS : PSORTS;
  const i = sorts.findIndex(x => x[0] === (st.sort || 'name'));
  st.sort = sorts[(i + 1) % sorts.length][0];
  listRender(which);
  const el = $$('.pill', $(which === 'dv' ? '#v-deck' : '#v-pc')).find(e => e.textContent.trim().startsWith('Sort'));
  if (el) focus(el); else restoreFocus();
}
// Libertar espaço: os jogos do Deck do maior para o mais pequeno, com quando se jogou cada um;
// escolhem-se vários e apagam-se de uma vez (com cópia das gravações para o PC).
function openFreeSpace() {
  const h = S.home || {};
  const sp = ((h.deck || {}).space || {}).interno || {};
  const gs = (h.games || []).filter(g => !g.job).slice().sort((a, b) => (b.size || 0) - (a.size || 0));
  const l = openLayer(`<div class="sheet confirm" style="width:900px"><h3>Free space on the Deck</h3>
    <p>${gb(sp.free)} free of ${gb(sp.total)}. Choose the games to delete: ${isLocal() ? 'the saves and settings are backed up first, and you can install the games again from the Catalogue'
      : 'the saves and settings are copied to the PC first, and the games stay on the PC to install again'}.</p>
    <div class="opts" style="max-height:430px;overflow:auto">${gs.map(g => `<button class="check f" data-slug="${esc(g.slug)}" data-size="${g.size || 0}" data-hint="Choose" onclick="this.classList.toggle('on');freeTotal()">
      <span class="box">✓</span><span style="flex:1">${esc(g.title)}</span><span style="color:var(--muted);margin-left:12px">${gb(g.size)} · ${g.last_played ? 'played ' + ago(g.last_played) : 'never played'}</span></button>`).join('')}</div>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn d f" id="freebtn" data-hint="Delete" onclick="confirmFree()" disabled>Delete</button></div></div>`, { focus: '.check' });
  return l;
}
function freeTotal() {
  const sel = $$('.check.on', scope());
  const total = sel.reduce((a, b) => a + (parseInt(b.dataset.size, 10) || 0), 0);
  const btn = $('#freebtn', scope());
  btn.disabled = !sel.length;
  btn.textContent = sel.length ? `Delete ${sel.length} game(s) · frees ${gb(total)}` : 'Delete';
}
function confirmFree() {
  const sel = $$('.check.on', scope());
  if (!sel.length) return;
  const slugs = sel.map(b => b.dataset.slug);
  const names = slugs.map(sl => (deckGame(sl) || { title: sl }).title);
  const total = sel.reduce((a, b) => a + (parseInt(b.dataset.size, 10) || 0), 0);
  openLayer(`<div class="sheet confirm"><h3>Delete ${slugs.length} game(s) from the Deck?</h3>
    <p>${names.map(esc).join(', ')}. Frees ${gb(total)}. ${isLocal() ? 'The saves and settings are backed up first; this cannot be undone (install again from the Catalogue).'
      : 'The saves and settings are copied to the PC first; this cannot be undone on the Deck (install again from On PC).'}</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn d f" data-hint="Delete" onclick='doFree(${JSON.stringify(slugs).replace(/'/g, "&#39;")})'>Delete</button></div></div>`, { focus: '.btn' });
}
async function doFree(slugs) {
  try {
    const j = await api('/api/remote/delete', { body: { slugs, backup: true } });
    S.seen[j.id] = j.status;
    toast(`Deleting ${slugs.length} game(s) from the Deck: follow it in Requests`);
    closeAll();
    setTimeout(() => refreshHome(), 4000);
  } catch (e) { toast(e.message, true); }
}
// Os jogos que "Update all" e "Rebuild all" levam (as mesmas contas que o PC faz).
function batchGames(mode) {
  return ((S.home || {}).games || []).filter(g => g.on_pc && !g.job && (mode === 'update'
    ? (g.update || !g.complete || (!g.in_library && !g.pending_add))
    : (g.fresh && g.fresh.state === 'desatualizado')));
}
function confirmBatch(mode) {
  const gs = batchGames(mode);
  if (!gs.length) return;
  const rebuild = mode === 'rebuild';
  openLayer(`<div class="sheet confirm" style="width:860px"><h3>${rebuild ? 'Rebuild' : 'Update'} ${gs.length} game(s)?</h3>
    <p>${rebuild ? 'Each one is built again on the PC with the latest ReXNative fixes, tested (also with the Deck settings) and sent to the Deck, one after the other: about 5 minutes per game.'
      : 'The newer build on the PC of each one goes to the Deck, one after the other (only the files that changed).'}
      One request in Requests, and one notice at the end.</p>
    <div class="note" style="color:var(--text)">${gs.map(g => esc(g.title)).join(' · ')}</div>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="${rebuild ? 'Rebuild' : 'Update'}" onclick="doBatch('${mode}')">${rebuild ? 'Rebuild all' : 'Update all'}</button></div></div>`, { focus: '.btn.p' });
}
async function doBatch(mode) {
  try {
    const j = await api('/api/remote/' + (mode === 'rebuild' ? 'rebuild-all' : 'update-all'), { body: {} });
    S.seen[j.id] = j.status;
    toast(`${mode === 'rebuild' ? 'Rebuilding' : 'Updating'} on ${side()}: follow it in Requests (R1)`);
    closeAll();
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}
function deckGame(slug) { return ((S.home || {}).games || []).find(g => g.slug === slug); }
function openDeckGame(slug) {
  const g = deckGame(slug);
  if (!g) return;
  const notes = [];
  if (g.update) notes.push(`A newer build is ready on ${side()}.`);
  if (g.pending_add) notes.push('Joins the library when you exit the Manager.');
  else if (!g.in_library) notes.push('Has no shortcut in the Steam library.');
  if (!g.complete) notes.push('The transfer did not finish: update to send the rest.');
  const fr = g.fresh;
  const stale = fr && fr.state === 'desatualizado';
  if (stale) notes.push(`Built before ${[fr.missing_count ? fr.missing_count + ' ReXNative fix(es)' : '', fr.sdk_changed ? 'the new SDK' : ''].filter(Boolean).join(' and ')}: rebuild to get them (${isLocal() ? 'it takes a while on the Deck' : '5 to 7 min on the PC'}).`);
  // Sem PC mode, a game the PC built and sent: no work folder here. Its settings, saves and
  // achievements work all the same; updating it or a report needs it built here first.
  const pcBuilt = isLocal() && !g.on_pc;
  const mine = g.on_pc || pcBuilt;
  openLayer(`<div class="sheet detail">
    <div class="big">${img(g.title, g.slug)}</div>
    <div class="grow">
      <h3>${esc(g.title)}</h3>
      <div class="facts">
        <span>Size</span><b>${gb(g.size)}</b>
        <span>Location</span><b>${g.where === 'sd' ? 'microSD card' : 'Internal storage'}</b>
        <span>Saves</span><b>${g.saves ? g.saves + ' save(s)' : 'none yet'}</b>
        <span>Last played</span><b>${g.last_played ? ago(g.last_played) : 'never'}</b>
        ${g.snapshots ? `<span>Snapshots</span><b>${g.snapshots} in the last day (newest ${ago(g.snapshot_at)})</b>` : ''}
        ${g.achievements && g.achievements.count ? `<span>Achievements</span><b>${g.achievements.unlocked} of ${g.achievements.count} · ${g.achievements.got_score} of ${g.achievements.gamerscore} G</b>` : ''}
      </div>
      ${notes.length ? `<div class="note">${notes.map(esc).join('<br>')}</div>` : ''}
      <div class="acts">
        ${g.appid && g.in_library && g.complete ? `<button class="btn p f" data-hint="Play" onclick="playGame('${esc(g.slug)}')">▶ Play</button>` : ''}
        ${g.on_pc && (g.update || !g.complete || (!g.in_library && !g.pending_add)) ? `<button class="btn p f" data-hint="Send" onclick="updateGame('${esc(g.slug)}')">${g.update ? 'Update' : 'Complete'}</button>` : ''}
        ${g.on_pc && stale && !g.job ? `<button class="btn p f" data-hint="Rebuild" onclick="rebuildGame('${esc(g.slug)}')">Rebuild and send</button>` : ''}
        ${g.achievements && g.achievements.count ? `<button class="btn f" data-hint="Open" onclick="openAchievements('${esc(g.slug)}')">Achievements</button>` : ''}
        ${pcBuilt && !g.job ? `<button class="btn f" data-hint="Build" onclick="openTakeover('${esc(g.slug)}')">Build on this Deck</button>` : ''}
        ${mine ? `<button class="btn f" onclick="openSettings('${esc(g.slug)}')">Settings</button>` : ''}
        ${g.on_pc ? `<button class="btn f" onclick="openReport('${esc(g.slug)}')">Report a problem</button>`
          : pcBuilt ? `<button class="btn f" onclick="openTakeover('${esc(g.slug)}', true)">Report a problem</button>` : ''}
        ${mine ? `<button class="btn f" onclick="openRestore('${esc(g.slug)}')">Restore saves</button>` : ''}
        ${isLocal() && !g.job && (g.where === 'sd' || ((S.home || {}).deck || {}).sd) ? `<button class="btn f" onclick="openMove('${esc(g.slug)}')">${g.where === 'sd' ? 'Move to internal storage' : 'Move to the microSD card'}</button>` : ''}
        ${linuxButton(g)}
        <button class="btn d f" onclick="confirmDelete('${esc(g.slug)}')">Delete from Deck</button>
        <button class="btn f" onclick="closeLayer()">Close</button>
      </div>
      ${g.on_pc ? '' : pcBuilt ? '<div class="note">The PC built this game. Play it, change its settings, restore its saves and see its achievements here; to update it, rebuild it or have Claude look at a problem on this Deck, build it here first (Build on this Deck).</div>'
        : '<div class="note">This game is not in the PC folders: it can only be deleted.</div>'}
      <div id="gcard"><div class="note">Reading the versions…</div></div>
    </div></div>`);
  if (mine) loadGameCard(slug);
  else $('#gcard').innerHTML = '';
}
// Sem PC mode: the game moved between internal storage and the microSD card, its saves with it.
function openMove(slug) {
  const g = deckGame(slug) || { title: slug };
  const to = g.where === 'sd' ? 'internal' : 'sd';
  const sp = ((S.home || {}).deck || {}).space || {};
  const free = (to === 'sd' ? sp.sd : sp.interno) || {};
  const there = to === 'sd' ? 'the microSD card' : 'internal storage';
  const short = g.size != null && free.free != null && g.size + 5e8 > free.free;
  openLayer(`<div class="sheet confirm" style="width:760px"><h3>Move ${esc(g.title)} to ${there}?</h3>
    <p>The game (${gb(g.size)}) and its saves go to ${there} (${gb(free.free)} free there), then the old copy is removed. Steam's shortcut follows when you exit the Manager.${g.on_pc ? '' : ' The PC built it: its folder is copied as it is.'}</p>
    ${short ? '<p style="color:var(--warn)">There is not enough space there.</p>' : ''}
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" onclick="doMove('${esc(slug)}', '${to}')"${short ? ' disabled' : ''}>Move</button></div></div>`, { focus: '.btn:not(.p)' });
}
async function doMove(slug, to) {
  try {
    await api('/api/remote/move/' + encodeURIComponent(slug), { body: { to } });
    closeAll();
    toast('Moving: follow it in Requests');
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}
// Sem PC mode: a game the PC built, built again on this Deck (its archive from the catalogue, the
// PC's recipe), over the PC's copy: the saves and settings stay; then it is this Deck's game.
async function openTakeover(slug, report) {
  const g = deckGame(slug) || { title: slug };
  let t;
  try { t = await api('/api/remote/takeover/' + encodeURIComponent(slug), { timeout: 90000 }); }
  catch (e) { toast(e.message, true); return; }
  const lead = report ? `<p>The PC built ${esc(g.title)}. Claude looks at a problem on this Deck once the game is built here: build it first, then Report a problem works on it.</p>` : '';
  if (!t.possible) {
    openLayer(`<div class="sheet confirm" style="width:760px"><h3>Build ${esc(g.title)} on this Deck</h3>${lead}
      <p>${esc(t.why)}</p><div class="acts"><button class="btn f" onclick="closeLayer()">Close</button></div></div>`);
    return;
  }
  const mins = t.prepare_min || [0, 0];
  const steps = [t.download ? `download ${gb(t.download)} (about ${t.download_min} min)` : 'its archive is already on the Deck',
    `prepare, build and test it: ${mins[0]} to ${mins[1]} min${t.recipe ? ", with what the PC's prepare learned" : ''}`];
  openLayer(`<div class="sheet confirm" style="width:820px"><h3>Build ${esc(g.title)} on this Deck</h3>${lead}
    <p>It takes about ${mins[0] + (t.download_min || 0)} to ${mins[1] + (t.download_min || 0)} minutes: ${esc(steps.join(', then '))}. While you play, it waits.</p>
    <p>Space: about ${gb(t.need)} while it builds; the Deck has ${gb(t.free)} free.${t.enough ? '' : ' <b style="color:var(--warn)">Not enough: delete a game or move one to the microSD card first.</b>'}</p>
    <p>Your saves and your settings for this game stay. Afterwards it is this Deck's game: Update, Rebuild and Report a problem work here. If you use the PC again (PC or Automatic mode), the PC's next update of this game replaces this build; the saves stay.</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" onclick="doTakeover('${esc(slug)}')"${t.enough ? '' : ' disabled'}>Build it here</button></div></div>`, { focus: '.btn:not(.p)' });
}
async function doTakeover(slug) {
  const g = deckGame(slug) || { title: slug };
  try {
    await api('/api/remote/takeover/' + encodeURIComponent(slug), { body: {}, timeout: 90000 });
    closeAll();
    toast(`Building ${g.title} on this Deck: follow it in Requests`);
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}
// O cartão do jogo: a versão no Deck e a do PC, o que cada uma corrige, o histórico, os relatórios.
const when2 = t => { if (!t) return '?'; const d = new Date(typeof t === 'number' ? t * 1000 : t); return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); };
function verLine(v) {
  if (!v) return 'unknown';
  const p = ['built ' + when2(v.built_at)];
  p.push(v.commit ? 'ReXNative ' + v.commit + (v.dirty ? ' with unpublished fixes' : '') : 'before version tracking');
  if (v.sent_at) p.push('sent ' + when2(v.sent_at));
  return p.join(' · ');
}
function chgList(cs, max = 6) {
  if (!cs || !cs.length) return '';
  const more = cs.length > max ? `<div class="chg dim f" tabindex="-1">and ${cs.length - max} more</div>` : '';
  return cs.slice(0, max).map(c => `<div class="chg f" tabindex="-1" title="${esc(c.en)}">• ${esc(c.pt)}</div>`).join('') + more;
}
// O cartão abre logo com o que ficou guardado da última vez (localStorage, no perfil do Firefox do
// Gestor) e atualiza-se quando o PC responde, só se mudou alguma coisa.
const CARD_KEY = slug => 'gestor-card-' + slug;
async function loadGameCard(slug) {
  let cached = null;
  try { cached = localStorage.getItem(CARD_KEY(slug)); } catch (e) { /* sem armazenamento: só o PC */ }
  if (cached) { try { renderGameCard(slug, JSON.parse(cached)); } catch (e) { cached = null; } }
  let d;
  try { d = await api('/api/remote/game/' + encodeURIComponent(slug)); }
  catch (e) { const el = $('#gcard'); if (el && !cached) el.innerHTML = `<div class="note">Could not read the versions: ${esc(e.message)}</div>`; return; }
  const text = JSON.stringify(d);
  if (text === cached) return;
  try { localStorage.setItem(CARD_KEY(slug), text); } catch (e) { /* cheio ou sem armazenamento */ }
  renderGameCard(slug, d);
}
function renderGameCard(slug, d) {
  const el = $('#gcard');
  if (!el || el.closest('.layer') !== S.layers[S.layers.length - 1]?.el) return;  // o cartão já fechou
  const inf = d.info || {};
  const meta = [(inf.genres || []).join(', '), inf.year, inf.mc ? 'Metacritic ' + inf.mc : '', d.title_update ? 'TU ' + d.title_update : '', d.dlc ? d.dlc + ' DLC' : ''].filter(Boolean).join(' · ');
  const st = d.deck_settings || {};
  const sets = [d.renderer, st.upscaler === false ? 'upscaler off' : st.upscaler_mode ? 'upscaler ' + st.upscaler_mode : '', st.menu_fps ? st.menu_fps + ' FPS cap' : ''].filter(Boolean).join(' · ');
  const h = [];
  if (meta) h.push(`<div class="meta" style="margin:14px 0 0">${esc(meta)}</div>`);
  h.push(`<div class="sec"><h4>On the Deck</h4><div class="vline f" tabindex="-1">${esc(verLine(d.deck_version))}</div><div class="vline dim">${esc(sets)}</div></div>`);
  if (d.pc_newer) {
    h.push(`<div class="sec"><h4>Ready on ${side()} <span class="bd g">Update</span></h4><div class="vline f" tabindex="-1">${esc(verLine(d.pc_version))}</div>
      ${d.pc_brings.length ? '<div class="sub2">What it brings:</div>' + chgList(d.pc_brings) : '<div class="vline dim">No ReXNative fixes in between (the SDK or the game itself changed).</div>'}</div>`);
  }
  if (d.missing.length || d.sdk_changed) {
    h.push(`<div class="sec"><h4>Not built yet <span class="bd w">Rebuild</span></h4>
      ${d.sdk_changed ? '<div class="chg f" tabindex="-1">• The new SDK (ReXGlue): larger keyboard and message boxes that work with the gamepad, and other system fixes.</div>' : ''}
      ${chgList(d.missing)}</div>`);
  }
  if (d.history.length) {
    h.push(`<div class="sec"><h4>History on the Deck</h4>${d.history.slice(0, 6).map((v, i) => `<div class="hist f" tabindex="-1"><b>${i === 0 ? 'Now: ' : ''}${esc(verLine(v))}</b>
      ${v.changes && v.changes.length ? v.changes.slice(0, 4).map(c => `<div class="chg">• ${esc(c.pt)}</div>`).join('') + (v.changes.length > 4 ? `<div class="chg dim">and ${v.changes.length - 4} more</div>` : '') : `<div class="chg dim">${i === d.history.length - 1 ? 'the first version sent by the Manager' : 'no ReXNative fixes in between'}</div>`}</div>`).join('')}</div>`);
  }
  if ((d.tunings || []).length) {
    h.push(`<div class="sec"><h4>What ReXNative tunes for this game</h4>${d.tunings.map(t => `<div class="chg f" tabindex="-1"><b style="font-weight:600">${esc(t.k)}</b> · ${esc(t.t)}</div>`).join('')}</div>`);
  }
  if (d.reports.length) {
    h.push(`<div class="sec"><h4>Reports</h4>${d.reports.map(r => `<div class="hist f" tabindex="-1"><b>${esc(when2(r.at))} · ${esc(r.where || '')} · ${esc(r.status || '')}</b>
      <div class="chg">${esc(r.text || '')}</div>${r.summary ? `<div class="chg dim" style="white-space:pre-wrap">${esc(r.summary.replace(/\s*(REXNATIVE|COMMITS|SUSPECTS|SUSPEITOS):.*$/gms, '').trim())}</div>` : ''}</div>`).join('')}</div>`);
  }
  el.innerHTML = h.join('');
}
// A build para Linux (experimental) a partir do Deck: compilar no PC, enviar, ou trocar o que arranca.
function linuxButton(g) {
  if (!(S.home || {}).linux_enabled || !g.on_pc || g.job) return '';
  if (g.linux) return `<button class="btn f" data-hint="Change" onclick="linuxDo('${esc(g.slug)}', 'runner', '${g.runner === 'linux' ? 'windows' : 'linux'}')">${g.runner === 'linux' ? 'Start the Windows build' : 'Start the Linux build (experimental)'}</button>`;
  const pc = pcGame(g.slug);
  if (pc && pc.linux_built) return `<button class="btn f" onclick="linuxDo('${esc(g.slug)}', 'deck')">Send the Linux build (experimental)</button>`;
  return `<button class="btn f" onclick="confirmLinuxBuild('${esc(g.slug)}')">Build for Linux (experimental)</button>`;
}
function confirmLinuxBuild(slug) {
  const g = deckGame(slug) || pcGame(slug) || { title: slug };
  openLayer(`<div class="sheet confirm"><h3>Build ${esc(g.title)} for Linux?</h3>
    <p>Experimental: a native Linux build, no Proton, drawn by ReXGlue's renderer on Vulkan (ReXNative is D3D12 only). On the Deck it uses far more GPU than the Windows build, so it is for games that run better, or only, this way.
      The PC builds it in WSL (the first time takes a while); then send it from this card and choose which build the Steam shortcut starts. Saves are separate.</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="Build" onclick="linuxDo('${esc(slug)}', 'build')">Build for Linux</button></div></div>`, { focus: '.btn.p' });
}
async function linuxDo(slug, what, runner) {
  try {
    const j = await api(`/api/remote/linux/${encodeURIComponent(slug)}/${what}`, { body: { runner } });
    S.seen[j.id] = j.status;
    toast(what === 'build' ? 'Building for Linux on the PC: follow it in Requests' : what === 'deck' ? 'Sending the Linux build to the Deck'
      : runner === 'linux' ? 'The Steam shortcut will start the Linux build' : 'The Steam shortcut will start the Windows build');
    closeAll();
    setTimeout(() => { refreshHome(); loadPc(); }, 1500);
  } catch (e) { toast(e.message, true); }
}
// As conquistas de um jogo: a lista vem do jogo, as desbloqueadas do que ele gravou no Deck.
async function openAchievements(slug) {
  let r;
  try { r = await api('/api/remote/achievements/' + encodeURIComponent(slug)); } catch (e) { toast(e.message, true); return; }
  if (r.none) { toast(r.reason, true); return; }
  const s = encodeURIComponent(slug);
  const row = a => `<div class="ach f${a.unlocked ? '' : ' locked'}" tabindex="-1">
    ${a.image != null ? `<img src="/api/remote/achievements/${s}/icon/${a.image}" alt="">` : '<div class="ph">?</div>'}
    <div class="grow"><b>${esc(a.name)}</b><span class="g">${a.gamerscore} G</span>
      <div class="d">${esc(a.description)}</div>
      <div class="w">${a.unlocked ? 'Unlocked' + (a.when ? ' ' + esc(when2(a.when)) : '') + (a.where.includes('deck') ? '' : ' on the PC') : 'Locked'}</div></div></div>`;
  const pct = r.count ? 100 * r.unlocked / r.count : 0;
  openLayer(`<div class="sheet confirm achsheet" style="width:900px"><h3>Achievements: ${esc(r.title)}</h3>
    <p style="margin:0 0 6px">${r.unlocked} of ${r.count} unlocked · ${r.got_score} of ${r.gamerscore} G</p>
    <div class="achbar"><div style="width:${pct.toFixed(1)}%"></div></div>
    <div class="achlist scrollbox">${r.items.map(row).join('')}</div>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Close</button></div></div>`, { focus: '.ach' });
}
// Conquistas novas desde a última vez que o Gestor as viu (o PC lê-as do Deck sempre que o alcança).
// A snapshot taken in a game since the Manager last looked: say how to send it.
const SNAP_KEY = 'gestor-snap-last';
function notifySnapshots(h) {
  const gs = (h.games || []).filter(g => g.snapshot_at);
  if (!gs.length) return;
  const newest = gs.reduce((a, g) => g.snapshot_at > a.snapshot_at ? g : a);
  let last = null;
  try { last = localStorage.getItem(SNAP_KEY); localStorage.setItem(SNAP_KEY, String(newest.snapshot_at)); } catch (e) { return; }
  if (last !== null && newest.snapshot_at > parseFloat(last))
    toast(`Snapshot from ${newest.title}: open the game here and Report a problem to send it to Claude`);
}
const ACH_KEY = 'gestor-ach-last';
function notifyAchievements(h) {
  const r = h.achievements_recent || [];
  if (!r.length) return;
  let last = null;
  try { last = localStorage.getItem(ACH_KEY); } catch (e) { return; }
  try { localStorage.setItem(ACH_KEY, r[0].when || ''); } catch (e) { /* sem armazenamento */ }
  if (last === null) {
    const n = (h.games || []).reduce((t, g) => t + ((g.achievements || {}).unlocked || 0), 0);
    if (n) toast(`Achievements: ${n} unlocked so far. Open a game on the Deck tab to see them all.`);
    return;
  }
  const fresh = r.filter(a => (a.when || '') > last);
  if (fresh.length === 1) toast(`Achievement unlocked in ${fresh[0].title}: ${fresh[0].name} (${fresh[0].gamerscore} G)`);
  else if (fresh.length > 1) toast(`${fresh.length} achievements unlocked: ${fresh.map(a => a.name).join(', ')}`);
}
async function openRestore(slug) {
  const g = deckGame(slug) || { title: slug };
  let bs = [];
  try { bs = (await api('/api/remote/backups/' + encodeURIComponent(slug))).backups; } catch (e) { toast(e.message, true); return; }
  openLayer(`<div class="sheet confirm" style="width:820px"><h3>Restore saves: ${esc(g.title)}</h3>
    ${bs.length ? `<p>The copies on ${side()} (made when the game was deleted from the Deck). Restoring puts that copy's saves and settings back on the Deck, over the current ones.</p>
      <div class="opts">${bs.map(b => `<button class="hist f" data-hint="Restore" onclick="confirmRestore('${esc(slug)}', '${esc(b.file)}', '${esc(when2(b.at))}')"><b>${esc(when2(b.at))}</b>
        <div class="chg">${b.saves} save file(s) · ${gb(b.size)}</div></button>`).join('')}</div>`
      : `<p>No copies of this game's saves on ${side()} yet: they are made when you delete the game from the Deck with "Back up the saves" on.</p>`}
    <div class="acts"><button class="btn f" onclick="closeLayer()">Close</button></div></div>`);
}
function confirmRestore(slug, file, at) {
  openLayer(`<div class="sheet confirm"><h3>Restore the copy of ${esc(at)}?</h3>
    <p>The saves and settings on the Deck are replaced by that copy. The game must not be open.</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="Restore" onclick="doRestore('${esc(slug)}', '${esc(file)}')">Restore</button></div></div>`, { focus: '.btn.p' });
}
async function doRestore(slug, file) {
  try {
    const j = await api('/api/remote/restore/' + encodeURIComponent(slug), { body: { file } });
    S.seen[j.id] = j.status;
    toast('Restoring the saves: follow it in Requests');
    closeAll();
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}
// Jogar: o Gestor fecha e o PC arranca o jogo pelo Steam assim que ele fechou.
async function playGame(slug) {
  const g = deckGame(slug) || { title: slug };
  try {
    await api('/api/remote/play/' + encodeURIComponent(slug), { body: {} });
    closeAll();
    toast(`Starting ${g.title}: the Manager closes first`);
    setTimeout(doExit, 600);
  } catch (e) { toast(e.message, true); }
}
async function rebuildGame(slug) {
  try {
    await api('/api/remote/rebuild/' + encodeURIComponent(slug), { body: {} });
    toast(isLocal() ? 'Rebuilding on this Deck: it is installed again on its own' : 'Rebuilding on the PC: it then goes to the Deck on its own');
    closeAll();
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}
async function updateGame(slug) {
  try {
    await api('/api/remote/update/' + encodeURIComponent(slug), { body: {} });
    toast('Sending the rest to the Deck');
    closeAll();
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}

const QUICK = [
  ['rexnative.classic', 'Renderer', [['', 'Default (Native)'], ['false', 'Native (ReXNative)'], ['true', 'Classic (ReXGlue)']]],
  ['rexnative.upscaler', 'Upscaler', [['', 'Default'], ['true', 'On'], ['false', 'Off']]],
  ['rexnative.upscaler_mode', 'Upscaler mode', [['', 'Default'], ['native', 'Native AA'], ['quality', 'Quality'], ['balanced', 'Balanced'], ['performance', 'Performance']]],
  ['rexnative.menu_fps', 'FPS limit', [['', 'Default (60)'], ['30', '30'], ['60', '60'], ['0', 'Unlimited']]],
];
async function openSettings(slug) {
  let vals = {};
  try { vals = (await api('/api/remote/settings/' + encodeURIComponent(slug))).values; } catch (e) { toast(e.message, true); return; }
  const g = deckGame(slug) || { title: slug };
  const rows = QUICK.map(([k, label, opts]) => {
    const i = Math.max(0, opts.findIndex(o => o[0] === (vals[k] || '')));
    return `<button class="opt f" data-key="${k}" data-i="${i}" data-hint="Change" onclick="cycle(this, 1)">
      <span class="l">${esc(label)}</span><span class="arr">◀</span><span class="v">${esc(opts[i][1])}</span><span class="arr">▶</span></button>`;
  }).join('');
  openLayer(`<div class="sheet confirm" style="width:720px"><h3>Settings on the Deck</h3>
    <p>${esc(g.title)}: what you change here goes to the Deck and replaces the game's settings there.</p>
    <div class="opts">${rows}</div>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="Save" onclick="saveSettings('${esc(slug)}')">Save and send</button></div></div>`);
}
function cycle(el, d) {
  if (el.id === 'rsecs') return reportSecs(d);
  if (el.id === 'owhere') {
    const sp = ((S.home || {}).deck || {}).space || {};
    const opts = [`Internal storage (${gb((sp.interno || {}).free)} free)`, `microSD card (${gb((sp.sd || {}).free)} free)`];
    const i = (parseInt(el.dataset.i, 10) + d + 2) % 2;
    el.dataset.i = i;
    $('.v', el).textContent = opts[i];
    return;
  }
  const q = QUICK.find(x => x[0] === el.dataset.key);
  if (!q) return;
  const n = q[2].length;
  const i = (parseInt(el.dataset.i, 10) + d + n) % n;
  el.dataset.i = i;
  $('.v', el).textContent = q[2][i][1];
}
async function saveSettings(slug) {
  const values = {};
  for (const el of $$('.opt', scope())) { const q = QUICK.find(x => x[0] === el.dataset.key); values[el.dataset.key] = q[2][parseInt(el.dataset.i, 10)][0]; }
  try {
    await api('/api/remote/settings/' + encodeURIComponent(slug), { body: { values } });
    toast('Settings on their way to the Deck');
    closeAll();
  } catch (e) { toast(e.message, true); }
}
function confirmDelete(slug) {
  const g = deckGame(slug);
  if (!g) return;
  const l = openLayer(`<div class="sheet confirm"><h3>Delete ${esc(g.title)} from the Deck?</h3>
    <p>Frees ${gb(g.size)}. ${g.saves ? `It has <b style="color:var(--warn)">${g.saves} save(s)</b>, kept in the game folder.` : 'No saves found.'}
      ${isLocal() ? 'This cannot be undone (install it again from the Catalogue).' : 'This cannot be undone (the game stays on the PC so you can install it again).'}</p>
    <button class="check f on" id="bk" data-hint="Change" onclick="this.classList.toggle('on')"><span class="box">✓</span>${isLocal() ? 'Back up the saves and settings first' : 'Back up the saves and settings to the PC first'}</button>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn d f" data-hint="Delete" onclick="doDelete('${esc(slug)}')">Delete</button></div></div>`, { focus: '.btn' });
  return l;
}
async function doDelete(slug) {
  const backup = $('#bk', scope()).classList.contains('on');
  try {
    await api('/api/remote/delete', { body: { slugs: [slug], backup } });
    toast('Deleting from the Deck');
    closeAll();
    setTimeout(() => refreshHome(), 4000);
  } catch (e) { toast(e.message, true); }
}

// -- No PC: os jogos preparados neste PC ----------------------------------------------------------
const PCF = [['all', 'All'], ['notdeck', 'Not on Deck'], ['deck', 'On Deck'], ['fixes', 'New fixes'], ['notbuilt', 'Not built']];
const CMP = { iguais: 'same as the classic renderer', nativo_com_erros: 'the native renderer has errors', brilho_diferente: 'different brightness from the classic',
  cenas_diferentes: 'compared at different moments', classico_com_erros: 'the classic renderer is the wrong one', inconclusivo: 'inconclusive' };
const DPC = { iguais: 'fine with the Deck settings', deck_com_erros: 'errors with the Deck settings', cenas_diferentes: 'different moments', inconclusivo: 'inconclusive' };
async function loadPc() {
  try {
    const d = await api('/api/remote/pc', { timeout: 20000 });
    S.pcAt = Date.now();
    const text = JSON.stringify(d.games);
    if (text === S.pcSig) return;
    S.pcSig = text;
    S.pc = d.games;
    if (S.tab === 'pc' && !S.layers.length) {
      const id = S.cur && S.cur.dataset.id;
      renderPc();
      const el = id && $$('.f', $('#v-pc')).find(e => e.dataset.id === id);
      if (el) focus(el, false); else if (!S.cur || !document.body.contains(S.cur)) restoreFocus();
    }
  } catch (e) { /* outra vez mais tarde */ }
}
function pcShown() {
  const f = S.pcf || 'all';
  return sortSearch((S.pc || []).filter(g => f === 'all' || (f === 'notdeck' && !g.on_deck && g.built) || (f === 'deck' && g.on_deck)
    || (f === 'fixes' && g.fresh && g.fresh.state === 'desatualizado') || (f === 'notbuilt' && !g.built)), S.pv || {}, PSORTS);
}
function renderPc() {
  const v = $('#v-pc');
  if (!S.pc) { v.innerHTML = '<div class="center"><div class="spin"></div><p>Reading the games on the PC…</p></div>'; return; }
  const all = S.pc, gs = pcShown();
  const built = all.filter(g => g.built).length, onDeck = all.filter(g => g.on_deck).length;
  const tiles = gs.map(g => {
    const b = [];
    if (g.on_deck) b.push('<span class="bd g">On Deck</span>');
    if (g.xna) b.push('<span class="bd b">XNA</span>');
    else if (!g.built) b.push('<span class="bd b">Not built</span>');
    else if (g.fresh && g.fresh.state === 'desatualizado') b.push('<span class="bd w">New fixes</span>');
    if (g.classic) b.push('<span class="bd i">Classic</span>');
    if (g.compare === 'nativo_com_erros' || g.deckpc === 'deck_com_erros') b.push('<span class="bd w">Errors seen</span>');
    const mc = g.mc ? `<div class="mc ${g.mc >= 75 ? 'h' : g.mc >= 50 ? 'm' : 'l'}">${g.mc}</div>` : '';
    return `<button class="tile f" data-id="${esc(g.slug)}" data-cover="${esc(cover(g.title, g.art ? g.slug : null))}" onclick="openPcGame('${esc(g.slug)}')">
      <div class="cv">${img(g.title, g.art ? g.slug : null)}<div class="badges">${b.join('')}</div>${mc}${g.job ? '<div class="busy"><div class="spin"></div></div>' : ''}</div>
      <div class="nm">${esc(g.title)}</div></button>`;
  }).join('');
  v.innerHTML = `<div class="vhead"><div><h2>On the PC</h2><div class="sub">${all.length} game(s) prepared · ${built} built · ${onDeck} on the Deck</div></div></div>
    <div class="tools">
      <button class="pill search f" data-hint="Search" onclick="openListSearch('pv')">🔍 <span class="${(S.pv || {}).q ? 'q' : ''}">${(S.pv || {}).q ? esc(S.pv.q) : 'Search'}</span></button>
      <button class="pill f" data-hint="Change" onclick="cycleListSort('pv')">Sort: ${(PSORTS.find(x => x[0] === ((S.pv || {}).sort || 'name')) || PSORTS[0])[1]}</button>
      ${PCF.map(([k, t]) => `<button class="pill f ${(S.pcf || 'all') === k ? 'on' : ''}" onclick="setPcFilter('${k}')">${t}</button>`).join('')}</div>
    ${gs.length ? `<div class="grid">${tiles}</div>` : '<div class="empty"><b>Nothing here</b>Change the filter.</div>'}`;
}
function setPcFilter(k) {
  S.pcf = k;
  renderPc();
  const el = $$('.pill', $('#v-pc')).find(e => e.textContent.trim() === PCF.find(x => x[0] === k)[1]);
  if (el) focus(el); else restoreFocus();
}
function pcGame(slug) { return (S.pc || []).find(g => g.slug === slug); }
function openPcGame(slug) {
  const g = pcGame(slug);
  if (!g) return;
  const fr = g.fresh;
  const rows = [];
  rows.push(['On the PC', g.built ? `built ${when2(g.built_at)}${fr && fr.commit ? ' · ReXNative ' + fr.commit : ''}` : (g.xna ? 'XNA: does not run yet' : 'prepared, not built')]);
  if (fr && fr.state === 'desatualizado') rows.push(['Fixes', `${fr.missing_count ? fr.missing_count + ' ReXNative fix(es)' : ''}${fr.missing_count && fr.sdk_changed ? ' and ' : ''}${fr.sdk_changed ? 'the new SDK' : ''} not built in yet`]);
  else if (fr) rows.push(['Fixes', 'has the latest ReXNative fixes']);
  if (g.boot) rows.push(['Boot test', g.boot.ok ? `runs${g.boot.fps ? ' · about ' + g.boot.fps + ' FPS' : ''}${g.boot.classic_fallback ? ' (on the classic renderer: the native one failed)' : ''}` : 'failed']);
  if (g.compare) rows.push(['Native vs classic', CMP[g.compare] || g.compare]);
  if (g.deckpc) rows.push(['Deck settings test', DPC[g.deckpc] || g.deckpc]);
  rows.push(['Renderer', `${g.classic ? 'Classic' : 'Native'} on the PC · ${g.classic_deck ? 'Classic' : 'Native'} on the Deck`]);
  if (g.title_update || g.dlc) rows.push(['Content', [g.title_update ? 'title update ' + g.title_update : '', g.dlc ? g.dlc + ' DLC' : ''].filter(Boolean).join(' · ')]);
  const meta = [(g.genres || []).join(', '), g.year, g.mc ? 'Metacritic ' + g.mc : ''].filter(Boolean).join(' · ');
  const acts = [];
  if (g.job) acts.push(`<button class="btn f" onclick="closeLayer();switchTab('orders')">Busy on the PC: see Requests</button>`);
  else {
    if (g.built && !g.on_deck && !g.xna) acts.push(`<button class="btn p f" data-hint="Install" onclick="confirmPcInstall('${esc(g.slug)}')">Install on the Deck</button>`);
    if (g.on_deck) acts.push(`<button class="btn p f" onclick="closeLayer();switchTab('deck');openDeckGame('${esc(g.slug)}')">Open on the Deck tab</button>`);
    if (!g.xna && (!g.built || (fr && fr.state === 'desatualizado'))) acts.push(`<button class="btn f" data-hint="Build" onclick="pcRebuild('${esc(g.slug)}')">${g.built ? (g.on_deck ? 'Rebuild and send' : 'Rebuild') : 'Build and test'}</button>`);
    if ((S.home || {}).linux_enabled && g.built && !g.xna) acts.push(`<button class="btn f" onclick="confirmLinuxBuild('${esc(g.slug)}')">${g.linux_built ? 'Rebuild for Linux' : 'Build for Linux'} (experimental)</button>`);
  }
  acts.push('<button class="btn f" onclick="closeLayer()">Close</button>');
  openLayer(`<div class="sheet detail">
    <div class="big">${img(g.title, g.art ? g.slug : null)}</div>
    <div class="grow">
      <h3>${esc(g.title)}</h3>
      ${meta ? `<div class="meta">${esc(meta)}</div>` : ''}
      <div class="facts">${rows.map(([k, t]) => `<span>${esc(k)}</span><b style="font-weight:500">${esc(t)}</b>`).join('')}</div>
      <div class="acts">${acts.join('')}</div>
      <div id="pctune"></div>
    </div></div>`);
  api('/api/remote/tunings/' + encodeURIComponent(slug)).then(d => {
    const el = $('#pctune');
    if (el && (d.tunings || []).length) el.innerHTML = `<div class="sec"><h4>What ReXNative tunes for this game</h4>${d.tunings.map(t => `<div class="chg f" tabindex="-1"><b style="font-weight:600">${esc(t.k)}</b> · ${esc(t.t)}</div>`).join('')}</div>`;
  }).catch(() => {});
}
function confirmPcInstall(slug) {
  const g = pcGame(slug);
  const h = S.home || {};
  const sp = (h.deck || {}).space || {};
  const where = sp.sd ? `<button class="opt f" id="owhere" data-i="0" data-hint="Change" onclick="cycle(this, 1)">
      <span class="l">Install to</span><span class="arr">◀</span><span class="v">Internal storage (${gb((sp.interno || {}).free)} free)</span><span class="arr">▶</span></button>` : '';
  openLayer(`<div class="sheet confirm"><h3>Install ${esc(g.title)} on the Deck?</h3>
    <p>It is already built on the PC: it goes straight to the Deck and joins the library (when you exit the Manager).</p>
    ${where}
    <p>Free on the Deck: <b style="color:var(--text)">${gb((sp.interno || {}).free)}</b></p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="Install" onclick="doPcInstall('${esc(slug)}')">Install</button></div></div>`, { focus: '.btn.p' });
}
async function doPcInstall(slug) {
  const w = $('#owhere', scope());
  try {
    const j = await api('/api/remote/install/' + encodeURIComponent(slug), { body: { root: w && w.dataset.i === '1' ? 'sd' : null } });
    S.seen[j.id] = j.status;
    toast('Sending to the Deck: follow it in Requests');
    closeAll();
    setTimeout(() => { refreshHome(); loadPc(); }, 1500);
  } catch (e) { toast(e.message, true); }
}
async function pcRebuild(slug) {
  try {
    await api('/api/remote/rebuild/' + encodeURIComponent(slug), { body: {} });
    toast('Building on the PC: follow it in Requests');
    closeAll();
    setTimeout(() => { refreshHome(); loadPc(); }, 1500);
  } catch (e) { toast(e.message, true); }
}

// -- Catálogo -----------------------------------------------------------------------------------
async function loadCatalog() {
  try {
    // Com a assinatura do que já tem: o PC só manda o catálogo (590 KB) se mudou.
    const c = await api('/api/remote/catalog' + (S.catSig ? '?since=' + S.catSig : ''), { timeout: 30000 });
    if (c.same) return;
    S.catSig = c.sig;
    S.cat = c.games;
    S.filt = null;
    S.genres = [...new Set(S.cat.flatMap(g => g.genres || []))].sort((a, b) => a.localeCompare(b, 'en-GB'));
    if (S.tab === 'catalog' && !S.layers.length) { const id = S.cur && S.cur.dataset.id; renderCatalog(); const el = id && $$('.f', $('#v-catalog')).find(e => e.dataset.id === id); if (el) focus(el, false); }
  } catch (e) { /* tenta outra vez mais tarde */ }
}
const SORTS = [['name', 'Name'], ['mc', 'Metacritic'], ['year', 'Year'], ['size', 'Size']];
const KINDS = [['all', 'All'], ['xbla', 'Arcade (XBLA)'], ['disc', 'Discs'], ['deck', 'On Deck'], ['mine', 'Your files']];
// Filtrar e ordenar os jogos todos só quando o filtro ou o catálogo mudam (era a cada passo do foco).
function filtered() {
  const k = JSON.stringify(S.f);
  if (!S.filt || S.filt.k !== k || S.filt.cat !== S.cat) S.filt = { k, cat: S.cat, gs: filterNow() };
  return S.filt.gs;
}
function filterNow() {
  const f = S.f;
  const q = f.q.trim().toLowerCase();
  let gs = (S.cat || []).filter(g =>
    (!q || g.title.toLowerCase().includes(q) || g.key.includes(q)) &&
    (f.kind === 'all' || (f.kind === 'xbla' && g.xbla) || (f.kind === 'disc' && !g.xbla) || (f.kind === 'deck' && g.on_deck) || (f.kind === 'mine' && g.own)) &&
    (!f.genre || (g.genres || []).includes(f.genre)));
  if (f.sort === 'mc') gs = gs.slice().sort((a, b) => (b.mc || 0) - (a.mc || 0));
  else if (f.sort === 'year') gs = gs.slice().sort((a, b) => (b.year || 0) - (a.year || 0));
  else if (f.sort === 'size') gs = gs.slice().sort((a, b) => a.size - b.size);
  return gs;
}
function catTile(g) {
  const b = [];
  if (g.on_deck) b.push('<span class="bd g">On Deck</span>');
  else if (g.order) b.push('<span class="bd i">Requested</span>');
  else if (g.built) b.push(`<span class="bd">${isLocal() ? 'Built' : 'On PC'}</span>`);
  else if (g.own) b.push('<span class="bd i">Your file</span>');
  const mc = g.mc ? `<div class="mc ${g.mc >= 75 ? 'h' : g.mc >= 50 ? 'm' : 'l'}">${g.mc}</div>` : '';
  const slug = g.art ? g.local : null;
  return `<button class="tile f" data-id="${esc(g.key)}" data-cover="${esc(cover(g.title, slug, g.xbla))}" onclick="openCatGame(${JSON.stringify(g.key).replace(/"/g, '&quot;')})">
    <div class="cv">${img(g.title, slug, g.xbla)}<div class="badges">${b.join('')}</div>${mc}</div>
    <div class="nm">${esc(g.title)}</div></button>`;
}
function renderCatalog() {
  const v = $('#v-catalog');
  if (!S.cat) { v.innerHTML = '<div class="center"><div class="spin"></div><p>Loading the catalogue…</p></div>'; return; }
  const gs = filtered();
  const f = S.f;
  v.innerHTML = `<div class="vhead"><div><h2>Catalogue</h2><div class="sub">${gs.length} of ${S.cat.length} games · XNA games are left out (they don't run yet)</div></div></div>
    <div class="tools">
      <button class="pill search f" data-hint="Search" onclick="openSearch()">🔍 <span class="${f.q ? 'q' : ''}">${f.q ? esc(f.q) : 'Search for a game'}</span></button>
      ${KINDS.filter(([k]) => k !== 'mine' || S.cat.some(g => g.own)).map(([k, t]) => `<button class="pill f ${f.kind === k ? 'on' : ''}" onclick="setKind('${k}')">${t}</button>`).join('')}
      <button class="pill f" data-hint="Change" onclick="cycleSort()">Sort: ${SORTS.find(s => s[0] === f.sort)[1]}</button>
      <button class="pill f ${f.genre ? 'on' : ''}" onclick="openGenres()">Genre: ${esc(f.genre || 'all')}</button>
    </div>
    ${gs.length ? `<div class="grid" id="cgrid">${gs.slice(0, S.shown).map(catTile).join('')}</div>` : '<div class="empty"><b>Nothing found</b>Change the search or the filters.</div>'}
    ${gs.length > S.shown ? `<div class="empty" style="padding:24px">Showing ${S.shown} of ${gs.length}: scroll down for more</div>` : ''}`;
}
function maybeMore(el) {
  const tiles = $$('#cgrid .tile');
  const i = tiles.indexOf(el);
  const total = filtered().length;
  if (i >= tiles.length - 12 && S.shown < total) {
    S.shown += 60;
    const grid = $('#cgrid');
    grid.insertAdjacentHTML('beforeend', filtered().slice(tiles.length, S.shown).map(catTile).join(''));
    const note = grid.nextElementSibling;
    if (note) note.textContent = S.shown < total ? `Showing ${S.shown} of ${total}: scroll down for more` : '';
  }
}
function refilter(keepFocus) {
  S.shown = 60;
  renderCatalog();
  if (keepFocus) { const el = $$('.f', $('#v-catalog')).find(e => e.textContent.trim().startsWith(keepFocus)); if (el) { focus(el); return; } }
  restoreFocus();
}
function setKind(k) { S.f.kind = k; refilter(KINDS.find(x => x[0] === k)[1]); }
function cycleSort() { const i = SORTS.findIndex(s => s[0] === S.f.sort); S.f.sort = SORTS[(i + 1) % SORTS.length][0]; refilter('Sort'); }
function openGenres() {
  const all = [''].concat(S.genres || []);
  openLayer(`<div class="sheet confirm" style="width:760px"><h3>Genre</h3><div class="tools" style="margin:0">
    ${all.map(g => `<button class="pill f ${S.f.genre === g ? 'on' : ''}" onclick="setGenre(${JSON.stringify(g).replace(/"/g, '&quot;')})">${esc(g || 'All')}</button>`).join('')}</div></div>`,
  { focus: '.pill.on' });
}
function setGenre(g) { S.f.genre = g; closeLayer(); refilter('Genre'); }
function catGame(key) { return (S.cat || []).find(g => g.key === key); }
function openCatGame(key) {
  const g = catGame(key);
  if (!g) return;
  const order = g.order && ((S.home || {}).orders || []).find(o => o.id === g.order);
  const state = g.on_deck ? 'Already on your Deck.' : order ? `Request in progress: ${stageText(order)}`
    : g.built ? (isLocal() ? 'Already built on this Deck: it installs straight away.' : 'Already built on the PC: it goes straight to the Deck.') : '';
  const slug = g.art ? g.local : null;
  openLayer(`<div class="sheet detail">
    <div class="big">${img(g.title, slug, g.xbla)}</div>
    <div class="grow">
      <h3>${esc(g.title)}</h3>
      <div class="meta">${(g.genres || []).length ? `<span>${esc(g.genres.join(', '))}</span>` : ''}${g.year ? `<span>${g.year}</span>` : ''}
        ${g.mc ? `<span>Metacritic <b>${g.mc}</b></span>` : ''}<span>${g.xbla ? 'Arcade (XBLA)' : 'Disc'}</span></div>
      <div class="facts"><span>${g.own ? 'Size' : 'Download'}</span><b>${gb(g.size)}</b><span>Source</span><b>${esc(g.own ? 'Your files (' + g.own + ')' : g.source)}</b><span>${g.own ? 'On ' + side() : 'File'}</span><b style="font-weight:500;font-size:14px;overflow-wrap:anywhere">${esc(g.name)}</b></div>
      ${state ? `<div class="note" style="color:var(--text)">${esc(state)}</div>` : ''}
      <div class="acts">
        ${order ? `<button class="btn p f" onclick="closeLayer();switchTab('orders')">View the request</button>`
          : `<button class="btn p f" data-hint="Install" onclick="confirmOrder(${JSON.stringify(g.key).replace(/"/g, '&quot;')})">${g.on_deck ? 'Install again' : 'Install on the Deck'}</button>`}
        <button class="btn f" onclick="closeLayer()">Close</button>
      </div>
    </div></div>`);
}
function confirmOrder(key) {
  const g = catGame(key);
  const h = S.home || {};
  const free = (((h.deck || {}).space || {}).interno || {}).free;
  const tight = free != null && free < g.size * 1.3 + 1e9;
  const steps = [];
  if (!g.built && !g.own) steps.push(`Download to ${side()} (${gb(g.size)})`);
  if (!g.built) steps.push(`Prepare, build and test on ${side()}${g.own ? ' from your file' : ''} (${isLocal() ? 'it takes a while: the Deck is slower than a PC' : '10 to 40 minutes'}; if it fails, the assistant tries to fix it)`);
  steps.push(isLocal() ? 'Install and add to the library (when you exit the Manager)' : 'Send to the Deck and add to the library (when you exit the Manager)');
  const sdFree = ((((h.deck || {}).space || {}).sd) || {}).free;
  const where = sdFree != null ? `<button class="opt f" id="owhere" data-i="0" data-hint="Change" onclick="cycle(this, 1)">
      <span class="l">Install to</span><span class="arr">◀</span><span class="v">Internal storage (${gb(free)} free)</span><span class="arr">▶</span></button>` : '';
  openLayer(`<div class="sheet confirm"><h3>Install ${esc(g.title)}?</h3>
    <ol style="color:var(--muted);margin:0 0 14px;padding-left:22px">${steps.map(s => `<li style="margin-bottom:6px">${esc(s)}</li>`).join('')}</ol>
    ${where}
    <p>Free on the Deck: <b style="color:${tight ? 'var(--warn)' : 'var(--text)'}">${gb(free)}</b>${sdFree != null ? ` · microSD card: <b style="color:var(--text)">${gb(sdFree)}</b>` : ''}${!isLocal() && h.pc_free_gb != null ? ` · on the PC: <b style="color:var(--text)">${h.pc_free_gb.toFixed(0)} GB</b>` : ''}${tight ? ' (may not be enough: delete a game from the Deck first, or install to the microSD card)' : ''}</p>
    <p>You can keep using the Deck: follow it in Requests.</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="Install" onclick="doOrder(${JSON.stringify(g.key).replace(/"/g, '&quot;')})">Install</button></div></div>`, { focus: '.btn.p' });
}
async function doOrder(key) {
  const g = catGame(key);
  try {
    const w = $('#owhere', scope());
    const root = w && w.dataset.i === '1' ? 'sd' : null;
    const j = await api('/api/remote/order', { body: { item: g.item, name: g.name, root } });
    g.order = j.id;
    S.seen[j.id] = j.status;
    toast(`Requested: ${g.title}. Follow it in Requests (R1).`);
    closeAll();
    const id = S.cur && S.cur.dataset.id;
    renderCatalog();
    const el = $$('.f', $('#v-catalog')).find(e => e.dataset.id === id);
    if (el) focus(el, false);
    refreshHome();
  } catch (e) { toast(e.message, true); }
}

// -- teclado no ecrã ----------------------------------------------------------------------------
const OSK = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM'];
const OSK_SYMBOLS = '@.-_+#!?$%&*()=/:;';
function openSearch() {
  openKeyboard(S.f.q, { live: t => { S.f.q = t; S.shown = 60; renderCatalog(); }, done: () => restoreFocus(), clear: true });
}
// -- reportar um problema a partir do Deck -------------------------------------------------------
const RCHIPS = [['metade', 'Only part of the screen shows'], ['preto', 'Black screen'], ['cintila', 'The image flickers or shakes'],
  ['transparente', 'Things see-through or disappearing'], ['luz', 'Missing lighting or shadows'], ['cores', 'Wrong colours'],
  ['texto', 'Wrong text or menus'], ['lento', 'Slow (low FPS)'], ['fecha', 'Crashes or freezes'],
  ['som', 'Sound problems'], ['comandos', 'Controls do not respond']];
const RSECS = [20, 40, 60, 90];
function openReport(slug) {
  const g = deckGame(slug) || { title: slug };
  const st = { text: '', secs: 1 };
  const l = openLayer(`<div class="sheet confirm" style="width:980px"><h3>Report a problem: ${esc(g.title)}</h3>
    <p>What do you see on the Deck? (choose one or more) Claude investigates on ${side()} with what the Deck knows about the game: the log, the settings and the Steam screenshots (Steam + R1).</p>
    <div class="tools" style="margin:0 0 12px">${RCHIPS.map(([k, t]) => `<button class="pill f" data-chip="${k}" data-hint="Choose" onclick="this.classList.toggle('on')">${esc(t)}</button>`).join('')}</div>
    <button class="check f" id="rtext" data-hint="Type" onclick="reportText()"><span class="box">✎</span><span id="rtextv">Write more (on-screen keyboard)</span></button>
    <div style="height:10px"></div>
    ${g.snapshots ? `<button class="check f on" id="rsnap" data-hint="Change" onclick="this.classList.toggle('on')"><span class="box">✓</span>Send the snapshot${g.snapshots > 1 ? 's' : ''} you took in the game (${g.snapshots}, newest ${ago(g.snapshot_at)}): Claude sees that moment and replays its frames on ${side()}</button>
    <div style="height:10px"></div>` : `<p class="note" style="margin:0 0 10px">Tip: at the place, in the game, press View + Menu and then Y. That moment is saved as a snapshot, and the next report sends it: Claude sees what you saw and replays those frames on ${side()}.</p>`}
    <button class="check f${g.snapshots ? '' : ' on'}" id="rcap" data-hint="Change" onclick="this.classList.toggle('on')"><span class="box">✓</span>Take a screenshot on the Deck: the game opens, is captured and closes on its own</button>
    <div style="height:10px"></div>
    <button class="opt f" id="rsecs" data-hint="Change" onclick="reportSecs(1)"><span class="l">Screenshot at</span><span class="arr">◀</span><span class="v">${RSECS[st.secs]} s</span><span class="arr">▶</span></button>
    <div style="height:10px"></div>
    <button class="check f on" id="rsave" data-hint="Change" onclick="this.classList.toggle('on')"><span class="box">✓</span>Send my save: Claude plays from your progress, to reach a menu or level a new game does not have (your save on the Deck stays as it is)</button>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" data-hint="Send" onclick="sendReport('${esc(slug)}')">Send to Claude</button></div></div>`, { focus: '.pill' });
  l.report = st;
}
function reportSecs(d) {
  const l = S.layers[S.layers.length - 1];
  if (!l || !l.report) return;
  l.report.secs = (l.report.secs + d + RSECS.length) % RSECS.length;
  $('#rsecs .v', l.el).textContent = RSECS[l.report.secs] + ' s';
}
function reportText() {
  const base = S.layers[S.layers.length - 1];
  openTextInput(base.report.text, t => {
    base.report.text = t;
    $('#rtextv', base.el).textContent = t ? '“' + (t.length > 70 ? t.slice(0, 70) + '…' : t) + '”' : 'Write more (on-screen keyboard)';
    $('#rtext', base.el).classList.toggle('on', !!t);
  });
}
async function sendReport(slug) {
  const l = S.layers[S.layers.length - 1];
  const chips = $$('.pill.on', l.el).map(b => b.dataset.chip);
  if (!chips.length && !l.report.text) { toast('Choose what you see or write a description', true); return; }
  const capture = $('#rcap', l.el).classList.contains('on');
  const saves = $('#rsave', l.el).classList.contains('on');
  const snapshots = !!$('#rsnap', l.el) && $('#rsnap', l.el).classList.contains('on');
  try {
    const j = await api('/api/remote/report/' + encodeURIComponent(slug), { body: { chips, text: l.report.text, capture, saves, snapshots, seconds: RSECS[l.report.secs] } });
    S.seen[j.id] = j.status;
    toast(capture ? 'Report sent: the game will open on the Deck for the screenshot and close on its own' : 'Report sent to Claude: follow it in Requests');
    closeAll();
    setTimeout(() => refreshHome(), 1500);
  } catch (e) { toast(e.message, true); }
}
// O teclado no ecrã (a procura do catálogo e o texto livre dos relatórios). live: a cada tecla;
// done: com o texto, quando fecha; clear: a tecla Clear (senão uma vírgula).
// opts.full: capitals (Shift) and symbols, typed as they are (e-mails, passwords, sign-in codes);
// opts.secret: dots in place of what is typed (a password), never shown or kept anywhere else.
function openKeyboard(initial, opts = {}) {
  let text = initial || '';
  let upper = false;
  const keys = opts.full ? OSK.concat([OSK_SYMBOLS]) : OSK;
  const rows = keys.map(r => `<div class="row">${[...r].map(c => `<button class="key f" data-k="${esc(c)}">${esc(c)}</button>`).join('')}</div>`).join('');
  const shown = () => opts.secret ? '•'.repeat(text.length) : text;
  const draw = () => { $('.field span', layer.el).textContent = shown(); if (opts.live) opts.live(text); };
  const type = ch => { text += ch; draw(); };
  const del = () => { text = text.slice(0, -1); draw(); };
  const finish = () => { closeLayer(); if (opts.done) opts.done(text.trim()); };
  const extra = opts.full ? '<button class="key w2 f" data-k="shift">Shift</button>'
    : opts.clear ? '<button class="key w2 f" data-k="clr">Clear</button>' : '<button class="key w2 f" data-k=",">,</button>';
  const layer = openLayer(`<div class="sheet osk">${opts.title ? `<h3>${esc(opts.title)}</h3>` : ''}<div class="field"><span></span><i class="c"></i></div>
    <div class="rows">${rows}<div class="row"><button class="key w4 f" data-k=" ">Space</button><button class="key w2 f" data-k="del">Delete</button>
      ${extra}<button class="key w2 ok f" data-k="ok">Done</button></div></div></div>`,
  { focus: '.key[data-k="Q"]', actions: { x: ['Delete', del], y: ['Space', () => type(' ')], menu: finish } });
  // Small letters until Shift (opts.full); the plain keyboard types small letters only.
  const shift = () => {
    upper = !upper;
    for (const b of $$('.key', layer.el)) if (/^[A-Z]$/.test(b.dataset.k)) b.textContent = upper ? b.dataset.k : b.dataset.k.toLowerCase();
    const sk = $('.key[data-k="shift"]', layer.el);
    if (sk) sk.classList.toggle('on', upper);
  };
  layer.type = type;
  layer.full = !!opts.full;
  layer.del = del;
  layer.back = finish;
  $('.field span', layer.el).textContent = shown();
  if (opts.full) { shift(); shift(); }
  for (const b of $$('.key', layer.el)) b.onclick = () => {
    const k = b.dataset.k;
    if (k === 'del') del(); else if (k === 'clr') { text = ''; draw(); } else if (k === 'ok') finish();
    else if (k === 'shift') shift();
    else type(/^[A-Z]$/.test(k) && !upper ? k.toLowerCase() : opts.full ? k : k.toLowerCase());
  };
  return layer;
}
function openTextInput(initial, done) { return openKeyboard(initial, { done }); }

// -- Pedidos ----------------------------------------------------------------------------------
const OSTEPS = () => [['download', 'Download'], ['build', 'Build on ' + side()], ['deck', isLocal() ? 'Install' : 'Send to the Deck'], ['library', 'Library']];
const RSTEPS = [['deck', 'Collect on the Deck'], ['claude', 'Claude investigates'], ['deck_send', 'Send the fix']];
// O que se pediu do Deck além de instalar e reportar (recompilar, atualizar, definições, apagar).
const KIND_LABEL = { gameplay: 'Gameplay scene', 'deck-report': 'Report', pipeline: 'Rebuild', deck: 'Send', 'deck-delete': 'Delete', 'deck-flush': 'Library', report: 'Report', 'deck-gestor': 'Launcher', 'deck-restore': 'Restore', 'deck-plugin': 'Plugin', 'deck-batch': 'All', 'linux-build': 'Linux build', 'linux-deck': 'Linux to Deck', 'linux-runner': 'Linux / Windows' };
// O título sem o "Report:" que a tarefa já traz (a etiqueta diz o que é).
const otitle = o => String(o.title || '').replace(/^(Report|Relatório|Reenviar para o Deck|Instalar para o Deck|Resend to the Deck|Install to the Deck|Delete from the Deck): /, '');
const stepsOf = o => o.kind === 'deck-report' ? RSTEPS : o.kind === 'order' ? OSTEPS() : [];
function stageIndex(o) {
  const st = stepsOf(o);
  if (o.status === 'ok') return o.kind === 'deck-report' ? st.length : o.stage === 'library' ? 3 : 4;
  const i = st.findIndex(s => s[0] === o.stage);
  return i < 0 ? 0 : i;
}
// What a queued job waits for: the job running before it on the PC (one build or Claude at a time).
function waitText(w) {
  if (!w) return '';
  if (w.restart) return `Continues when the Manager on ${side()} has restarted`;
  const n = w.ahead ? `${w.ahead} more request${w.ahead > 1 ? 's' : ''} before this one` : '';
  if (!w.title) return 'Waiting: ' + (n || side() + ' is busy');
  return `Waiting for ${side()} to finish ${w.title}${w.for_s != null ? ' (running for ' + eta(w.for_s) + ')' : ''}${n ? ', then ' + n : ''}`;
}
const interrupted = () => isLocal() ? 'interrupted (the Manager on this Deck stopped)' : 'interrupted (the PC app closed)';
function stageText(o) {
  const p = o.progress || {};
  if (p.waiting && o.status === 'running') return waitText(p.waiting);
  if (o.status === 'queued' && o.waiting) return waitText(o.waiting);
  if (o.kind !== 'order' && o.kind !== 'deck-report') {
    const b = p.batch;
    if (b && o.status === 'running') {
      const head = `${b.i + 1} of ${b.n}: ${b.current || ''}`;
      const rest = p.total ? `${gb(p.done)} of ${gb(p.total)}` : [p.step_pt, p.phase].filter(Boolean).join(': ');
      return head + (rest ? ' · ' + rest : '') + (b.failed ? ` · ${b.failed} failed` : '');
    }
    if (o.status === 'queued') return 'queued';
    if (o.status === 'ok') return o.last || 'done';
    if (o.status === 'failed') return o.error || 'failed';
    if (o.status === 'cancelled') return 'cancelled';
    if (o.status === 'interrupted') return interrupted();
    if (p.total) return `${gb(p.done)} of ${gb(p.total)}${p.rate ? ' · ' + (p.rate / 1e6).toFixed(1) + ' MB/s' : ''}${p.eta != null && p.done < p.total ? ' · ' + eta(p.eta) + ' left' : ''}`;
    if (p.phase) return [p.step_pt, p.phase].filter(Boolean).join(': ') + (p.pct != null ? ` · ${Math.round(p.pct)}%` : '');
    return o.last || 'running';
  }
  if (o.kind === 'deck-report') {
    const r = o.report || {};
    if (o.status === 'ok') return (r.status || 'investigated') + (r.summary ? ': ' + r.summary.replace(/\s+/g, ' ').slice(0, 200) : '');
    if (o.status === 'failed') return o.error || 'failed';
    if (o.status === 'queued') return 'queued';
    if (o.stage === 'claude') return 'Claude is investigating on ' + side() + (p.phase ? ': ' + p.phase : '');
    if (o.stage === 'deck_send') return 'Sending the fixed version to the Deck' + (p.total ? ` · ${gb(p.done)} of ${gb(p.total)}` : '');
    return o.last || 'Collecting the log and settings on the Deck';
  }
  if (o.status === 'queued') return 'queued';
  if (o.status === 'ok') return o.stage === 'library' ? 'on the Deck: joins the library when you exit the Manager' : "in the Deck's library";
  if (o.status === 'failed') return o.error || 'failed';
  if (o.status === 'cancelled') return 'cancelled';
  if (o.status === 'interrupted') return interrupted();
  if (p.total) return `${gb(p.done)} of ${gb(p.total)}${p.rate ? ' · ' + (p.rate / 1e6).toFixed(1) + ' MB/s' : ''}${p.eta != null && p.done < p.total ? ' · ' + eta(p.eta) + ' left' : ''}`;
  if (p.phase) return [p.step_pt, p.phase].filter(Boolean).join(': ') + (p.pct != null ? ` · ${Math.round(p.pct)}%` : '') + (p.rate && !p.total ? ' · ' + (p.rate / 1e6).toFixed(1) + ' MB/s' : '');
  return p.step || (OSTEPS().find(s => s[0] === o.stage) || ['', 'starting'])[1];
}
// Os passos do PC (preparar, compilar, testar) e as fases do passo em curso, com o que já está feito.
const PSTEP = { prepare: 'Prepare', build: 'Build', get boot() { return 'Test on ' + side(); }, compare: 'Compare', claude: 'Fix by Claude' };
function pcSteps(p) {
  if (!p.step_pt && !(p.phases || []).length) return '';
  const done = (p.steps_done || []).map(k => `<span class="ps done">✓ ${esc(PSTEP[k] || k)}</span>`).join('');
  const phases = (p.phases || []).map(x => `<span class="ps ${x.now ? 'now' : 'done'}">${x.now ? '▶' : '✓'} ${esc(x.name)}</span>`).join('');
  const cur = p.pstep && !(p.phases || []).length ? `<span class="ps now">▶ ${esc(PSTEP[p.pstep] || p.step_pt || '')}</span>` : '';
  const t = [p.step_elapsed != null ? 'in this step for ' + eta(p.step_elapsed) : '', p.elapsed != null ? 'requested ' + eta(p.elapsed) + ' ago' : ''].filter(Boolean).join(' · ');
  return `<div class="psteps">${done}${phases ? `<span class="pgroup">${esc(PSTEP[p.pstep] || '')}:</span>${phases}` : cur}</div>${t ? `<div class="ptime">${esc(t)}</div>` : ''}`;
}
function renderOrders() {
  const v = $('#v-orders');
  const h = S.home;
  if (!h) { v.innerHTML = ''; return; }
  S.sig.orders = ordersShape(h);
  const os = (h.orders || []).slice().sort((a, b) => {
    const act = o => (o.status === 'running' || o.status === 'queued') ? 0 : 1;
    return act(a) - act(b) || String(b.created).localeCompare(String(a.created));
  });
  const rows = os.map(o => {
    const i = stageIndex(o);
    const failed = o.status === 'failed' || o.status === 'cancelled' || o.status === 'interrupted';
    const st = stepsOf(o);
    const steps = st.map(([k, t], n) => `<div class="${n < i ? 'done' : n === i ? (failed ? 'fail' : 'now') : ''}">${t}</div>`).join('');
    const label = o.kind !== 'order' && KIND_LABEL[o.kind] ? `<span class="bd w" style="margin-right:8px">${KIND_LABEL[o.kind]}</span>` : '';
    return `<button class="order f" data-id="${o.id}" data-order="${o.id}" data-cover="${esc(cover(o.title, o.slug))}" data-hint="Details" onclick="openOrder('${o.id}')">
      <div class="th">${img(o.title, o.slug)}</div>
      <div class="body"><div class="t">${label}${esc(otitle(o))}</div>${st.length ? `<div class="steps">${steps}</div>` : ''}
        <div class="live">${orderLive(o)}</div></div></button>`;
  }).join('');
  const done = (h.orders || []).some(o => !['running', 'queued'].includes(o.status));
  v.innerHTML = `<div class="vhead"><div><h2>Requests</h2><div class="sub">From download to library: ${isLocal() ? 'this Deck does the work in the background' : 'the PC does the work, you can keep using the Deck'}</div></div>
    ${done ? '<button class="btn f" data-hint="Clear" onclick="clearRequests()">Clear finished</button>' : ''}</div>
    ${pcWork(h)}
    ${pendingBanner(h)}
    ${rows ? `<div class="orders">${rows}</div>` : '<div class="empty"><b>No requests</b>Choose a game in the Catalogue and press Install.</div>'}`;
}
// Tira da lista os pedidos acabados (os que correm ou estão em fila ficam).
async function clearRequests() {
  try {
    const r = await api('/api/remote/requests/clear', { body: { which: 'finished' } });
    toast(r.cleared ? `${r.cleared} finished request(s) cleared` : 'Nothing to clear');
    await refreshHome();
    S.sig.orders = null;
    if (S.tab === 'orders') render('orders');
  } catch (e) { toast(e.message, true); }
}
// A parte de um pedido que muda enquanto corre: os passos do PC, a linha de estado e a barra.
function orderLive(o) {
  const failed = o.status === 'failed' || o.status === 'cancelled' || o.status === 'interrupted';
  const p = o.progress || {};
  const live = o.status === 'running';
  const pc = p.total ? 100 * p.done / p.total : p.pct;
  const bar = live ? (pc != null ? `<div class="pb"><div style="width:${pc.toFixed(1)}%"></div></div>` : '<div class="pb ind"><div></div></div>') : '';
  return `${live && (o.stage === 'build' || o.kind === 'pipeline') ? pcSteps(p) : ''}
    <div class="line" style="color:${failed ? 'var(--bad)' : o.status === 'ok' ? 'var(--accent)' : 'var(--muted)'}">${esc(stageText(o))}</div>${bar}`;
}
// Só o progresso mudou: atualiza no sítio (sem redesenhar a lista, as capas e o foco).
function updateOrders(h) {
  const v = $('#v-orders');
  const w = $('#pcw span:last-child', v);
  if (w) w.textContent = pcWorkText(h);
  for (const o of h.orders || []) {
    if (o.status !== 'running') continue;
    const box = $(`.order[data-order="${o.id}"] .live`, v);
    if (!box) continue;
    const bar = $('.pb > div', box);
    const p = o.progress || {};
    const pc = p.total ? 100 * p.done / p.total : p.pct;
    if (bar && pc != null && !$('.psteps', box) && !(o.stage === 'build' || o.kind === 'pipeline')) {
      bar.style.width = pc.toFixed(1) + '%';
      $('.line', box).textContent = stageText(o);
    } else box.innerHTML = orderLive(o);
  }
}
// O que muda na folha de um pedido: o estado e os últimos passos.
function orderBody(o) {
  const evs = (o.events || []).slice(-12).reverse();
  const icon = k => ({ ok: '✓', fail: '✕', step: '›', info: '·' }[k] || '·');
  const brief = ((S.home || {}).orders || []).find(x => x.id === o.id) || {};
  return `<p>${esc(stageText(Object.assign({}, brief, o, { stage: (o.result || {}).stage })))}</p>
    <div style="max-height:380px;overflow:auto;font-size:14.5px">${evs.map(e => `<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #ffffff10;color:${e.kind === 'fail' ? 'var(--bad)' : e.kind === 'ok' ? 'var(--text)' : 'var(--muted)'}"><b style="width:16px">${icon(e.kind)}</b><span style="width:60px;color:var(--dim)">${esc((e.t || '').slice(11, 16))}</span><span style="flex:1">${esc(e.text)}</span></div>`).join('')}</div>`;
}
async function openOrder(id) {
  let o;
  try { o = await api('/api/remote/job/' + id); } catch (e) { toast(e.message, true); return; }
  const active = o.status === 'running' || o.status === 'queued';
  const brief = ((S.home || {}).orders || []).find(x => x.id === o.id) || {};
  const rep = brief.report;
  const layer = openLayer(`<div class="sheet confirm" style="width:900px"><h3>${o.kind !== 'order' && KIND_LABEL[o.kind] ? KIND_LABEL[o.kind] + ': ' : ''}${esc(otitle(o))}</h3>
    ${rep ? `<p style="color:var(--text)">${esc(rep.text || '')}</p>${rep.summary ? `<div class="banner" style="margin:0 0 12px;white-space:pre-wrap">${esc(rep.status || '')}: ${esc(rep.summary)}</div>` : ''}` : ''}
    <div class="ochat" hidden><div class="chead"><b class="who">Claude</b><span class="cst"></span></div><div class="clog"></div></div>
    <div class="obody">${orderBody(o)}</div>
    <div class="acts"><button class="btn p f osay" style="display:none" data-hint="Write" onclick="chatWrite('${o.id}')">Write to Claude</button>${active ? `<button class="btn d f" onclick="cancelOrder({id:'${o.id}',title:${JSON.stringify(o.title).replace(/"/g, '&quot;')}})">Cancel request</button>` : ''}
      ${o.kind === 'order' && ['failed', 'cancelled', 'interrupted'].includes(o.status) ? `<button class="btn p f" onclick="retryOrder({id:'${o.id}',title:${JSON.stringify(o.title).replace(/"/g, '&quot;')}})">Try again</button>` : ''}
      <button class="btn f" onclick="closeLayer()">Close</button></div></div>`, { focus: '.btn:last-child' });
  refreshChat(layer, id);
  // Enquanto o pedido corre, a folha atualiza-se (de 2,5 em 2,5 s, só com ela à vista).
  if (active) {
    let busy = false;
    const timer = setInterval(async () => {
      if (busy || S.layers[S.layers.length - 1] !== layer) return;
      busy = true;
      try {
        const n = await api('/api/remote/job/' + id);
        const box = $('.obody', layer.el);
        if (box) box.innerHTML = orderBody(n);
        await refreshChat(layer, id);
        if (n.status !== 'running' && n.status !== 'queued') clearInterval(timer);
      } catch (e) { /* tenta outra vez */ }
      busy = false;
    }, 2500);
    layer.onclose = () => clearInterval(timer);
  }
}
// -- a conversa com o assistente: o que diz e faz (Claude ou outro), e escrever-lhe enquanto trabalha
function chatHtml(c) {
  const out = [];
  let tools = [];
  const flush = () => {
    if (tools.length) out.push(`<div class="ct">› ${tools.length > 1 ? tools.length + ' steps · ' : ''}${esc(tools[tools.length - 1])}</div>`);
    tools = [];
  };
  const at = m => esc((m.t || '').slice(11, 16));
  for (const m of c.messages) {
    if (m.kind === 'claude-tool') { tools.push(m.text); continue; }
    flush();
    if (m.kind === 'claude-user') out.push(`<div class="cm u"><span>${esc(m.text)}</span><i>You · ${at(m)}</i></div>`);
    // O resumo final é a última mensagem dele (e o que a folha já mostra em cima): só o início de cada sessão.
    else if (m.kind === 'claude') { if (!m.final) out.push(`<div class="cn">${esc(m.text)}</div>`); }
    else out.push(`<div class="cm a"><span>${esc(m.text)}</span><i>${esc(c.who)} · ${at(m)}</i></div>`);
  }
  flush();
  return out.join('');
}
async function refreshChat(layer, id) {
  let c;
  try { c = await api('/api/remote/chat/' + id); } catch (e) { return; }
  const box = $('.ochat', layer.el);
  if (!box) return;
  box.hidden = !c.messages.length && !c.live;
  layer.el.classList.toggle('haschat', !box.hidden);
  $('.who', box).textContent = c.who;
  $('.cst', box).textContent = c.live ? ' is working on it · X to write to it' : c.messages.length ? ' · finished' : '';
  const log = $('.clog', box);
  const html = chatHtml(c);
  if (html !== log.dataset.html) {
    const atEnd = !log.dataset.html || log.scrollTop + log.clientHeight >= log.scrollHeight - 40;
    log.dataset.html = html;
    log.innerHTML = html;
    if (atEnd) log.scrollTop = log.scrollHeight;
  }
  const btn = $('.osay', layer.el);
  btn.textContent = 'Write to ' + c.who;
  btn.style.display = c.live ? '' : 'none';
  layer.actions = Object.assign({}, c.live ? { x: ['Write to ' + c.who, () => chatWrite(id)] } : {},
    c.messages.length ? { y: ['Older', () => chatScroll(layer)] } : {});
  if (S.layers[S.layers.length - 1] === layer) hints();
}
// Y: a conversa sobe uma página; no princípio, volta ao fim.
function chatScroll(layer) {
  const log = $('.clog', layer.el);
  if (!log) return;
  log.scrollTop = log.scrollTop <= 0 ? log.scrollHeight : log.scrollTop - log.clientHeight * 0.8;
}
function chatWrite(id) {
  const layer = S.layers[S.layers.length - 1];
  openTextInput('', async t => {
    if (!t) return;
    try {
      await api('/api/remote/chat/' + id, { body: { text: t } });
      toast('Sent: it reads it in what it is doing now');
      if (layer) refreshChat(layer, id);
    } catch (e) { toast(e.message, true); }
  });
}
function cancelOrder(o) {
  openLayer(`<div class="sheet confirm"><h3>Cancel the request for ${esc(o.title)}?</h3>
    <p>What was already downloaded stays on ${side()}: requesting it again resumes from there.</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">No</button>
      <button class="btn d f" onclick="doCancel('${o.id}')">Cancel request</button></div></div>`);
}
async function doCancel(id) {
  try { await api('/api/remote/order/' + id + '/cancel', { body: {} }); toast('Request cancelled'); } catch (e) { toast(e.message, true); }
  closeAll();
  refreshHome();
}
async function retryOrder(o) {
  try { const j = await api('/api/remote/order/' + o.id + '/retry', { body: {} }); S.seen[j.id] = j.status; toast('Requested again: ' + o.title); } catch (e) { toast(e.message, true); }
  closeAll();
  refreshHome();
}

// -- Definições: o modo (PC, Sem PC, Automático) ---------------------------------------------------
// The choice lives on the Deck (the mode file the launcher and the Decky plugin read), so it goes
// through whoever serves this page: the PC writes it over SSH, the Deck service itself. "go" is
// where to reopen now so that it applies at once (null: from the next time the Manager opens).
const MODES = [
  ['pc', 'PC', 'Your PC downloads, builds and tests the games and sends them to this Deck. The PC must be on.'],
  ['local', 'Without PC', 'This Deck downloads, builds and installs the games by itself, with no PC.'],
  ['auto', 'Automatic', 'The PC when it answers, this Deck when it does not.'],
];
// Whether the Sem PC mode is on this Deck (its service answers; /api/ping allows any origin).
async function deckReady() {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), 2500);
  try {
    const r = await fetch(LOCAL + '/api/ping', { cache: 'no-store', signal: c.signal });
    return (await r.json()).app === 'gestor-rexnative';
  } catch (e) { return false; } finally { clearTimeout(t); }
}
async function loadMode() {
  const [m, ready] = await Promise.all([api('/api/remote/mode').catch(e => ({ error: e.message })), deckReady()]);
  S.modes = { mode: m.mode, serving: m.serving, error: m.error || null, ready };
  if (S.tab !== 'settings' || S.layers.length) return;
  const id = S.cur && S.cur.dataset.id;
  renderSettings();
  const el = id && $$('.f', $('#v-settings')).find(e => e.dataset.id === id && !e.disabled);
  if (el) focus(el, false); else restoreFocus();
}
function renderSettings() {
  const v = $('#v-settings');
  const m = S.modes;
  const head = '<div class="vhead"><div><h2>Settings</h2><div class="sub">Where the Manager does its work</div></div></div>';
  if (!m) { v.innerHTML = head + '<div class="empty"><div class="spin" style="margin:0 auto 14px"></div>Reading the mode…</div>'; return; }
  const rows = MODES.map(([k, name, text]) => {
    const off = k !== 'pc' && !m.ready;
    const on = m.mode === k;
    return `<button class="mopt f${on ? ' on' : ''}" data-id="mode-${k}" data-hint="${on ? 'In use' : 'Use this'}" onclick="setMode('${k}')"${off ? ' disabled' : ''}>
      <span class="box"></span><span class="mt"><b>${esc(name)}</b>${on ? '<span class="bd g">In use</span>' : ''}
        <span class="d">${esc(text)}</span>${off ? '<span class="d w">Install the Sem PC mode on this Deck first</span>' : ''}</span></button>`;
  }).join('');
  const pc = (S.home || {}).pc;
  const now = m.serving === 'local' ? 'Now the Manager runs on this Deck (Sem PC mode).'
    : m.serving === 'pc' ? `Now the Manager runs on the PC${pc ? ' ' + pc : ''}.` : '';
  v.innerHTML = `${head}<div class="setsec"><h4>Mode</h4><div class="opts">${rows}</div>
    ${m.error ? `<div class="note">Could not read the mode: ${esc(m.error)}</div>` : ''}
    ${now ? `<div class="note">${esc(now)}</div>` : ''}</div>${accountsSection(m)}`;
  // The first time, the focus starts on the mode in use.
  const cur = $(`.mopt.on:not([disabled])`, v);
  if (!S.lastFocus.settings && cur) S.lastFocus.settings = cur.dataset.id;
}
async function setMode(k) {
  const m = S.modes || {};
  const name = (MODES.find(x => x[0] === k) || [k, k])[1];
  if (S.modeBusy) return;
  if (k === m.mode && k === m.serving) { toast(name + ' is already in use'); return; }
  S.modeBusy = true;
  try {
    const r = await api('/api/remote/mode', { body: { mode: k } });
    S.modes = Object.assign({}, m, { mode: r.mode || k, serving: r.serving || m.serving, error: null });
    if (r.relaunch) {
      // The launcher (gestor.sh) closes this window and opens the Manager again on the other side,
      // in its Settings: a page moved from one Manager to the other froze the Deck's Firefox at
      // times. A launcher that did not do it in 15 s: the page moves itself, as before.
      S.leaving = true;
      toast(r.relaunch === 'local' ? 'Opening the Manager on this Deck…' : 'Opening the Manager on the PC…');
      if (r.go) setTimeout(() => location.replace(r.go + (r.go.includes('#') ? '&' : '#') + 'tab=settings'), 15000);
      return;
    }
    if (r.go) {
      toast(r.go.startsWith(LOCAL) ? 'Opening the Manager on this Deck…' : 'Opening the Manager on the PC…');
      // The Settings tab again, there: the new mode shows as the one in use.
      location.replace(r.go + (r.go.includes('#') ? '&' : '#') + 'tab=settings');
      return;
    }
    toast(k === 'pc' && S.modes.serving === 'local' ? 'PC: the PC does not answer now; it is used from the next time the Manager opens'
      : name + ': it applies from the next time the Manager opens');
    S.lastFocus.settings = 'mode-' + k;
    if (S.tab === 'settings' && !S.layers.length) { renderSettings(); restoreFocus(); }
  } catch (e) { toast(e.message, true); }
  finally { if (!S.leaving) S.modeBusy = false; }
}

// -- Settings > Accounts: archive.org, Claude, GitHub on this Deck -------------------------------
// One row each: its state and one button (Sign in, Sign out, Install). Claude and GitHub sign in by
// their own flows on the Deck's service (logins.py): the link as a QR code for the phone, GitHub's code
// to type there, Claude's code typed back here. The secrets go to the service and the tools only.
const ACCOUNTS = [
  ['archive', 'archive.org', 'Downloads the catalogue\'s games'],
  ['claude', 'Claude', 'Reports and the fixes of a game that fails'],
  ['github', 'GitHub', 'Pushes Claude\'s fixes, the shared recipes, the app\'s updates'],
];
async function loadAccounts() {
  if (!isLocal()) return;
  try { S.accounts = await api('/api/remote/accounts', { timeout: 40000 }); S.accountsError = null; }
  catch (e) { S.accountsError = e.message; }
  if (S.tab !== 'settings' || S.layers.length) return;
  const id = S.cur && S.cur.dataset.id;
  renderSettings();
  const el = id && $$('.f', $('#v-settings')).find(e => e.dataset.id === id && !e.disabled);
  if (el) focus(el, false); else restoreFocus();
  // An install going on: look again in a moment.
  clearTimeout(S.accountsTimer);
  if (S.accounts && ACCOUNTS.some(([k]) => (S.accounts[k] || {}).installing)) S.accountsTimer = setTimeout(loadAccounts, 4000);
}
function accountsSection(m) {
  if (!isLocal()) {
    return `<div class="setsec"><h4>Accounts</h4><div class="note">The sign-ins of this Deck (archive.org, Claude, GitHub) are in the Sem PC mode's Settings.</div>
      ${m.ready ? `<div class="opts"><button class="btn f" data-id="acct-open" onclick="location.href='${LOCAL}/deck#tab=settings'">Open them on this Deck</button></div>` : ''}</div>`;
  }
  const a = S.accounts;
  if (!a) return `<div class="setsec"><h4>Accounts</h4><div class="note">${S.accountsError ? 'Could not read the accounts: ' + esc(S.accountsError) : 'Reading the accounts\u2026'}</div></div>`;
  const rows = ACCOUNTS.map(([k, name, what]) => {
    const x = a[k] || {};
    const state = !x.installed ? '<span class="bd w">Not installed</span>' : x.signed_in ? '<span class="bd g">Signed in</span>' : '<span class="bd">Not signed in</span>';
    const who = x.signed_in ? [x.user ? 'as ' + x.user : '', x.how || '', k === 'archive' && x.own === false ? 'the system\'s ia.ini' : ''].filter(Boolean).join(' \u00b7 ') : '';
    let btn;
    if (x.installing) btn = '<button class="btn f" disabled>Installing\u2026</button>';
    else if (!x.installed) btn = `<button class="btn p f" data-id="acct-${k}" onclick="accountInstall('${k}')">Install</button>`;
    else if (!x.signed_in) btn = `<button class="btn p f" data-id="acct-${k}" onclick="accountSignIn('${k}')">Sign in</button>`;
    else if (k === 'archive' && x.own === false) btn = `<button class="btn f" data-id="acct-${k}" onclick="accountSignIn('${k}')">Use another account</button>`;
    else btn = `<button class="btn f" data-id="acct-${k}" onclick="accountSignOut('${k}')">Sign out</button>`;
    return `<div class="acct"><span class="mt"><b>${esc(name)}</b>${state}<span class="d">${esc(who || what)}</span></span>${btn}</div>`;
  }).join('');
  return `<div class="setsec"><h4>Accounts</h4><div class="opts">${rows}</div></div>`;
}
async function accountInstall(k) {
  try { await api(`/api/remote/accounts/${k}/install`, { body: {} }); toast('Installing ' + (k === 'claude' ? 'Claude Code' : 'the GitHub CLI') + ' on this Deck'); }
  catch (e) { toast(e.message, true); }
  loadAccounts();
}
function accountSignOut(k) {
  const name = (ACCOUNTS.find(x => x[0] === k) || [k, k])[1];
  openLayer(`<div class="sheet confirm"><h3>Sign out of ${esc(name)}?</h3>
    <p>${esc(k === 'archive' ? 'Downloads from the catalogue stop until you sign in again.' : k === 'claude' ? 'Reports and the automatic fixes stop until you sign in again.' : 'Claude\'s fixes stay on this Deck, not pushed, until you sign in again.')}</p>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" onclick="accountSignOutNow('${k}')">Sign out</button></div></div>`, { focus: '.btn:not(.p)' });
}
async function accountSignOutNow(k) {
  closeLayer();
  try { S.accounts = await api(`/api/remote/accounts/${k}/sign-out`, { body: {}, timeout: 40000 }); toast('Signed out'); }
  catch (e) { toast(e.message, true); }
  loadAccounts();
}
function accountSignIn(k) {
  if (k === 'archive') return archiveSignIn();
  return flowSignIn(k);
}
// archive.org: the e-mail and the password (or, for an account that signs in with Google, its S3 keys
// from archive.org/account/s3.php), typed with the page's keyboard. The password is never kept.
function archiveSignIn() {
  const f = { keys: false, email: '', password: '', access: '', secret: '' };
  const field = (id, label, secret) => `<button class="field2 f" data-fid="${id}" onclick="archiveField('${id}')"><span class="l">${label}</span><span class="v">${secret ? '\u2022'.repeat(f[id].length) || '\u2014' : esc(f[id]) || '\u2014'}</span></button>`;
  const fields = () => f.keys ? field('access', 'S3 access key') + field('secret', 'S3 secret key', true)
    : field('email', 'E-mail') + field('password', 'Password', true);
  const swap = () => f.keys ? 'Use the e-mail and password' : 'An account with Google? Use its S3 keys';
  const layer = openLayer(`<div class="sheet confirm" style="width:760px"><h3>Sign in to archive.org</h3>
    <p>The games of the catalogue are lent to signed-in accounts. The password goes to archive.org only and is never kept on the Deck.</p>
    <div class="fields opts">${fields()}</div>
    <div class="acts"><button class="btn f swap" onclick="archiveSwap()">${swap()}</button><button class="btn f" onclick="closeLayer()">Cancel</button>
      <button class="btn p f" onclick="archiveSubmit()">Sign in</button></div></div>`, { focus: '.field2' });
  layer.form = f;
  layer.draw = () => { $('.fields', layer.el).innerHTML = fields(); $('.swap', layer.el).textContent = swap(); };
}
function archiveLayer() { return S.layers.find(l => l.form); }
function archiveSwap() { const l = archiveLayer(); l.form.keys = !l.form.keys; l.draw(); focus($('.field2', l.el)); }
function archiveField(id) {
  const l = archiveLayer();
  const titles = { email: 'archive.org e-mail', password: 'archive.org password', access: 'S3 access key', secret: 'S3 secret key' };
  openKeyboard(l.form[id], { full: true, secret: id === 'password' || id === 'secret', title: titles[id], done: t => {
    l.form[id] = t; l.draw();
    const el = $$('.field2', l.el).find(e => e.dataset.fid === id);
    if (el) focus(el);
  } });
}
async function archiveSubmit() {
  const l = archiveLayer();
  const f = l.form;
  const body = f.keys ? { access: f.access, secret: f.secret } : { email: f.email, password: f.password };
  if (!Object.values(body).every(Boolean)) { toast('Fill in both fields first', true); return; }
  try {
    S.accounts = await api('/api/remote/accounts/archive/sign-in', { body, timeout: 40000 });
    f.password = f.secret = '';
    closeLayer();
    toast('Signed in to archive.org' + ((S.accounts.archive || {}).user ? ' as ' + S.accounts.archive.user : ''));
  } catch (e) { toast(e.message, true); }
  loadAccounts();
}
// Claude and GitHub: the tool's own sign-in on the Deck, followed here until it ends.
async function flowSignIn(k) {
  let v;
  try { v = await api(`/api/remote/accounts/${k}/sign-in`, { body: {}, timeout: 40000 }); }
  catch (e) { toast(e.message, true); return; }
  const gh = k === 'github';
  const layer = openLayer(`<div class="sheet confirm signin" style="width:860px"><h3>Sign in to ${gh ? 'GitHub' : 'Claude'}</h3>
    <div class="qrrow"><div class="qr"><div class="spin"></div></div><div class="qrtext">
      ${gh ? '<p>On your phone, scan the code (or open <b>github.com/login/device</b>), sign in, and type this code there:</p><div class="bigcode">\u2026</div>'
        : '<p>On your phone, scan the code and sign in with your Claude account (Google works too). The page then shows a code: type it here.</p>'}
      <div class="flowstate note"></div></div></div>
    <div class="acts"><button class="btn f" onclick="closeLayer()">Cancel</button>
      ${gh ? '' : '<button class="btn p f" onclick="flowCode()">Type the code</button>'}</div></div>`, { focus: gh ? '.btn' : '.btn.p' });
  layer.flow = k;
  let shownUrl = null;
  const show = f => {
    if (!f) return;
    if (f.url && f.url !== shownUrl && !f.done) {
      shownUrl = f.url;
      $('.qr', layer.el).innerHTML = `<img alt="QR code" src="/api/remote/accounts/${k}/qr?n=${Date.now()}">`;
    }
    if (gh && f.code) $('.bigcode', layer.el).textContent = f.code;
    $('.flowstate', layer.el).textContent = f.error ? 'It did not sign in: ' + f.error : f.done && f.ok ? 'Signed in.' : 'Waiting for the sign-in\u2026';
  };
  show(v);
  const tick = async () => {
    if (!S.layers.includes(layer)) return;
    try {
      const a = await api(`/api/remote/accounts/${k}/flow`, { timeout: 40000 });
      show(a.flow);
      if (a.flow && a.flow.done && a.flow.ok) {
        layer.finished = true;
        closeLayer();
        toast('Signed in to ' + (gh ? 'GitHub' : 'Claude') + (a.user ? ' as ' + a.user : ''));
        return;
      }
    } catch (e) { /* the next look */ }
    layer.timer = setTimeout(tick, 2000);
  };
  layer.timer = setTimeout(tick, 1500);
  layer.onclose = () => {
    clearTimeout(layer.timer);
    if (!layer.finished) api(`/api/remote/accounts/${k}/cancel`, { body: {} }).catch(() => {});
    loadAccounts();
  };
}
function flowCode() {
  const l = S.layers.find(x => x.flow === 'claude');
  if (!l) return;
  openKeyboard('', { full: true, title: 'The code from Claude\'s page', done: async t => {
    if (!t) return;
    try { await api('/api/remote/accounts/claude/code', { body: { code: t }, timeout: 40000 }); $('.flowstate', l.el).textContent = 'Checking the code\u2026'; }
    catch (e) { toast(e.message, true); }
  } });
}

// -- sair ---------------------------------------------------------------------------------------
function openExit() {
  if (S.layers.length) return;
  const p = (S.home || {}).pending || {};
  const titles = p.titles || [];
  openLayer(`<div class="sheet confirm"><h3>Exit the Manager?</h3>
    ${p.add || p.remove ? `<p>${titles.length ? 'Joining the library now: <b style="color:var(--text)">' + titles.map(esc).join(', ') + '</b>. ' : ''}Steam on the Deck closes and reopens for a few seconds to do this.</p>` : `<p>Requests keep running on ${side()}${isLocal() ? ' in the background' : ''}: whatever finishes meanwhile shows up next time.</p>`}
    <div class="acts"><button class="btn f" onclick="closeLayer()">Stay</button>
      <button class="btn f" onclick="closeLayer();openWhatsNew()">What's new (v${esc((S.ver || {}).running || '?')})</button>
      <button class="btn p f" onclick="doExit()">Exit</button></div></div>`, { focus: '.btn.p' });
}
async function doExit() {
  try { await api('/api/remote/closed', { body: {} }); } catch (e) { /* o lançador avisa outra vez */ }
  window.close();
  setTimeout(() => { closeAll(); toast('You can close this window'); }, 400);
}

// -- emparelhar -------------------------------------------------------------------------------
function showPair() {
  $('#top').classList.add('hide');
  for (const v of $$('.view')) v.classList.add('hide');
  const v = $('#v-pair');
  v.classList.remove('hide');
  let code = '';
  const draw = () => { $$('.code div', v).forEach((d, i) => { d.textContent = code[i] || ''; d.classList.toggle('cur', i === code.length); }); };
  v.innerHTML = `<div class="center"><h1><b>ReXNative</b> Manager</h1>
    <p>This device is not paired with the PC app yet. On the PC: <b style="color:var(--text)">Settings → Deck mode → Pair another device</b>, then enter the 6-digit code here.</p>
    <div class="code">${'<div></div>'.repeat(6)}</div>
    <div class="pad">${'123456789'.split('').map(n => `<button class="key f" data-n="${n}">${n}</button>`).join('')}<button class="key f" data-n="del">⌫</button><button class="key f" data-n="0">0</button><button class="key ok f" data-n="ok">OK</button></div></div>`;
  S.tab = 'pair';
  const send = async () => {
    try { await api('/api/pair/claim', { body: { code, name: navigator.userAgent.includes('Linux') ? 'Steam Deck' : 'Device' } }); location.reload(); }
    catch (e) { toast(e.message, true); code = ''; draw(); }
  };
  for (const b of $$('.key', v)) b.onclick = () => {
    const n = b.dataset.n;
    if (n === 'del') code = code.slice(0, -1); else if (n === 'ok') { if (code.length === 6) send(); } else if (code.length < 6) code += n;
    draw();
    if (code.length === 6 && n !== 'ok' && n !== 'del') send();
  };
  draw();
  S.layers = [];
  focus($('.key', v));
  $('#hints').innerHTML = '<span><span class="k a">A</span>Type</span>';
}

// -- entrada: comando, teclado ---------------------------------------------------------------
document.addEventListener('keydown', e => {
  pad.key = Date.now();
  const l = S.layers[S.layers.length - 1];
  if (l && l.type && l.full && e.key.length === 1) { l.type(e.key); e.preventDefault(); return; }
  if (l && l.type && e.key.length === 1 && /[\w ]/.test(e.key)) { l.type(e.key.toLowerCase()); e.preventDefault(); return; }
  if (l && l.del && e.key === 'Backspace') { l.del(); e.preventDefault(); return; }
  const map = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
  if (map[e.key]) {
    e.preventDefault();
    // The same press seen twice (Steam Input can send the D-pad as the pad and as arrow keys): one move.
    const i = { up: 12, down: 13, left: 14, right: 15 }[map[e.key]];
    if (pad.moved && pad.moved.i === i && pad.moved.src === 'pad' && Date.now() - pad.moved.at < 60) return;
    pad.moved = { i, at: Date.now(), src: 'key' };
    move(map[e.key]);
    return;
  }
  if (e.key === 'Enter' || e.key === ' ') { activate(); e.preventDefault(); return; }
  if (e.key === 'Escape' || e.key === 'Backspace') { back(); e.preventDefault(); return; }
  if (e.key === 'q' || e.key === 'PageUp') { nextTab(-1); return; }
  if (e.key === 'e' || e.key === 'PageDown') { nextTab(1); return; }
  if (e.key === '[' || e.key === 'Home') { jumpGrid(-1); e.preventDefault(); return; }
  if (e.key === ']' || e.key === 'End') { jumpGrid(1); e.preventDefault(); return; }
  if (e.key === 'x') { const a = actions().x; if (a) a[1](); return; }
  if (e.key === 'y') { const a = actions().y; if (a) a[1](); return; }
  if (e.key === 'm' || e.key === 'F10') { const a = actions().menu; if (a) a(); else openExit(); }
});
document.addEventListener('pointerover', e => {
  const el = e.target.closest('.f');
  if (el && e.pointerType === 'mouse' && scope().contains(el)) focus(el, false);
});

const pad = { prev: [], held: {}, ids: {}, last: 0, key: 0 };
addEventListener('gamepadconnected', e => { pad.ids[e.gamepad.id] = e.gamepad.mapping || 'no mapping'; });
function press(b) {
  switch (b) {
    case 0: activate(); break;
    case 1: back(); break;
    case 2: { const a = actions().x; if (a) a[1](); break; }
    case 3: { const a = actions().y; if (a) a[1](); break; }
    case 4: nextTab(-1); break;
    case 5: nextTab(1); break;
    case 6: jumpGrid(-1); break;
    case 7: jumpGrid(1); break;
    case 9: { const a = actions().menu; if (a) a(); else openExit(); break; }
    case 12: case 13: case 14: case 15: {
      if (pad.moved && pad.moved.i === b && pad.moved.src === 'key' && Date.now() - pad.moved.at < 60) break;
      pad.moved = { i: b, at: Date.now(), src: 'pad' };
      move(['up', 'down', 'left', 'right'][b - 12]);
      break;
    }
  }
}
function padLoop(t) {
  // Todos os comandos juntos (no Deck o do Steam é o "X-Box 360 pad" virtual; outro pode aparecer
  // primeiro na lista); com o mapeamento "standard" os botões são os do comando da Xbox.
  const gps = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  const b = [];
  for (const g of gps) {
    pad.ids[g.id] = g.mapping || 'no mapping';
    g.buttons.forEach((x, i) => { if (x.pressed) b[i] = true; });
    // O analógico esquerdo como a cruz, só pelo eixo mais forte: um "para baixo" um pouco torto
    // passava também os 0,6 do lado e andava para baixo e para o lado ao mesmo tempo. O eixo que já
    // manda continua a mandar até descer dos 0,4 (sem saltar de um para o outro a meio).
    const ax = g.axes[0] || 0, ay = g.axes[1] || 0;
    const held = pad.dir;
    const keepV = (held === 12 || held === 13) && Math.abs(ay) > 0.4;
    const keepH = (held === 14 || held === 15) && Math.abs(ax) > 0.4;
    if (keepV || (!keepH && Math.abs(ay) >= Math.abs(ax) && Math.abs(ay) > 0.6)) b[ay < 0 ? 12 : 13] = true;
    else if (keepH || Math.abs(ax) > 0.6) b[ax < 0 ? 14 : 15] = true;
    if (g.mapping !== 'standard' && g.axes.length >= 8) {
      if (g.axes[7] < -0.5) b[12] = true; if (g.axes[7] > 0.5) b[13] = true;
      if (g.axes[6] < -0.5) b[14] = true; if (g.axes[6] > 0.5) b[15] = true;
    }
  }
  // Uma direção de cada vez: a que já está carregada manda enquanto não a largas (o polegar que
  // rola para a diagonal não leva o foco para o lado); numa diagonal carregada de uma vez, ganha
  // a vertical. Largada a primeira, a outra que ainda está carregada anda como um toque novo.
  let dir = pad.dir && b[pad.dir] ? pad.dir : [13, 12, 15, 14].find(i => b[i]);
  for (const i of [12, 13, 14, 15]) if (i !== dir) b[i] = false;
  if (dir !== pad.dir) pad.prev[dir] = false;
  pad.dir = dir;
  for (let i = 0; i < 16; i++) {
    if (b[i] && !pad.prev[i]) { press(i); pad.held[i] = t + 380; pad.last = Date.now(); }
    else if (b[i] && i >= 12 && i <= 15 && t > pad.held[i]) { press(i); pad.held[i] = t + 130; }  // held: 7 or 8 a second, easy to stop on a game
    else if (b[i] && (i === 6 || i === 7) && t > pad.held[i]) { press(i); pad.held[i] = t + 260; }  // held: letter after letter
  }
  pad.prev = b;
  requestAnimationFrame(padLoop);
}

// -- arranque ---------------------------------------------------------------------------------
async function boot() {
  for (const b of $$('#tabs .tab')) b.onclick = () => switchTab(b.dataset.tab);
  applyMode();
  const P = new URLSearchParams(location.hash.slice(1));
  if (P.get('t')) {
    try { await api('/api/pair/session', { body: { token: P.get('t') } }); } catch (e) { /* mostra emparelhar */ }
  }
  if (P.get('tab')) S.openTab = P.get('tab');  // depois de mudar de modo: as Definições outra vez
  if (P.get('t') || P.get('tab')) history.replaceState(null, '', location.pathname);
  let st;
  try { st = await api('/api/pair/state'); } catch (e) { setTimeout(boot, 3000); return; }
  // Sem PC não há nada a emparelhar (o serviço do Deck só aceita este Deck).
  if (!st.paired && !isLocal()) { showPair(); requestAnimationFrame(padLoop); return; }
  $('#top').classList.remove('hide');
  $('#v-boot').classList.add('hide');
  await refreshHome();
  loadCatalog();
  setTimeout(() => loadVersion(), 1200);
  setTimeout(() => loadLog(), 5000);  // quantas mudanças novas no ReXNative (no separador)
  setInterval(() => { if (S.tab !== 'log') loadLog(); }, 600000);
  setInterval(() => loadVersion(), 600000);
  switchTab(tabs().includes(S.openTab) ? S.openTab : firstTab());
  requestAnimationFrame(padLoop);
  // Atualiza depressa com pedidos a decorrer, devagar sem eles; e diz ao PC que o Gestor está aberto.
  const tick = async () => {
    await refreshHome();
    if (S.tab === 'pc' && Date.now() - (S.pcAt || 0) > 20000) loadPc();
    const busy = ((S.home || {}).orders || []).some(o => o.status === 'running' || o.status === 'queued');
    setTimeout(tick, busy || S.tab === 'orders' ? 2500 : 12000);
  };
  setTimeout(tick, 2500);
  // O sinal de vida leva o que a página vê do comando (para se perceber à distância se o comando
  // chega ao Firefox).
  let beating = false;
  setInterval(() => {
    if (beating || S.tab === 'pair' || S.leaving) return;  // um sinal ainda sem resposta: não se juntam mais
    beating = true;
    api('/api/remote/heartbeat', { body: { pads: pad.ids, pad_last: pad.last, key_last: pad.key, ua: navigator.userAgent } })
      .catch(() => {}).finally(() => { beating = false; });
  }, 30000);  // o sinal de vida já vai com cada /home (2,5 a 12 s): este só leva o que se vê do comando
  setInterval(() => { if (S.tab === 'catalog' && !S.layers.length) loadCatalog(); }, 60000);
  // Ler o Deck (tamanhos, atalhos) logo no início, sem pressa.
  setTimeout(() => refreshHome(true).then(() => {}), 600);
}
boot();
