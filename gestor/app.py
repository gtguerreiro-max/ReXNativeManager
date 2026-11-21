"""A API e a página da app (FastAPI em 127.0.0.1; o Modo Deck, /deck, também na rede de casa
para os aparelhos emparelhados: lan.py)."""
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (agents, catalog, catcovers, changelog, claude, config, connection, covers, deck, deckapp, freshness,
               games, github, info, jobs, lan, linuxbuild, orders, owngames, pipeline, rexlog, rexrepo, saves,
               scenes, sdk, state, tunings, versions, xna)

HERE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title='ReXNative Manager')
manager = jobs.Manager()
# Ver se já há uma tarefa e pô-la na fila de uma vez (dois pedidos ao mesmo tempo, do PC e do Deck,
# punham duas para o mesmo jogo ou ficheiro).
_submit_lock = threading.RLock()
# Comprimido para quem o pede (o catálogo do Deck: 590 KB, 83 KB comprimido). Registado antes do
# guard, que fica por fora (o último a ser registado é o primeiro a correr).
app.add_middleware(GZipMiddleware, minimum_size=2000)


def _deck_appeared():
    """O Deck voltou a responder: lê a lista dos jogos, se ninguém estiver a jogar (a leitura
    mede as pastas, o que pesa no disco do Deck durante um jogo)."""
    try:
        dk = deck.Deck()
        if not deck._playing(dk):
            deck.status(refresh=True)
    except Exception:  # noqa: BLE001
        pass


watcher = connection.Watcher(on_online=_deck_appeared)
# O pipeline põe em fila os relatórios automáticos (nativo com erros) por aqui.
pipeline.SUBMIT = lambda kind, title, fn, lane, game, params: manager.submit(
    kind, title, fn, lane=lane, game=game, params=params)
# Género, ano e nota do Metacritic (Wikidata + Wikipédia): lidos de novo ao fim de 14 dias.
if info.stale():
    info.refresh_in_background()


# De fora (a rede de casa) só isto, e tudo menos a página e o emparelhar com o token de um
# aparelho emparelhado (lan.py).
REMOTE_PATHS = ('/deck', '/static/deck', '/static/fonts', '/static/rexlog.js', '/api/ping', '/api/pair/', '/api/remote/')
REMOTE_OPEN = ('/deck', '/static/deck', '/static/fonts', '/static/rexlog.js', '/api/ping', '/api/pair/')


@app.middleware('http')
async def guard(request: Request, call_next):
    # Nesta máquina: o Host tem de ser o local (contra DNS rebinding) e os pedidos que mudam
    # alguma coisa trazem X-Gestor (uma página de outro site não o consegue enviar sem CORS, que
    # esta app não dá). Da rede de casa: só com a opção ligada, de um endereço privado, com o Host
    # deste PC, só o Modo Deck, e com o token de um aparelho emparelhado.
    client = request.client.host if request.client else ''
    host = (request.headers.get('host') or '').rsplit(':', 1)[0].strip('[]').lower()
    path = request.url.path
    if '..' in path or '\\' in path:
        return PlainTextResponse('bad path', status_code=400)
    if lan.is_loopback(client):
        if host not in ('127.0.0.1', 'localhost'):
            return PlainTextResponse('host not allowed', status_code=403)
    else:
        if not config.load().get('lan_enabled') or not lan.is_private(client):
            return PlainTextResponse('the app only accepts connections from this PC', status_code=403)
        if host not in lan.allowed_hosts():
            return PlainTextResponse('host not allowed', status_code=403)
        if not path.startswith(REMOTE_PATHS):
            return PlainTextResponse('not available on the network', status_code=403)
        if not path.startswith(REMOTE_OPEN):
            token = request.cookies.get(lan.COOKIE) or request.headers.get('x-gestor-token')
            dev = lan.check(token, client)
            if not dev:
                return JSONResponse({'detail': 'pair this device first'}, status_code=401)
    if request.method not in ('GET', 'HEAD') and request.headers.get('x-gestor') != '1':
        return PlainTextResponse('the X-Gestor header is missing', status_code=403)
    # A sessão no GitHub é obrigatória: sem ela só a página e o login respondem (as correções são
    # partilhadas pelo GitHub, e os commits levam a identidade de quem usa a app).
    if path.startswith('/api/') and not path.startswith(LOGIN_FREE) and not github.logged_in_fast():
        return JSONResponse({'detail': 'Sign in with GitHub first (on the PC: the ReXNative Manager page)',
                             'login_required': True}, status_code=428)
    return await call_next(request)


LOGIN_FREE = ('/api/github', '/api/ping', '/api/version', '/api/pair/')


@app.get('/api/github')
def github_state(refresh: bool = False):
    """A sessão no GitHub (gh): quem é, se pode publicar no ReXNative, e o login a decorrer."""
    return dict(github.status(refresh=refresh), login_flow=github.login_state())


@app.post('/api/github/login')
def github_login():
    """Começa o login do gh: o código para escrever em github.com/login/device."""
    return github.login_start()


def _work(slug):
    # Só o nome de um jogo das pastas de trabalho (um caminho deixava pedir qualquer pasta do PC).
    w = None if os.path.isabs(slug) else games.find(slug)
    if not w:
        raise HTTPException(404, 'game %s not found in the work folders' % slug)
    return w


def _job(j):
    return j.to_dict()


# -- catálogo ------------------------------------------------------------------------------------
def _download_path(item, name):
    return orders.download_path(item, name)


@app.get('/api/catalog')
def get_catalog(refresh: bool = False):
    items, errors = catalog.entries(refresh=refresh)
    find_local = games.local_lookup()
    active = {(j.params.get('item'), j.params.get('name')): j.id
              for j in manager.active(kind='download')}
    xna_seen = xna.load()
    for e in items:
        e['local'] = (find_local(e) or {}).get('slug')
        if e.get('own'):
            e['downloaded'] = 'sim'  # um jogo teu já está no disco
        else:
            p = _download_path(e['item'], e['name'])
            have = os.path.getsize(p) if os.path.exists(p) else 0
            e['downloaded'] = 'sim' if have == e['size'] else ('parcial' if have else None)
        e['job'] = active.get((e['item'], e['name']))
        e['info'] = info.compact(e['title'])
        if (xna_seen.get(e['name']) or {}).get('xna'):
            e['unsupported'] = 'XNA'
    xna_info = {'scanned': sum(1 for e in items if e['name'] in xna_seen),
                'count': sum(1 for e in items if e.get('unsupported') == 'XNA')}
    sources = [{'item': s['item'], 'label': s.get('label') or s['item'],
                'count': sum(1 for e in items if e['item'] == s['item']),
                'size': sum(e['size'] for e in items if e['item'] == s['item']),
                'error': errors.get(s['item'])} for s in config.load()['sources']]
    if owngames.dirs():
        mine = [e for e in items if e.get('own')]
        sources.insert(0, {'item': owngames.ITEM, 'label': owngames.LABEL, 'count': len(mine),
                           'size': sum(e['size'] for e in mine), 'error': errors.get(owngames.ITEM), 'own': True})
    return {'entries': items, 'sources': sources, 'xna': xna_info, 'own_dirs': owngames.dirs()}


@app.post('/api/xna/scan')
def xna_scan():
    """Procura os jogos XNA nos itens de XBLA (sem descarregar: o início de cada pacote)."""
    for j in manager.active(kind='xna'):
        return _job(j)
    return _job(manager.submit('xna', 'Find XNA games in the catalog', lambda job: xna.scan(job),
                               lane='quick'))


@app.get('/api/search')
def search(q: str, xbox: bool = True):
    try:
        return {'results': catalog.search(q, xbox_only=xbox)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, 'the Internet Archive search failed: %s' % e)


@app.get('/api/item/{item}')
def get_item(item: str):
    try:
        data = catalog.item_games(item)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))
    for f in data['files']:
        p = _download_path(item, f['name'])
        have = os.path.getsize(p) if os.path.exists(p) else 0
        f['downloaded'] = 'sim' if have == f['size'] else ('parcial' if have else None)
    return data


def _submit_pipeline(title, source=None, work=None, steps=None, after_deck=None):
    slug = catalog.slug(source) if source else os.path.basename(work)

    def fn(job):
        res = pipeline.run(job, source=source, work=work, steps=steps)
        if after_deck:
            _submit_deck(res['work'], **after_deck)
        return res
    with _submit_lock:
        for j in manager.active(kind='pipeline', game=slug):
            raise HTTPException(409, 'there is already a job for %s (%s)' % (slug, j.id))
        return manager.submit('pipeline', title, fn, lane='build', game=slug,
                              params={'source': source, 'work': work, 'steps': steps})


@app.post('/api/download')
def start_download(body: dict = Body(...)):
    if xna.is_xna_name(body['name']) and not body.get('force'):
        raise HTTPException(400, xna.UNSUPPORTED_PT)
    try:
        return _job(_submit_download(body['item'], body['name'], then=body.get('then')))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except OSError as e:
        raise HTTPException(507, str(e))


def _submit_download(item, name, then=None):
    """A tarefa de download (a que já estiver a correr para o mesmo ficheiro, se houver)."""
    f = catalog.find_file(item, name)
    if not f:
        raise LookupError('file not found in the item')
    dest = _download_path(item, name)
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    free = pipeline.free_gb(config.load()['download_dir'])
    if (f['size'] - have) / 1e9 + 1 > free:
        raise OSError('Not enough space on %s: %.1f GB free, %.1f GB still to download' % (
            config.load()['download_dir'], free, (f['size'] - have) / 1e9))
    title, _ = catalog.parse_name(name)

    def fn(job):
        job.progress = jobs.with_rate(lambda: {
            'done': os.path.getsize(dest) if os.path.exists(dest) else 0, 'total': f['size']})
        job.event('step', 'Downloading %s (%.2f GB) to %s' % (name, f['size'] / 1e9, dest))
        rc = job.run([config.python_exe(), '-u', '-m', 'gestor.worker', 'download', item, name,
                      dest, str(f['size']), f.get('md5') or ''], cwd=config.ROOT,
                     env=config.tool_env())
        if rc != 0:
            raise RuntimeError('the download failed: %s' % jobs.tail(job.log_path, 3).splitlines()[-1:])
        job.event('ok', 'Downloaded and verified (MD5)')
        if then == 'prepare':
            pj = _submit_pipeline(title, source=dest)
            job.event('info', 'Preparation queued: job %s' % pj.id, job=pj.id)
        return {'path': dest}
    with _submit_lock:
        for j in manager.active(kind='download'):
            if j.params.get('item') == item and j.params.get('name') == name:
                return j
        return manager.submit('download', 'Download: %s' % title, fn, lane='download',
                              game=catalog.slug(name), params={'item': item, 'name': name, 'then': then})


@app.get('/api/downloads')
def list_downloads():
    root = config.load()['download_dir']
    out = []
    if os.path.isdir(root):
        for item in sorted(os.listdir(root)):
            d = os.path.join(root, item)
            if not os.path.isdir(d):
                continue
            for n in sorted(os.listdir(d)):
                p = os.path.join(d, n)
                if os.path.isfile(p):
                    out.append({'item': item, 'name': n, 'path': p, 'size': os.path.getsize(p),
                                'slug': catalog.slug(n), 'prepared': bool(games.find(catalog.slug(n)))})
    return {'dir': root, 'files': out, 'free_gb': pipeline.free_gb(root)}


@app.post('/api/downloads/delete')
def delete_download(body: dict = Body(...)):
    """Apaga um arquivo descarregado (só por ação do utilizador, depois de confirmar)."""
    root = os.path.abspath(config.load()['download_dir'])
    p = os.path.abspath(body['path'])
    if not p.startswith(root + os.sep) or not os.path.isfile(p):
        raise HTTPException(400, 'only files in the downloads folder')
    if body.get('confirm') != os.path.basename(p):
        raise HTTPException(400, 'the confirmation is missing')
    os.remove(p)
    return {'deleted': p}


# -- espaço no disco e compatibilidade (as páginas do PC) ------------------------------------------
DISK_PARTS = {'game-data': 'game', 'archive': 'archive', 'title-update': 'game', 'build': 'build',
              'generated': 'build', 'run': 'run'}


