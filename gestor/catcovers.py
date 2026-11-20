"""Capas do catálogo, sem descarregar o jogo: o XboxUnity procura o título pelo nome e dá as capas
da caixa (a oficial primeiro). Guarda-se só a frente, 300x420, em <data_dir>/catalog/covers/.

O XboxUnity procura por pedaços do nome ("Asuras Wrath" não encontra "ASURA'S WRATH", "Wrath"
encontra), por isso pergunta-se pelas palavras mais compridas do título e escolhe-se o resultado
cujas palavras (catalog.words) mais se parecem com as do título. Os nomes de lá trazem abreviaturas
e notas ("GTA San Andreas (Xbox 360)", "Midnight Club: LA"): as notas entre parênteses saem e uma
sigla que seja as iniciais de palavras seguidas do título conta como essas palavras.

Sem capa no XboxUnity: a caixa do marketplace da Xbox (pelo TitleID que o XboxUnity deu) e, sem
isso, a imagem do artigo da Wikipédia do jogo (a capa, quase sempre; o nome vem da Wikidata, info.py).

Uma falha de rede não é "não há capa": só um "não encontrado" fica marcado (MISS_DAYS); as marcas
antigas, de antes de se distinguir (sem 'v'), procuram-se outra vez."""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from . import catalog, config, covers, fsutil

LIST = ('http://xboxunity.net/Resources/Lib/TitleList.php?page=0&count=40&search=%s&sort=3'
        '&direction=1&category=0&filter=0')
INFO = 'http://xboxunity.net/Resources/Lib/CoverInfo.php?titleid=%s'
COVER = 'http://xboxunity.net/Resources/Lib/Cover.php?size=large&cid=%s'
SIZE = (300, 420)
MISS_DAYS = 7
MISS_V = 2  # as marcas de "não há capa" desta versão (as anteriores contavam falhas de rede)
# pilicense=any: as capas na Wikipédia são quase sempre imagens não livres (fair use), que o
# pageimages deixa de fora sem isto.
WIKI = ('https://en.wikipedia.org/w/api.php?action=query&format=json&prop=pageimages&piprop=original'
        '&pilicense=any&redirects=1&titles=%s')

_sem = threading.Semaphore(4)  # no máximo 4 perguntas ao XboxUnity ao mesmo tempo
_key_locks = {}
_index_lock = threading.Lock()


def _dir():
    return config.data_dir('catalog', 'covers')


def _name(key):
    return hashlib.md5(key.encode('utf-8')).hexdigest()[:16]


def _index_path():
    return os.path.join(_dir(), 'index.json')


