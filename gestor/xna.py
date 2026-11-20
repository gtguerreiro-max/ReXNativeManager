"""Jogos XNA: o código do jogo é .NET (IL) que o .NET Compact Framework da consola compila durante
a execução (JIT); o ReXGlue só corre código recompilado antes de arrancar, por isso não os corre
(por agora). Reconhecem-se pelos ficheiros: HostLoader.dll, Runtime/<v>/NetCFUserMode.dll,
mscorlib.dll e o conteúdo .xnb.

No catálogo, sem descarregar: um RAR de XBLA traz um pacote STFS, cuja tabela de ficheiros está no
início; o archive.org dá um ficheiro de dentro do RAR, e chegam os primeiros 512 KB do pacote
(~5 s por jogo). O resultado fica em <data_dir>/catalog/xna.json, por nome e MD5."""
import concurrent.futures
import json
import os
import re
import threading
import time
import urllib.parse

from . import catalog, config, fsutil, jobs

MARKERS = (b'HostLoader.dll', b'NetCFUserMode', b'mscorlib.dll', b'.xnb')
FILES = ('hostloader.dll', 'netcfusermode.dll')
_lock = threading.Lock()


def _path():
    return os.path.join(config.data_dir('catalog'), 'xna.json')


def load():
    p = _path()
    try:
        return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    except ValueError:
        return {}


def _save(data):
    with _lock:
        fsutil.write_json(_path(), data, indent=0)


def is_xna_markers(found):
    return bool(found.get('HostLoader.dll') or found.get('NetCFUserMode'))


def probe(session, auth, item, name, nbytes=512 * 1024):
    """{'xna': bool, 'markers': {...}} de um arquivo do catálogo, sem o descarregar."""
    base = 'https://archive.org/download/%s/%s/' % (item, urllib.parse.quote(name))
    r = session.get(base, auth=auth, timeout=90)
    r.raise_for_status()
    text = r.text
    # Um disco traz os ficheiros soltos: os nomes estão na própria lista.
    low = text.lower()
    if any(f in low for f in FILES):
        return {'xna': True, 'markers': {'listing': True}}
    # <title id>/<tipo de conteúdo, 000D0000 nos XBLA>/<pacote>, no fim de cada ligação da lista.
    members = [urllib.parse.unquote(m) for m in re.findall(
        r'href="[^"]*?/([0-9A-Fa-f]{8}(?:%2F|/)[0-9A-Fa-f]{8}(?:%2F|/)[0-9A-Fa-f]{8,64})"', text)]
    found = {}
    for path in members[:2]:
        with session.get(base + urllib.parse.quote(path), auth=auth, timeout=120, stream=True) as rr:
            data = b''
            for chunk in rr.iter_content(65536):
                data += chunk
                if len(data) >= nbytes:
                    break
        for mk in MARKERS:
            if mk in data:
                found[mk.decode()] = found.get(mk.decode(), 0) + data.count(mk)
        if is_xna_markers(found):
            break
    if not members:
        raise RuntimeError('no STFS package in the archive listing')
    return {'xna': is_xna_markers(found), 'markers': found, 'packages': len(members)}


def scan(job=None, items=None, workers=6):
    """Procura os XNA nos itens (por omissão os de XBLA das fontes); só os arquivos ainda não
    vistos (ou cujo MD5 mudou)."""
    import internetarchive as ia
    entries, _ = catalog.entries()
    if items is None:
        items = [s['item'] for s in config.load()['sources'] if 'xbla' in s['item'].lower()]
    todo_all = [e for e in entries if e['item'] in items]
    data = load()
    todo = [e for e in todo_all if (data.get(e['name']) or {}).get('md5') != e['md5']]
    done = {'n': 0}
    if job is not None:
        job.progress = lambda: {'done': len(todo_all) - len(todo) + done['n'], 'total': len(todo_all)}
        job.event('step', 'Checking %d archive(s) of %d (the others were already checked)' % (len(todo), len(todo_all)))
    session = ia.get_session()
    auth = ia.auth.S3Auth(session.access_key, session.secret_key)

    def one(e):
        for attempt in range(3):
            try:
                return e, probe(session, auth, e['item'], e['name'])
            except Exception as ex:  # noqa: BLE001
                err = str(ex)
                time.sleep(3 * (attempt + 1))
        return e, {'error': err}

    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, e) for e in todo]
        for i, f in enumerate(concurrent.futures.as_completed(futs)):
            if job is not None and job._cancel.is_set():
                ex.shutdown(cancel_futures=True)
                _save(data)
                raise jobs.Cancelled()
            e, res = f.result()
            done['n'] += 1
            if 'error' not in res:
                data[e['name']] = dict(res, md5=e['md5'], item=e['item'], at=time.time())
                if res['xna'] and job is not None:
                    job.event('info', 'XNA: %s' % e['title'])
            if i % 25 == 0:
                _save(data)
    _save(data)
    n = sum(1 for e in todo_all if (data.get(e['name']) or {}).get('xna'))
    seen = sum(1 for e in todo_all if e['name'] in data)
    if job is not None:
        job.event('ok', '%d XNA games among %d checked (of %d)' % (n, seen, len(todo_all)))
    return {'xna': n, 'seen': seen, 'total': len(todo_all)}


def is_xna_name(name):
    return bool((load().get(os.path.basename(name or '')) or {}).get('xna'))


def is_xna_work(work):
    """Um jogo já preparado: os ficheiros do .NET Compact Framework na pasta do jogo."""
    data = os.path.join(work, 'game-data')
    if not os.path.isdir(data):
        return False
    if os.path.exists(os.path.join(data, 'HostLoader.dll')):
        return True
    rt = os.path.join(data, 'Runtime')
    if os.path.isdir(rt):
        for d in os.listdir(rt):
            if os.path.exists(os.path.join(rt, d, 'NetCFUserMode.dll')):
                return True
    return False


UNSUPPORTED_PT = ('XNA: the game is .NET, which the console compiles while it runs; ReXGlue only runs '
                  'code recompiled before the start (not supported, for now)')