def _tree_size(path):
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def disk_scan_job(job):
    """Mede cada pasta de jogo, por partes: o jogo (game-data, title-update), a cópia do arquivo
    (archive), a compilação (build, generated), o run (o executável e os registos) e o resto."""
    gs = games.scan()
    for i, g in enumerate(gs):
        job.check()
        job.progress = {'done': i, 'total': len(gs), 'phase': g.get('title')}
        parts = {'game': 0, 'archive': 0, 'build': 0, 'run': 0, 'other': 0}
        try:
            with os.scandir(g['work']) as it:
                for e in it:
                    key = DISK_PARTS.get(e.name, 'other')
                    try:
                        parts[key] += _tree_size(e.path) if e.is_dir(follow_symlinks=False) else e.stat().st_size
                    except OSError:
                        pass
        except OSError:
            continue
        state.update('disk', g['slug'], dict(parts, total=sum(parts.values()), at=time.time()))
    job.event('ok', 'Measured %d game folder(s)' % len(gs))
    return {'games': len(gs)}


@app.post('/api/disk/scan')
def disk_scan():
    with _submit_lock:
        for j in manager.active(kind='disk-scan'):
            return _job(j)
        return _job(manager.submit('disk-scan', 'Measure the game folders', disk_scan_job, lane='quick'))


@app.get('/api/disk')
def disk_state():
    """O espaço: cada jogo por partes (a última medição), os arquivos descarregados e o livre em cada disco."""
    idx = deck.index()
    measured = state.get('disk') or {}
    work = []
    for g in games.scan(idx):
        m = measured.get(g['slug']) or {}
        work.append({'slug': g['slug'], 'title': g.get('title'), 'work': g.get('work'), 'built': g.get('built'),
                     'on_deck': g['slug'] in idx, **{k: m.get(k) for k in ('game', 'archive', 'build', 'run', 'other', 'total', 'at')}})
    dl = list_downloads()
    drives = {}
    for p in list(config.load()['work_roots']) + [config.load()['download_dir']]:
        d = os.path.splitdrive(os.path.abspath(p))[0] + os.sep
        if d not in drives:
            try:
                u = shutil.disk_usage(d)
                drives[d] = {'drive': d, 'free': u.free, 'total': u.total}
            except OSError:
                pass
    return {'work': work, 'downloads': dl, 'drives': list(drives.values())}


@app.post('/api/downloads/delete-prepared')
def delete_prepared(body: dict = Body(...)):
    """Apaga os arquivos descarregados dos jogos já preparados (o jogo extraído fica na pasta do
    jogo; preparar outra vez pede o arquivo de novo). Só com a confirmação do número de ficheiros."""
    files = [f for f in list_downloads()['files'] if f['prepared']]
    if body.get('confirm') != len(files):
        raise HTTPException(400, 'the confirmation is missing (%d file(s))' % len(files))
    root = os.path.abspath(config.load()['download_dir'])
    freed, done = 0, []
    for f in files:
        p = os.path.abspath(f['path'])
        if p.startswith(root + os.sep) and os.path.isfile(p):
            try:
                os.remove(p)
                freed += f['size']
                done.append(f['name'])
            except OSError:
                pass
    return {'deleted': done, 'freed': freed}


@app.get('/api/sdk')
def sdk_state(fetch: bool = False):
    """O SDK do ReXGlue: a versão instalada, as nossas alterações, o que o oficial tem de novo e as
    últimas publicações no GitHub."""
    return sdk.status(fetch=fetch)


@app.post('/api/sdk/update')
def sdk_update():
    """Traz o oficial, põe as nossas alterações por cima e compila o SDK (na pista das compilações)."""
    with _submit_lock:
        for j in manager.active(kind='sdk-update'):
            return _job(j)
        return _job(manager.submit('sdk-update', 'Update the ReXGlue SDK', sdk.update_job, lane='build'))


@app.get('/api/compat')
def compat():
    """A tabela de compatibilidade: os jogos do PC com os testes e o que o ReXNative afina."""
    rows = remote_pc()['games']
    for r in rows:
        w = games.find(r['slug'])
        lay = None
        if w:
            try:
                with open(os.path.join(w, 'layer', 'layer.json'), encoding='utf-8') as f:
                    lay = json.load(f)
            except (OSError, ValueError):
                pass
        d3d = ((lay or {}).get('target') or {}).get('d3d') or []
        r['xdk'] = d3d[1] if len(d3d) > 1 else None
    return {'games': rows}


@app.post('/api/prepare')
def prepare_local(body: dict = Body(...)):
    """Prepara um jogo que já está no disco: um arquivo descarregado, ou um jogo teu (um dump numa
    pasta, um .iso, um .7z/.zip/.rar, um pacote do Xbox Live)."""
    kind, title, src = owngames.kind_of((body.get('path') or '').strip().strip('"'))
    if not kind:
        raise HTTPException(400, 'Cannot prepare that: %s' % title)
    return _job(_submit_pipeline(title, source=src))


# -- os teus jogos (owngames.py) -----------------------------------------------------------------
@app.get('/api/own/pick')
def own_pick(what: str = 'file'):
    """A janela do Windows para escolher um ficheiro ou uma pasta (só nesta máquina)."""
    return {'path': owngames.pick('folder' if what == 'folder' else 'file')}


@app.post('/api/own/check')
def own_check(body: dict = Body(...)):
    kind, title, path = owngames.kind_of((body.get('path') or '').strip().strip('"'))
    return {'ok': bool(kind), 'kind': kind, 'what': owngames.KINDS.get(kind), 'title': title if kind else None,
            'why': None if kind else title, 'path': path}


@app.post('/api/own/dirs')
def own_dirs_add(body: dict = Body(...)):
    """Junta uma pasta às tuas pastas de jogos (os jogos lá dentro passam a estar no catálogo)."""
    p = os.path.abspath((body.get('path') or '').strip().strip('"'))
    if not os.path.isdir(p):
        raise HTTPException(400, 'not a folder: %s' % p)
    cur = owngames.dirs()
    if os.path.normcase(p) not in {os.path.normcase(d) for d in cur}:
        config.save({'own_dirs': cur + [p]})
    _cat_cache['data'] = None
    found = [e for e in owngames.scan(max_age=0) if os.path.normcase(e['path']).startswith(os.path.normcase(p))]
    return {'dirs': owngames.dirs(), 'found': len(found)}


# -- jogos ---------------------------------------------------------------------------------------
@app.get('/api/games')
def list_games():
    idx = deck.index()
    gs = games.scan(idx)
    for g in gs:
        if g.get('work') and xna.is_xna_work(g['work']):
            g['unsupported'] = 'XNA'
        act = manager.active(game=g['slug'])
        g['active_job'] = act[0].id if act else None
        g['info'] = info.compact(g.get('title') or g['slug'])
        g['fresh'] = _fresh(g)
    return {'games': gs, 'roots': config.load()['work_roots']}


def _fresh(g):
    if not g.get('built_at') or not g.get('work'):
        return None
    try:
        return freshness.status(g['work'], g['built_at'])
    except Exception as e:  # noqa: BLE001 - sem git ou sem rede: não se sabe
        return {'state': '?', 'error': str(e)}


@app.post('/api/rebuild')
def rebuild(body: dict = Body(default={})):
    """Recompila (compilar e testar) os jogos pedidos, ou os desatualizados (only_deck: só os que
    estão no Deck); os que estão no Deck são reenviados no fim."""
    return {'jobs': _rebuild(body.get('slugs'), bool(body.get('only_deck')))}


def _rebuild(slugs=None, only_deck=False):
    idx = deck.index()
    out = []
    for g in games.scan(idx):
        if slugs is not None and g['slug'] not in slugs:
            continue
        if not g.get('built') or xna.is_xna_work(g['work']):
            continue
        if slugs is None:
            f = _fresh(g) or {}
            if f.get('state') != 'desatualizado' or (only_deck and g['slug'] not in idx):
                continue
        after = {'action': 'resend', 'steam': False, 'wait': True} if g['slug'] in idx else None
        try:
            j = _submit_pipeline(g['title'], work=g['work'], steps=['build', 'boot'] + (['deckpc'] if after else []),
                                 after_deck=after)
        except HTTPException as e:  # já há uma tarefa para o jogo
            out.append({'slug': g['slug'], 'error': e.detail})
            continue
        out.append({'slug': g['slug'], 'job': j.id, 'deck': bool(after)})
    return out


@app.get('/api/games/{slug}')
def game_detail(slug: str):
    w = _work(slug)
    g = games.info(w, deck.index())
    files = games.settings_files(w)
    g['settings'] = {k: {'path': p, 'text': games.read_text(p), 'exists': os.path.exists(p)}
                     for k, p in files.items()}
    g['jobs'] = [j.to_dict(with_events=False) for j in manager.list(game=slug, limit=15)]
    g['info'] = info.find(g['title'])
    g['contrib'] = contributions(slug, w)
    g['fresh'] = _fresh(g)
    g['tunings'] = tunings.read(w)
    g['linux'] = linuxbuild.status(w)
    if xna.is_xna_work(w):
        g['unsupported'] = 'XNA'
        g['unsupported_why'] = xna.UNSUPPORTED_PT
    return g


# -- jogar ---------------------------------------------------------------------------------------
def _exe_running(exe):
    """O jogo já está aberto neste PC? (pelo nome do executável, que é o do projeto)"""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % os.path.basename(exe), '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, timeout=10, creationflags=jobs.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.basename(exe).lower() in out.lower()


def _pads():
    """Quantos comandos o Windows vê ligados a este PC (a API de joysticks do winmm: Xbox, PlayStation,
    genéricos), ou None se não se souber."""
    try:
        import ctypes
        from ctypes import wintypes

        class JOYINFOEX(ctypes.Structure):
            _fields_ = [(n, wintypes.DWORD) for n in (
                'dwSize', 'dwFlags', 'dwXpos', 'dwYpos', 'dwZpos', 'dwRpos', 'dwUpos', 'dwVpos', 'dwButtons',
                'dwButtonNumber', 'dwPOV', 'dwReserved1', 'dwReserved2')]
        winmm = ctypes.windll.winmm
        info = JOYINFOEX()
        info.dwSize = ctypes.sizeof(JOYINFOEX)
        info.dwFlags = 0xFF  # JOY_RETURNALL
        return sum(1 for i in range(min(int(winmm.joyGetNumDevs()), 16))
                   if winmm.joyGetPosEx(i, ctypes.byref(info)) == 0)
    except (OSError, AttributeError, ValueError):
        return None


def _keyboard_flag(toml_path):
    """O teclado como comando (hid.mnk_mode do ReXGlue, desligado de origem): sem ele, um PC sem
    comando ligado não tinha controlos nenhuns. Junta-se ao comando no jogador 1 (não lhe tira o
    lugar). Fica o que o .toml do jogo disser, se disser."""
    try:
        import tomllib
        with open(toml_path, 'rb') as f:
            if 'mnk_mode' in (tomllib.load(f).get('hid') or {}):
                return []
    except (OSError, ValueError):
        pass
    return ['--hid.mnk_mode=true']


