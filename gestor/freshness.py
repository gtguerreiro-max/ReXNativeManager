"""Cada jogo compilado tem as correções mais recentes? Compara o que a compilação diz que usou
(run/rexnative-build.json: o commit do ReXNative e o SDK instalado; o ReXNative 4b6940d em diante
escreve-o) com o main publicado e o SDK de agora. Uma compilação mais antiga, sem esse ficheiro,
compara-se pela data (uma estimativa).

Só contam as mudanças que entram no jogo compilado: o renderizador (renderer/) e o gerador do
projeto e da camada (rexnative/), não a documentação, os scripts nem o kit do Deck."""
import glob
import hashlib
import json
import os
import re
import subprocess
import threading
import time

from . import config, fsutil, jobs

STAMP = 'rexnative-build.json'
# Módulos do rexnative/ que não mexem no jogo compilado (o Deck, a arte, DLC, a linha de comandos).
NOT_BUILD = {'rexnative/deck.py', 'rexnative/art.py', 'rexnative/dlc.py', 'rexnative/title_update.py',
             'rexnative/report.py', 'rexnative/xiso.py', 'rexnative/stfs.py', 'rexnative/__main__.py',
             'rexnative/i18n.py', 'rexnative/prepare.py', 'rexnative/project.py'}
_lock = threading.Lock()
_cache = {'at': 0.0, 'commits': None, 'sdk': None, 'sdk_at': 0.0}


def relevant(path):
    if path.endswith('.md') or path in NOT_BUILD:
        return False
    return path.startswith('renderer/') or path.startswith('rexnative/')


def _git(*args, timeout=60):
    rex = config.load()['rexnative_dir']
    r = subprocess.run(['git', '-C', rex] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout,
                       creationflags=jobs.CREATE_NO_WINDOW)
    return r.stdout


def commits(max_age=300):
    """Os últimos 400 commits do origin/main (o mais novo primeiro): {sha, at, subject, files,
    build} (build: se mexe no jogo compilado). Lidos de novo de 5 em 5 minutos (com fetch), num fio
    à parte: entretanto quem pergunta recebe a lista anterior (o fetch parava a lista dos jogos e o
    Modo Deck um segundo, ou muito mais se o GitHub não respondesse)."""
    if _cache['commits'] is None:
        _load_saved()
    if _cache['commits'] is not None:
        if time.time() - _cache['at'] >= max_age and not _cache.get('refreshing'):
            _cache['refreshing'] = True
            threading.Thread(target=_refresh_quietly, daemon=True).start()
        return _cache['commits']
    return _refresh()


def _refresh_quietly():
    try:
        _refresh()
    except Exception:  # noqa: BLE001 - fica a lista anterior
        pass
    finally:
        _cache['refreshing'] = False


def _refresh():
    try:
        _git('fetch', '-q', 'origin', timeout=90)
    except (OSError, subprocess.SubprocessError):
        pass
    with _lock:
        res = log('origin/main', 400)
        _cache.update(at=time.time(), commits=res)
        if res:
            try:
                fsutil.write_json(_saved_path(), {'at': _cache['at'], 'commits': res})
            except OSError:
                pass
        return res


def log(rev, n):
    """Os commits de rev (o mais novo primeiro), até n: {sha, at, subject, body, files, build}. A
    descrição (%b) vai entre dois \\x1f: o registo do ReXNative (rexlog.py) mostra-a."""
    out = _git('log', rev, '-%d' % n, '--format=%x1e%H%x09%ct%x09%s%x1f%b%x1f', '--name-only')
    res = []
    for block in out.split('\x1e'):
        parts = block.split('\x1f')
        if len(parts) < 3 or '\t' not in parts[0]:
            continue
        sha, at, subject = parts[0].strip().split('\t', 2)
        files = [l.strip() for l in parts[2].splitlines() if l.strip()]
        res.append({'sha': sha, 'at': int(at), 'subject': subject.lstrip('﻿'), 'body': clean_body(parts[1]),
                    'files': files, 'build': any(relevant(f) for f in files)})
    return res


TRAILER = re.compile(r'^(Co-Authored-By|Signed-off-by|Reviewed-by|Change-Id):', re.I)


def clean_body(text):
    """A descrição de um commit sem as linhas de assinatura do fim."""
    lines = [l.rstrip() for l in (text or '').strip().splitlines()]
    while lines and (not lines[-1].strip() or TRAILER.match(lines[-1].strip())):
        lines.pop()
    return '\n'.join(lines).strip()


def _saved_path():
    return config.data_dir('commits.json')


def _load_saved():
    """A lista guardada da última leitura (fica como velha: é lida outra vez em segundo plano)."""
    try:
        with open(_saved_path(), encoding='utf-8') as f:
            d = json.load(f)
        if d.get('commits'):
            _cache.update(at=0.0, commits=d['commits'])
    except (OSError, ValueError):
        pass


def sdk_now():
    """A identidade do SDK instalado agora (como rexnative.project.sdk_identity)."""
    if _cache['sdk'] is not None and time.time() - _cache['sdk_at'] < 60:
        return _cache['sdk']
    sdk = config.load()['env'].get('REXNATIVE_SDK_INSTALL') or ''
    h = hashlib.sha1()
    b = os.path.join(sdk, 'bin')
    files = sorted(glob.glob(os.path.join(b, '*.dll')) + glob.glob(os.path.join(b, 'rexglue.exe')))
    newest = 0
    for f in files:
        st = os.stat(f)
        newest = max(newest, st.st_mtime)
        h.update(('%s %d %d;' % (os.path.basename(f).lower(), st.st_size, int(st.st_mtime))).encode())
    _cache.update(sdk={'id': h.hexdigest()[:16] if files else None, 'at': newest}, sdk_at=time.time())
    return _cache['sdk']


def read_stamp(work):
    try:
        with open(os.path.join(work, 'run', STAMP), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def status(work, built_at):
    """{'state': 'atual'|'desatualizado'|'?', 'exact', 'commit', 'dirty', 'missing': [...],
    'sdk_changed'} de um jogo compilado (built_at: a data do executável)."""
    if not built_at:
        return {'state': '?'}
    st = read_stamp(work)
    cs = commits()
    newer, exact, commit = None, False, None
    if st and st.get('rexnative'):
        commit = st['rexnative']
        idx = next((i for i, c in enumerate(cs) if c['sha'] == commit), None)
        if idx is not None:
            newer, exact = cs[:idx], True
        else:  # um commit que o main não tem (trabalho local de outra sessão): pela data
            newer = [c for c in cs if c['at'] > (st.get('rexnative_date') or built_at)]
    else:
        # Sem registo: as mudanças publicadas depois da compilação (pela data do commit; uma
        # compilação feita de uma cópia atrasada parece mais nova do que é).
        newer = [c for c in cs if c['at'] > built_at]
    missing = [{'sha': c['sha'][:7], 'subject': c['subject'], 'at': c['at']} for c in newer if c['build']]
    sdk = sdk_now()
    if st and st.get('sdk'):
        sdk_changed = bool(sdk['id'] and st['sdk'] != sdk['id'])
    else:
        sdk_changed = bool(sdk['at'] and sdk['at'] > built_at + 60)
    return {'state': 'desatualizado' if (missing or sdk_changed) else 'atual', 'exact': exact,
            'commit': commit[:7] if commit else None, 'dirty': bool(st and st.get('dirty')),
            'missing': missing[:30], 'missing_count': len(missing), 'sdk_changed': sdk_changed}
