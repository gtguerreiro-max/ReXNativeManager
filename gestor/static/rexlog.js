'use strict';
// O registo do ReXNative (o separador Changelog): o que a app do PC e o Modo Deck partilham. Os
// dados vêm de /api/rexlog (rexlog.py): os commits do main, com a área, os jogos de que falam e as
// versões dos jogos de cá (o commit ou a data de cada compilação, no PC e no Deck).
const RL = {
  SEEN_KEY: 'gestor-rexlog-seen',
  AREA_ORDER: ['upscaling', 'renderer', 'sdk', 'tool', 'deck', 'debug', 'docs', 'other'],
  STATE: {
    deck: ['ok', 'on your Deck'],
    pc: ['ok', 'in the PC build'],
    update: ['info', 'built on the PC: update the Deck to get it'],
    rebuild: ['warn', 'not built in yet: rebuild to get it'],
  },
  h(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); },

  // A posição de cada commit no main (o mais novo é 0), pelos 7 primeiros caracteres.
  index(d) {
    if (d._idx) return d._idx;
    const m = {};
    d.commits.forEach((c, i) => { m[c.sha.slice(0, 7)] = i; });
    Object.defineProperty(d, '_idx', { value: m, enumerable: false });
    return m;
  },
  // A versão v (do PC ou do Deck) já tem o commit c (na posição i)? Pelo commit da compilação
  // quando se sabe, senão pela data.
  has(v, c, i, idx) {
    if (!v) return null;
    if (v.exact && v.commit && idx[v.commit] != null) return i >= idx[v.commit];
    return c.at <= (v.time || 0);
  },
  // O que um commit que entra no jogo compilado é para um jogo de cá.
  state(g, c, i, idx) {
    if (!g || !c.build || i == null) return null;
    const pc = RL.has(g.pc, c, i, idx), dk = RL.has(g.deck, c, i, idx);
    if (g.on_deck) return dk ? 'deck' : pc ? 'update' : 'rebuild';
    if (g.built) return pc ? 'pc' : 'rebuild';
    return null;
  },
  mineOf(d, gi) {
    const n = d.names[gi];
    return n && n.s ? (d._mine || (Object.defineProperty(d, '_mine', { value: Object.fromEntries(d.mine.map(g => [g.slug, g])), enumerable: false }), d._mine))[n.s] : null;
  },
  // Quantas mudanças faltam a cada jogo de cá: na compilação do PC e no Deck.
  pending(d) {
    const idx = RL.index(d);
    return d.mine.map(g => {
      let build = 0, deck = 0;
      d.commits.forEach((c, i) => {
        const s = RL.state(g, c, i, idx);
        if (s === 'rebuild') build++;
        if (g.on_deck && (s === 'rebuild' || s === 'update')) deck++;
      });
      return Object.assign({}, g, { missing_build: build, missing_deck: deck });
    });
  },

  // A descrição de um commit em blocos: parágrafos e pontos de lista ("- ...", com as linhas de
  // continuação), com `código` marcado.
  blocks(t) {
    const out = [];
    let cur = null;
    for (const raw of String(t || '').split('\n')) {
      const l = raw.replace(/\s+$/, '');
      if (!l.trim()) { cur = null; continue; }
      const m = l.match(/^\s*[-*•]\s+(.*)$/);
      if (m) { cur = { kind: 'li', text: m[1] }; out.push(cur); continue; }
      if (cur && (cur.kind === 'li' ? /^\s+\S/.test(l) : true)) { cur.text += ' ' + l.trim(); continue; }
      cur = { kind: 'p', text: l.trim() };
      out.push(cur);
    }
    return out.map(b => ({ kind: b.kind, html: RL.inline(b.text) }));
  },
  inline(s) {
    return RL.h(s).replace(/`([^`]+)`/g, '<code>$1</code>');
  },
  bodyHtml(t) {
    let html = '', ul = false;
    for (const b of RL.blocks(t)) {
      if (b.kind === 'li' && !ul) { html += '<ul>'; ul = true; }
      if (b.kind !== 'li' && ul) { html += '</ul>'; ul = false; }
      html += b.kind === 'li' ? `<li>${b.html}</li>` : `<p>${b.html}</p>`;
    }
    return html + (ul ? '</ul>' : '');
  },
  firstLine(t) { const b = RL.blocks(t)[0]; return b ? b.html : ''; },

  dayKey(at) { return new Date(at * 1000).toDateString(); },
  day(at) {
    const d = new Date(at * 1000), now = new Date();
    const full = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
    if (d.toDateString() === now.toDateString()) return 'Today · ' + full;
    if (d.toDateString() === new Date(now - 864e5).toDateString()) return 'Yesterday · ' + full;
    return full;
  },
  hm(at) { return new Date(at * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); },
  ago(at) {
    if (!at) return '';
    const s = Date.now() / 1000 - at;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' h ago';
    const n = Math.round(s / 86400);
    return n + (n === 1 ? ' day ago' : ' days ago');
  },

  // f: {q, area ('all', 'build' ou uma área), game (índice em names), mode ('mentions', 'notbuilt', 'notdeck')}
  filter(d, f, list) {
    const q = (f.q || '').trim().toLowerCase();
    const idx = RL.index(d);
    const g = f.game != null ? RL.mineOf(d, f.game) : null;
    const main = !list;
    return (list || d.commits).map((c, i) => ({ c, i: main ? i : null })).filter(({ c, i }) => {
      if (f.area === 'build' && !c.build) return false;
      if (f.area && f.area !== 'all' && f.area !== 'build' && c.area !== f.area) return false;
      if (f.game != null) {
        if (!f.mode || f.mode === 'mentions' || !g || !main) { if (!c.games.some(([gi]) => gi === f.game)) return false; }
        else {
          const s = RL.state(g, c, i, idx);
          if (f.mode === 'notbuilt' && s !== 'rebuild') return false;
          if (f.mode === 'notdeck' && s !== 'rebuild' && s !== 'update') return false;
        }
      }
      if (q && !(c.subject + '\n' + c.body + '\n' + c.sha).toLowerCase().includes(q)
        && !c.games.some(([gi]) => (d.names[gi].t || '').toLowerCase().includes(q))) return false;
      return true;
    });
  },
  counts(d) {
    const m = { all: d.commits.length, build: 0 };
    for (const c of d.commits) { m[c.area] = (m[c.area] || 0) + 1; if (c.build) m.build++; }
    return m;
  },
  // Os commits novos desde a última vez que se viu o separador (o sha do mais novo de então).
  seen() { try { return localStorage.getItem(RL.SEEN_KEY); } catch (e) { return null; } },
  markSeen(d) { try { if (d && d.head) localStorage.setItem(RL.SEEN_KEY, d.head); } catch (e) { /* */ } },
  newCount(d, seen) {
    if (!d || !d.commits.length) return 0;
    if (seen === undefined) seen = RL.seen();
    if (!seen) return 0;
    const i = d.commits.findIndex(c => c.sha === seen);
    return i < 0 ? Math.min(d.commits.length, 30) : i;
  },
};