@app.post('/api/games/{slug}/play')
def game_play(slug: str, body: dict = Body(default={})):
    """Jogar: where = 'pc' (o executável compilado, neste PC, com as definições do PC) ou 'deck' (o
    atalho do Steam do Deck, como o Jogar do Modo Deck)."""
    w = _work(slug)
    g = games.info(w, deck.index())
    if body.get('where') == 'deck':
        sc = (g.get('deck') or {}).get('shortcut') or {}
        if not sc.get('appid'):
            raise HTTPException(400, 'it is not in the Deck\'s Steam library yet')
        for j in manager.active(kind='deck-play'):
            return _job(j)
        return _job(manager.submit('deck-play', 'Play on the Deck: %s' % g['title'],
                                   lambda job: deck.play_job(job, sc['appid'], sc.get('name') or g['title']),
                                   lane='deck', game=slug))
    if not g.get('built') or not g.get('exe'):
        raise HTTPException(400, 'build it first')
    for j in manager.active(game=slug):
        if j.kind == 'pipeline':
            raise HTTPException(409, 'the PC is building or testing this game now (job %s): play when it ends' % j.id)
    exe = os.path.join(w, 'run', g['exe'] + '.exe')
    pads = _pads()
    if _exe_running(exe):
        return {'ok': True, 'already': True, 'title': g['title'], 'pads': pads}
    keys = _keyboard_flag(os.path.splitext(exe)[0] + '.toml')
    # Um processo à parte, no seu grupo: fica aberto se a app fechar. Com o ficheiro de controlo e a
    # pasta dos traces, para gravar cenas de teste enquanto se joga (Save this scene).
    p = subprocess.Popen([exe] + keys + scenes.live_flags(os.path.dirname(exe)), cwd=os.path.dirname(exe),
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    threading.Thread(target=_after_play, args=(p, w, slug, g['title']), daemon=True).start()
    return {'ok': True, 'already': False, 'title': g['title'], 'pads': pads, 'keyboard': bool(keys)}


def _after_play(p, w, slug, title):
    """Quando o jogo fecha, as cenas gravadas a jogar ganham as imagens de referência (desenhadas pela
    compilação com que foram gravadas: a de agora)."""
    p.wait()
    if scenes.pending_refs(slug):
        manager.submit('scenes', 'Scene pictures: %s' % title, lambda job: _scene_refs_job(job, w, slug),
                       lane='build', game=slug)


def _scene_refs_job(job, w, slug):
    made = 0
    for m in scenes.pending_refs(slug):
        job.event('step', 'Reference pictures of "%s" (a window opens for a few seconds)' % m['label'])
        try:
            scenes.make_refs(job, w, slug, m['id'])
            made += 1
            job.event('ok', '"%s": ready; it is checked after every ReXNative change' % m['label'])
        except scenes.SceneError as e:
            job.event('fail', '"%s": %s' % (m['label'], e))
    return {'made': made}


def _scene_or_404(slug, sid):
    m = scenes.load(slug, sid)
    if not m:
        raise HTTPException(404, 'unknown scene')
    return m


@app.get('/api/games/{slug}/scenes')
def game_scenes(slug: str):
    w = _work(slug)
    name = games.exe_name(w)
    running = bool(name) and _exe_running(os.path.join(w, 'run', name + '.exe'))
    busy = any(j.kind in ('scenes', 'pipeline') for j in manager.active(game=slug))
    return {'running': running, 'busy': busy, 'rex': scenes.build_rex(w),
            'scenes': [scenes.view(m) for m in scenes.scenes(slug)][::-1],
            'check': state.get('games', state.game_key(w), {}).get('scenes_check')}


@app.post('/api/games/{slug}/scenes/record')
def game_scene_record(slug: str, body: dict = Body(default={})):
    """Grava os próximos frames do jogo que está a correr (aberto com Play on this PC) como cena."""
    w = _work(slug)
    name = games.exe_name(w)
    if not name or not _exe_running(os.path.join(w, 'run', name + '.exe')):
        raise HTTPException(409, 'start the game with Play on this PC first, then go where you want to keep')
    try:
        trace = scenes.record_live(os.path.join(w, 'run'))
    except scenes.SceneError as e:
        raise HTTPException(409, '%s (a game opened before this version of the Manager cannot record: '
                                 'close it and press Play again)' % e)
    label = (body.get('label') or '').strip() or 'Your scene, %s' % jobs.now()[:16].replace('T', ' ')
    return scenes.view(scenes.add(w, slug, trace, 'play', label))


@app.post('/api/games/{slug}/scenes/check')
def game_scenes_check(slug: str):
    w = _work(slug)
    name = games.exe_name(w)
    if name and _exe_running(os.path.join(w, 'run', name + '.exe')):
        raise HTTPException(409, 'close the game first: the scenes are drawn by its executable')
    for j in manager.active(game=slug):
        if j.kind in ('scenes', 'pipeline'):
            return _job(j)
    title = games.info(w)['title']

    def fn(job):
        r = scenes.check_all(job, w, slug)
        out = {'at': jobs.now(), 'rex': scenes.build_rex(w), 'checked': r['checked'], 'worse': r['worse'],
               'better': r['better'], 'changed': r['changed'], 'job': job.id}
        state.update('games', state.game_key(w), {'scenes_check': out})
        return out
    return _job(manager.submit('scenes', 'Check the test scenes: %s' % title, fn, lane='build', game=slug))


@app.post('/api/scenes/{slug}/{sid}/{what}')
def scene_action(slug: str, sid: str, what: str, body: dict = Body(default={})):
    _scene_or_404(slug, sid)
    try:
        if what == 'accept':
            return scenes.view(scenes.accept(slug, sid))
        if what == 'undo':
            return scenes.view(scenes.undo_accept(slug, sid))
        if what == 'label':
            m = scenes.load(slug, sid)
            m['label'] = (body.get('label') or m['label']).strip()[:200]
            scenes.save(m)
            return scenes.view(m)
        if what == 'delete':
            scenes.delete(slug, sid)
            return {'ok': True}
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    raise HTTPException(404)


@app.get('/api/scenes/{slug}/{sid}/img/{which}')
def scene_image(slug: str, sid: str, which: str):
    m = _scene_or_404(slug, sid)
    d = scenes.scene_dir(slug, sid)
    if which == 'sheet':
        p = (m.get('last') or {}).get('sheet')
    elif which in ('ref', 'new', 'ref-prev'):
        imgs = scenes._pngs(os.path.join(d, which))
        p = imgs[len(imgs) // 2] if imgs else None
    else:
        p = None
    if not p or not os.path.exists(p) or not os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(d)):
        raise HTTPException(404)
    return FileResponse(p, headers={'Cache-Control': 'no-cache'})


@app.post('/api/games/{slug}/pipeline')
def game_pipeline(slug: str, body: dict = Body(default={})):
    w = _work(slug)
    steps = body.get('steps') or ['build', 'boot']
    bad = [s for s in steps if s not in pipeline.STEPS]
    if bad:
        raise HTTPException(400, 'unknown steps: %s' % bad)
    source = None
    if 'prepare' in steps:
        prep = games._read_json(os.path.join(w, 'prepare.json'))
        source = prep.get('source')
        if not source or not os.path.exists(source):
            raise HTTPException(400, 'the original archive (%s) no longer exists: only a build is possible' % source)
    title = games.info(w)['title']
    after = body.get('deck')
    j = _submit_pipeline(title, source=source, work=None if source else w, steps=steps,
                         after_deck=after)
    return _job(j)


@app.put('/api/games/{slug}/settings')
def save_settings(slug: str, body: dict = Body(...)):
    w = _work(slug)
    files = games.settings_files(w)
    which = body.get('which')
    if which not in files:
        raise HTTPException(400, 'unknown file: %s' % which)
    path = files[which]
    if 'values' in body:
        text = games.apply_values(games.read_text(path), body['values'])
    else:
        text = body.get('text', '')
    err = games.validate_toml(text)
    if err:
        raise HTTPException(400, 'invalid TOML: %s' % err)
    games.write_text(path, text)
    return {'path': path, 'text': games.read_text(path)}


@app.get('/api/games/{slug}/art/{name}')
def art(slug: str, name: str):
    p = os.path.join(_work(slug), 'deck', 'art', os.path.basename(name))
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p, headers={'Cache-Control': 'no-cache'})


@app.get('/api/games/{slug}/shot')
def shot(slug: str):
    p = os.path.join(config.data_dir('shots'), os.path.basename(slug) + '.png')
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p, headers={'Cache-Control': 'no-cache'})


# -- relatórios e o renderizador ----------------------------------------------------------------
@app.get('/api/games/{slug}/captures')
def game_captures(slug: str):
    w = _work(slug)
    out = []
    for p in reversed(covers.captures(w)):
        src = ('boot test' if os.path.dirname(p) == config.data_dir('shots') else
               'Deck' if os.sep + 'deck' + os.sep in p else 'PC (live.ps1)')
        out.append({'path': p, 'name': os.path.basename(p), 'source': src,
                    'at': os.path.getmtime(p)})
    return {'captures': out}


@app.get('/api/games/{slug}/capture')
def game_capture(slug: str, path: str):
    w = _work(slug)
    if path not in covers.captures(w):
        raise HTTPException(404)
    return FileResponse(path)


REPORT_KINDS = ['Graphics on the native renderer', 'Graphics on the classic renderer', 'Crashes or freezes',
                'Slow / FPS', 'Sound', 'Controls', 'Other']


@app.get('/api/games/{slug}/reports')
def game_reports(slug: str):
    w = _work(slug)
    key = state.game_key(w)
    reps = [dict(r, id=i) for i, r in (state.get('reports') or {}).items() if r.get('work') == key]
    return {'reports': sorted(reps, key=lambda r: r.get('at') or '', reverse=True), 'kinds': REPORT_KINDS}


@app.post('/api/games/{slug}/report')
def game_report(slug: str, body: dict = Body(...)):
    """Guarda o relatório e, se pedido, o Claude (modelo forte) investiga-o e corrige o que puder."""
    w = _work(slug)
    text = (body.get('text') or '').strip()
    if not text:
        raise HTTPException(400, 'describe the problem')
    allowed = set(covers.captures(w))
    caps = [c for c in body.get('captures') or [] if c in allowed]
    rid = '%s-%s' % (slug, jobs.now().replace(':', '').replace('-', ''))
    state.update('reports', rid, {'work': state.game_key(w), 'slug': slug, 'at': jobs.now(),
                                  'kind': body.get('kind') or 'Other', 'where': body.get('where') or 'PC',
                                  'text': text, 'captures': caps,
                                  'status': 'queued' if body.get('fix', True) else 'saved'})
    if not body.get('fix', True):
        return {'report': rid}
    title = games.info(w)['title']
    j = manager.submit('report', 'Report: %s' % title,
                       lambda job: pipeline.report_job(job, w, rid), lane='build', game=slug,
                       params={'report': rid})
    state.update('reports', rid, {'job': j.id})
    return dict(_job(j), report=rid)


@app.post('/api/games/{slug}/renderer')
def game_renderer(slug: str, body: dict = Body(...)):
    """Renderizador clássico (o do ReXGlue, com o HUD) ou nativo, no PC ou no Deck."""
    w = _work(slug)
    files = games.settings_files(w)
    which = body.get('where')
    if which not in files:
        raise HTTPException(400, 'where: pc or deck')
    path = files[which]
    text = games.apply_values(games.read_text(path), {'rexnative.classic': True if body.get('classic') else None})
    games.write_text(path, text)
    return {'path': path, 'text': text}


# -- capas ---------------------------------------------------------------------------------------
@app.get('/api/games/{slug}/covers')
def get_covers(slug: str):
    return covers.candidates(_work(slug))


@app.post('/api/games/{slug}/covers/fetch')
def fetch_covers(slug: str):
    w = _work(slug)

    def fn(job):
        job.event('step', 'Looking for covers (XboxUnity, Marketplace%s)' % (
            ', SteamGridDB' if config.load().get('steamgriddb_key') else ''))
        c = covers.fetch(w, log=lambda s: job.event('info', s))
        job.event('ok', '%d covers, %d backgrounds' % (len(c['portrait']), len(c['background'])))
    return _job(manager.submit('covers', 'Covers: %s' % slug, fn, lane='quick', game=slug))


@app.post('/api/games/{slug}/covers/auto')
def auto_covers(slug: str):
    """O modelo barato escolhe capa e fundo (e procura-as antes, se preciso) e compõe a arte."""
    w = _work(slug)

    def fn(job):
        job.event('step', 'The cheap model (%s) picks the cover and the background' % (
            config.load().get('claude_cheap_model') or 'haiku'))
        r = covers.auto_pick(w, log=lambda s: job.event('info', s))
        job.event('ok', 'Artwork made: %s' % ', '.join(r['art']), cost=r.get('cost'))
        return r
    return _job(manager.submit('covers', 'Automatic covers: %s' % slug, fn, lane='quick', game=slug))


