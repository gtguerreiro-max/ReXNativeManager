"""A cópia do ReXNative que só a app usa (rexnative_dir: um clone, ou uma worktree de outra cópia).

Quem trabalha noutras cópias não deve partilhar esta: numa pasta partilhada, os commits de uns
levavam as alterações de outros e as compilações apanhavam trabalho a meio. Antes de cada tarefa a
app põe esta na última versão publicada (origin/main), se não tiver nada por gravar; o assistente faz
commit aqui e publica no main (quem pode) ou a app abre um pull request (github.py). Na primeira vez,
se a pasta não existir, a app clona o ReXNative (rexnative_repo)."""
import os
import subprocess

from . import config, jobs


def _git(args, cwd, timeout=120):
    r = subprocess.run(['git', '-C', cwd] + args, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def status(fetch=False):
    d = config.load()['rexnative_dir']
    out = {'dir': d, 'exists': os.path.isdir(d)}
    if not out['exists']:
        return out
    if fetch:
        _git(['fetch', '-q', 'origin'], d, timeout=90)
    _, head, _ = _git(['log', '-1', '--format=%h %s'], d)
    _, up, _ = _git(['log', '-1', '--format=%h %s', 'origin/main'], d)
    _, dirty, _ = _git(['status', '--porcelain', '--untracked-files=no'], d)
    _, counts, _ = _git(['rev-list', '--left-right', '--count', 'HEAD...origin/main'], d)
    ahead, behind = (counts.split() + ['0', '0'])[:2]
    _, url, _ = _git(['remote', 'get-url', 'origin'], d)
    out.update(head=head, origin=up, dirty=[l for l in dirty.splitlines() if l.strip()],
               ahead=int(ahead or 0), behind=int(behind or 0), url=web_url(url))
    return out


_url = {}


def origin_url():
    """O endereço do repositório no GitHub (lido uma vez: o cartão do jogo pedia o estado todo, cinco
    comandos git, só por isto)."""
    d = config.load()['rexnative_dir']
    if d not in _url:
        _, url, _ = _git(['remote', 'get-url', 'origin'], d)
        _url[d] = web_url(url)
    return _url[d]


def web_url(remote):
    """https://github.com/dono/repo a partir do remote (https ou ssh)."""
    r = (remote or '').strip()
    if r.startswith('git@github.com:'):
        r = 'https://github.com/' + r[len('git@github.com:'):]
    return r[:-4] if r.endswith('.git') else r


# The lanes that work beside the build lane, each in a copy of ReXNative only it uses (a job there
# never sees what a fix session of another lane has half written, nor a main that changes under
# it): lane -> (the setting that turns it on, the setting with its folder, the folder's ending by
# default, the live.ps1 state folder of its assistant sessions).
LANE_COPY = {
    'report': ('report_lane', 'report_rexnative_dir', '-reports', 'rexnative-live-manager-reports'),
    'prepare': ('prepare_lane', 'prepare_rexnative_dir', '-prepare', 'rexnative-live-manager-prepare'),
}


def lane_dir(lane):
    """The copy of ReXNative of this lane, or None when the lane is off (its jobs then run in the
    build lane) or is not one with a copy."""
    spec = LANE_COPY.get(lane)
    cfg = config.stored()
    if not spec or not cfg.get(spec[0], True):
        return None
    return cfg.get(spec[1]) or (cfg['rexnative_dir'].rstrip('\\/') + spec[2])


def report_dir():
    return lane_dir('report')


def ensure_lane_dir(lane):
    """Makes the lane's copy the first time: a worktree of the app's ReXNative repository, detached
    at the published main, with the app's ports.json (not in git). Returns its folder."""
    d, base = lane_dir(lane), config.stored()['rexnative_dir']
    if not os.path.isdir(os.path.join(d, 'rexnative')):
        if not os.path.isdir(base):
            raise RuntimeError('no ReXNative copy yet (%s): build a game first' % base)
        _git(['fetch', '-q', 'origin'], base, timeout=90)
        _git(['worktree', 'prune'], base)
        rc, _, err = _git(['worktree', 'add', '--detach', d, 'origin/main'], base, timeout=600)
        if rc != 0:
            raise RuntimeError('could not make the %s lane\'s copy of ReXNative (%s): %s. Its jobs can '
                               'run in the build lane instead: Settings, "%s" off'
                               % (lane, d, err[-300:], LANE_COPY[lane][0]))
    src, dst = os.path.join(base, 'ports.json'), os.path.join(d, 'ports.json')
    try:
        if os.path.exists(src) and (not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst)):
            with open(src, 'rb') as a, open(dst, 'wb') as b:
                b.write(a.read())
    except OSError:
        pass
    return d


