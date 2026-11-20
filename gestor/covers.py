"""Capas oficiais para o atalho do Steam de cada jogo (<work>/deck/art, que o kit do Deck envia):
- XboxUnity: os scans das caixas (até 6, oficiais e mais bem votados primeiro; a frente é a parte
  direita de um scan inteiro: costas 129 mm, lombada 14, frente 129);
- o Xbox 360 Marketplace: fundo 1280x720, banner, box art, tile e capturas;
- SteamGridDB (opcional, com chave da API): grids 600x900, heroes e logos da comunidade;
- as capturas do próprio jogo (teste de arranque, Deck).
O utilizador escolhe a capa (retrato) e o fundo (grid/hero); compose() faz portrait 600x900,
grid 920x430, hero 1920x620, icon 256x256 (e logo.png se escolher um).
Adaptado de fetch_covers.py e compose.py (scripts de uma sessão anterior)."""
import glob
import hashlib
import http.client
import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request

from . import config, games

UA = {'User-Agent': 'Mozilla/5.0 (ReXNativeManager)'}
FRONT = 129 / 272
MP = 'http://download.xbox.com/content/images/66acd000-77fe-1000-9115-d802%s/1033/'
MP_FILES = ('background.jpg', 'banner.png', 'boxartlg.jpg', 'tile.png', 'screenlg1.jpg',
            'screenlg2.jpg', 'screenlg3.jpg')
SGDB = 'https://www.steamgriddb.com/api/v2'


def cache_dir(slug):
    return config.data_dir('covers', re.sub(r'[^a-z0-9._-]', '_', slug.lower()))


class _V4Connection(http.client.HTTPConnection):
    """Liga por IPv4: o xboxunity.net tem um endereço IPv6 que não responde e o urllib tenta-o
    primeiro (21 s perdidos em cada pedido, no Windows)."""

    def connect(self):
        addr = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)[0][4]
        self.sock = socket.create_connection(addr, self.timeout)


class _V4Handler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_V4Connection, req)


_opener = urllib.request.build_opener(_V4Handler)


def urlopen(req, timeout=40):
    """urllib.request.urlopen, com os pedidos http:// por IPv4."""
    return _opener.open(req, timeout=timeout)


def _get(url, path, headers=None):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    try:
        req = urllib.request.Request(url, headers=dict(UA, **(headers or {})))
        with urlopen(req, timeout=40) as r:
            if r.status != 200:
                return False
            data = r.read()
    except Exception:  # noqa: BLE001 - uma imagem em falta não pára as outras
        return False
    if len(data) < 500:
        return False
    with open(path, 'wb') as f:
        f.write(data)
    time.sleep(0.2)
    return True


def _json(url, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})))
    with urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def fetch(work, log=print):
    """Descarrega as imagens candidatas do jogo para a cache; devolve candidates()."""
    g = games.info(work)
    slug = g['slug']
    d = cache_dir(slug)
    tid = (g.get('title_id') or '').upper()
    if tid:
        base = MP % tid.lower()
        for f in MP_FILES:
            _get(base + f, os.path.join(d, 'mp-' + f))
        info = os.path.join(d, 'coverinfo.json')
        _get('http://xboxunity.net/Resources/Lib/CoverInfo.php?titleid=%s' % tid, info)
        try:
            covers = json.load(open(info, encoding='utf-8')).get('Covers') or []
        except (OSError, ValueError):
            covers = []
        covers.sort(key=lambda c: (-(int(c.get('Official') or 0)), -(int(c.get('Rating') or 0))))
        got = 0
        for c in covers[:6]:
            if _get('http://xboxunity.net/Resources/Lib/Cover.php?size=large&cid=%s' % c['CoverID'],
                    os.path.join(d, 'cover-%s.jpg' % c['CoverID'])):
                got += 1
        log('%s (%s): %d of %d XboxUnity covers, marketplace: %s' % (
            g['title'], tid, got, len(covers),
            ', '.join(f for f in MP_FILES if os.path.exists(os.path.join(d, 'mp-' + f))) or 'nothing'))
    key = config.load().get('steamgriddb_key')
    if key:
        try:
            _fetch_sgdb(g['title'], d, key, log)
        except Exception as e:  # noqa: BLE001
            log('SteamGridDB: %s' % e)
    return candidates(work)