@app.post('/api/games/{slug}/covers/compose')
def compose_covers(slug: str, body: dict = Body(...)):
    w = _work(slug)
    try:
        made = covers.compose(w, body['portrait'], body.get('background') or 'blur', body.get('logo'))
    except (OSError, ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    return {'art': made}


@app.get('/api/games/{slug}/covers/img/{path:path}')
def cover_img(slug: str, path: str):
    d = os.path.abspath(covers.cache_dir(slug))
    p = os.path.abspath(os.path.join(d, path))
    if not p.startswith(d + os.sep) or not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p)


# -- Steam Deck ----------------------------------------------------------------------------------
def _submit_deck(work, action='install', root=None, try_seconds=None, force_settings=False,
                 steam=None, wait=False):
    slug = os.path.basename(work)
    cfg = config.load()
    if action == 'install':
        steam = True if steam is None else steam
        try_seconds = cfg['deck_try_seconds'] if try_seconds is None else try_seconds
    else:  # reenviar: só os ficheiros que mudaram; sem fechar o Steam salvo se pedirem
        steam = bool(steam)
        try_seconds = try_seconds or 0
    if root is None:
        where = (deck.index().get(slug) or {}).get('where')
        root = 'sd' if where == 'sd' else None
    title = ('Install to the Deck: %s' if action == 'install' else 'Resend to the Deck: %s') % slug
    return manager.submit('deck', title, lambda job: deck.install_job(
        job, work, root=root, steam=steam, try_seconds=try_seconds, force_settings=force_settings,
        wait=wait), lane='deck', game=slug, params={'action': action, 'root': root})


@app.post('/api/games/{slug}/deck')
def game_deck(slug: str, body: dict = Body(default={})):
    w = _work(slug)
    if not games.info(w)['built']:
        raise HTTPException(400, 'the game is not built')
    j = _submit_deck(w, action=body.get('action', 'install'), root=body.get('root') or None,
                     try_seconds=body.get('try'), force_settings=bool(body.get('force_settings')),
                     steam=body.get('steam'))
    return _job(j)


@app.get('/api/deck')
def deck_status(refresh: bool = False):
    try:
        return deck.status(refresh=refresh)
    except Exception as e:  # noqa: BLE001
        return dict(deck.status(refresh=False), reachable=False, error=str(e))


@app.get('/api/deck/connection')
def deck_connection():
    cfg = config.load()
    return {'host': cfg['deck_host'], 'key': cfg['deck_key'], 'profiles': cfg.get('deck_profiles') or [],
            'watch': watcher.state, 'setup': connection.setup_state(),
            'public_key': connection.public_key(cfg['deck_key']), 'pc_ips': connection.local_ipv4s()}


@app.post('/api/deck/test')
def deck_test(body: dict = Body(default={})):
    r = connection.diagnose(body.get('host') or None, body.get('key'))
    watcher.check_now()
    return r


@app.post('/api/deck/discover')
def deck_discover():
    return connection.discover()


@app.post('/api/deck/use')
def deck_use(body: dict = Body(...)):
    """Passa a usar esta ligação (e guarda-a nos perfis com o nome dado)."""
    cfg = config.load()
    host = body['host'].strip()
    key = body.get('key', cfg['deck_key'])
    profiles = [p for p in (cfg.get('deck_profiles') or []) if p.get('host') != host]
    name = (body.get('name') or '').strip()
    if name:
        profiles = [p for p in profiles if p.get('name') != name]
        profiles.append({'name': name, 'host': host, 'key': key})
    config.save({'deck_host': host, 'deck_key': key, 'deck_profiles': profiles})
    watcher.check_now()
    return deck_connection()


@app.post('/api/deck/profiles/delete')
def deck_profile_delete(body: dict = Body(...)):
    cfg = config.load()
    profiles = [p for p in (cfg.get('deck_profiles') or []) if p.get('name') != body['name']]
    config.save({'deck_profiles': profiles})
    return deck_connection()


@app.post('/api/deck/trust')
def deck_trust(body: dict = Body(...)):
    return connection.trust(body['host'], forget_old=bool(body.get('forget_old')))


@app.post('/api/deck/setup')
def deck_setup(body: dict = Body(default={})):
    if body.get('action') == 'stop':
        connection.stop_setup()
        return connection.setup_state()
    try:
        return connection.start_setup(int(body.get('minutes') or 15))
    except (OSError, RuntimeError) as e:
        raise HTTPException(400, 'could not serve the script: %s' % e)


@app.get('/api/deck/backups')
def deck_backups(slug: str = None):
    return {'backups': deck.backups(slug), 'dir': config.data_dir('backups')}


@app.post('/api/deck/restore')
def deck_restore(body: dict = Body(...)):
    return _job(_submit_restore(body['slug'], body['file']))


def _submit_restore(slug, file, from_deck=False):
    for j in manager.active(kind='deck-restore', game=slug):
        raise HTTPException(409, 'a restore of this game is already running (%s)' % j.id)
    params = {'slug': slug, 'file': file}
    if from_deck:
        params['from_deck'] = True
    return manager.submit('deck-restore', 'Restore a backup on the Deck: %s' % slug,
                          lambda job: deck.restore_job(job, slug, file), lane='deck', game=slug,
                          params=params)


@app.post('/api/deck/delete-many')
def deck_delete_many(body: dict = Body(...)):
    slugs = [x for x in body.get('slugs') or [] if x]
    if not slugs:
        raise HTTPException(400, 'no game chosen')
    if body.get('confirm') != len(slugs):
        raise HTTPException(400, 'the confirmation is missing')
    j = manager.submit('deck-delete', 'Delete from the Deck: %d game(s)' % len(slugs),
                       lambda job: deck.delete_many_job(job, slugs, backup=bool(body.get('backup', True))),
                       lane='deck', params={'slugs': slugs, 'backup': body.get('backup', True)})
    return _job(j)


@app.post('/api/deck/delete')
def deck_delete(body: dict = Body(...)):
    slug = body['slug']
    if body.get('confirm') != slug:
        raise HTTPException(400, 'the confirmation is missing (the game folder name)')
    j = manager.submit('deck-delete', 'Delete from the Deck: %s' % slug,
                       lambda job: deck.delete_job(job, slug, backup=bool(body.get('backup', True))),
                       lane='deck', game=slug, params={'slug': slug, 'backup': body.get('backup', True)})
    return _job(j)


# -- tarefas -------------------------------------------------------------------------------------
@app.get('/api/jobs')
def list_jobs(game: str = None):
    return {'jobs': [j.to_dict(with_events=False) for j in manager.list(game=game, limit=150)]}


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404)
    return j.to_dict()


@app.get('/api/jobs/{job_id}/log')
def job_log(job_id: str, offset: int = 0, step: str = None):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404)
    path = j.log_path
    if step:  # o registo de um passo (prepare-1, boot-2...)
        cand = os.path.join(config.data_dir('logs'), '%s-%s.log' % (j.id, os.path.basename(step)))
        if os.path.exists(cand):
            path = cand
    text, new = jobs.read_log(path, offset)
    return {'text': text, 'offset': new}


@app.get('/api/jobs/{job_id}/steps')
def job_steps(job_id: str):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404)
    import glob
    out = []
    for p in sorted(glob.glob(os.path.join(config.data_dir('logs'), j.id + '-*'))):
        out.append({'name': os.path.basename(p)[len(j.id) + 1:].rsplit('.', 1)[0],
                    'size': os.path.getsize(p)})
    return {'steps': out}


@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id: str):
    return {'cancelled': manager.cancel(job_id)}


# -- definições ----------------------------------------------------------------------------------
@app.get('/api/config')
def get_config():
    cfg = config.load()
    cfg['_claude_exe'] = config.claude_exe()
    cfg['_config_path'] = config.CONFIG_PATH
    return cfg


@app.put('/api/config')
def put_config(body: dict = Body(...)):
    return config.save({k: v for k, v in body.items() if not k.startswith('_')})


@app.get('/api/claude/check')
def claude_check():
    return claude.check()


@app.post('/api/claude/selftest')
def claude_selftest():
    """Prova o ciclo de correção sem tocar no ReXNative (pipeline.selftest)."""
    return _job(manager.submit('pipeline', 'Self-test of the Claude fix loop', pipeline.selftest,
                               lane='quick', game='selftest'))


def contributions(slug, work):
    """O que o jogo levou ao ReXNative: cada correção do Claude (automática ou de um relatório)
    com os seus commits (só os dele: os que diz que fez, ou os que mencionou no resumo, nas
    correções antigas), o que mudou para todos os jogos, e o que ficou só na pasta do jogo."""
    url = rexrepo.origin_url()
    key = state.game_key(work)
    entries = []
    for j in manager.list(game=slug, limit=200):
        for f in (j.result or {}).get('claude') or []:
            if f.get('step') == 'report':
                continue  # os relatórios vêm abaixo, com o texto do utilizador
            entries.append(dict(f, at=j.started or j.created, job=j.id,
                                source='automatic fix (%s)' % f.get('step')))
    for rid, r in (state.get('reports') or {}).items():
        if r.get('work') == key and (r.get('summary') or r.get('commits')):
            entries.append(dict(r, source='report: %s' % r.get('kind'), report=rid))
    out = []
    norm = lambda p: os.path.normcase(os.path.abspath(p))  # noqa: E731
    wk = norm(work)
    for e in entries:
        summary = e.get('summary') or ''
        commits = e.get('commits') or []
        if not e.get('rex_note') and 'claimed' not in e:  # correções de antes: os que o resumo nomeia
            named = [c for c in commits if c.split(' ', 1)[0][:7] in summary]
            commits = named or commits
        edited = e.get('edited') or []
        game_files = [os.path.relpath(p, work) for p in edited if norm(p).startswith(wk + os.sep)]
        rex_files = [p for p in edited if not norm(p).startswith(wk + os.sep)]
        out.append({'at': e.get('at'), 'source': e.get('source'), 'job': e.get('job'),
                    'report': e.get('report'), 'note': e.get('rex_note'),
                    'summary': summary, 'pushed': e.get('pushed'),
                    'commits': [{'hash': c.split(' ', 1)[0], 'subject': c.split(' ', 1)[-1],
                                 'url': '%s/commit/%s' % (url, c.split(' ', 1)[0]) if url else None}
                                for c in commits],
                    'rex_files': len(rex_files), 'game_files': game_files})
    out.sort(key=lambda x: x['at'] or '', reverse=True)
    n = sum(len(x['commits']) for x in out)
    return {'entries': out, 'commits': n, 'fixes': len(out)}


@app.get('/api/rexnative')
def rexnative_status(fetch: bool = False):
    return rexrepo.status(fetch=fetch)


@app.post('/api/rexnative/sync')
def rexnative_sync():
    return _job(manager.submit('sync', 'Update the ReXNative worktree', lambda job: rexrepo.sync(job),
                               lane='build'))


@app.post('/api/test-batch')
def test_batch(body: dict = Body(...)):
    """Compila, testa e compara vários jogos, um de cada vez (os suspeitos de uma mudança)."""
    slugs = [x for x in body.get('slugs') or [] if games.find(x)]
    if not slugs:
        raise HTTPException(400, 'no games')
    reason = body.get('reason') or ''
    return _job(manager.submit('batch', 'Test %d game(s)%s' % (len(slugs), (': ' + body['label']) if body.get('label') else ''),
                               lambda job: pipeline.batch_job(job, slugs, reason), lane='build',
                               params={'slugs': slugs, 'reason': reason}))


@app.get('/api/info')
def info_status():
    return info.status()


@app.post('/api/info/refresh')
def info_refresh():
    def fn(job):
        job.event('step', 'Reading genre, year and Metacritic scores (Wikidata and Wikipedia)')
        info.refresh(log=lambda s: job.event('info', s))
        st = info.status()
        job.event('ok', '%d games, %d with a genre, %d with a Metacritic score' % (
            st['games'], st['with_genre'], st['with_mc']))
    return _job(manager.submit('info', 'Game info (Wikidata, Wikipedia)', fn, lane='quick'))


