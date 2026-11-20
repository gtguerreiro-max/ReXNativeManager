"""O que a app sabe de cada jogo e não está nos ficheiros do jogo (o último teste de arranque, o
último pipeline, o título em cache): <data_dir>/state.json, por pasta de trabalho.

O ficheiro lido fica em memória enquanto não mudar (data de modificação e tamanho): a lista de jogos
pedia-o cinco vezes por jogo, e cada leitura eram 150 KB de JSON. Quem lê recebe uma cópia."""
import copy
import json
import os
import threading

from . import config, fsutil

_lock = threading.Lock()
_cache = {'sig': None, 'data': None}


def _path():
    return config.data_dir('state.json')


def _sig(p):
    try:
        st = os.stat(p)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _read():
    """Os dados (os de memória: não os alterar sem gravar)."""
    p = _path()
    sig = (p,) + (_sig(p) or (None,))
    if sig == _cache['sig'] and _cache['data'] is not None:
        return _cache['data']
    data = None
    if sig[1] is not None:
        try:
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = None
    if not isinstance(data, dict):
        data = {'games': {}, 'deck': {}}
    _cache.update(sig=sig, data=data)
    return data


def get(section, key=None, default=None):
    with _lock:
        sec = _read().get(section, {})
        return copy.deepcopy(sec if key is None else sec.get(key, default))


def update(section, key, values):
    """Junta values (dict) ao registo key da secção."""
    with _lock:
        data = copy.deepcopy(_read())
        sec = data.setdefault(section, {})
        cur = sec.get(key) or {}
        cur.update(values)
        sec[key] = cur
        p = _path()
        fsutil.write_json(p, data, indent=1)
        _cache.update(sig=(p,) + (_sig(p) or (None,)), data=data)
        return copy.deepcopy(cur)


def game_key(work):
    return os.path.normcase(os.path.abspath(work))
