"""Os teus jogos, como os tens: as pastas das definições (own_dirs) com jogos fora das fontes do
catálogo. Em cada uma, até 4 níveis abaixo:

- um dump numa pasta (uma pasta com default.xex);
- uma imagem de disco (.iso);
- um arquivo (.7z, .zip, .rar);
- um pacote do Xbox Live (STFS: CON, LIVE ou PIRS; o do jogo, tipo 000D0000).

Aparecem no catálogo (no PC e no Modo Deck) como a fonte "Your files": preparar ou instalar dá o
caminho ao `rexnative prepare` (que já lê tudo isto), sem download. As pastas dos jogos já
preparados (com prepare.json) e as dos downloads ficam de fora."""
import os
import threading
import time

from . import catalog, config, games

ITEM = '@local'
LABEL = 'Your files'
MAX_DEPTH = 4
FILES = ('.7z', '.zip', '.rar', '.iso')
SKIP = {'$recycle.bin', 'system volume information', 'node_modules', '.git', 'game-data', 'generated'}
# Nomes de pasta que não dizem o jogo: o nome vem da pasta de cima.
GENERIC = {'game', 'games', 'default', 'disc1', 'disc 1', 'disc', 'dump', 'content', '000d0000', '00007000'}
KINDS = {'folder': 'a dump folder', 'iso': 'a disc image', 'archive': 'an archive', 'package': 'an Xbox Live package'}
_lock = threading.Lock()
_cache = {'key': None, 'at': 0.0, 'data': []}
_sizes = {}


def dirs():
    return [os.path.abspath(d) for d in (config.get('own_dirs') or []) if d and str(d).strip()]


def _skip_roots():
    """As pastas que a app já trata: os jogos preparados e os downloads."""
    cfg = config.load()
    out = {os.path.normcase(os.path.abspath(p)) for p in (cfg.get('work_roots') or []) if p}
    for k in ('work_dir', 'download_dir'):
        if cfg.get(k):
            out.add(os.path.normcase(os.path.abspath(cfg[k])))
    return out


def _package(p, stfs):
    """(nome, tipo de conteúdo) de um pacote STFS, ou None."""
    try:
        if os.path.getsize(p) < 0xA000:
            return None
        with open(p, 'rb') as f:
            if f.read(4) not in (b'CON ', b'LIVE', b'PIRS'):
                return None
        if stfs is None:
            return ('', 0x000D0000)
        pkg = stfs.Package(p)
        try:
            return (pkg.display_name or '', pkg.content_type)
        finally:
            pkg.close()
    except Exception:  # noqa: BLE001 - um ficheiro estranho não é um jogo
        return None


def _folder_size(d):
    try:
        k = (d, os.path.getmtime(d))
    except OSError:
        return 0
    if k not in _sizes:
        total = 0
        for root, _, files in os.walk(d):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        _sizes[k] = total
    return _sizes[k]


def _title_of_folder(d):
    name = os.path.basename(d.rstrip('\\/'))
    parent = os.path.basename(os.path.dirname(d.rstrip('\\/')))
    hexid = len(name) == 8 and all(c in '0123456789abcdefABCDEF' for c in name)
    return parent if (name.lower() in GENERIC or hexid) and parent else name


def _entry(path, kind, title=None):
    t, tags = catalog.parse_name(title or os.path.basename(path.rstrip('\\/')))
    size = os.path.getsize(path) if os.path.isfile(path) else _folder_size(path)
    return {'item': ITEM, 'source': LABEL, 'name': path, 'path': path, 'kind': kind, 'title': t or path,
            'tags': tags, 'size': size, 'md5': '', 'slug': catalog.slug(title or os.path.basename(path)),
            'key': catalog.words(t or path), 'own': True}


