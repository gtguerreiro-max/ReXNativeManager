"""O registo do ReXNative: o separador Changelog da app do PC e do Modo Deck.

- Os commits do main (freshness.commits: os últimos 400, com a descrição), sem os merges.
- Cada um com a sua área (o renderizador, o upscaler e a geração de frames, o SDK, o Deck, a
  ferramenta, a depuração, a documentação: pelo assunto e pelos ficheiros) e se entra no jogo
  compilado (freshness.relevant).
- Os jogos de que fala: os da biblioteca deste PC e os da lista do ReXNative (docs/GAMES.md), pelo
  nome no assunto e na descrição ("Halo", "Overlord II": "Overlord" sozinho não é o II).
- De cada jogo da biblioteca, a versão compilada no PC e a do Deck (o commit ou a data): a página
  vê se cada mudança já lá está.
- Os ramos do GitHub com trabalho ainda fora do main (ex.: vulkan-experiment), à parte."""
import re
import threading
import time

from . import catalog, changelog, freshness, games, state

AREAS = {
    'renderer': 'Renderer',
    'upscaling': 'Upscaling & frame generation',
    'sdk': 'SDK',
    'deck': 'Steam Deck',
    'tool': 'Porting tool',
    'debug': 'Debugging',
    'docs': 'Docs',
    'other': 'Other',
}
ORDER = ['upscaling', 'renderer', 'sdk', 'tool', 'deck', 'debug', 'other']
UPSCALE_FILES = ('dlss', 'fsr', 'fidelityfx', 'frame_gen', 'motion', 'neural', 'dynamic_resolution',
                 'upscal', 'optical')
SUBJECT_AREAS = [
    (re.compile(r'^(docs|readme|leia-me|games|notes|roadmap)\b', re.I), 'docs'),
    (re.compile(r'upscal|frame generation|motion vector|\bdlss|\bfsr|camera cut|optical flow|hud-less', re.I), 'upscaling'),
    (re.compile(r'^(sdk\b|move to rexglue)', re.I), 'sdk'),
    (re.compile(r'^(deck|steam deck)\b', re.I), 'deck'),
    (re.compile(r'^(live|live\.ps1|rdoc|scripts|f12|debugging)\b', re.I), 'debug'),
]
# Nomes curtos (antes de ':' ou ' - ') que são palavras comuns: só o nome inteiro conta.
COMMON = {'Dust'}
SEQUEL = r'(?!\s+(?:[2-9]|1[0-9]|I{1,3}|IV|VI{0,3}|IX)\b)'
_lock = threading.Lock()
_names = {'key': None, 'ents': [], 'pats': []}
_mentions = {'key': None, 'map': {}}
_branches = {'at': 0.0, 'data': []}
_repo = {'url': None}


def file_area(f):
    fl = f.lower()
    if fl.endswith('.md') or fl.startswith('docs/') or fl.startswith('.github/') or fl in (
            'license', 'third_party_notices.md'):
        return 'docs'
    if fl.startswith('renderer/'):
        base = fl.rsplit('/', 1)[-1]
        return 'upscaling' if any(k in base for k in UPSCALE_FILES) else 'renderer'
    if fl.startswith('sdk/'):
        return 'sdk'
    if fl.startswith('deck/') or fl == 'rexnative/deck.py':
        return 'deck'
    if fl.startswith('rexnative/'):
        return 'tool'
    if fl.startswith('scripts/'):
        return 'debug'
    return 'other'


def area(subject, files):
    """A área de um commit: o assunto manda quando diz (docs:, Upscaler:, SDK...), senão a parte
    do código com mais ficheiros mudados."""
    for rx, a in SUBJECT_AREAS:
        if rx.search(subject):
            return a
    counts = {}
    for f in files:
        a = file_area(f)
        counts[a] = counts.get(a, 0) + 1
    code = [a for a in ORDER if counts.get(a)]
    if code:
        return max(code, key=lambda a: (counts[a], -ORDER.index(a)))
    return 'docs' if counts.get('docs') else 'other'


# -- os jogos ------------------------------------------------------------------------------------
def _aliases(title):
    """'Deus Ex: Human Revolution - Director's Cut (TU 1)' -> ['Deus Ex: Human Revolution -
    Director's Cut', 'Deus Ex: Human Revolution', 'Deus Ex']: o nome inteiro primeiro."""
    t = re.sub(r'\s*\([^)]*\)', '', title).strip()
    out = [t]
    for sep in (' - ', ': '):
        if sep in t:
            h = t.split(sep, 1)[0].strip()
            if len(h) >= 3 and h not in out and h not in COMMON:
                out.append(h)
    return out


