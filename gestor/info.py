"""Informação dos jogos para as listas: género, ano, quem o fez e publicou, e a nota do Metacritic.

- Wikidata (dados livres, CC0, sem chave): todos os jogos com plataforma Xbox 360 (Q48263) de uma
  vez, em perguntas pequenas ao query.wikidata.org: nomes (inglês, português), data, géneros (o
  nome em inglês, curto), quem os fez e publicou, notas do Metacritic (P444 com "nota de"
  Metacritic) e o artigo da Wikipédia inglesa.
- Wikipédia inglesa: a Wikidata só tem a nota do Metacritic de poucos jogos; os artigos têm-na na
  tabela de críticas ({{Video game reviews | MC = X360: 87/100 ...}}). Lidos 50 artigos por pedido.
Tudo guardado em <data_dir>/info/xbox360.json e lido de novo ao fim de 14 dias (ou a pedido)."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import catalog, config, fsutil

UA = 'ReXNativeManager/1.0 (game library tool)'
SPARQL = 'https://query.wikidata.org/sparql'
WIKI_API = 'https://en.wikipedia.org/w/api.php'
MAX_AGE = 14 * 24 * 3600
X360 = 'Q48263'

QUERIES = {
    'base': 'SELECT ?game ?en ?pt (MIN(?date) AS ?d) WHERE { ?game wdt:P400 wd:%s . '
            'OPTIONAL { ?game rdfs:label ?en FILTER(LANG(?en)="en") } '
            'OPTIONAL { ?game rdfs:label ?pt FILTER(LANG(?pt)="pt") } '
            'OPTIONAL { ?game wdt:P577 ?date } } GROUP BY ?game ?en ?pt' % X360,
    'genre': 'SELECT ?game ?l WHERE { ?game wdt:P400 wd:%s ; wdt:P136 ?x . SERVICE wikibase:label '
             '{ bd:serviceParam wikibase:language "en". ?x rdfs:label ?l. } }' % X360,
    'dev': 'SELECT ?game ?l WHERE { ?game wdt:P400 wd:%s ; wdt:P178 ?x . ?x rdfs:label ?l '
           'FILTER(LANG(?l)="en") }' % X360,
    'pub': 'SELECT ?game ?l WHERE { ?game wdt:P400 wd:%s ; wdt:P123 ?x . ?x rdfs:label ?l '
           'FILTER(LANG(?l)="en") }' % X360,
    'score': 'SELECT ?game ?score ?plat WHERE { ?game wdt:P400 wd:%s ; p:P444 ?st . ?st ps:P444 '
             '?score ; pq:P447 wd:Q150248 . OPTIONAL { ?st pq:P400 ?plat } }' % X360,
    'wiki': 'SELECT ?game ?article WHERE { ?game wdt:P400 wd:%s . ?article schema:about ?game ; '
            'schema:isPartOf <https://en.wikipedia.org/> }' % X360,
}

_lock = threading.Lock()
_mem = {'data': None, 'index': None}
_refreshing = threading.Event()


def _path():
    return os.path.join(config.data_dir('info'), 'xbox360.json')


def _post(url, fields, timeout=120):
    data = urllib.parse.urlencode(fields).encode()
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers={
            'User-Agent': UA, 'Accept': 'application/json, application/sparql-results+json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'), strict=False)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                time.sleep(int(e.headers.get('Retry-After') or 20) + 1)
                continue
            raise


def _sparql(q):
    return _post(SPARQL, {'query': q, 'format': 'json'})['results']['bindings']


def _v(row, k):
    return (row.get(k) or {}).get('value')


def _qid(row):
    return _v(row, 'game').rsplit('/', 1)[-1]


GENRE_PREFIX = re.compile(r'^video game (genre )?', re.I)


NOT_GENRE = re.compile(r'LGBT|characters|set in|based on|franchise', re.I)


def short_genre(g):
    """'action game' -> 'Action'; 'racing video game' -> 'Racing'; temas -> ''."""
    if NOT_GENRE.search(g):
        return ''
    g = GENRE_PREFIX.sub('', g).strip()
    g = re.sub(r'\s+(video )?games?$', '', g, flags=re.I).strip()
    return g[:1].upper() + g[1:] if g else g


MC_PARAM = re.compile(r'\|\s*MC\s*=\s*(.*?)(?=\n\s*\||\n?\s*\}\})', re.S)
SCORE = re.compile(r'(\d{1,3})\s*/\s*100')


MC_X360 = re.compile(r'\|\s*MC_X360\s*=\s*(\d{1,3})\s*/\s*100')


def mc_from_wikitext(text):
    """A nota do Metacritic para Xbox 360 na tabela de críticas do artigo, ou None: o campo da
    plataforma (| MC_X360 = 76/100, o formato atual) ou o geral (| MC = X360: 87/100 ...)."""
    m = MC_X360.search(text or '')
    if m:
        return int(m.group(1))
    for m in MC_PARAM.finditer(text or ''):
        val = re.sub(r'<ref[^>]*?/>|<ref.*?</ref>', '', m.group(1), flags=re.S)
        x = re.search(r'(?:X360|Xbox\s*360|\b360\b)\W{0,12}?(?:[^0-9<|]{0,12})(\d{1,3})\s*/\s*100', val, re.I)
        if x:
            return int(x.group(1))
        scores = SCORE.findall(val)
        if len(scores) == 1:  # uma só plataforma
            return int(scores[0])
        # Várias plataformas sem dizer qual é qual: nenhuma (não se adivinha).
    return None


def refresh(log=print):
    """Lê tudo outra vez (uns 2 minutos) e grava a cache."""
    rows = {}
    for k, q in QUERIES.items():
        rows[k] = _sparql(q)
        log('Wikidata %s: %d rows' % (k, len(rows[k])))
        time.sleep(2)  # o serviço limita pedidos seguidos
    games = {}
    for r in rows['base']:
        g = games.setdefault(_qid(r), {'genres': [], 'devs': [], 'pubs': []})
        g['en'] = g.get('en') or _v(r, 'en')
        g['pt'] = g.get('pt') or _v(r, 'pt')
        d = _v(r, 'd')
        if d and d[:4].isdigit():
            g['year'] = min(int(d[:4]), g.get('year') or 9999)
    for k, field in (('genre', 'genres'), ('dev', 'devs'), ('pub', 'pubs')):
        for r in rows[k]:
            g = games.get(_qid(r))
            lab = _v(r, 'l')
            if g is not None and lab and not re.match(r'^Q\d+$', lab):
                lab = short_genre(lab) if k == 'genre' else lab
                if lab and lab not in g[field]:
                    g[field].append(lab)
    for r in rows['score']:
        g = games.get(_qid(r))
        m = SCORE.search(_v(r, 'score') or '') or re.match(r'^(\d{1,3})$', _v(r, 'score') or '')
        if g is None or not m:
            continue
        plat = (_v(r, 'plat') or '').rsplit('/', 1)[-1]
        if plat == X360 or (not plat and 'mc' not in g):
            g['mc'] = int(m.group(1))
            g['mc_from'] = 'wikidata'
    for r in rows['wiki']:
        g = games.get(_qid(r))
        if g is not None:
            g['wiki'] = urllib.parse.unquote(_v(r, 'article').rsplit('/wiki/', 1)[-1]).replace('_', ' ')
    # As notas que faltam, da Wikipédia (50 artigos por pedido).
    todo = [(q, g['wiki']) for q, g in games.items() if g.get('wiki') and 'mc' not in g]
    by_title = {t: q for q, t in todo}
    found = 0
    for i in range(0, len(todo), 50):
        titles = [t for _, t in todo[i:i + 50]]
        try:
            data = _post(WIKI_API, {'action': 'query', 'prop': 'revisions', 'rvprop': 'content',
                                    'rvslots': 'main', 'format': 'json', 'formatversion': '2',
                                    'redirects': '1', 'titles': '|'.join(titles)})
        except (OSError, ValueError) as e:
            log('Wikipedia: %s' % e)
            continue
        q = data.get('query', {})
        back = {n['to']: n['from'] for n in q.get('redirects', [])}
        back.update({n['to']: n['from'] for n in q.get('normalized', [])})
        for p in q.get('pages', []):
            revs = p.get('revisions') or []
            if not revs:
                continue
            text = revs[0].get('slots', {}).get('main', {}).get('content', '')
            title = p.get('title')
            qid = by_title.get(title) or by_title.get(back.get(title, '')) or \
                by_title.get(back.get(back.get(title, ''), ''))
            mc = mc_from_wikitext(text)
            if qid and mc is not None:
                games[qid]['mc'] = mc
                games[qid]['mc_from'] = 'wikipedia'
                found += 1
        time.sleep(1)
    log('Wikipedia: %d Metacritic scores from %d articles' % (found, len(todo)))
    data = {'fetched': time.time(), 'games': games}
    fsutil.write_json(_path(), data)
    with _lock:
        _mem['data'], _mem['index'] = data, None
        _found.clear()
    log('%d games, %d with a genre, %d with a Metacritic score' % (
        len(games), sum(1 for g in games.values() if g['genres']),
        sum(1 for g in games.values() if 'mc' in g)))
    return data


def load():
    with _lock:
        if _mem['data'] is None and os.path.exists(_path()):
            try:
                _mem['data'] = json.load(open(_path(), encoding='utf-8'))
            except ValueError:
                _mem['data'] = None
        return _mem['data']


def stale():
    d = load()
    return not d or time.time() - d.get('fetched', 0) > MAX_AGE


def refresh_in_background(log=print):
    """Lê de novo num fio à parte, se ainda ninguém o estiver a fazer."""
    if _refreshing.is_set():
        return False

    def run():
        try:
            refresh(log)
        except Exception as e:  # noqa: BLE001 - sem rede: fica a cache que houver
            log('game info: %s' % e)
        finally:
            _refreshing.clear()
    _refreshing.set()
    threading.Thread(target=run, daemon=True).start()
    return True


DIGITS = re.compile(r'^(\d+|i{1,3}|iv|v|vi{0,3}|ix|x)$')


def _index():
    with _lock:
        if _mem['index'] is not None:
            return _mem['index']
    d = load()
    exact, tokens = {}, []
    for qid, g in (d or {}).get('games', {}).items():
        for name in (g.get('en'), g.get('pt'), g.get('wiki')):
            if not name:
                continue
            k = catalog.words(re.sub(r'\s*\((video )?game\)$', '', name, flags=re.I))
            if k:
                exact.setdefault(k, qid)
                tokens.append((set(k.split()), qid))
    idx = {'exact': exact, 'tokens': tokens}
    with _lock:
        _mem['index'] = idx
    return idx


_found = {}


def find(title):
    key = (title, (load() or {}).get('fetched'))
    if key not in _found:
        _found[key] = _find(title)
    return _found[key]


def _find(title):
    """O registo do jogo pelo nome (exato depois de normalizado; senão, um nome da Wikidata que
    contenha todas as palavras do do catálogo e mais só palavras que não sejam números: "007
    Blood Stone" -> "James Bond 007: Blood Stone", mas "Saints Row" não vira "Saints Row 2")."""
    d = load()
    if not d:
        return None
    idx = _index()
    k = catalog.words(title)
    if not k:
        return None
    qid = idx['exact'].get(k)
    if not qid:  # "Minecraft Xbox 360 Edition" -> "Minecraft"
        bare = ' '.join(w for w in k.split() if w not in ('xbox', '360', 'hd', 'xbla', 'arcade'))
        qid = idx['exact'].get(bare) if bare and bare != k else None
    if not qid:
        want = set(k.split())
        if len(want) >= 2:
            best = None
            for toks, q in idx['tokens']:
                if want <= toks:
                    extra = toks - want
                    if extra and len(extra) <= 3 and not any(DIGITS.match(t) for t in extra):
                        if best is None or len(toks) < best[0]:
                            best = (len(toks), q)
            qid = best[1] if best else None
    if not qid:
        return None
    g = d['games'][qid]
    return {'qid': qid, 'name': g.get('en') or g.get('pt'), 'genres': g['genres'][:4],
            'year': g.get('year'), 'devs': g['devs'][:3], 'pubs': g['pubs'][:3],
            'mc': g.get('mc'), 'wiki': g.get('wiki')}


def compact(title):
    """Só o que as listas mostram."""
    i = find(title)
    if not i:
        return None
    return {'genres': i['genres'][:2], 'year': i['year'], 'mc': i['mc']}


def status():
    d = load() or {}
    gs = d.get('games', {})
    return {'fetched': d.get('fetched'), 'games': len(gs), 'refreshing': _refreshing.is_set(),
            'with_genre': sum(1 for g in gs.values() if g.get('genres')),
            'with_mc': sum(1 for g in gs.values() if g.get('mc') is not None)}
