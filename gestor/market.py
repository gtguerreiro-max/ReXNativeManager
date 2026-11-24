"""A ficha de um jogo como a da loja: o catálogo do Marketplace da Xbox 360 (catalog.xboxlive.com,
o da Microsoft, sem chave), junto com a Wikidata (info.py) e o resumo da Wikipédia.

- Índice: todos os jogos da Xbox 360 (MediaTypes 1) e do Xbox Live Arcade (23), nome e title id,
  em páginas de 100 (uns 4100 jogos, 42 pedidos): <data>/market/index.json, lido de novo ao fim
  de 30 dias. É ele que dá o title id a um jogo do catálogo (que só tem o nome do ficheiro).
- Detalhes de um jogo (DetailView 5): a descrição, quem o fez e publicou, a data, a nota e o
  número de avaliações dos jogadores, as categorias da loja, os modos de jogo (jogadores, co-op,
  system link, online), e as imagens (fundo, banner, caixa, capturas): <data>/market/<TID>.json.
- Imagens: de download.xbox.com, só na primeira vez que uma ficha as mostra, para
  <data>/market/img/<TID>/<nome>; a página do PC e a do Deck pedem-nas ao PC.
- card(): a ficha inteira, a da loja e a da Wikidata juntas (os géneros das duas, sem repetir)."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import catalog, config, fsutil, info

UA = 'ReXNativeManager/1.0 (game library tool)'
QUERY = 'http://catalog.xboxlive.com/Catalog/Catalog.asmx/Query'
MEDIA_ID = '66acd000-77fe-1000-9115-d802%s'
IMG_HOST = 'download.xbox.com'
WIKI_SUMMARY = 'https://en.wikipedia.org/api/rest_v1/page/summary/%s'
MAX_AGE = 30 * 24 * 3600
TID = re.compile(r'^[0-9A-Fa-f]{8}$')
IMG_NAME = re.compile(r'^[a-z0-9_-]{1,40}\.(jpg|jpeg|png)$')
# Categorias da loja que não são géneros.
NOT_GENRES = {'game genres', 'xbox live games', 'xbox live arcade', 'games on demand', 'xbox 360 games',
              'indie games', 'avatar', 'kinect', 'demos', 'trials'}
NOT_GENRE = re.compile(r'^game publisher bit|^xbox|^games on demand', re.I)
# Como a loja e a Wikidata dizem o mesmo género de maneiras diferentes (para não o mostrar duas vezes).
SAME = {'role-playing': 'role playing', 'rpg': 'role playing', 'role playing game': 'role playing',
        'racing': 'racing flying', 'racing and flying': 'racing flying', 'shooter': 'shooter',
        'puzzle': 'puzzle trivia', 'puzzle and trivia': 'puzzle trivia', 'platform': 'platformer',
        'fighting': 'fighting', 'sports': 'sports recreation', 'sports and recreation': 'sports recreation',
        'music': 'music', 'strategy': 'strategy simulation', 'strategy and simulation': 'strategy simulation',
        'action': 'action adventure', 'adventure': 'action adventure', 'action adventure': 'action adventure',
        'action and adventure': 'action adventure', 'card and board': 'card board', 'family': 'family'}
# Os modos de jogo que a loja guarda (gameCapabilities), como se leem.
CAPS = [('offlinePlayersMax', 'Players', '{}'), ('offlineCoopPlayersMax', 'Co-op (same console)', 'up to {}'),
        ('offlineSystemLinkMax', 'System link', 'up to {}'), ('onlineMultiplayerMax', 'Online players', 'up to {}'),
        ('onlineCoopPlayersMax', 'Online co-op', 'up to {}')]
FEATURES = [('offlineMaxHDTVModeId', {1: '480p', 2: '720p', 3: '1080i', 4: '1080p'}, 'HDTV'),
            ('offlineDolbyDigital', None, 'Dolby Digital'), ('onlineContentDownload', None, 'Downloadable content'),
            ('onlineLeaderboards', None, 'Online leaderboards'), ('onlineVoice', None, 'Voice chat'),
            ('onlineTournaments', None, 'Tournaments'), ('offlineCustomSoundtrack', None, 'Custom soundtracks')]

_lock = threading.Lock()
_mem = {'index': None, 'keys': None, 'building': False, 'error': None}


def _dir(*parts):
    return config.data_dir('market', *parts)


def _get(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def _query(params):
    base = [('methodName', 'FindGames')]
    fixed = [('Locale', 'en-US'), ('LegalLocale', 'en-US'), ('Store', '1'), ('OfferFilterLevel', '1'),
             ('UserTypes', '2')]
    q = base + [x for k, v in fixed + params for x in (('Names', k), ('Values', v))]
    return _decode(_get(QUERY + '?' + urllib.parse.urlencode(q)))


def _decode(raw):
    """UTF-8, with the odd Windows-1252 byte some descriptions carry (the Fable II one's
    apostrophe, 0x92) read as Windows-1252."""
    text = raw.decode('utf-8', 'surrogateescape')
    return re.sub('[\udc80-\udcff]', lambda m: bytes([ord(m.group()) - 0xdc00]).decode('cp1252', 'replace'), text)


def _tag(text, name):
    m = re.search(r'<live:%s>(.*?)</live:%s>' % (name, name), text, re.S)
    return _unescape(m.group(1).strip()) if m else None


def _unescape(s):
    return (s.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
            .replace('&#39;', "'").replace('&amp;', '&'))


# -- índice ---------------------------------------------------------------------------------------
def _index_path():
    return _dir('index.json')


def _load_index():
    try:
        return json.load(open(_index_path(), encoding='utf-8'))
    except (OSError, ValueError):
        return None


def build_index(log=print):
    """Todos os jogos da loja: [[nome, TID, tipo]] (tipo 1 Xbox 360, 23 Arcade)."""
    games = []
    for mt in ('1', '23'):
        page = 1
        while True:
            text = _query([('PageSize', '100'), ('PageNum', str(page)), ('DetailView', '1'), ('MediaTypes', mt)])
            total = int((re.search(r'<live:totalItems>(\d+)', text) or [0, 0])[1])
            for entry in re.findall(r'<entry.*?</entry>', text, re.S):
                title = re.search(r'<title>(.*?)</title>', entry, re.S)
                mid = re.search(r'gameTitleMediaId>urn:uuid:[0-9A-Fa-f-]+?([0-9A-Fa-f]{8})<', entry)
                if title and mid:
                    games.append([_unescape(title.group(1)).strip(), mid.group(1).upper(), int(mt)])
            if page * 100 >= total or not total:
                break
            page += 1
    data = {'at': time.time(), 'games': games}
    fsutil.write_json(_index_path(), data)
    log('Marketplace: %d games' % len(games))
    return data


def _ensure_index(wait=False):
    """O índice (em memória); se faltar ou estiver velho, faz-se outra vez numa thread (ou já,
    com wait)."""
    with _lock:
        if _mem['index'] is not None and time.time() - _mem['index'].get('at', 0) < MAX_AGE:
            return _mem['index']
    d = _load_index()
    if d and time.time() - d.get('at', 0) < MAX_AGE:
        with _lock:
            _mem.update(index=d, keys=None)
        return d

    def run():
        try:
            nd = build_index(log=lambda *_: None)
            with _lock:
                _mem.update(index=nd, keys=None, error=None)
        except Exception as e:  # noqa: BLE001 - sem rede: fica o índice velho, se houver
            with _lock:
                _mem['error'] = str(e)
        finally:
            with _lock:
                _mem['building'] = False

    with _lock:
        start = not _mem['building']
        if start:
            _mem['building'] = True
    if wait:
        if start:
            run()
        return _mem['index'] or d
    if start:
        threading.Thread(target=run, daemon=True, name='market-index').start()
    if d:
        with _lock:
            _mem.update(index=d, keys=None)
    return d


def _keys():
    d = _ensure_index()
    if not d:
        return None
    with _lock:
        if _mem['keys'] is not None:
            return _mem['keys']
    exact, tokens = {}, []
    for name, tid, mt in d['games']:
        k = catalog.words(re.sub(r'[™®©]', '', name))
        if not k:
            continue
        exact.setdefault((k, mt), tid)
        exact.setdefault((k, 0), tid)
        tokens.append((set(k.split()), tid, mt))
    keys = {'exact': exact, 'tokens': tokens}
    with _lock:
        _mem['keys'] = keys
    return keys


DIGITS = re.compile(r'^(\d+|i{1,3}|iv|v|vi{0,3}|ix|x)$')
EDITION = re.compile(r'\b(goty|game of the year|complete|ultimate|platinum|classics|edition|collection|'
                     r'directors cut|remastered|hd|xbla|arcade|xbox|360)\b')


_tids = {}


def find_tid(title, xbla=None):
    """O title id de um jogo da loja pelo nome (o do catálogo), ou None (ou enquanto o índice se faz).
    Lembrado por índice (o catálogo pergunta por 2000 nomes de cada vez)."""
    keys = _keys()
    if not keys:
        return None
    memo = (id(keys), title, xbla)
    if memo not in _tids:
        if len(_tids) > 20000:
            _tids.clear()
        _tids[memo] = _find_tid(keys, title, xbla)
    return _tids[memo]


def _find_tid(keys, title, xbla):
    k = catalog.words(title)
    if not k:
        return None
    mt = 23 if xbla else 1 if xbla is not None else 0
    for kk in (k, EDITION.sub(' ', k)):
        kk = ' '.join(kk.split())
        tid = keys['exact'].get((kk, mt)) or keys['exact'].get((kk, 0))
        if tid:
            return tid
    # "Brothers: A Tale of Two Sons" is "Brothers" in the store: the name before the subtitle,
    # of the same kind (Arcade or disc) when the catalogue says which.
    main = re.split(r'\s*(?::|\s-\s)\s*', title, 1)[0]
    if main != title and mt:
        tid = keys['exact'].get((catalog.words(main), mt))
        if tid:
            return tid
    want = set(EDITION.sub(' ', k).split())
    if len(want) < 2:
        return None
    best = None
    for toks, tid, t in keys['tokens']:
        if mt and t != mt:
            continue
        # The store's name with more words ("007 Blood Stone" -> "James Bond 007: Blood Stone"), or
        # with one word less that is not a number ("Sega Rally Revo" -> "SEGA Rally"; not
        # "Saints Row 2" -> "Saints Row").
        extra = toks - want
        fewer = want - toks
        if (want <= toks and len(extra) <= 3 and not any(DIGITS.match(x) for x in extra)) or (
                toks <= want and len(toks) >= 2 and len(fewer) == 1 and not any(DIGITS.match(x) for x in fewer)):
            if best is None or abs(len(toks) - len(want)) < best[0]:
                best = (abs(len(toks) - len(want)), tid)
    return best[1] if best else None


# -- detalhes de um jogo ----------------------------------------------------------------------------
def _parse(tid, text):
    entry = (re.search(r'<entry.*?</entry>', text, re.S) or [None])[0]
    if not entry:
        return None
    out = {'tid': tid, 'title': _tag(entry, 'fullTitle') or _unescape((re.search(r'<title>(.*?)</title>', entry, re.S)
                                                                         or ['', ''])[1]).strip()}
    desc = _tag(entry, 'reducedDescription') or _tag(entry, 'description') or ''
    desc = re.sub(r'^\s*\(Online Interactions Not Rated by the ESRB\)\s*', '', desc)
    desc = re.sub(r'^This game supports [^.]*\.\s*', '', desc)
    desc = re.sub(r'\s*There are no refunds for this item\..*$', '', desc, flags=re.S)
    out['description'] = desc.strip()
    out['developer'] = _tag(entry, 'developer')
    out['publisher'] = _tag(entry, 'publisher')
    rd = _tag(entry, 'releaseDate') or ''
    out['released'] = rd[:10] if rd[:4].isdigit() and not rd.startswith('1900') else None
    try:
        out['rating'] = round(float(_tag(entry, 'ratingAggregate')), 2)
        out['ratings'] = int(_tag(entry, 'numberOfRatings') or 0)
    except (TypeError, ValueError):
        out['rating'], out['ratings'] = None, 0
    cats = re.findall(r'<live:category>.*?<live:name>(.*?)</live:name>.*?</live:category>', entry, re.S)
    out['categories'] = [_unescape(c) for c in cats
                         if _unescape(c).lower() not in NOT_GENRES and not NOT_GENRE.search(_unescape(c))]
    caps = {}
    m = re.search(r'<live:gameCapabilities>(.*?)</live:gameCapabilities>', entry, re.S)
    for k, v in re.findall(r'<live:(\w+)>(\d+)</live:\1>', m.group(1) if m else ''):
        caps[k] = int(v)
    out['modes'] = [[label, fmt.format(caps[k])] for k, label, fmt in CAPS if caps.get(k, 0) > 0]
    feats = []
    for k, names, label in FEATURES:
        v = caps.get(k)
        if v:
            feats.append('%s %s' % (label, names[v]) if names and v in names else label)
    out['features'] = feats
    imgs = {}
    for u in re.findall(r'<live:fileUrl>(.*?)</live:fileUrl>', entry):
        u = _unescape(u)
        p = urllib.parse.urlparse(u)
        if p.hostname != IMG_HOST:
            continue
        name = os.path.basename(p.path).lower()
        if IMG_NAME.match(name):
            imgs.setdefault(name, u)
    out['images'] = imgs
    shots = sorted((n for n in imgs if re.match(r'screenlg\d+\.', n)), key=lambda n: int(re.findall(r'\d+', n)[0]))
    out['screens'] = shots
    return out


def details(tid, refresh=False):
    """Os detalhes da loja de um jogo (guardados 30 dias), ou None se a loja não o tem."""
    tid = (tid or '').upper()
    if not TID.match(tid):
        return None
    p = _dir('%s.json' % tid)
    if not refresh and os.path.exists(p) and time.time() - os.path.getmtime(p) < MAX_AGE:
        try:
            return json.load(open(p, encoding='utf-8')) or None
        except ValueError:
            pass
    try:
        text = _query([('PageSize', '1'), ('PageNum', '1'), ('DetailView', '5'), ('MediaIds', MEDIA_ID % tid.lower()),
                       ('MediaTypes', '1'), ('MediaTypes', '21'), ('MediaTypes', '23'), ('MediaTypes', '37')])
    except (urllib.error.URLError, OSError):
        try:
            return json.load(open(p, encoding='utf-8')) or None  # sem rede: o que havia
        except (OSError, ValueError):
            return None
    d = _parse(tid, text)
    fsutil.write_json(p, d or {})
    return d


def image(tid, name):
    """O caminho de uma imagem da ficha (descarregada na primeira vez), ou None."""
    tid, name = (tid or '').upper(), (name or '').lower()
    if not TID.match(tid) or not IMG_NAME.match(name):
        return None
    p = _dir('img', tid, name)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return p
    d = details(tid)
    u = (d or {}).get('images', {}).get(name)
    if not u or urllib.parse.urlparse(u).hostname != IMG_HOST:
        return None
    try:
        data = _get(u, timeout=40, tries=2)
    except (urllib.error.URLError, OSError):
        return None
    if not data[:4] in (b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\xff\xd8\xff\xdb', b'\x89PNG') and data[:3] != b'\xff\xd8\xff':
        return None
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(p + '.tmp', p)
    return p


def _wiki_summary(article):
    """O resumo do artigo da Wikipédia inglesa (para um jogo que a loja não tem), guardado 30 dias."""
    if not article:
        return None
    name = article.rsplit('/', 1)[-1]
    p = _dir('wiki', re.sub(r'[^A-Za-z0-9_.-]', '_', name)[:120] + '.json')
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < MAX_AGE:
        try:
            return json.load(open(p, encoding='utf-8')).get('extract')
        except ValueError:
            pass
    try:
        d = json.loads(_get(WIKI_SUMMARY % urllib.parse.quote(urllib.parse.unquote(name)), tries=2))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    fsutil.write_json(p, {'extract': d.get('extract')})
    return d.get('extract')


def _gkey(g):
    k = catalog.words(g).replace(' video game', '').replace(' game', '')
    return SAME.get(k, k)


def card(title, tid=None, xbla=None):
    """A ficha de um jogo: a da loja (se a tem) e a da Wikidata juntas.
    {title, tid, description, description_from, developer(s), publisher(s), released, year,
     genres, mc, rating, ratings, modes, features, images: {background, boxart, banner}, screens,
     wiki, store: bool, pending: bool (o índice da loja ainda se está a fazer)}"""
    w = info.find(title) or {}
    if not tid:
        tid = find_tid(title, xbla)
    m = details(tid) if tid else None
    genres, seen = [], set()
    for g in (m or {}).get('categories', []) + list(w.get('genres') or []):
        k = _gkey(g)
        if g and k not in seen:
            seen.add(k)
            genres.append(g)
    desc, src = (m or {}).get('description'), 'store'
    if not desc:
        desc, src = _wiki_summary(w.get('wiki')), 'wikipedia'
    imgs = (m or {}).get('images', {})
    pick = lambda *names: next((n for n in names if n in imgs), None)  # noqa: E731
    st = (m or {}).get('title')
    if st and st.isupper():  # "FABLE II": the Wikidata name, or the catalogue's
        st = None
    out = {'title': w.get('name') or st or title, 'tid': tid,
           'description': desc or None, 'description_from': src if desc else None,
           'developers': [x for x in [(m or {}).get('developer')] if x] or w.get('devs') or [],
           'publishers': [x for x in [(m or {}).get('publisher')] if x] or w.get('pubs') or [],
           'released': (m or {}).get('released'), 'year': w.get('year') or (
               int(m['released'][:4]) if m and m.get('released') else None),
           'genres': genres[:8], 'mc': w.get('mc'), 'rating': (m or {}).get('rating'),
           'ratings': (m or {}).get('ratings') or 0, 'modes': (m or {}).get('modes') or [],
           'features': (m or {}).get('features') or [], 'wiki': w.get('wiki'),
           'images': {'background': pick('background.jpg'), 'boxart': pick('boxartlg.jpg', 'boxartsm.jpg'),
                      'banner': pick('banner.png', 'banner.jpg')},
           'screens': (m or {}).get('screens') or [], 'store': bool(m),
           'pending': bool(not tid and _mem['building'])}
    return out


def status():
    d = _mem['index'] or _load_index()
    return {'games': len((d or {}).get('games', [])), 'at': (d or {}).get('at'), 'building': _mem['building'],
            'error': _mem['error']}


def cached(tid):
    """Os detalhes já guardados de um jogo (sem ir à rede), ou None."""
    tid = (tid or '').upper()
    if not TID.match(tid):
        return None
    try:
        return json.load(open(_dir('%s.json' % tid), encoding='utf-8')) or None
    except (OSError, ValueError):
        return None


def genres(title, xbla=None, wikidata=None):
    """Os géneros de um jogo para as listas: os da loja (se os detalhes já cá estão) e os da
    Wikidata, sem repetir. Não vai à rede."""
    tid = find_tid(title, xbla)
    m = cached(tid) if tid else None
    out, seen = [], set()
    for g in (m or {}).get('categories', []) + list(wikidata or []):
        k = _gkey(g)
        if g and k not in seen:
            seen.add(k)
            out.append(g)
    return out


_prefetch = {'started': False, 'total': 0, 'done': 0, 'finished_at': None}


def prefetch(games):
    """Vai buscando os detalhes da loja dos jogos do catálogo em segundo plano (um pedido por
    segundo, uma vez por mês: os que já cá estão não pedem nada), para as listas terem os géneros
    da loja. games: [(nome, xbla)]."""
    if _prefetch['started'] and (not _prefetch['finished_at'] or time.time() - _prefetch['finished_at'] < 6 * 3600):
        return _prefetch
    _prefetch.update(started=True, total=len(games), done=0, finished_at=None)

    def run():
        try:
            _ensure_index(wait=True)
            for title, xbla in games:
                try:
                    tid = find_tid(title, xbla)
                    p = _dir('%s.json' % tid) if tid else None
                    if p and not (os.path.exists(p) and time.time() - os.path.getmtime(p) < MAX_AGE):
                        details(tid)
                        time.sleep(1)
                except Exception:  # noqa: BLE001 - um jogo que falha não pára os outros
                    pass
                _prefetch['done'] += 1
        finally:
            _prefetch['finished_at'] = time.time()
    threading.Thread(target=run, daemon=True, name='market-prefetch').start()
    return _prefetch


def game_genres(tid, wikidata=None):
    """Os géneros de um jogo preparado (o title id é o do executável): os da loja, se os detalhes já
    cá estão, e os da Wikidata. Não vai à rede."""
    m = cached(tid)
    out, seen = [], set()
    for g in (m or {}).get('categories', []) + list(wikidata or []):
        k = _gkey(g)
        if g and k not in seen:
            seen.add(k)
            out.append(g)
    return out


_tid_fetch = {'busy': False}


def prefetch_tids(tids):
    """Os detalhes da loja dos jogos preparados que ainda não os têm, em segundo plano."""
    todo = [t.upper() for t in tids if t and TID.match(t) and not os.path.exists(_dir('%s.json' % t.upper()))]
    if not todo or _tid_fetch['busy']:
        return
    _tid_fetch['busy'] = True

    def run():
        try:
            for t in todo:
                try:
                    details(t)
                except Exception:  # noqa: BLE001 - um jogo que falha não pára os outros
                    pass
                time.sleep(0.5)
        finally:
            _tid_fetch['busy'] = False
    threading.Thread(target=run, daemon=True, name='market-tids').start()