def _fetch_sgdb(title, d, key, log):
    h = {'Authorization': 'Bearer %s' % key}
    found = _json(SGDB + '/search/autocomplete/' + urllib.parse.quote(title), h).get('data') or []
    if not found:
        log('SteamGridDB: nothing for "%s"' % title)
        return
    gid = found[0]['id']
    n = 0
    for kind, query, prefix in (('grids', '?dimensions=600x900', 'sgdb-p-'),
                                ('heroes', '', 'sgdb-h-'), ('logos', '', 'sgdb-l-')):
        try:
            items = _json('%s/%s/game/%d%s' % (SGDB, kind, gid, query), h).get('data') or []
        except Exception:  # noqa: BLE001
            continue
        for it in items[:6]:
            ext = os.path.splitext(urllib.parse.urlparse(it['url']).path)[1] or '.png'
            if _get(it['url'], os.path.join(d, '%s%s%s' % (prefix, it['id'], ext))):
                n += 1
    log('SteamGridDB: "%s" (id %d), %d images' % (found[0].get('name'), gid, n))


# -- imagens -----------------------------------------------------------------------------------
def _pil():
    from PIL import Image, ImageDraw, ImageFilter, ImageStat  # noqa: F401
    return Image


def front(path):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    if w > h:  # um scan inteiro: a frente é a parte direita
        fw = round(w * FRONT)
        im = im.crop((w - fw, 0, w, h))
    return im


def cover_crop(im, size, focus=0.5):
    from PIL import Image
    w, h = im.size
    s = max(size[0] / w, size[1] / h)
    im = im.resize((max(size[0], round(w * s)), max(size[1], round(h * s))), Image.LANCZOS)
    x = (im.width - size[0]) // 2
    y = round((im.height - size[1]) * focus)
    return im.crop((x, y, x + size[0], y + size[1]))


_md5_cache = {}


