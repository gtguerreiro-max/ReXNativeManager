"""O catálogo: os ficheiros dos itens do Internet Archive configurados (API de metadados, pública;
os ficheiros em si pedem uma conta, ver downloads.py), guardados em cache um dia, e a pesquisa no
Internet Archive por jogos que não estejam nesses itens."""
import itertools
import json
import os
import re
import time
import urllib.parse
import urllib.request

from . import config, fsutil

METADATA = 'https://archive.org/metadata/%s'
UA = 'ReXNativeManager/1.0 (+https://github.com)'
GAME_EXT = ('.rar', '.7z', '.zip', '.iso')
# Os sufixos de uma release "scene": região, plataforma e grupo.
REGIONS = {'USA', 'EUR', 'PAL', 'JAP', 'JPN', 'NTSC', 'RF', 'ASIA', 'AUS', 'KOR', 'GER', 'FRA',
           'ITA', 'SPA', 'UK', 'NTSC-J', 'NTSC-U', 'CHN', 'TWN', 'RUS', 'POL', 'NORDIC', 'EU',
           'MULTI', 'MULTI2', 'MULTI3', 'MULTI4', 'MULTI5', 'MULTI6', 'MULTI7', 'MULTI8', 'DLC',
           'XBLA', 'X360', 'XBOX360', 'XBOX', 'PROPER', 'REPACK', 'READ.NFO', 'RIP', 'DVD9',
           'JTAG', 'RGH', 'GOD', 'XEX', 'INTERNAL', 'LIMITED', 'EX'}
ROMAN = {'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9'}
FILLER = {'the', 'a', 'an', 'of', 'and', 's', 'edition', 'complete', 'goty', 'directors',
          'director', 'cut', 'game', 'year', '1'}


def _get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def parse_name(name):
    """'007.Blood.Stone.USA.X360-ZTM.rar' -> ('007 Blood Stone', ['USA']);
    'Spelunky (World) (XBLA).7z' -> ('Spelunky', ['World', 'XBLA'])."""
    base = os.path.basename(name)
    for ext in GAME_EXT:
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
    tags = re.findall(r'\(([^)]*)\)', base)
    if tags or ' ' in base:
        title = re.sub(r'\s*[\(\[][^)\]]*[\)\]]', '', base).strip()
        return title.replace(' - ', ': ', 1), tags
    base = re.sub(r'-[A-Za-z0-9]+$', '', base)  # o grupo (-ZTM)
    parts = base.split('.')
    regions = []
    while len(parts) > 1 and parts[-1].upper() in REGIONS:
        regions.insert(0, parts.pop())
    title = ' '.join(p for p in parts if p).replace('_', ' ')
    return title, [r for r in regions if r.upper() not in ('X360', 'XBOX360', 'XBOX')]


def words(title):
    """Chave para comparar nomes: 'Asura's Wrath' -> 'asuras wrath'."""
    t = title.lower().replace('&', ' and ').replace("'", '').replace('’', '')
    out = [ROMAN.get(w, w) for w in re.findall(r'[a-z0-9]+', t)]
    return ' '.join(w for w in out if w not in FILLER)


def slug(name):
    """Como `rexnative prepare` nomeia a pasta do jogo (prepare.slug)."""
    base = os.path.basename(name)
    for ext in GAME_EXT:
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
    base = re.sub(r'\s*\([^)]*\)', '', base)
    s = re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')
    return s or 'game'


def _cache_path(item):
    return os.path.join(config.data_dir('catalog'), re.sub(r'[^A-Za-z0-9_.-]', '_', item) + '.json')


def item_metadata(item, refresh=False, max_age=24 * 3600):
    """Os metadados do item (da cache se tiverem menos de max_age)."""
    path = _cache_path(item)
    if not refresh and os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        try:
            return json.load(open(path, encoding='utf-8'))
        except ValueError:
            pass
    try:
        data = _get_json(METADATA % urllib.parse.quote(item))
    except OSError:
        if os.path.exists(path):  # sem rede: a cache, mesmo velha
            return json.load(open(path, encoding='utf-8'))
        raise
    if not data or 'files' not in data:
        raise ValueError('the item %s does not exist or has no files' % item)
    keep = {'metadata': {k: data.get('metadata', {}).get(k) for k in ('title', 'identifier',
                                                                      'access-restricted-item')},
            'files': [{'name': f['name'], 'size': int(f.get('size') or 0),
                       'md5': (f.get('md5') or '').lower(), 'format': f.get('format')}
                      for f in data['files'] if f.get('source') == 'original'],
            'fetched': time.time()}
    fsutil.write_json(path, keep)
    return keep


def game_files(meta):
    return [f for f in meta['files'] if f['name'].lower().endswith(GAME_EXT) and
            '/' not in f['name']]


def entries(refresh=False):
    """Todos os jogos de todas as fontes: [{item, source, name, title, tags, size, md5, slug,
    key}], e os erros por fonte."""
    out, errors = [], {}
    for src in config.load()['sources']:
        item = src['item'] if isinstance(src, dict) else src
        label = (src.get('label') if isinstance(src, dict) else None) or item
        try:
            meta = item_metadata(item, refresh=refresh)
        except Exception as e:  # noqa: BLE001 - uma fonte em falta não tapa as outras
            errors[item] = str(e)
            continue
        for f in game_files(meta):
            title, tags = parse_name(f['name'])
            out.append({'item': item, 'source': label, 'name': f['name'], 'title': title,
                        'tags': tags, 'size': f['size'], 'md5': f['md5'],
                        'slug': slug(f['name']), 'key': words(title)})
    # Os teus jogos (as pastas de own_dirs), sem passar pelo Internet Archive.
    from . import owngames
    try:
        out.extend(owngames.scan())
    except Exception as e:  # noqa: BLE001 - uma pasta ilegível não tapa o catálogo
        errors[owngames.ITEM] = str(e)
    return out, errors


def find_file(item, name):
    meta = item_metadata(item)
    for f in meta['files']:
        if f['name'] == name:
            return f
    meta = item_metadata(item, refresh=True)
    return next((f for f in meta['files'] if f['name'] == name), None)


def search(text, xbox_only=True, rows=40):
    """Itens do Internet Archive para um texto (o motor de pesquisa do arquivo, via a biblioteca
    internetarchive), os mais descarregados primeiro."""
    import internetarchive
    text = text.strip()
    if not text:
        return []
    q = '(%s)' % text
    if xbox_only:
        q += ' AND (xbox OR x360 OR xbla OR "xbox 360")'
    fields = ['identifier', 'title', 'item_size', 'downloads', 'mediatype', 'publicdate']
    res = internetarchive.search_items(q, fields=fields, sorts=['downloads desc'],
                                       params={'rows': rows})
    out = []
    for r in itertools.islice(res, rows):
        out.append({k: r.get(k) for k in fields})
    return out


def item_games(item):
    """Os ficheiros de jogo de um item qualquer (para os resultados da pesquisa)."""
    meta = item_metadata(item, refresh=True)
    files = game_files(meta) or [f for f in meta['files'] if f['name'].lower().endswith(GAME_EXT)]
    out = []
    for f in files:
        title, tags = parse_name(os.path.basename(f['name']))
        out.append(dict(f, item=item, title=title, tags=tags, slug=slug(f['name']),
                        key=words(title)))
    return {'title': meta['metadata'].get('title'), 'restricted':
            bool(meta['metadata'].get('access-restricted-item')), 'files': out}