def _pattern(alias):
    forms = {alias}
    if alias.isupper() and len(alias) > 4:
        forms.add(alias.title())  # LIMBO -> Limbo
    alt = '|'.join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    tail = '' if re.search(r'\b(\d+|[IVX]+)$', alias) else SEQUEL
    return re.compile(r'(?<![\w.])(?:%s)(?!\w)%s' % (alt, tail))


def _games_md():
    """Os nomes da tabela de docs/GAMES.md do ReXNative (a primeira coluna)."""
    try:
        txt = freshness._git('show', 'origin/main:docs/GAMES.md')
    except Exception:  # noqa: BLE001 - sem git: só a biblioteca
        return []
    out = []
    for line in txt.splitlines():
        if not line.startswith('| ') or line.startswith('| Game |'):
            continue
        cell = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', line.split('|')[1]).strip()
        if cell and not set(cell) <= set('-: '):
            out.append(cell)
    return out


def _entities(lib, head):
    """Os jogos a procurar: os da biblioteca (com slug) e os do GAMES.md que não são deles. Um nome
    curto que serve a dois jogos do mesmo lado não conta; entre a biblioteca e o GAMES.md, conta o
    da biblioteca."""
    key = (head, tuple(sorted((g['slug'], g['title']) for g in lib)))
    if _names['key'] == key:
        return _names['ents'], _names['pats']
    ents = []
    for g in lib:
        al = _aliases(g['title'])
        ents.append({'t': re.sub(r'\s*\([^)]*\)', '', g['title']).strip(), 'n': al[-1], 's': g['slug'],
                     'al': al, 'tier': 0})
    lib_al = {a for e in ents for a in e['al']}
    lib_keys = [catalog.words(e['t']) for e in ents]
    for name in _games_md():
        al = _aliases(name)
        if catalog.words(al[0]) in lib_keys or any(a in lib_al for a in al):
            continue
        # 'Geometry Wars: Retro Evolved' do GAMES.md é o 'Geometry Wars Evolved' da biblioteca: o
        # nome curto começa o de um só jogo de cá, que fica com os nomes deste.
        head = catalog.words(al[-1])
        cand = [i for i, k in enumerate(lib_keys) if head and (k == head or k.startswith(head + ' '))]
        if len(cand) == 1 and len(al) > 1:
            ents[cand[0]]['al'] += [a for a in al if a not in ents[cand[0]]['al']]
            continue
        ents.append({'t': al[0], 'n': al[-1], 's': None, 'al': al, 'tier': 1})
    owners = {}
    for i, e in enumerate(ents):
        for a in e['al']:
            owners.setdefault((a, e['tier']), []).append(i)
    pats = []
    for i, e in enumerate(ents):
        for j, a in enumerate(e['al']):
            if j and len(owners[(a, e['tier'])]) > 1:
                continue  # 'Halo' de dois jogos: ambíguo
            pats.append((_pattern(a), i))
    for e in ents:
        e.pop('al')
    _names.update(key=key, ents=ents, pats=pats)
    return ents, pats


def _find(text, pats):
    """Os jogos nomeados em text, pela ordem em que aparecem; um nome dentro de outro mais comprido
    ('Dust' em 'From Dust') não conta."""
    hits = []
    for rx, i in pats:
        for m in rx.finditer(text):
            hits.append((m.start(), m.end(), i))
    hits.sort(key=lambda h: (-(h[1] - h[0]), h[0]))
    taken, out = [], {}
    for s, e, i in hits:
        if any(s < te and ts < e for ts, te in taken):
            continue
        taken.append((s, e))
        out.setdefault(i, s)
    return [i for i, _ in sorted(out.items(), key=lambda kv: kv[1])]


def _mentions_of(cs, pats, key):
    if _mentions['key'] == key:
        return _mentions['map']
    m = {}
    for c in cs:
        subj = _find(c['subject'], pats)
        body = [i for i in _find(c.get('body') or '', pats) if i not in subj]
        m[c['sha']] = [[i, 1] for i in subj] + [[i, 0] for i in body[:8]]
    _mentions.update(key=key, map=m)
    return m