@app.get('/api/overview')
def overview():
    cfg = config.load()
    disks = {}
    for k in ('download_dir', 'work_dir'):
        try:
            disks[k] = {'path': cfg[k], 'free_gb': round(pipeline.free_gb(cfg[k]), 1)}
        except OSError:
            disks[k] = {'path': cfg[k], 'free_gb': None}
    last = deck.status(refresh=False)
    return {'disks': disks, 'active': [j.to_dict(with_events=False) for j in manager.active()],
            'deck': {'at': last.get('at'), 'watch': watcher.state, 'setup': connection.setup_state()}}


# -- Modo Deck: a rede de casa, os aparelhos, o Gestor no Deck --------------------------------------
servers = lan.Servers(app)

orders.Hooks.manager = manager
orders.Hooks.submit_download = staticmethod(lambda item, name: _submit_download(item, name))
orders.Hooks.submit_pipeline = staticmethod(lambda title, source=None, work=None, steps=None:
                                            _submit_pipeline(title, source=source, work=work, steps=steps))
orders.Hooks.submit_deck = staticmethod(lambda work, wait=True, root=None: _submit_deck(
    work, action='install', try_seconds=0, steam=True, wait=wait, root=root))

# Sessões do Gestor no Deck: a página manda sinal de vida; quando se cala (o Steam fechou o
# Gestor sem passar pelo Sair) e há atalhos à espera, a biblioteca é atualizada.
_session = {'beat': 0.0, 'open': False}


def _submit_flush(reason):
    with _submit_lock:
        for j in manager.active(kind='deck-flush'):
            return j
        p = deck.pending()
        if not p['add'] and not p['remove']:
            return None
        return manager.submit('deck-flush', 'Deck library: pending shortcuts (%s)' % reason,
                              lambda job: deck.flush_job(job), lane='deck')


def _session_watch():
    while True:
        time.sleep(15)
        try:
            if _session['open'] and time.time() - _session['beat'] > 45:
                _session['open'] = False
                _submit_flush('the Manager closed')
                _submit_play()
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=_session_watch, daemon=True).start()


@app.get('/api/ping')
def ping():
    # Para a página de arranque do Deck (file://), que procura o PC: nada mais do que isto.
    return JSONResponse({'app': 'gestor-rexnative', 'v': deckapp.VERSION},
                        headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'})


def _cookie(resp, token):
    resp.set_cookie(lan.COOKIE, token, max_age=10 * 365 * 86400, httponly=True, samesite='strict',
                    path='/')
    return resp


@app.post('/api/pair/session')
def pair_session(request: Request, body: dict = Body(...)):
    """O token que o lançador do Deck traz no fragmento passa a cookie."""
    client = request.client.host if request.client else ''
    dev = lan.check(body.get('token'), client)
    if not dev:
        raise HTTPException(401, 'unknown token: install the Manager on the Deck again')
    return _cookie(JSONResponse({'device': dev['name']}), body['token'])


@app.post('/api/pair/claim')
def pair_claim(request: Request, body: dict = Body(...)):
    """Emparelhar com o código que a app do PC mostra (Definições > Modo Deck)."""
    client = request.client.host if request.client else ''
    token = lan.claim(body.get('code', ''), (body.get('name') or '')[:40] or None, client)
    if not token:
        raise HTTPException(403, 'wrong or expired code')
    return _cookie(JSONResponse({'ok': True}), token)


@app.get('/api/pair/state')
def pair_state(request: Request):
    token = request.cookies.get(lan.COOKIE)
    client = request.client.host if request.client else ''
    local = lan.is_loopback(client)
    dev = lan.check(token, client) if token else None
    return {'paired': bool(dev) or local, 'device': dev and dev['name'], 'local': local}


# A página do Modo Deck
@app.get('/deck')
def deck_page():
    static = os.path.join(HERE, 'static')
    html = open(os.path.join(static, 'deck.html'), encoding='utf-8').read()
    for name in ('deck.js', 'deck.css'):
        v = int(os.path.getmtime(os.path.join(static, name)))
        html = html.replace('/static/%s"' % name, '/static/%s?v=%d"' % (name, v))
    return HTMLResponse(html, headers={'Cache-Control': 'no-cache'})


def _from_deck(j):
    """Marca uma tarefa pedida a partir do Deck: aparece nos Pedidos do Modo Deck."""
    if j is not None and isinstance(j.params, dict):
        j.params['from_deck'] = True
    return j


_names = {}


def _game_name(slug):
    """O nome do jogo para mostrar (o atalho do Steam, o título do PC), em vez da pasta."""
    if not slug:
        return None
    if slug not in _names:
        sc = (deck.index().get(slug) or {}).get('shortcut') or {}
        name = sc.get('name')
        if not name:
            w = games.find(slug)
            name = games.info(w).get('title') if w else None
        _names[slug] = name or slug
    return _names[slug]


def _orders_list(limit=40):
    out = []
    for j in manager.list(limit=400):
        if j.kind not in ('order', 'deck-report', 'deck-batch') and not (j.params or {}).get('from_deck'):
            continue
        d = j.to_dict(with_events=False)
        evs = [e for e in j.events if e['kind'] in ('ok', 'fail', 'info')]
        out.append({k: d.get(k) for k in ('id', 'title', 'status', 'status_pt', 'created', 'started',
                                         'ended', 'error', 'progress', 'game', 'waiting')} |
                   {'stage': (d.get('result') or {}).get('stage'), 'slug': (d.get('result') or {}).get('slug'),
                    'key': (j.params or {}).get('key'), 'last': evs[-1]['text'] if evs else None,
                    'cover': (j.params or {}).get('title'), 'kind': j.kind,
                    'name': d.get('title') if j.kind == 'order' else (
                        _game_name(j.game or ((j.params or {}).get('slugs') or [None])[0])
                        if j.game or len((j.params or {}).get('slugs') or []) == 1 else d.get('title')),
                    'report': _report_brief((j.params or {}).get('report'))})
        if len(out) >= limit:
            break
    return out


def _report_brief(rid):
    if not rid:
        return None
    r = state.get('reports', rid) or {}
    return {'status': r.get('status'), 'summary': (r.get('summary') or '')[:600], 'text': r.get('text'),
            'commits': r.get('commits'), 'slug': r.get('slug')}


def _deck_view(d):
    """Os jogos do Deck para o Modo Deck (com o que o PC sabe deles)."""
    local = {g['slug']: g for g in games.scan(deck.index())}
    p = deck.pending()
    gid = deck.gestor_appid()
    out = []
    for g in d.get('games', []):
        loc = local.get(g['slug']) or {}
        built = loc.get('built_at')
        sc = g.get('shortcut')
        act = manager.active(game=g['slug'])
        fr = _fresh(loc) if loc else None
        out.append({
            'fresh': {k: (fr or {}).get(k) for k in ('state', 'missing_count', 'sdk_changed')} if fr else None,
            'slug': g['slug'], 'title': (sc or {}).get('name') or loc.get('title') or g['slug'],
            'size': g.get('size'), 'where': g.get('where'), 'last_played': g.get('last_played'),
            'saves': len(g.get('saves') or []), 'in_library': bool(sc) and str(sc.get('appid')) not in p['remove'],
            'pending_add': g['slug'] in p['add'], 'complete': g.get('complete', True),
            'update': bool(built and g.get('mtime') and built > g['mtime'] + 120),
            'art': 'portrait' in (loc.get('art') or []), 'on_pc': bool(loc), 'mtime': g.get('mtime'),
            'appid': (sc or {}).get('appid'), 'linux': bool(g.get('linux')), 'runner': g.get('runner') or 'windows',
            'job': act[0].id if act else None, 'gestor': bool(sc and sc.get('appid') == gid)})
    return out


def _is_deck_client(request):
    """A página do Gestor aberta no Deck (pela rede): uma /deck aberta neste PC, para ver ou
    testar, não é o Gestor aberto no Deck e não deve adiar os atalhos."""
    client = request.client.host if request.client else ''
    return bool(client) and not lan.is_loopback(client)


@app.get('/api/remote/home')
def remote_home(request: Request, refresh: bool = False, beat: bool = True, plugin: str = None):
    # beat: a página do Gestor (o plugin do menu rápido pergunta com beat=false: não é o Gestor
    # aberto, e não deve atrasar a atualização da biblioteca quando o Gestor fecha). plugin: a
    # versão do plugin do Decky que pergunta.
    if plugin:
        versions.seen_plugin(plugin)
    if beat and _is_deck_client(request):
        _session.update(beat=time.time(), open=True)
    try:
        d = deck.status(refresh=refresh)
    except Exception as e:  # noqa: BLE001
        d = dict(deck.status(refresh=False), reachable=False, error=str(e))
    sp = (d.get('space') or {})
    gid = deck.gestor_appid()
    playing = d.get('playing') and d.get('playing_appid') != gid
    p = deck.pending()
    try:
        pc_free = round(pipeline.free_gb(config.load()['download_dir']), 1)
    except OSError:
        pc_free = None
    return {'pc': lan.pc_name(), 'pc_free_gb': pc_free, 'gestor_appid': gid, 'version': versions.RUNNING,
            'linux_enabled': linuxbuild.cfg_ok()[0],
            'plugin_latest': versions.plugin_latest(), 'gestor_open': bool(_session.get('open')),
            # O PC chega ao Deck por SSH? (o vigia, de 20 em 20 s): sem isso, instalar espera.
            'ssh': watcher.state.get('online'),
            'deck': {'reachable': d.get('reachable', False), 'at': d.get('at'), 'space': sp,
                     'sd': d.get('sd'), 'playing': bool(playing),
                     'playing_title': d.get('playing_title') if playing else None},
            'games': [g for g in _deck_view(d) if not g['gestor']], 'orders': _orders_list(),
            'pending': {'add': len(p['add']), 'remove': len(p['remove']),
                        'titles': [a['title'] for a in p['add'].values()]}}


@app.post('/api/remote/heartbeat')
def remote_heartbeat(request: Request, body: dict = Body(default={})):
    if _is_deck_client(request):
        _session.update(beat=time.time(), open=True,
                        diag={k: body.get(k) for k in ('pads', 'pad_last', 'key_last', 'ua')})
    return {'ok': True}


@app.post('/api/remote/closed')
def remote_closed():
    """O Gestor no Deck fechou (o Sair da página, ou o lançador depois do Firefox)."""
    _session.update(open=False)
    j = _submit_flush('the Manager closed')
    p = _submit_play()
    return {'flush': j and j.id, 'play': p and p.id}


@app.post('/api/remote/play/{slug}')
def remote_play(slug: str):
    """Jogar a partir do Gestor: o Gestor fecha (a página sai a seguir) e, quando já fechou, o PC
    arranca o jogo pelo Steam do Deck (com o Gestor aberto o Steam pedia para o fechar primeiro)."""
    sc = (deck.index().get(slug) or {}).get('shortcut') or {}
    if not sc.get('appid'):
        raise HTTPException(400, 'this game has no Steam shortcut yet: it joins the library when you exit the Manager')
    _session['play'] = {'slug': slug, 'appid': sc['appid'], 'title': sc.get('name') or slug, 'at': time.time()}
    return {'ok': True}


def _submit_play():
    p = _session.pop('play', None)
    if not p or time.time() - p['at'] > 300:
        return None
    return manager.submit('deck-play', 'Play on the Deck: %s' % p['title'],
                          lambda job: deck.play_job(job, p['appid'], p['title']), lane='deck', game=p['slug'])


_cat_cache = {'at': 0, 'data': None}


@app.get('/api/remote/catalog')
def remote_catalog(since: str = None):
    """O catálogo agrupado por jogo (uma entrada por título, a melhor região)."""
    if _cat_cache['data'] is not None and time.time() - _cat_cache['at'] < 60:
        data = _cat_cache['data']
    else:
        items, _ = catalog.entries()
        xna_seen = xna.load()
        find_local = games.local_lookup(deck.index())
        order = {'USA': 0, 'World': 0, 'Europe': 1, 'PAL': 1, 'EUR': 1, 'UK': 2}
        groups = {}
        for e in items:
            if (xna_seen.get(e['name']) or {}).get('xna'):
                continue
            # Um jogo teu ganha a qualquer região de uma fonte: não há nada para descarregar.
            rank = -1 if e.get('own') else min([order.get(t, 5) for t in e['tags']] or [3])
            cur = groups.get(e['key'])
            if cur is None or rank < cur[0]:
                groups[e['key']] = (rank, e)
        data = []
        for key, (_, e) in groups.items():
            g = find_local(e)
            inf = info.compact(e['title']) or {}
            data.append({'key': key, 'title': e['title'], 'item': e['item'], 'name': e['name'],
                         'size': e['size'], 'source': e['source'],
                         'xbla': 'xbla' in e['item'].lower() or e.get('kind') == 'package',
                         'own': owngames.KINDS.get(e.get('kind')) if e.get('own') else None,
                         'genres': inf.get('genres') or [], 'year': inf.get('year'), 'mc': inf.get('mc'),
                         'local': g and g['slug'], 'built': bool(g and g.get('built')),
                         'art': bool(g and 'portrait' in (g.get('art') or []))})
        data.sort(key=lambda x: catalog.words(x['title']))
        _cat_cache.update(at=time.time(), data=data)
        catcovers.prefetch([x['title'] for x in data])
    on_deck = set(deck.index())
    active = {}
    for j in manager.active(kind='order'):
        active[(j.params or {}).get('key')] = j.id
    out = [dict(x, on_deck=bool(x['local'] and x['local'] in on_deck), order=active.get(x['key']))
           for x in data]
    # A página do Deck pede de novo de minuto a minuto: com a assinatura do que já tem, só recebe
    # o catálogo se mudou (eram 590 KB e 2000 capas desenhadas outra vez).
    text = json.dumps({'games': out}, ensure_ascii=False, separators=(',', ':'))
    sig = hashlib.md5(text.encode('utf-8')).hexdigest()[:16]
    if since and since == sig:
        return JSONResponse({'same': True, 'sig': sig})
    return Response(text[:-1] + ',"sig":"%s"}' % sig, media_type='application/json')


@app.get('/api/remote/cover')
def remote_cover(t: str, slug: str = None, a: int = 0):
    """A capa de um jogo: a arte da biblioteca, se já estiver preparado no PC; senão a do
    XboxUnity (procurada pelo nome na primeira vez); sem nenhuma, uma capa genérica ao estilo das
    caixas da Xbox 360 com o nome do jogo (a: 1 num jogo do Xbox Live Arcade), por pouco tempo em
    cache, para a verdadeira a substituir quando aparecer."""
    if slug:
        w = games.find(slug)
        if w:
            pth = os.path.join(w, 'deck', 'art', 'portrait.png')
            if os.path.isfile(pth):
                return FileResponse(pth, headers={'Cache-Control': 'max-age=600'})
    pth = catcovers.path(t)
    if pth:
        return FileResponse(pth, headers={'Cache-Control': 'max-age=86400'})
    xbla = bool(a) or bool(slug and '-xbla' in slug)
    try:
        return FileResponse(catcovers.placeholder(t, xbla), headers={'Cache-Control': 'max-age=600'})
    except Exception:  # noqa: BLE001 - sem capa nenhuma: a página mostra o nome
        raise HTTPException(404)


@app.post('/api/remote/order')
def remote_order(body: dict = Body(...)):
    item, name = body.get('item'), body.get('name')
    if not item or not name:
        raise HTTPException(400, 'no game given')
    if item != owngames.ITEM and xna.is_xna_name(name):
        raise HTTPException(400, xna.UNSUPPORTED_PT)
    e = orders.entry_for(item, name)
    if not e:
        raise HTTPException(404, 'that file is no longer in your folders' if item == owngames.ITEM
                            else 'that file is no longer in the archive')
    # Onde fica no Deck: 'sd' (o cartão microSD, se houver) ou o armazenamento interno.
    e = dict(e, root='sd' if body.get('root') == 'sd' else None)
    with _submit_lock:
        for j in manager.active(kind='order'):
            if (j.params or {}).get('key') == e['key']:
                return _job(j)
        j = manager.submit('order', e['title'], lambda job: orders.order_job(job, orders.Hooks, e),
                           lane='orders', game=e['slug'], params=e)
    return _job(j)


# Repor uma cópia das gravações a partir do Deck (as cópias que o apagar fez, no PC).
@app.get('/api/remote/backups/{slug}')
def remote_backups(slug: str):
    _work(slug)
    return {'backups': [{k: b.get(k) for k in ('file', 'at', 'size', 'entries', 'saves')}
                        for b in deck.backups(slug)][:10]}


@app.post('/api/remote/restore/{slug}')
def remote_restore(slug: str, body: dict = Body(...)):
    _work(slug)
    file = body.get('file') or ''
    if not any(b['file'] == file for b in deck.backups(slug)):
        raise HTTPException(404, 'that backup is not on the PC')
    return _job(_submit_restore(slug, file, from_deck=True))


@app.post('/api/remote/order/{job_id}/cancel')
def remote_order_cancel(job_id: str):
    j = manager.get(job_id)
    if not j or not _remote_visible(j):
        raise HTTPException(404)
    return {'cancelled': manager.cancel(job_id)}


@app.post('/api/remote/order/{job_id}/retry')
def remote_order_retry(job_id: str):
    j = manager.get(job_id)
    if not j or j.kind != 'order':
        raise HTTPException(404)
    return remote_order({'item': j.params['item'], 'name': j.params['name']})


def _remote_visible(j):
    return j.kind in ('order', 'deck-report', 'deck', 'deck-delete', 'deck-flush', 'deck-restore', 'deck-plugin',
                      'deck-batch', 'linux-deck', 'linux-runner') or \
        bool((j.params or {}).get('from_deck'))


# -- a conversa com o assistente: ver o que faz e escrever-lhe (Modo Deck e app do PC) --------------
CHAT_KINDS = ('claude', 'claude-text', 'claude-tool', 'claude-user')


def _assistant_job(j):
    """A tarefa onde corre (ou correu) a sessão do assistente: a própria, ou uma que ela seguiu (um
    pedido do Deck segue o relatório ou o pipeline). A mais recente com conversa."""
    cands = [j] + [manager.get(e['job']) for e in j.events if e.get('job')]
    if (j.result or {}).get('sub'):
        cands.append(manager.get(j.result['sub']))
    found = None
    for c in cands:
        if c is not None and (c._say is not None or any(e.get('kind') in CHAT_KINDS for e in c.events)):
            found = c if c._say is not None or found is None or found._say is None else found
    return found


def _chat_view(j):
    aj = _assistant_job(j)
    ag = agents.name()
    who = 'Claude' if ag == 'claude' else agents.NAMES.get(ag, ag)
    if aj is None:
        return {'job': None, 'live': False, 'who': who, 'messages': [], 'status': None}
    msgs = [{'t': e.get('t'), 'kind': e['kind'], 'text': e.get('text') or '', 'final': bool(e.get('final'))}
            for e in aj.events if e.get('kind') in CHAT_KINDS]
    return {'job': aj.id, 'live': aj._say is not None, 'who': who, 'messages': msgs[-150:], 'status': aj.status}


def _chat_say(j, body):
    text = (body.get('text') or '').strip()[:2000]
    if not text:
        raise HTTPException(400, 'write something first')
    aj = _assistant_job(j)
    say = aj._say if aj is not None else None  # a sessão pode fechar entretanto: a mesma função
    if say is None:
        raise HTTPException(409, 'the assistant is not working on this now')
    try:
        say(text)
    except (RuntimeError, OSError) as e:
        raise HTTPException(409, str(e))
    return _chat_view(j)


@app.get('/api/remote/chat/{job_id}')
def remote_chat(job_id: str):
    j = manager.get(job_id)
    if not j or not _remote_visible(j):
        raise HTTPException(404)
    return _chat_view(j)


@app.post('/api/remote/chat/{job_id}')
def remote_chat_say(job_id: str, body: dict = Body(...)):
    j = manager.get(job_id)
    if not j or not _remote_visible(j):
        raise HTTPException(404)
    return _chat_say(j, body)


@app.get('/api/jobs/{job_id}/chat')
def job_chat(job_id: str):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404)
    return _chat_view(j)