def _md5(path):
    """O md5 de um ficheiro, guardado enquanto o ficheiro não mudar (os fundos de todos os jogos
    eram lidos outra vez sempre que se abriam as capas de um)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.normcase(path), st.st_mtime_ns, st.st_size)
    if key not in _md5_cache:
        with open(path, 'rb') as f:
            _md5_cache[key] = hashlib.md5(f.read()).hexdigest()
    return _md5_cache[key]


def _generic_backgrounds():
    """Os fundos do marketplace iguais em vários jogos (o genérico do Xbox LIVE)."""
    from collections import Counter
    paths = glob.glob(os.path.join(config.data_dir('covers'), '*', 'mp-background.jpg'))
    count = Counter(_md5(p) for p in paths)
    return {h for h, n in count.items() if n > 1}


def _white(path):
    from PIL import Image, ImageStat
    return ImageStat.Stat(Image.open(path).convert('L')).mean[0] > 190


def _thumb(src, dst, size, crop_front=False):
    from PIL import Image
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    im = front(src) if crop_front else Image.open(src).convert('RGB')
    im.thumbnail(size)
    im.save(dst, quality=85)
    return dst


def captures(work):
    """Capturas do jogo: do teste de arranque da app, do Deck (deck/try-*.png) e do live.ps1."""
    g = os.path.basename(work)
    files = glob.glob(os.path.join(config.data_dir('shots'), g + '.png'))
    files += sorted(glob.glob(os.path.join(work, 'deck', 'try-*.png')), key=os.path.getmtime)[-6:]
    files += sorted(glob.glob(os.path.join(work, 'run', 'live', 'shots', '*.png')), key=os.path.getmtime)[-6:]
    # As capturas da comparação nativo / clássico (pipeline.step_compare).
    files += sorted(glob.glob(os.path.join(config.data_dir('compare', g), '*-[0-9][0-9][0-9].png')))
    return [f for f in files if os.path.getsize(f) > 20000]


def candidates(work):
    """{'portrait': [...], 'background': [...], 'logo': [...]}: cada um {id, label, thumb}
    (thumb é um nome de ficheiro na cache do jogo)."""
    slug = os.path.basename(work)
    d = cache_dir(slug)
    th = os.path.join(d, 'thumbs')
    os.makedirs(th, exist_ok=True)
    out = {'portrait': [], 'background': [], 'logo': []}
    # Pela ordem do XboxUnity: as oficiais primeiro, depois as mais bem votadas.
    try:
        info = json.load(open(os.path.join(d, 'coverinfo.json'), encoding='utf-8')).get('Covers') or []
    except (OSError, ValueError):
        info = []
    rank = {str(c.get('CoverID')): (-(int(c.get('Official') or 0)), -(int(c.get('Rating') or 0)), i)
            for i, c in enumerate(info)}
    official = {str(c.get('CoverID')) for c in info if int(c.get('Official') or 0)}
    files = sorted(glob.glob(os.path.join(d, 'cover-*.jpg')),
                   key=lambda f: rank.get(os.path.basename(f)[6:-4], (1, 0, 999)))
    for f in files:
        cid = os.path.basename(f)[6:-4]
        _thumb(f, os.path.join(th, 'p-' + cid + '.jpg'), (240, 360), crop_front=True)
        out['portrait'].append({'id': 'xu:' + cid, 'label': 'XboxUnity %s%s' % (
                                    cid, ' (official)' if cid in official else ''),
                                'thumb': 'thumbs/p-%s.jpg' % cid})
    bx = os.path.join(d, 'mp-boxartlg.jpg')
    if os.path.exists(bx):
        _thumb(bx, os.path.join(th, 'p-mp.jpg'), (240, 360))
        out['portrait'].append({'id': 'mp', 'label': 'Marketplace (box art)', 'thumb': 'thumbs/p-mp.jpg'})
    for f in sorted(glob.glob(os.path.join(d, 'sgdb-p-*'))):
        n = os.path.splitext(os.path.basename(f))[0]
        _thumb(f, os.path.join(th, n + '.jpg'), (240, 360))
        out['portrait'].append({'id': 'sgdb:' + os.path.basename(f), 'label': 'SteamGridDB',
                                'thumb': 'thumbs/%s.jpg' % n})
    generic = _generic_backgrounds()
    for name in ('mp-background.jpg', 'mp-screenlg1.jpg', 'mp-screenlg2.jpg', 'mp-screenlg3.jpg'):
        f = os.path.join(d, name)
        if not os.path.exists(f):
            continue
        if name == 'mp-background.jpg' and (_md5(f) in generic or _white(f)):
            continue
        n = name[:-4]
        _thumb(f, os.path.join(th, 'b-%s.jpg' % n), (384, 216))
        out['background'].append({'id': 'file:' + name, 'label': 'Marketplace %s' % n[3:],
                                  'thumb': 'thumbs/b-%s.jpg' % n})
    for f in sorted(glob.glob(os.path.join(d, 'sgdb-h-*'))):
        n = os.path.splitext(os.path.basename(f))[0]
        _thumb(f, os.path.join(th, n + '.jpg'), (384, 216))
        out['background'].append({'id': 'file:' + os.path.basename(f), 'label': 'SteamGridDB hero',
                                  'thumb': 'thumbs/%s.jpg' % n})
    for i, f in enumerate(captures(work)):
        h = hashlib.md5(f.encode()).hexdigest()[:10]
        _thumb(f, os.path.join(th, 'c-%s.jpg' % h), (384, 216))
        out['background'].append({'id': 'cap:' + f, 'label': 'Capture %s' % os.path.basename(f),
                                  'thumb': 'thumbs/c-%s.jpg' % h})
    out['background'].append({'id': 'blur', 'label': 'The cover, blurred', 'thumb': None})
    for f in sorted(glob.glob(os.path.join(d, 'sgdb-l-*'))):
        n = os.path.splitext(os.path.basename(f))[0]
        _thumb(f, os.path.join(th, n + '.jpg'), (300, 120))
        out['logo'].append({'id': 'file:' + os.path.basename(f), 'label': 'SteamGridDB logo',
                            'thumb': 'thumbs/%s.jpg' % n})
    picks = _picks_path(work)
    out['picked'] = json.load(open(picks, encoding='utf-8')) if os.path.exists(picks) else {}
    out['current'] = sorted(f[:-4] for f in os.listdir(os.path.join(work, 'deck', 'art'))
                            if f.endswith('.png')) if os.path.isdir(os.path.join(work, 'deck', 'art')) else []
    return out


def _picks_path(work):
    return os.path.join(cache_dir(os.path.basename(work)), 'picks.json')


def _open_pick(work, pick):
    from PIL import Image
    d = cache_dir(os.path.basename(work))
    if pick.startswith('xu:'):
        return front(os.path.join(d, 'cover-%s.jpg' % re.sub(r'\D', '', pick[3:])))
    if pick == 'mp':
        return Image.open(os.path.join(d, 'mp-boxartlg.jpg')).convert('RGB')
    if pick.startswith('sgdb:') or pick.startswith('file:'):
        name = os.path.basename(pick.split(':', 1)[1])
        return Image.open(os.path.join(d, name)).convert('RGBA' if 'sgdb-l-' in name else 'RGB')
    if pick.startswith('cap:'):
        path = pick[4:]
        if path not in captures(work):
            raise ValueError('unknown capture')
        return Image.open(path).convert('RGB')
    raise ValueError('unknown choice: %s' % pick)


def compose(work, portrait, background='blur', logo=None):
    """Escreve <work>/deck/art (portrait, grid, hero, icon e logo) a partir das escolhas."""
    from PIL import Image, ImageFilter
    out = os.path.join(work, 'deck', 'art')
    os.makedirs(out, exist_ok=True)
    fr = _open_pick(work, portrait)
    cover_crop(fr, (600, 900), 0.5).save(os.path.join(out, 'portrait.png'), optimize=True)
    if background and background != 'blur':
        bg = _open_pick(work, background)
    else:
        bg = cover_crop(fr, (1280, 720)).filter(ImageFilter.GaussianBlur(20))
        fw = fr.resize((round(720 * fr.width / fr.height), 720), Image.LANCZOS)
        bg.paste(fw, ((1280 - fw.width) // 2, 0))
    cover_crop(bg, (920, 430), 0.35).save(os.path.join(out, 'grid.png'), optimize=True)
    cover_crop(bg, (1920, 620), 0.35).save(os.path.join(out, 'hero.png'), optimize=True)
    d = cache_dir(os.path.basename(work))
    tile = os.path.join(d, 'mp-tile.png')
    icon = Image.open(tile).convert('RGBA') if os.path.exists(tile) else cover_crop(fr, (256, 256), 0.3)
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(out, 'icon.png'), optimize=True)
    logo_path = os.path.join(out, 'logo.png')
    if logo:
        lg = _open_pick(work, logo)
        lg.thumbnail((1280, 720))
        lg.save(logo_path, optimize=True)
    elif os.path.exists(logo_path) and logo == '':
        os.remove(logo_path)
    with open(_picks_path(work), 'w', encoding='utf-8') as f:
        json.dump({'portrait': portrait, 'background': background, 'logo': logo}, f)
    return sorted(f[:-4] for f in os.listdir(out) if f.endswith('.png'))


# -- escolha automática (modelo barato) -------------------------------------------------------------
AUTO_SCHEMA = {
    'type': 'object',
    'properties': {'portrait': {'type': 'integer'}, 'background': {'type': 'integer'},
                   'reason': {'type': 'string'}},
    'required': ['portrait', 'background', 'reason'],
}

AUTO_PROMPT = """Choose Steam library artwork for the Xbox 360 game "{title}" (title id {tid}).