# -- o resto ------------------------------------------------------------------------------------
def repo_url():
    """O endereço do ReXNative no GitHub (para abrir cada commit), se o remoto é do GitHub."""
    if _repo['url'] is None:
        try:
            u = freshness._git('remote', 'get-url', 'origin', timeout=10).strip()
        except Exception:  # noqa: BLE001
            u = ''
        m = re.match(r'(?:https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?/?$', u)
        _repo['url'] = 'https://github.com/' + m.group(1) if m else ''
    return _repo['url'] or None


def branches(max_age=300):
    """Os ramos do GitHub com commits fora do main, mexidos nos últimos 45 dias: {name, at,
    commits} (os commits como no main, até 80)."""
    if time.time() - _branches['at'] < max_age:
        return _branches['data']
    out = []
    try:
        refs = freshness._git('for-each-ref', 'refs/remotes/origin',
                              '--format=%(refname:short)%09%(committerdate:unix)')
        for line in refs.splitlines():
            if '\t' not in line:
                continue
            name, at = line.split('\t', 1)
            b = name.split('/', 1)[1] if '/' in name else ''
            if not b or b in ('HEAD', 'main', 'master') or time.time() - int(at or 0) > 45 * 86400:
                continue
            cs = [c for c in freshness.log('origin/main..' + name, 80) if not _merge(c)]
            if cs:
                out.append({'name': b, 'at': int(at), 'commits': cs})
    except Exception:  # noqa: BLE001 - sem git: sem ramos
        out = _branches['data']
    out.sort(key=lambda b: -b['at'])
    _branches.update(at=time.time(), data=out)
    return out


def _merge(c):
    return c['subject'].startswith(('Merge branch', 'Merge pull request', "Merge remote-tracking"))


def _vmark(v):
    if not v:
        return None
    return {'commit': v.get('commit'), 'time': v.get('time'), 'exact': bool(v.get('exact')),
            'built_at': v.get('built_at'), 'dirty': bool(v.get('dirty'))}


def _pack(c, mentions):
    files = c.get('files') or []
    return {'sha': c['sha'], 'at': c['at'], 'subject': c['subject'], 'body': c.get('body') or '',
            'area': area(c['subject'], files), 'build': bool(c.get('build')), 'files': len(files),
            'paths': files[:10], 'games': mentions.get(c['sha'], [])}


def view(refresh=False):
    """Tudo o que o separador mostra (o PC e o Modo Deck pedem o mesmo)."""
    if refresh:
        try:
            freshness._refresh()
        except Exception:  # noqa: BLE001 - sem rede: a lista que há
            pass
        _branches['at'] = 0.0
    cs = [c for c in freshness.commits() if not _merge(c)]
    last = state.get('deck', 'last') or {}
    on_deck = {g['slug']: g for g in last.get('games', [])}
    lib = [g for g in games.scan() if not g.get('error')]
    head = cs[0]['sha'] if cs else None
    brs = branches()
    with _lock:
        ents, pats = _entities(lib, head)
        allc = cs + [c for b in brs for c in b['commits']]
        # A hora da leitura entra na chave: a lista guardada no disco (de antes das descrições)
        # dá lugar à lida do git com o mesmo commit à cabeça.
        mkey = (_names['key'], freshness._cache.get('at'), tuple(c['sha'] for c in allc[:1]), len(allc),
                tuple(b['commits'][0]['sha'] for b in brs))
        mentions = _mentions_of(allc, pats, mkey)
    mine = []
    for g in lib:
        dg = on_deck.get(g['slug'])
        pc = changelog.version_of(g['work'], g['built_at']) if g.get('built_at') else None
        dv = changelog.deck_version(g['slug'], dg.get('mtime')) if dg else None
        mine.append({'slug': g['slug'], 'title': g['title'], 'built': bool(g.get('built')),
                     'on_deck': bool(dg), 'pc': _vmark(pc), 'deck': _vmark(dv)})
    mine.sort(key=lambda g: catalog.words(g['title']))
    return {
        'repo': repo_url(), 'checked_at': freshness._cache.get('at') or None, 'head': head,
        'areas': AREAS, 'names': ents, 'mine': mine,
        'commits': [_pack(c, mentions) for c in cs],
        'branches': [{'name': b['name'], 'at': b['at'], 'commits': [_pack(c, mentions) for c in b['commits']]}
                     for b in brs],
    }