@app.post('/api/jobs/{job_id}/say')
def job_say(job_id: str, body: dict = Body(...)):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404)
    return _chat_say(j, body)


@app.get('/api/remote/job/{job_id}')
def remote_job(job_id: str):
    j = manager.get(job_id)
    if not j or not _remote_visible(j):
        raise HTTPException(404)
    d = j.to_dict()
    d.pop('log_path', None)
    d['events'] = d.get('events', [])[-40:]
    return d


@app.get('/api/remote/game/{slug}')
def remote_game(slug: str):
    """O cartão de um jogo do Deck: a versão que lá está e a do PC, o que a do PC traz de novo, o
    que ainda está por compilar, o histórico dos envios (cada um com o que corrigiu), os relatórios
    deste jogo e as definições do Deck."""
    import tomllib
    w = _work(slug)
    g = games.info(w, deck.index())
    last = state.get('deck', 'last') or {}
    dg = next((x for x in last.get('games', []) if x['slug'] == slug), None) or {}
    hist = (state.get('deck_versions', slug) or {}).get('history') or []
    cur = changelog.deck_version(slug, dg.get('mtime'), hist)
    pc =changelog.version_of(w, g.get('built_at')) if g.get('built_at') else None
    newer = bool(pc and cur and (pc['built_at'] or 0) > (cur['built_at'] or 0) + 120)
    fresh = _fresh(dict(g, work=w)) or {}
    # O que cada versão corrigiu fica guardado no histórico (changelog.record_send); os envios de
    # antes disso são calculados uma vez aqui e guardados também.
    hist = changelog.fill_changes(slug, hist)
    history = [dict(v, changes=v.get('changes') or []) for v in hist]
    reports = []
    for rid, r in sorted((state.get('reports') or {}).items(), key=lambda kv: kv[1].get('at') or '', reverse=True):
        if r.get('slug') == slug:
            reports.append({'at': r.get('at'), 'status': r.get('status'), 'text': r.get('text'),
                            'where': r.get('where'), 'summary': (r.get('summary') or '')[:900]})
        if len(reports) >= 4:
            break
    try:
        dt = tomllib.loads(games.read_text(games.settings_files(w)['deck']))
    except (tomllib.TOMLDecodeError, OSError):
        dt = {}
    rx = dt.get('rexnative') or {}
    inf = info.compact(g.get('title') or slug) or {}
    return {
        'tunings': tunings.read(w),
        'slug': slug, 'title': g.get('title'), 'info': inf, 'title_update': g.get('title_update'),
        'dlc': g.get('dlc'), 'size': dg.get('size'), 'saves': len(dg.get('saves') or []),
        'last_played': dg.get('last_played'), 'where': dg.get('where'),
        'renderer': 'Classic (ReXGlue)' if rx.get('classic') else 'Native (ReXNative)',
        'deck_settings': {k: v for k, v in rx.items() if k in ('classic', 'upscaler', 'upscaler_mode', 'menu_fps')},
        'deck_version': cur, 'pc_version': pc, 'pc_newer': newer,
        'pc_brings': changelog.pack(changelog.between(cur['time'], pc['time'])) if newer and cur and pc else [],
        'missing': changelog.pack(changelog.between(pc['time'], None)) if pc else [],
        'sdk_changed': bool(fresh.get('sdk_changed')),
        'history': list(reversed(history)), 'reports': reports}


DECK_QUICK = ['rexnative.classic', 'rexnative.upscaler', 'rexnative.upscaler_mode', 'rexnative.menu_fps']


@app.get('/api/remote/settings/{slug}')
def remote_settings(slug: str):
    import tomllib
    w = _work(slug)
    try:
        cur = tomllib.loads(games.read_text(games.settings_files(w)['deck']))
    except (tomllib.TOMLDecodeError, OSError):
        cur = {}
    out = {}
    for dotted in DECK_QUICK:
        sec, key = dotted.split('.')
        v = (cur.get(sec) or {}).get(key)
        out[dotted] = '' if v is None else (str(v).lower() if isinstance(v, bool) else str(v))
    return {'values': out}