def _index():
    try:
        with open(_index_path(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _remember(key, value):
    with _index_lock:
        idx = _index()
        idx[key] = value
        fsutil.write_json(_index_path(), idx)


def _get(url, timeout=25, tries=3):
    """O conteúdo de url; tenta outra vez (o XboxUnity falha às vezes com muitos pedidos seguidos)."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=covers.UA)
            with covers.urlopen(req, timeout=timeout) as r:
                return r.read()
        except OSError:
            if i + 1 == tries:
                raise
            time.sleep(2 * (i + 1))


# A Wikimedia limita quem se apresenta como browser e quem pede muito seguido (429): os pedidos à
# Wikipédia vão um de cada vez, com um intervalo, com um nome de programa (sem dados de quem o usa).
WIKI_UA = {'User-Agent': 'ReXNativeManagerCovers/1.2 (personal game library; python-urllib)'}
_wiki_lock = threading.Lock()
_wiki_last = [0.0]
_wiki_block = [0.0]  # recusou (429): sem Wikipédia até esta hora
WIKI_GAP = 10.0  # segundos entre pedidos (o servidor das imagens recusa depois de poucos seguidos)


def _wiki_get(url, timeout=40):
    import urllib.error
    with _wiki_lock:
        if time.time() < _wiki_block[0]:
            raise OSError('Wikimedia asked to wait')  # não se sabe: não fica marcado como sem capa
        wait = WIKI_GAP - (time.time() - _wiki_last[0])
        if wait > 0:
            time.sleep(wait)
        _wiki_last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers=WIKI_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _wiki_block[0] = time.time() + 3600
            raise


def _words(name, title_words):
    """As palavras de um nome do XboxUnity, sem as notas entre parênteses e com as siglas
    desdobradas pelas palavras do título ("gta" -> "grand theft auto", "la" -> "los angeles")."""
    name = re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', name or '')
    out = []
    for w in catalog.words(name).split():
        if w not in title_words and 2 <= len(w) <= 5 and w.isalpha():
            for i in range(len(title_words) - len(w) + 1):
                run = title_words[i:i + len(w)]
                if ''.join(x[0] for x in run) == w:
                    out.extend(run)
                    break
            else:
                out.append(w)
        else:
            out.append(w)
    return out


def _score(title_words, name):
    """Quanto o nome do XboxUnity se parece com o título (0 a 1.5)."""
    a, b = set(title_words), set(_words(name, list(title_words)))
    if not a or not b:
        return 0.0
    # Outro número é outro jogo ("Pinball FX 2" não é "Pinball FX"); o 360 de "Xbox 360" não conta.
    if {w for w in a if w.isdigit() and w != '360'} != {w for w in b if w.isdigit() and w != '360'}:
        return 0.0
    jac = len(a & b) / len(a | b)
    if jac == 1:
        return 1.5
    if b <= a and len(b) * 3 >= len(a):  # "The Bureau" em "Bureau XCOM Declassified"
        return max(jac, 0.75)
    if a <= b and len(a) * 2 >= len(b):
        return max(jac, 0.7)
    return jac


def find_title(title):
    """{'tid', 'name', 'type'} do XboxUnity para um título do catálogo, ou None."""
    tw = catalog.words(title).split()
    if not tw:
        return None
    queries = sorted({w for w in tw if len(w) >= 3 and not w.isdigit()}, key=len, reverse=True)[:3]
    if not queries:
        queries = tw[:1]
    best = (0.0, None)
    failed = 0
    for qw in queries:
        try:
            data = json.loads(_get(LIST % urllib.parse.quote(qw)).decode('utf-8', 'replace'))
        except (OSError, ValueError):
            failed += 1
            continue
        for it in data.get('Items') or []:
            if it.get('TitleType') not in ('360', 'XBLA') or str(it.get('Covers') or '0') == '0':
                continue
            s = _score(tw, it.get('Name') or '')
            if s > best[0]:
                best = (s, {'tid': it['TitleID'], 'name': it['Name'], 'type': it['TitleType']})
        if best[0] >= 1.5:
            break
    if best[0] < 0.6 and failed == len(queries):
        raise OSError('XboxUnity did not answer')  # não se sabe: não fica marcado como sem capa
    return best[1] if best[0] >= 0.6 else None


def path(title):
    """O ficheiro da capa do título (procurada e guardada na primeira vez), ou None."""
    key = catalog.words(title)
    if not key:
        return None
    f = os.path.join(_dir(), _name(key) + '.jpg')
    if os.path.exists(f):
        return f
    known = _index().get(key)
    if known and known.get('miss') and known.get('v') == MISS_V and \
            time.time() - known['miss'] < MISS_DAYS * 86400:
        return None
    with _index_lock:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        if os.path.exists(f):
            return f
        with _sem:
            return _fetch(key, title, f)


def _save_front(raw, f, whole_scan=True):
    """Guarda a frente da capa em f (300x420). whole_scan: um scan da caixa inteira (o XboxUnity:
    a frente é a parte direita); senão a imagem já é a frente (marketplace, Wikipédia)."""
    tmp = f + '.part'
    with open(tmp, 'wb') as out:
        out.write(raw)
    try:
        if whole_scan:
            im = covers.front(tmp)
        else:
            from PIL import Image
            im = Image.open(tmp).convert('RGB')
        if min(im.size) < 120:
            return False  # um ícone, não uma capa
        covers.cover_crop(im, SIZE).save(f, quality=86)
        return True
    except Exception:  # noqa: BLE001 - uma imagem estragada
        return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _fallback(key, title, f, tid=None):
    """Sem capa no XboxUnity: a caixa do marketplace (pelo TitleID) ou a imagem da Wikipédia."""
    if tid:
        try:
            raw = _get(covers.MP % tid.lower() + 'boxartlg.jpg', tries=1)
            if _save_front(raw, f, whole_scan=False):
                _remember(key, {'tid': tid, 'source': 'marketplace', 'at': time.time()})
                return f
        except OSError:
            pass
    from . import info
    wiki = (info.find(title) or {}).get('wiki')
    if not wiki:
        return None
    try:
        data = json.loads(_wiki_get(WIKI % urllib.parse.quote(wiki)).decode('utf-8', 'replace'))
        pages = (data.get('query') or {}).get('pages') or {}
        src = next((p.get('original', {}).get('source') for p in pages.values() if p.get('original')), None)
        src = src and src.split('?')[0]
        if src and src.lower().endswith(('.jpg', '.jpeg', '.png')):
            if _save_front(_wiki_get(src), f, whole_scan=False):
                _remember(key, {'source': 'wikipedia', 'wiki': wiki, 'at': time.time()})
                return f
    except (OSError, ValueError):
        raise
    return None


def _fetch(key, title, f):
    try:
        t = find_title(title)
    except OSError:
        return None  # sem rede: tenta outra vez da próxima
    if not t:
        try:
            if _fallback(key, title, f):
                return f
        except OSError:
            return None
        _remember(key, {'miss': time.time(), 'v': MISS_V})
        return None
    try:
        info = json.loads(_get(INFO % t['tid']).decode('utf-8', 'replace'))
    except (OSError, ValueError):
        return None  # sem rede: tenta outra vez da próxima
    cs = sorted(info.get('Covers') or [], key=lambda c: (-(int(c.get('Official') or 0)),
                                                        -(int(c.get('Rating') or 0))))
    errors = 0
    for c in cs[:3]:
        try:
            raw = _get(COVER % c['CoverID'], timeout=40)
        except OSError:
            errors += 1
            continue
        if _save_front(raw, f):
            _remember(key, dict(t, cover=c['CoverID'], at=time.time()))
            return f
    try:
        if _fallback(key, title, f, t['tid']):
            return f
    except OSError:
        return None
    if errors and errors == len(cs[:3]):
        return None  # as capas não vieram (rede): outra vez da próxima
    _remember(key, dict(t, miss=time.time(), v=MISS_V))
    return None


_prefetch = {'started': False, 'done': 0, 'total': 0}


def prefetch(titles, workers=3):
    """Vai buscando as capas de todos os títulos em segundo plano, para o catálogo do Modo Deck não
    esperar por elas: no arranque da app e outra vez de 6 em 6 horas (as que falharam por a rede ou a
    Wikimedia não responderem ficam para a volta seguinte)."""
    if _prefetch['started'] and (not _prefetch.get('finished_at') or
                                 time.time() - _prefetch['finished_at'] < 6 * 3600):
        return _prefetch
    _prefetch.update(started=True, total=len(titles), done=0, finished_at=None)

    def run():
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(workers) as ex:
                for _ in ex.map(lambda t: _safe(t), titles):
                    _prefetch['done'] += 1
        finally:
            _prefetch['finished_at'] = time.time()

    def _safe(t):
        try:
            path(t)
        except Exception:  # noqa: BLE001 - uma capa em falta não pára as outras
            pass
    threading.Thread(target=run, daemon=True, name='catcovers').start()
    return _prefetch


# -- uma capa genérica para quando não há nenhuma ---------------------------------------------------
GEN_V = 2  # sobe quando o desenho muda (os ficheiros guardados levam-no no nome)


def placeholder(title, xbla=False):
    """Uma capa ao estilo de uma caixa de Xbox 360, desenhada aqui, para um jogo sem capa encontrada:
    a faixa verde de cima com "XBOX 360" (ou "XBOX LIVE ARCADE"), um emblema verde com um X e o nome
    do jogo em letra grande. Guardada em <capas>/gen-*.jpg (600x840)."""
    key = catalog.words(title) or title
    f = os.path.join(_dir(), 'gen%d-%s%s.jpg' % (GEN_V, _name(key), '-a' if xbla else ''))
    if os.path.exists(f):
        return f
    from PIL import Image, ImageDraw, ImageFilter
    from .deckapp import _font
    W, H = 600, 840
    green, light = (16, 124, 16), (122, 200, 66)
    # O fundo: um verde muito escuro com um brilho por trás do emblema e riscas diagonais leves.
    im = Image.new('RGB', (W, H), (12, 16, 13))
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W * 0.5 - 330, 330 - 330, W * 0.5 + 330, 330 + 330), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im.paste(Image.new('RGB', (W, H), (26, 74, 30)), (0, 0), glow)
    d = ImageDraw.Draw(im)
    for x in range(-H, W, 28):
        d.line([(x, H), (x + H, 0)], fill=(18, 26, 19), width=2)
    # A faixa de cima, como nas caixas.
    band = 74
    d.rectangle((0, 0, W, band), fill=green)
    d.rectangle((0, band, W, band + 5), fill=light)
    label = 'XBOX LIVE ARCADE' if xbla else 'XBOX 360'
    fb = _font(40, 'black')
    d.text((30, band // 2 + 2), label, font=fb, fill=(255, 255, 255), anchor='lm')
    # O emblema: uma esfera verde com um X branco (um desenho próprio).
    cx, cy, r = W // 2, 330, 120
    orb = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(orb)
    for i in range(r, 0, -2):  # um degradé radial: claro em cima à esquerda, escuro na borda
        t = i / r
        col = tuple(int(a * t + b * (1 - t)) for a, b in zip((14, 92, 14), (170, 230, 120)))
        ox, oy = cx - (r - i) * 0.25, cy - (r - i) * 0.3
        od.ellipse((ox - i, oy - i, ox + i, oy + i), fill=col + (255,))
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    im.paste(orb, (0, 0), Image.composite(orb, Image.new('RGBA', (W, H)), mask).split()[3])
    d = ImageDraw.Draw(im)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(220, 245, 200), width=4)
    # Um X em letra (não um X de fechar), com sombra.
    fx = _font(int(r * 1.55), 'black')
    d.text((cx + 4, cy + 6), 'X', font=fx, fill=(8, 50, 8), anchor='mm')
    d.text((cx, cy), 'X', font=fx, fill=(250, 255, 245), anchor='mm')
    # O nome do jogo: o maior tamanho que caiba na largura e na altura que sobra por baixo do
    # emblema (de y0 a y1), centrado nesse espaço.
    words = (title or '?').split()
    y0, y1 = cy + r + 40, H - 34
    lines, size = [title or '?'], 64
    for size in range(68, 22, -3):
        fnt = _font(size, 'black')
        lines, cur = [], ''
        for w in words:
            tryl = (cur + ' ' + w).strip()
            if d.textlength(tryl, font=fnt) <= W - 70:
                cur = tryl
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) * int(size * 1.12) <= y1 - y0 and all(d.textlength(l, font=fnt) <= W - 70 for l in lines):
            break
    fnt = _font(size, 'black')
    lh = int(size * 1.12)
    y = y0 + (y1 - y0 - len(lines) * lh) // 2
    for l in lines:
        d.text((W // 2 + 3, y + 3), l, font=fnt, fill=(0, 0, 0), anchor='mt')  # sombra
        d.text((W // 2, y), l, font=fnt, fill=(255, 255, 255), anchor='mt')
        y += lh
    d.rectangle((0, H - 10, W, H), fill=green)
    im.save(f, quality=90)
    return f
