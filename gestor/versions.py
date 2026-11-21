"""As versões da app: a que está a correr, a do disco (um commit novo que ainda não foi reiniciado)
e a do GitHub (origin/main da própria app); atualizar (git pull) e reiniciar quando nenhuma tarefa
estiver a correr. Também as do lançador do Deck e do plugin do Decky."""
import json
import os
import subprocess
import sys
import threading
import time

from . import config, jobs, state, version

RUNNING = version.VERSION
_remote = {'at': 0.0, 'data': None, 'busy': False, 'error': None}
_restart = {'pending': False, 'reason': None, 'at': None}


def _git(args, timeout=60):
    r = subprocess.run(['git', '-C', config.ROOT] + args, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def on_disk():
    try:
        with open(os.path.join(config.ROOT, 'gestor', 'version.py'), encoding='utf-8') as f:
            return version.parse(f.read())
    except OSError:
        return {'version': None, 'changes': []}


def _fetch_remote():
    try:
        rc, _, err = _git(['fetch', '-q', 'origin'], timeout=90)
        if rc != 0:
            raise RuntimeError(err[-200:] or 'git fetch failed')
        rc, text, err = _git(['show', 'origin/main:gestor/version.py'])
        data = version.parse(text) if rc == 0 else {'version': None, 'changes': []}
        _, counts, _ = _git(['rev-list', '--left-right', '--count', 'HEAD...origin/main'])
        ahead, behind = (counts.split() + ['0', '0'])[:2]
        _, dirty, _ = _git(['status', '--porcelain', '--untracked-files=no'])
        data.update(ahead=int(ahead or 0), behind=int(behind or 0),
                    dirty=[l[3:] for l in dirty.splitlines() if l.strip()])
        _remote.update(data=data, error=None)
    except Exception as e:  # noqa: BLE001 - sem rede: fica o que se sabia
        _remote['error'] = str(e)[:200]
    finally:
        _remote.update(at=time.time(), busy=False)


def remote(max_age=1800, wait=False):
    """A versão do GitHub (lida de 30 em 30 minutos, num fio à parte)."""
    if (_remote['data'] is None or time.time() - _remote['at'] > max_age) and not _remote['busy']:
        _remote['busy'] = True
        if wait:
            _fetch_remote()
        else:
            threading.Thread(target=_fetch_remote, daemon=True).start()
    return _remote['data']


def kit_latest():
    from . import deckapp
    return deckapp.VERSION


def plugin_latest():
    try:
        with open(os.path.join(config.ROOT, 'decky', 'package.json'), encoding='utf-8') as f:
            return json.load(f).get('version')
    except (OSError, ValueError):
        return None


def seen_plugin(v):
    """O plugin do Decky diz a sua versão quando pergunta (guardada uma vez por minuto)."""
    if not v:
        return
    cur = state.get('deck', 'plugin') or {}
    if cur.get('version') != v or time.time() - (cur.get('at') or 0) > 60:
        state.update('deck', 'plugin', {'version': str(v)[:20], 'at': time.time()})


def newer_changes(changes, than):
    return [c for c in changes or [] if version.key(c[0]) > version.key(than)]


def status(fetch=False):
    disk = on_disk()
    rem = remote(max_age=0 if fetch else 1800, wait=fetch) or {}
    kit_on = (state.get('deck', 'gestor') or {}).get('version')
    plug = state.get('deck', 'plugin') or {}
    best = max([RUNNING, disk.get('version') or RUNNING, rem.get('version') or RUNNING], key=version.key)
    changes = disk.get('changes') or version.CHANGES
    if rem.get('version') and version.key(rem['version']) > version.key(disk.get('version') or RUNNING):
        changes = rem.get('changes') or changes
    return {
        'running': RUNNING,
        'disk': disk.get('version'),
        'remote': rem.get('version'),
        'remote_behind': rem.get('behind'), 'remote_dirty': rem.get('dirty'), 'remote_error': _remote['error'],
        'remote_at': _remote['at'] or None,
        'restart_needed': bool(disk.get('version') and version.key(disk['version']) > version.key(RUNNING)),
        'update_available': bool(rem.get('behind')) and bool(rem.get('version')) and
        version.key(rem['version']) >= version.key(disk.get('version') or RUNNING),
        'latest': best,
        'changes': changes,
        'new': newer_changes(changes, RUNNING),
        'restart': dict(_restart),
        'kit': {'latest': kit_latest(), 'on_deck': kit_on,
                'outdated': bool(kit_on) and int(kit_on) < int(kit_latest())},
        'plugin': {'latest': plugin_latest(), 'on_deck': plug.get('version'), 'seen_at': plug.get('at'),
                   'outdated': bool(plug.get('version')) and bool(plugin_latest()) and
                   version.key(plug['version']) < version.key(plugin_latest())},
    }


def update():
    """git pull --ff-only da própria app (sem mudanças por gravar). Devolve o texto do git."""
    rem = remote(max_age=0, wait=True) or {}
    if rem.get('dirty'):
        raise RuntimeError('The app folder has uncommitted changes (%s): not updating' % ', '.join(rem['dirty'][:5]))
    if rem.get('ahead'):
        raise RuntimeError('The app folder has %d commit(s) not on GitHub: not updating' % rem['ahead'])
    if not rem.get('behind'):
        return 'already up to date'
    rc, out, err = _git(['pull', '-q', '--ff-only', 'origin', 'main'], timeout=180)
    if rc != 0:
        raise RuntimeError('git pull failed: %s' % (err or out)[-300:])
    _remote['at'] = 0
    return 'updated to %s' % (on_disk().get('version') or '?')


def compile_errors():
    """O primeiro erro de sintaxe nos ficheiros .py da app no disco ('ficheiro:linha: erro'), ou None."""
    import ast
    import glob
    for f in sorted(glob.glob(os.path.join(config.ROOT, 'gestor', '**', '*.py'), recursive=True)):
        try:
            with open(f, encoding='utf-8') as fh:
                ast.parse(fh.read(), f)
        except SyntaxError as e:
            return '%s:%s: %s' % (os.path.relpath(f, config.ROOT), e.lineno, e.msg)
        except (OSError, ValueError) as e:
            return '%s: %s' % (os.path.relpath(f, config.ROOT), e)
    return None


def restart_when_idle(manager, reason='update'):
    """Reinicia a app quando as tarefas que estão a correr acabarem (não se perdem a meio). As que
    estão em fila não começam: ficam em jobs.json e voltam à fila quando a app abrir
    (jobs.Manager.drain / resume); antes da 1.18 esperava-se pela fila vazia, o que com pedidos
    seguidos levava horas. Um processo à parte espera que esta saia e volta a abrir o iniciar.bat."""
    if _restart['pending']:
        return dict(_restart)
    broken = compile_errors()
    if broken:
        # Reiniciar com código que não compila deixava a app em baixo (o iniciar.bat abria e fechava):
        # fica a versão que está a correr, e diz-se onde está o erro.
        return dict(_restart, pending=False, refused='the code on disk does not compile: %s' % broken)
    _restart.update(pending=True, reason=reason, at=jobs.now())

    def wait_and_go():
        while not manager.drain():
            time.sleep(2)
        time.sleep(1)
        bat = os.path.join(config.ROOT, 'iniciar.bat')
        ps = ('Start-Sleep -Seconds 4; Start-Process -FilePath \'%s\' -ArgumentList \'--no-browser\' '
              '-WorkingDirectory \'%s\' -WindowStyle Minimized' % (bat, config.ROOT))
        # Sem janela e num grupo seu (sobrevive a esta). DETACHED_PROCESS não serve: o PowerShell sem
        # consola nem chegava a correr.
        flags = jobs.CREATE_NO_WINDOW | 0x00000200  # CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(['powershell', '-NoProfile', '-Command', ps],
                         creationflags=flags, close_fds=True)
        manager.save()
        sys.stdout.flush()
        os._exit(0)
    threading.Thread(target=wait_and_go, daemon=True).start()
    return dict(_restart)
