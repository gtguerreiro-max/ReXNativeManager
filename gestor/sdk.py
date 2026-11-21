"""O SDK do ReXGlue: a versão instalada, o que há de novo e atualizá-lo.

O SDK em uso não é o zip oficial: é o fork (gtguerreiro-max/rexglue-sdk) compilado aqui, com
as nossas alterações por cima do oficial (rexglue/rexglue-sdk, o remote origin). Atualizar é
trazer o que o oficial publicou, voltar a pôr as nossas alterações por cima (rebase) e compilar com o
build-llvm20.cmd da pasta, que instala onde a app o usa (REXNATIVE_SDK_INSTALL). Antes do rebase, o
estado de agora fica num ramo backup/sdk-<data>; se o rebase tiver conflitos, desfaz-se e nada muda.
Depois de compilado, os jogos aparecem com "new SDK" (freshness) para recompilar."""
import json
import os
import re
import subprocess
import time
import urllib.request

from . import config, jobs

API = 'https://api.github.com/repos/rexglue/rexglue-sdk/releases?per_page=8'
_cache = {'at': 0.0, 'data': None}


def install_dir():
    return config.load()['env'].get('REXNATIVE_SDK_INSTALL') or ''


def source_dir():
    """A pasta das fontes: a de config (sdk_source_dir) ou a de onde a instalação vem
    (<fontes>/out/install/<nome>)."""
    d = config.load().get('sdk_source_dir')
    if d:
        return d
    inst = os.path.abspath(install_dir()) if install_dir() else ''
    parts = inst.replace('/', os.sep).split(os.sep)
    if len(parts) > 3 and parts[-3].lower() == 'out' and parts[-2].lower() == 'install':
        return os.sep.join(parts[:-3])
    return ''