@app.post('/api/remote/settings/{slug}')
def remote_settings_save(slug: str, body: dict = Body(...)):
    w = _work(slug)
    def typed(v):
        if v is None or v == '' or isinstance(v, (bool, int, float)):
            return v
        s = str(v).strip()
        if s.lower() in ('true', 'false'):
            return s.lower() == 'true'
        if s.lstrip('-').isdigit():
            return int(s)
        return s
    vals = {k: typed(v) for k, v in (body.get('values') or {}).items() if k in DECK_QUICK}
    path = games.settings_files(w)['deck']
    text = games.apply_values(games.read_text(path), vals)
    err = games.validate_toml(text)
    if err:
        raise HTTPException(400, 'invalid TOML: %s' % err)
    games.write_text(path, text)
    j = _from_deck(_submit_deck(w, action='resend', steam=False, force_settings=True))
    return _job(j)


# -- "On the PC" no Modo Deck: os jogos preparados neste PC -------------------------------------------
@app.get('/api/remote/pc')
def remote_pc():
    """Os jogos preparados no PC, com o que o Modo Deck mostra: compilado ou não, no Deck ou não, se
    lhe faltam correções, os testes (arranque, nativo vs clássico, definições do Deck)."""
    idx = deck.index()
    out = []
    for g in games.scan(idx):
        slug = g['slug']
        if g.get('error'):
            out.append({'slug': slug, 'title': g.get('title') or slug, 'error': str(g['error'])[:200]})
            continue
        fr = (_fresh(g) or {}) if g.get('built') else {}
        boot, cmp, dp = g.get('boot') or {}, g.get('compare') or {}, g.get('deckpc') or {}
        act = manager.active(game=slug)
        inf = info.compact(g['title']) or {}
        out.append({
            'slug': slug, 'title': g['title'], 'prepared': g.get('prepared'), 'built': bool(g.get('built')),
            'built_at': g.get('built_at'), 'on_deck': slug in idx, 'art': 'portrait' in (g.get('art') or []),
            'xna': xna.is_xna_work(g['work']), 'title_update': g.get('title_update'), 'dlc': g.get('dlc'),
            'fresh': {k: fr.get(k) for k in ('state', 'missing_count', 'sdk_changed', 'commit')} if fr else None,
            'classic': (g.get('classic') or {}).get('pc'), 'classic_deck': (g.get('classic') or {}).get('deck'),
            'boot': {'ok': boot.get('ok'), 'fps': round(1000.0 / boot['frame_ms']) if boot.get('frame_ms') else None,
                     'at': boot.get('at'), 'classic_fallback': boot.get('classic_fallback')} if boot else None,
            'compare': cmp.get('verdict'), 'deckpc': dp.get('verdict'),
            'pipeline': (g.get('pipeline') or {}).get('status'),
            'linux_built': bool(((state.get('games', state.game_key(g['work']), {}) or {}).get('linux') or {}).get('built_at')),
            'job': act[0].id if act else None,
            'genres': inf.get('genres') or [], 'year': inf.get('year'), 'mc': inf.get('mc')})
    out.sort(key=lambda x: catalog.words(x['title']))
    return {'games': out}


# -- builds para Linux (experimental) ------------------------------------------------------------
def _submit_linux(slug, what, runner=None, from_deck=False):
    w = _work(slug)
    ok, why = linuxbuild.cfg_ok()
    if not ok:
        raise HTTPException(400, why)
    title = games.info(w)['title']
    params = {'from_deck': True} if from_deck else {}
    with _submit_lock:
        for j in manager.active(game=slug):
            if j.kind.startswith('linux-'):
                return j
        if what == 'build':
            if not games.info(w).get('built'):
                raise HTTPException(400, 'build it for Windows first (the Linux build starts from the same project)')
            return manager.submit('linux-build', 'Build for Linux: %s' % title, lambda job: linuxbuild.build_job(job, w),
                                  lane='build', game=slug, params=params)
        if what == 'deck':
            return manager.submit('linux-deck', 'Linux build to the Deck: %s' % title,
                                  lambda job: linuxbuild.deck_send_job(job, w, True), lane='deck', game=slug, params=params)
        return manager.submit('linux-runner', '%s on the Deck: %s' % ('Linux' if runner == 'linux' else 'Windows', title),
                              lambda job: linuxbuild.runner_job(job, slug, runner), lane='deck', game=slug, params=params)


@app.post('/api/games/{slug}/linux/{what}')
def game_linux(slug: str, what: str, body: dict = Body(default={})):
    """Build para Linux (experimental): what = build (compilar no WSL), deck (enviar e usar no
    Deck) ou runner (body.runner: linux ou windows, o que o atalho do Steam arranca)."""
    if what not in ('build', 'deck', 'runner'):
        raise HTTPException(404)
    runner = 'linux' if body.get('runner') == 'linux' else 'windows'
    return _job(_submit_linux(slug, what, runner))


@app.post('/api/remote/linux/{slug}/{what}')
def remote_linux(slug: str, what: str, body: dict = Body(default={})):
    if what not in ('build', 'deck', 'runner'):
        raise HTTPException(404)
    runner = 'linux' if body.get('runner') == 'linux' else 'windows'
    return _job(_submit_linux(slug, what, runner, from_deck=True))


# -- o registo do ReXNative (o separador Changelog) --------------------------------------------------
@app.get('/api/rexlog')
def rex_log(refresh: bool = False):
    """Os commits do ReXNative, com a área, os jogos de que falam e as versões dos jogos de cá
    (refresh: vai ao GitHub agora)."""
    return rexlog.view(refresh)


@app.get('/api/remote/rexlog')
def remote_rexlog(refresh: bool = False):
    return rexlog.view(refresh)


@app.get('/api/remote/tunings/{slug}')
def remote_tunings(slug: str):
    """O que o ReXNative afina para este jogo (a ficha do separador On PC)."""
    return {'tunings': tunings.read(_work(slug))}


@app.post('/api/remote/install/{slug}')
def remote_install(slug: str, body: dict = Body(default={})):
    """Instalar no Deck um jogo já compilado no PC (o separador "On the PC")."""
    w = _work(slug)
    if not games.info(w).get('built'):
        raise HTTPException(400, 'not built on the PC yet: build it first')
    root = 'sd' if body.get('root') == 'sd' else None
    return _job(_from_deck(_submit_deck(w, action='install', try_seconds=0, steam=True, wait=True,
                                        root=root)))


@app.post('/api/remote/rebuild/{slug}')
def remote_rebuild(slug: str):
    w = _work(slug)
    if not games.info(w).get('built'):
        # Preparado mas sem executável (a compilação falhou ou não chegou a correr): compilar e testar.
        try:
            j = _submit_pipeline(games.info(w)['title'], work=w, steps=['build', 'boot', 'deckpc'])
        except HTTPException as e:
            raise HTTPException(409, e.detail)
        _from_deck(j)
        return {'slug': slug, 'job': j.id, 'deck': False}
    res = _rebuild([slug])
    if not res or res[0].get('error'):
        raise HTTPException(409, (res[0].get('error') if res else None) or 'could not rebuild')
    _from_deck(manager.get(res[0].get('job')))
    return res[0]


# Relatórios a partir do Deck: o que se vê (escolhas rápidas e texto), o que o Deck sabe do jogo
# (registos, definições, capturas do Steam) e, se pedido, uma captura lá; o Claude investiga no PC e,
# se corrigir, o jogo volta compilado e testado para o Deck.
REPORT_CHIPS = {
    'metade': 'Only part of the screen shows', 'preto': 'Black screen', 'cintila': 'The picture flickers or shakes',
    'transparente': 'Things are see-through or disappear', 'luz': 'Lighting or shadows missing',
    'cores': 'Wrong colors', 'texto': 'Wrong text or menus', 'lento': 'Slow (low FPS)',
    'fecha': 'Crashes or freezes', 'som': 'Sound problems', 'comandos': 'The controls do not respond'}
REPORT_KIND = {'lento': 'Slow / FPS', 'fecha': 'Crashes or freezes', 'som': 'Sound', 'comandos': 'Controls'}


def _deck_saves_to_pc(job, dk, g, w, slug, dest, rid):
    """Os saves do jogador no Deck vão para a cópia do PC, para o Claude chegar ao sítio do relatório
    (um menu que só abre com o progresso do jogo); os do PC ficam antes numa cópia."""
    if not g.get('saves'):
        job.event('info', 'The game has no saves on the Deck: Claude starts from the PC copy')
        return
    info = games.info(w)
    if info.get('exe') and _exe_running(os.path.join(w, 'run', info['exe'] + '.exe')):
        job.event('info', 'The game is open on this PC: its saves stay as they are (close it and report again '
                          'to send the Deck save)')
        return
    try:
        tar = deck.fetch_saves(job, dk, g, os.path.join(dest, 'deck-saves.tar'))
        if not tar:
            return
        put = saves.install(w, slug, tar)
    except (RuntimeError, OSError, tarfile.TarError) as e:
        job.event('info', 'The Deck save did not reach the PC: %s' % e)
        return
    put['deck'] = tar
    state.update('reports', rid, {'saves': put})
    job.event('ok', 'Your Deck save is in the PC copy, for Claude (%d files)%s' % (
        put['files'], '; the PC saves from before are in %s' % put['backup'] if put['backup'] else ''))


def deck_report_job(job, w, slug, body, rid):
    hooks = orders.Hooks
    job.progress = orders._progress(job, hooks)  # a fase do Claude, ou o que a tarefa dele espera
    dest = config.data_dir('reports', rid)
    job.result.update(stage='deck', report=rid)
    dk = deck.Deck()
    files = []
    try:
        data = dk.listing(light=True, tries=3)  # responde, o que está a correr e os jogos, numa ligação
        ok, err = True, ''
    except RuntimeError as e:
        data, ok, err = None, False, str(e)
    if ok:
        b = deck.busy_from(data.get('playing_line'))
        g = next((x for x in data['games'] if x['slug'] == slug), None)
        if g:
            g['title'] = (g.get('shortcut') or {}).get('name') or slug
            ev = deck.evidence(job, dk, g, dest)
            files += ev['logs'] + ([ev['settings']] if ev['settings'] else []) + ev['screenshots']
            if body.get('capture'):
                if b and not b['gestor']:
                    job.event('info', 'A game is open on the Deck: no capture (close it and report again to get one)')
                else:
                    try:
                        files += deck.capture(job, dk, g, dest, int(body.get('seconds') or 40))
                    except RuntimeError as e:
                        job.event('info', 'No capture: %s' % e)
            if body.get('saves', True):
                _deck_saves_to_pc(job, dk, g, w, slug, dest, rid)
        else:
            job.event('info', '%s is not on the Deck: sending only the description' % slug)
    else:
        job.event('info', 'The Deck is not responding (%s): sending only the description' % err)
    caps = [f for f in files if f.lower().endswith(('.png', '.jpg'))]
    notes = [f for f in files if f not in caps]
    state.update('reports', rid, {'captures': caps, 'deck_files': notes})
    job.result.update(stage='claude')
    sub = manager.submit('report', 'Report: %s' % games.info(w)['title'],
                         lambda j: pipeline.report_job(j, w, rid), lane='build', game=slug,
                         params={'report': rid})
    state.update('reports', rid, {'job': sub.id})
    orders._follow(job, sub, 'claude', hooks)
    rep = state.get('reports', rid) or {}
    if rep.get('commits') or rep.get('edited'):
        job.result.update(stage='deck_send')
        sub = _submit_deck(w, action='resend', steam=False, force_settings=True, wait=True)
        orders._follow(job, sub, 'deck_send', hooks)
        job.event('ok', 'The fixed version is on the Deck: try it')
        job.result.update(stage='done')
    else:
        job.result.update(stage='done')
    return {'report': rid, 'status': rep.get('status')}


