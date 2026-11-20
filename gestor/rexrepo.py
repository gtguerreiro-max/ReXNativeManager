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


def sync(job=None):
    """Põe a worktree na última versão publicada; nunca deita fora trabalho por gravar ou
    commits por publicar (com esses, tenta um rebase e desiste se tiver conflitos)."""
    log = (lambda kind, text: job.event(kind, text)) if job else (lambda kind, text: print(text))
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