def ensure_report_dir():
    return ensure_lane_dir('report')


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _other_copies(d):
    """The copies of ReXNative of the other lanes (the app's own and each lane's that exists)."""
    all_ = [config.stored()['rexnative_dir']] + [lane_dir(lane) for lane in LANE_COPY]
    return [c for c in all_ if c and os.path.exists(os.path.join(c, '.git')) and not _same(c, d)]


def _take_unpublished(d, log):
    """Commits the assistant made in another lane's copy and could not publish (someone who cannot
    push to ReXNative: they wait in a pull request) come to this copy too, so every lane builds the
    same code. Nothing to do for who publishes: main has them."""
    for o in _other_copies(d):
        rc, head, _ = _git(['rev-parse', 'HEAD'], o)
        if rc != 0 or not head:
            continue
        # Commits of origin/main..<the other HEAD> with no equal change here.
        rc, out, _ = _git(['cherry', 'HEAD', head, 'origin/main'], d)
        new = [l[2:].strip() for l in out.splitlines() if l.startswith('+ ')] if rc == 0 else []
        if not new:
            continue
        rc, _, err = _git(['cherry-pick'] + new, d)
        if rc != 0:
            _git(['cherry-pick', '--abort'], d)
            log('info', 'ReXNative: %d unpublished commit(s) of the other copy (%s) do not apply here (%s)' % (
                len(new), o, err[-160:]))
        else:
            log('info', 'ReXNative: %d unpublished commit(s) of the other copy (%s) brought here' % (len(new), o))


def sync(job=None):
    """Põe a worktree na última versão publicada; nunca deita fora trabalho por gravar ou
    commits por publicar (com esses, tenta um rebase e desiste se tiver conflitos). No fim, os commits
    por publicar da cópia da outra pista vêm para esta (_take_unpublished)."""
    log = (lambda kind, text: job.event(kind, text)) if job else (lambda kind, text: print(text))
    st = _sync(log, job)
    try:
        if st.get('exists') and not st.get('dirty'):
            before = st.get('head')
            _take_unpublished(st['dir'], log)
            st = status() if before else st
    except Exception as e:  # noqa: BLE001 - never a reason to stop a job
        log('info', 'ReXNative: the other copy was not looked at (%s)' % str(e)[:160])
    return st


def _sync(log, job=None):
    d = config.load()['rexnative_dir']
    if not os.path.isdir(d):
        # A primeira vez: um clone do ReXNative só desta app.
        repo = config.load().get('rexnative_repo') or 'gtguerreiro-max/ReXNative'
        log('step', 'Cloning ReXNative (%s) into %s' % (repo, d))
        os.makedirs(os.path.dirname(d) or '.', exist_ok=True)
        r = subprocess.run(['git', 'clone', 'https://github.com/%s.git' % repo, d], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=900, creationflags=jobs.CREATE_NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError('could not clone ReXNative into %s: %s' % (d, (r.stderr or r.stdout)[-300:]))
    rc, _, err = _git(['fetch', '-q', 'origin'], d, timeout=90)
    if rc != 0:
        log('info', 'ReXNative: no access to GitHub (%s); keeping the current version' % err[-160:])
        return status()
    # O que uma tarefa anterior deixou por gravar (uma sessão do Claude cancelada ou que falhou)
    # entrava nas compilações seguintes e não deixava atualizar: fica de parte num stash, com nome.
    # Só as tarefas da app usam esta worktree, e a pista das compilações é uma só.
    _, left, _ = _git(['status', '--porcelain'], d)
    left = [x for x in left.splitlines() if x.strip()]
    if left:
        name = 'gestor: left over before %s' % (job.id if job else 'a job')
        rc, _, err = _git(['stash', 'push', '-u', '-m', name], d)
        if rc == 0:
            log('info', 'ReXNative: changes no job had committed (%s) were put aside in git stash '
                        '("%s")' % (', '.join(x[3:] for x in left[:5]), name))
        else:
            log('info', 'ReXNative: the worktree has uncommitted changes and they could not be put '
                        'aside (%s)' % err[-160:])
    st = status()
    if st['behind'] == 0:
        return st
    if st['dirty']:
        log('info', 'ReXNative: the worktree has uncommitted changes (%s): not updating it' % (
            ', '.join(x[3:] for x in st['dirty'][:5])))
        return st
    if st['ahead'] == 0:
        rc, _, err = _git(['checkout', '-q', '--detach', 'origin/main'], d)
    else:
        rc, _, err = _git(['rebase', '-q', 'origin/main'], d)
        if rc != 0:
            _git(['rebase', '--abort'], d)
    st2 = status()
    if rc == 0:
        log('info', 'ReXNative updated to %s (%d new published commit(s))' % (
            st2['head'][:80], st['behind']))
    else:
        log('info', 'ReXNative: could not update (%s); staying on %s' % (err[-200:], st2['head'][:60]))
    return st2