@app.post('/api/remote/report/{slug}')
def remote_report(slug: str, body: dict = Body(...)):
    w = _work(slug)
    chips = [c for c in body.get('chips') or [] if c in REPORT_CHIPS]
    text = (body.get('text') or '').strip()[:2000]
    if not chips and not text:
        raise HTTPException(400, 'pick what you see or write a description')
    what = '; '.join([REPORT_CHIPS[c] for c in chips] + ([text] if text else []))
    kind = next((REPORT_KIND[c] for c in chips if c in REPORT_KIND), 'Graphics on the native renderer')
    for j in manager.active(kind='deck-report', game=slug):
        raise HTTPException(409, 'a report for this game is already running')
    renderer = (games.info(w).get('classic') or {}).get('deck')
    rid = '%s-%s' % (slug, jobs.now().replace(':', '').replace('-', ''))
    state.update('reports', rid, {
        'work': state.game_key(w), 'slug': slug, 'at': jobs.now(), 'kind': kind, 'where': 'Steam Deck',
        'text': what + ('. (On the Deck this game starts on the classic renderer.)' if renderer else ''),
        'captures': [], 'status': 'queued', 'from': 'deck'})
    j = manager.submit('deck-report', 'Report: %s' % games.info(w)['title'],
                       lambda job: deck_report_job(job, w, slug, body, rid), lane='orders', game=slug,
                       params={'report': rid, 'chips': chips, 'capture': bool(body.get('capture')),
                               'saves': bool(body.get('saves', True))})
    return _job(j)


@app.post('/api/remote/update/{slug}')
def remote_update(slug: str):
    return _job(_from_deck(_submit_update(slug, _work(slug))))


def _submit_update(slug, w, wait=False):
    last = state.get('deck', 'last') or {}
    dg = next((x for x in last.get('games', []) if x.get('slug') == slug), None) or {}
    if dg and not dg.get('shortcut'):
        # Sem atalho na biblioteca (o "Completar"): instalar põe o atalho (ou deixa-o à espera de
        # o Gestor fechar); um reenvio só copiava os ficheiros.
        return _submit_deck(w, action='install', try_seconds=0, steam=True, wait=True)
    return _submit_deck(w, action='resend', steam=False, wait=wait)


# -- tudo de uma vez: Atualizar tudo / Recompilar tudo ----------------------------------------------
# Uma só tarefa, que trata os jogos um a um: uma linha nos Pedidos e um aviso no fim (eram N tarefas e
# N avisos seguidos).
BATCH_TITLE = {'update': 'Update all on the Deck', 'rebuild': 'Rebuild all on the Deck'}


def _batch_candidates(mode):
    """[(slug, work, nome)] dos jogos do Deck: 'update' os que têm no PC uma versão mais nova ou um
    envio a meio; 'rebuild' os que não têm as correções mais recentes do ReXNative."""
    out = []
    for g in _deck_view(deck.status(refresh=False)):
        if g['gestor'] or not g['on_pc'] or g['job']:
            continue
        if mode == 'update':
            want = g['update'] or not g['complete'] or (not g['in_library'] and not g['pending_add'])
        else:
            want = (g.get('fresh') or {}).get('state') == 'desatualizado'
        w = games.find(g['slug']) if want else None
        if w:
            out.append((g['slug'], w, g['title']))
    return out


def _batch_progress(job):
    base = orders._progress(job, orders.Hooks)

    def f():
        p = base()
        r = job.result
        n, i = r.get('total') or 0, r.get('i') or 0
        p['batch'] = {'i': i, 'n': n, 'current': r.get('current'), 'done': len(r.get('ok') or []),
                      'failed': len(r.get('failed') or [])}
        if n and p.get('total') is None and p.get('pct') is not None:
            p['pct'] = 100.0 * (i + p['pct'] / 100.0) / n  # o todo, não só o jogo de agora
        return p
    return f


def deck_batch_job(job, mode, items):
    job.result.update(total=len(items), ok=[], failed=[])
    job.progress = _batch_progress(job)
    for i, (slug, w, name) in enumerate(items):
        job.check()
        job.result.update(i=i, current=name)
        try:
            if mode == 'rebuild':
                p = _submit_pipeline(name, work=w, steps=['build', 'boot', 'deckpc'])
                orders._follow(job, p, 'build', orders.Hooks)
            orders._follow(job, _submit_update(slug, w, wait=True), 'deck', orders.Hooks)
            job.result['ok'].append(name)
            job.event('ok', '%s: %s (%d of %d)' % (name, 'rebuilt and sent' if mode == 'rebuild' else 'updated',
                                                   i + 1, len(items)))
        except jobs.Cancelled:
            raise
        except HTTPException as e:
            job.result['failed'].append(name)
            job.event('fail', '%s: %s' % (name, e.detail))
        except Exception as e:  # noqa: BLE001 - um jogo que falha não pára os outros
            job.result['failed'].append(name)
            job.event('fail', '%s: %s' % (name, str(e)[:200]))
    ok, failed = job.result['ok'], job.result['failed']
    verb = 'rebuilt and sent' if mode == 'rebuild' else 'updated'
    text = '%d of %d %s' % (len(ok), len(items), verb) + (
        '; failed: %s' % ', '.join(failed) if failed else '')
    if failed and not ok:
        raise RuntimeError(text)
    job.event('ok', text)
    return {'ok': ok, 'failed': failed}


def _submit_batch(mode, from_deck=False):
    with _submit_lock:
        for j in manager.active(kind='deck-batch'):
            if (j.params or {}).get('mode') == mode:
                return j
        items = _batch_candidates(mode)
        if not items:
            raise HTTPException(400, 'every game on the Deck is up to date' if mode == 'update'
                                else 'every game on the Deck has the latest fixes')
        params = {'mode': mode, 'slugs': [x[0] for x in items]}
        if from_deck:
            params['from_deck'] = True
        return manager.submit('deck-batch', '%s: %d game(s)' % (BATCH_TITLE[mode], len(items)),
                              lambda job: deck_batch_job(job, mode, items), lane='orders', params=params)


@app.post('/api/remote/update-all')
def remote_update_all():
    return _job(_submit_batch('update', from_deck=True))


@app.post('/api/remote/rebuild-all')
def remote_rebuild_all():
    return _job(_submit_batch('rebuild', from_deck=True))


@app.post('/api/deck/update-all')
def deck_update_all():
    return _job(_submit_batch('update'))


@app.post('/api/deck/rebuild-all')
def deck_rebuild_all():
    return _job(_submit_batch('rebuild'))


@app.post('/api/remote/delete')
def remote_delete(body: dict = Body(...)):
    slugs = [x for x in body.get('slugs') or [] if x]
    if not slugs:
        raise HTTPException(400, 'no game chosen')
    j = manager.submit('deck-delete', 'Delete from the Deck: %s' % ', '.join(slugs),
                       lambda job: deck.delete_many_job(job, slugs, backup=bool(body.get('backup', True))),
                       lane='deck', params={'slugs': slugs, 'backup': body.get('backup', True), 'from_deck': True})
    return _job(j)


# Definições do Modo Deck (só nesta máquina: os caminhos não estão em REMOTE_PATHS)
def _startup_file():
    return os.path.join(os.environ.get('APPDATA', ''), r'Microsoft\Windows\Start Menu\Programs\Startup',
                        'Gestor ReXNative.cmd')


@app.get('/api/lan')
def lan_state():
    return {'servers': servers.state(), 'devices': lan.devices(), 'pairing': lan.pairing(),
            'session': dict(_session),
            'gestor': deckapp.status(), 'pending': deck.pending(), 'pc': lan.pc_name(),
            'autostart': os.path.exists(_startup_file())}


@app.post('/api/lan/enable')
def lan_enable(body: dict = Body(...)):
    config.save({'lan_enabled': bool(body.get('on'))})
    servers.refresh()
    time.sleep(2.5)
    return lan_state()


@app.post('/api/lan/pair')
def lan_pair():
    lan.start_pairing()
    return lan_state()


@app.post('/api/lan/revoke')
def lan_revoke(body: dict = Body(...)):
    lan.revoke(body.get('id'))
    return lan_state()


@app.post('/api/lan/install-deck')
def lan_install_deck():
    return _job(_submit_kit())


def _submit_kit(title='Install the Manager on the Deck', from_deck=False):
    for j in manager.active(kind='deck-gestor'):
        return j
    return manager.submit('deck-gestor', title, lambda job: deckapp.install_job(job, servers), lane='deck',
                          params={'from_deck': True} if from_deck else {})


# -- versões da app ---------------------------------------------------------------------------------
@app.get('/api/version')
def version_state(fetch: bool = False):
    """A versão a correr, a do disco e a do GitHub, o que muda, e as do lançador e do plugin no Deck."""
    return versions.status(fetch=fetch)


@app.post('/api/version/update')
def version_update():
    """Traz a versão do GitHub (git pull) e reinicia quando nenhuma tarefa estiver a correr."""
    try:
        text = versions.update()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    st = versions.status()
    if st['restart_needed']:
        r = versions.restart_when_idle(manager, 'update to %s' % st['disk'])
        if r.get('refused'):
            raise HTTPException(409, 'Updated, but not restarted: %s' % r['refused'])
    return dict(versions.status(), message=text)


@app.post('/api/version/restart')
def version_restart():
    """Reinicia a app (a versão do disco) quando nenhuma tarefa estiver a correr."""
    r = versions.restart_when_idle(manager, 'restart')
    if r.get('refused'):
        raise HTTPException(409, 'Not restarted: %s' % r['refused'])
    return versions.status()


@app.get('/api/server/log')
def server_log(lines: int = 400):
    """O fim do registo do servidor (erros, tracebacks dos fios, avisos): o que a app escreve no ecrã,
    também quando corre escondida depois de reiniciar."""
    p = os.path.join(config.data_dir(), 'logs', 'server.log')
    text = jobs.tail(p, max(20, min(int(lines), 5000)))
    return PlainTextResponse(text or '(nothing in the server log yet: it starts with version 1.14.0)')


@app.get('/api/remote/version')
def remote_version():
    st = versions.status()
    st.pop('remote_dirty', None)
    return st


def _submit_plugin(prompt=True, from_deck=False):
    with _submit_lock:
        for j in manager.active(kind='deck-plugin'):
            return j
        return manager.submit('deck-plugin', 'Decky plugin to the Deck', lambda job: deck.plugin_job(job, prompt),
                              lane='deck', params={'from_deck': True} if from_deck else {})


@app.post('/api/deck/plugin')
def deck_plugin(body: dict = Body(default={})):
    """O plugin do Decky para ~/Downloads do Deck e (prompt) a Decky pede lá para o instalar."""
    return _job(_submit_plugin(bool(body.get('prompt', True))))


@app.post('/api/remote/plugin-update')
def remote_plugin_update():
    return _job(_submit_plugin(True, from_deck=True))


@app.post('/api/remote/kit-update')
def remote_kit_update():
    """Atualiza o lançador do Gestor no Deck (só os ficheiros: o atalho já lá está)."""
    return _job(_submit_kit('Update the Manager launcher on the Deck', from_deck=True))


@app.post('/api/deck/flush')
def deck_flush():
    j = _submit_flush('requested in the app')
    if not j:
        raise HTTPException(400, 'no shortcuts are pending')
    return _job(j)


@app.post('/api/autostart')
def autostart(body: dict = Body(...)):
    """Arrancar o Gestor com o Windows (um .cmd na pasta Arranque do utilizador)."""
    f = _startup_file()
    if body.get('on'):
        with open(f, 'w', encoding='ascii', newline='') as fh:
            fh.write('@echo off\r\nrem ReXNative Manager: starts with Windows (Settings > Deck Mode)\r\n'
                     'start "" /min cmd /c ""%s" --no-browser"\r\n' % os.path.join(config.ROOT, 'iniciar.bat'))
    elif os.path.exists(f):
        os.remove(f)
    return {'autostart': os.path.exists(f)}


@app.exception_handler(Exception)
async def errors(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=500)


app.mount('/static', StaticFiles(directory=os.path.join(HERE, 'static')), name='static')


@app.get('/')
def index():
    # app.js e style.css com a sua data no endereço: depois de uma atualização o browser não usa
    # a cópia velha da cache.
    static = os.path.join(HERE, 'static')
    html = open(os.path.join(static, 'index.html'), encoding='utf-8').read()
    for name in ('app.js', 'style.css'):
        v = int(os.path.getmtime(os.path.join(static, name)))
        html = html.replace('/static/%s"' % name, '/static/%s?v=%d"' % (name, v))
    return HTMLResponse(html, headers={'Cache-Control': 'no-cache'})