def _walk(d, depth, out, skip, ctx):
    if os.path.normcase(d) in skip:
        return
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return
    low = {n.lower() for n in names}
    if 'prepare.json' in low:
        return  # um jogo já preparado (uma pasta de trabalho)
    if 'default.xex' in low:
        out.append(_entry(d, 'folder', _title_of_folder(d)))
        return
    for n in names:
        p = os.path.join(d, n)
        if os.path.isdir(p):
            if depth < MAX_DEPTH and n.lower() not in SKIP and not n.startswith('.'):
                _walk(p, depth + 1, out, skip, ctx)
        elif n.lower().endswith(FILES):
            out.append(_entry(p, 'iso' if n.lower().endswith('.iso') else 'archive'))
        elif '.' not in n:
            if 'stfs' not in ctx:
                try:
                    ctx['stfs'] = games.rexnative('stfs')
                except Exception:  # noqa: BLE001 - sem o ReXNative: só pela assinatura
                    ctx['stfs'] = None
            pk = _package(p, ctx['stfs'])
            if pk and pk[1] == 0x000D0000:
                out.append(_entry(p, 'package', pk[0] or _title_of_folder(os.path.dirname(os.path.dirname(p)))))


def scan(max_age=30):
    """Os jogos nas tuas pastas: entradas como as do catálogo (item '@local', name = o caminho),
    com path e kind. Lidas outra vez de 30 em 30 segundos."""
    key = tuple(dirs())
    with _lock:
        if _cache['key'] == key and time.time() - _cache['at'] < max_age:
            return list(_cache['data'])
        out, skip, ctx = [], _skip_roots(), {}
        for base in key:
            if os.path.isdir(base):
                _walk(base, 0, out, skip, ctx)
        seen, uniq = set(), []
        for e in out:
            k = os.path.normcase(e['path'])
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        _cache.update(key=key, at=time.time(), data=uniq)
        return list(uniq)


def entry(path):
    """A entrada de um caminho que está mesmo nas tuas pastas (o Modo Deck só pede estes), ou None."""
    k = os.path.normcase(os.path.abspath(path or ''))
    return next((e for e in scan() if os.path.normcase(e['path']) == k), None)


def kind_of(path):
    """O que um caminho é, para preparar (o PC pode dar um qualquer): (kind, título, o caminho a
    preparar) ou (None, porquê, None). Uma pasta com um só jogo dentro dá o caminho desse jogo."""
    if not path or not os.path.exists(path):
        return None, 'it does not exist', None
    if os.path.isdir(path):
        found = []
        _walk(path, 0, found, set(), {})
        if not found:
            return None, 'no game in that folder (a default.xex, an .iso, an archive or an Xbox Live package)', None
        if len(found) > 1:
            return None, ('that folder has %d games: choose one of them, or add the folder to your game '
                          'folders to see them all in the catalogue' % len(found)), None
        f = found[0]
        return f['kind'], f['title'], f['path']
    low = path.lower()
    if low.endswith('.iso'):
        return 'iso', catalog.parse_name(os.path.basename(path))[0], path
    if low.endswith(('.7z', '.zip', '.rar')):
        return 'archive', catalog.parse_name(os.path.basename(path))[0], path
    try:
        stfs = games.rexnative('stfs')
    except Exception:  # noqa: BLE001
        stfs = None
    pk = _package(path, stfs)
    if pk:
        if pk[1] != 0x000D0000:
            return None, 'that Xbox Live package is not a game (a title update or DLC?)', None
        return 'package', pk[0] or os.path.basename(path), path
    return None, 'not a game: use a dump folder, an .iso, a .7z/.zip/.rar or an Xbox Live package', None


def pick(what):
    """A janela do Windows para escolher um ficheiro ou uma pasta (a app corre neste PC): o caminho,
    ou '' se se cancelou. Num processo à parte (o Tk quer o seu fio principal)."""
    import subprocess
    import sys
    from . import jobs
    code = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        "if %r == 'folder':\n"
        "    p = filedialog.askdirectory(title='Choose the game folder (a dump with default.xex) or a folder of games')\n"
        "else:\n"
        "    p = filedialog.askopenfilename(title='Choose a game: a disc image, an archive or an Xbox Live package',\n"
        "        filetypes=[('Games', '*.iso *.7z *.zip *.rar'), ('All files (Xbox Live packages)', '*.*')])\n"
        "print(p or '')\n") % what
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=900,
                       encoding='utf-8', errors='replace', creationflags=getattr(jobs, 'CREATE_NO_WINDOW', 0))
    p = (r.stdout or '').strip()
    return os.path.normpath(p) if p else ''