def _git(args, timeout=120):
    r = subprocess.run(['git', '-C', source_dir()] + args, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def installed_version():
    """PACKAGE_VERSION do rexglueConfigVersion.cmake da instalação (ex.: 0.11.0.34)."""
    base = os.path.join(install_dir(), 'lib', 'cmake')
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith('configversion.cmake'):
                try:
                    m = re.search(r'set\(PACKAGE_VERSION "([^"]+)"\)', open(os.path.join(root, f), encoding='utf-8').read())
                except OSError:
                    m = None
                if m:
                    return m.group(1)
    return None


def _releases():
    """As últimas publicações do oficial no GitHub (de 6 em 6 horas): a estável e a noturna."""
    if _cache['data'] is not None and time.time() - _cache['at'] < 6 * 3600:
        return _cache['data']
    out = {'stable': None, 'nightly': None, 'error': None}
    try:
        req = urllib.request.Request(API, headers={'User-Agent': 'ReXNativeManager',
                                                   'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=20) as r:
            rel = json.loads(r.read().decode('utf-8', 'replace'))
        for x in rel:
            key = 'nightly' if x.get('prerelease') else 'stable'
            if out[key] is None:
                body = (x.get('body') or '').strip()
                lines = [l for l in body.splitlines() if l.strip()][:12]
                out[key] = {'tag': x.get('tag_name'), 'date': x.get('published_at'), 'url': x.get('html_url'),
                            'notes': lines}
    except (OSError, ValueError) as e:
        out['error'] = str(e)[:200]
    _cache.update(at=time.time(), data=out)
    return out


def _new_official():
    """Os commits do oficial que ainda não temos, e se mudam alguma coisa: os "Release vX" do oficial
    juntam o main à linha das publicações sem mudar nenhum ficheiro, e não são novidade para trazer."""
    _, new, _ = _git(['log', '--format=%h %s', 'HEAD..origin/main'])
    new = new.splitlines()
    if not new:
        return [], []
    rc, base, _ = _git(['merge-base', 'HEAD', 'origin/main'])
    if rc == 0 and base:
        rc, _, _ = _git(['diff', '--quiet', base, 'origin/main'])
        if rc == 0:  # a mesma árvore: só marcas de versão
            return [], new
    return new, []


def status(fetch=False):
    src = source_dir()
    st = {'install': install_dir(), 'source': src, 'version': installed_version(),
          'git': os.path.isdir(os.path.join(src, '.git')) if src else False}
    if st['git']:
        if fetch:
            _git(['fetch', '-q', 'origin'], timeout=120)
        _, st['describe'], _ = _git(['describe', '--tags'])
        _, ours, _ = _git(['log', '--format=%h %s', 'origin/main..HEAD'])
        new, marks = _new_official()
        _, dirty, _ = _git(['status', '--porcelain', '--untracked-files=no'])
        st.update(ours=ours.splitlines(), new=new[:40], new_count=len(new), release_marks=marks[:10],
                  dirty=[l[3:] for l in dirty.splitlines() if l.strip()])
    st['releases'] = _releases()
    return st


def _other_builds():
    """Compilações a correr fora desta app (ninja/cmake de outras sessões usam o mesmo SDK)."""
    try:
        import psutil
    except ImportError:
        return []
    me = os.getpid()
    out = []
    for p in psutil.process_iter(['pid', 'name']):
        try:
            if (p.info['name'] or '').lower() in ('ninja.exe', 'cmake.exe', 'clang-cl.exe', 'lld-link.exe') and \
                    not any(a.pid == me for a in p.parents()):
                out.append(p.info['pid'])
        except Exception:  # noqa: BLE001
            continue
    return out


def update_job(job):
    """Traz o oficial, põe as nossas alterações por cima e compila o SDK (a pista das compilações:
    nenhum jogo compila ao mesmo tempo)."""
    src = source_dir()
    if not src or not os.path.isdir(os.path.join(src, '.git')):
        raise RuntimeError('The SDK source folder was not found (%s): set sdk_source_dir in the settings' % src)
    before = installed_version()
    _, dirty, _ = _git(['status', '--porcelain', '--untracked-files=no'])
    if dirty.strip():
        raise RuntimeError('The SDK sources have uncommitted changes: commit or put them aside first (%s)'
                           % ', '.join(l[3:] for l in dirty.splitlines()[:5]))
    job.event('step', 'Fetching the official ReXGlue SDK')
    rc, _, err = _git(['fetch', 'origin'], timeout=300)
    if rc != 0:
        raise RuntimeError('git fetch failed: %s' % err[-200:])
    new, marks = _new_official()
    if not new:
        job.event('ok', 'Nothing new in the official SDK%s: version %s stays' % (
            ' (only release marks that change no file: %s)' % ', '.join(m.split(' ', 1)[-1] for m in marks[:4])
            if marks else '', before))
        return {'version': before, 'updated': False}
    backup = 'backup/sdk-%s' % time.strftime('%Y%m%d-%H%M%S')
    _git(['branch', backup, 'HEAD'])
    job.event('info', 'The SDK as it was is kept in the branch %s' % backup)
    job.event('step', 'Putting our %s change(s) on top of %d new official commit(s)' % (
        len(_git(['log', '--format=%h', 'origin/main..HEAD'])[1].splitlines()), len(new)))
    rc, out, err = _git(['rebase', 'origin/main'], timeout=600)
    if rc != 0:
        _, conflicts, _ = _git(['diff', '--name-only', '--diff-filter=U'])
        _git(['rebase', '--abort'])
        raise RuntimeError('Our changes conflict with the official ones in: %s. Nothing changed (the SDK '
                           'stays at %s); this needs a hand merge.' % (', '.join(conflicts.splitlines()[:8]) or '?', before))
    others = _other_builds()
    t0 = time.time()
    if others:
        job.event('info', 'Other builds are running on the PC (they use this SDK): waiting for them to finish')
    while others and time.time() - t0 < 1800:
        job.sleep(20)
        others = _other_builds()
    script = os.path.join(src, 'build-llvm20.cmd')
    if not os.path.exists(script):
        raise RuntimeError('%s not found: the sources were updated, build the SDK by hand' % script)
    job.event('step', 'Building and installing the SDK (this takes a while)')
    rc = job.run(['cmd', '/c', script], cwd=src)
    if rc != 0:
        raise RuntimeError('The SDK build failed (code %d): see %s and the job log. The sources are updated; '
                           'the branch %s has the previous state.' % (rc, os.path.join(src, 'build-llvm20.log'), backup))
    after = installed_version()
    job.event('ok', 'ReXGlue SDK %s -> %s: the games show "new SDK" and can be rebuilt' % (before, after))
    return {'version': after, 'before': before, 'updated': True, 'backup': backup}