1. Read the image {psheet}: {np} numbered candidate covers (1 to {np}). Pick the best one for the
   tall library capsule: the game's own official front cover / box art (the right game, not a
   different game or a fan-made cover), complete, sharp and readable; when several are the same art,
   prefer one XboxUnity marks official, then the cleanest one (fewest stickers or borders).
   The candidates: {plabels}
2. Read the image {bsheet}: {nb} numbered candidate backgrounds (1 to {nb}) for the wide banner
   and the hero image (cropped to wide strips). Prefer official key art or a striking in-game scene
   without big text; avoid menus, loading screens, logos on plain colour and blurry images. Answer 0
   if none fits (a blurred copy of the cover is used then).

Answer with the JSON: portrait (number), background (number, 0 = none) and reason (one short
sentence in English saying why)."""


def _sheet(items, d, path, size):
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    cols = min(4, max(1, len(items)))
    rows = (len(items) + cols - 1) // cols
    img = Image.new('RGB', (cols * (w + 12) + 12, rows * (h + 12) + 12), (24, 24, 24))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arialbd.ttf', 34)
    except OSError:
        font = ImageFont.load_default()
    for i, it in enumerate(items):
        im = Image.open(os.path.join(d, it['thumb'])).convert('RGB')
        im.thumbnail((w, h))
        x = 12 + (i % cols) * (w + 12)
        y = 12 + (i // cols) * (h + 12)
        img.paste(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))
        dr.rectangle((x, y, x + 52, y + 44), fill=(0, 0, 0))
        dr.text((x + 10, y + 3), str(i + 1), fill=(255, 220, 0), font=font)
    img.save(path, quality=88)


def auto_pick(work, log=print):
    """Procura as capas se ainda não houver, deixa o modelo barato escolher capa e fundo, e
    compõe a arte. Devolve {portrait, background, reason, cost}."""
    from . import claude
    c = candidates(work)
    if not c['portrait']:
        c = fetch(work, log=log)
    if not c['portrait']:
        raise RuntimeError('there are no covers to choose from (no title id, or no covers on XboxUnity/Marketplace)')
    g = games.info(work)
    d = cache_dir(g['slug'])
    portraits = c['portrait']
    backs = [b for b in c['background'] if b['thumb']]
    _sheet(portraits, d, os.path.join(d, 'escolha-capas.jpg'), (240, 360))
    if backs:
        _sheet(backs, d, os.path.join(d, 'escolha-fundos.jpg'), (384, 216))
    plabels = '; '.join('%d = %s' % (i + 1, p['label']) for i, p in enumerate(portraits))
    prompt = AUTO_PROMPT.format(title=g['title'], tid=g.get('title_id') or '?', plabels=plabels,
                                psheet='escolha-capas.jpg', np=len(portraits),
                                bsheet='escolha-fundos.jpg' if backs else '(none)', nb=len(backs))
    answer, cost = claude.ask(prompt, AUTO_SCHEMA, cwd=d)
    pi = int(answer.get('portrait') or 1)
    bi = int(answer.get('background') or 0)
    portrait = portraits[pi - 1]['id'] if 1 <= pi <= len(portraits) else portraits[0]['id']
    background = backs[bi - 1]['id'] if 1 <= bi <= len(backs) else 'blur'
    made = compose(work, portrait, background)
    log('The cheap model picked: cover %s, background %s — %s' % (
        portrait, background, answer.get('reason', '')))
    return {'portrait': portrait, 'background': background, 'reason': answer.get('reason'),
            'cost': cost, 'art': made}
