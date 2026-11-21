"""O GitHub de quem usa a app: a sessão é obrigatória (GitHub CLI, `gh`), dá a identidade dos commits
e diz se pode publicar no ReXNative. Quem não pode (todos menos quem mantém o ReXNative) partilha as
correções que o assistente fez num pull request: a app faz o fork na conta da pessoa, envia o ramo e
abre o pull request para o ReXNative, com o jogo, o que mudou e os testes. A pessoa fica logo com a
correção nos seus jogos; quando o pull request entra, passa a ser de todos.

A app nunca vê palavras-passe: o login é o do `gh` (um código que a pessoa escreve em github.com)."""
import os
import re
import shutil
import subprocess
import threading
import time

from . import config, jobs, state

_status = {'at': 0.0, 'data': None}
_login = {'state': 'idle', 'code': None, 'url': None, 'error': None, 'proc': None, 'started': None}
_lock = threading.Lock()


def gh_exe():
    exe = shutil.which('gh')
    if exe:
        return exe
    for p in (r'C:\Program Files\GitHub CLI\gh.exe', r'C:\Program Files (x86)\GitHub CLI\gh.exe'):
        if os.path.exists(p):
            return p
    return None


def run(args, timeout=60, cwd=None):
    exe = gh_exe()
    if not exe:
        return 127, '', 'GitHub CLI (gh) is not installed'
    r = subprocess.run([exe] + args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=timeout, cwd=cwd, creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def status(refresh=False):
    """{'installed', 'logged_in', 'login', 'id', 'name', 'repo', 'can_push'} (5 minutos em cache)."""
    if not refresh and _status['data'] is not None and time.time() - _status['at'] < 300:
        return dict(_status['data'])
    repo = config.load().get('rexnative_repo') or 'gtguerreiro-max/ReXNative'
    out = {'installed': bool(gh_exe()), 'logged_in': False, 'login': None, 'id': None, 'name': None,
           'repo': repo, 'can_push': False}
    if out['installed']:
        try:
            # A sessão é o token que o gh guarda neste PC (sem rede). Sem internet, valem os dados
            # da última verificação: a app não fica fechada por o GitHub não responder.
            rc, tok, _ = run(['auth', 'token'], timeout=20)
            if rc == 0 and tok.strip():
                rc, user, _ = run(['api', 'user', '--jq', '[.login, .id, .name] | @tsv'], timeout=30)
                if rc == 0 and user:
                    login, uid, name = (user.split('\t') + ['', '', ''])[:3]
                    out.update(logged_in=True, login=login, id=int(uid) if uid.isdigit() else None,
                               name=name or login)
                    rc, push, _ = run(['api', 'repos/%s' % repo, '--jq', '.permissions.push'], timeout=30)
                    out['can_push'] = rc == 0 and push.strip() == 'true'
                else:
                    last = state.get('github', 'user') or {}
                    if last.get('login'):
                        out.update(logged_in=True, offline=True, **{k: last.get(k) for k in ('login', 'id', 'name', 'can_push')})
        except (OSError, subprocess.SubprocessError):
            # gh did not answer in time (the PC busy, as right after the app reopens): the last
            # session known, as without internet. Taken as signed out, the whole app stayed closed
            # until the next check, five minutes later.
            last = state.get('github', 'user') or {}
            if last.get('login'):
                out.update(logged_in=True, offline=True, **{k: last.get(k) for k in ('login', 'id', 'name', 'can_push')})
    _status.update(at=time.time(), data=out)
    if out['logged_in']:
        state.update('github', 'user', {k: out[k] for k in ('login', 'id', 'name', 'can_push')})
    return dict(out)


def identity():
    """(nome, email) para os commits: o login e o email sem resposta do GitHub (nunca o email real)."""
    st = status()
    if st.get('login') and st.get('id'):
        return st['login'], '%d+%s@users.noreply.github.com' % (st['id'], st['login'])
    u = state.get('github', 'user') or {}
    if u.get('login') and u.get('id'):
        return u['login'], '%d+%s@users.noreply.github.com' % (u['id'], u['login'])
    return None, None


# -- o login (gh auth login --web: um código para escrever em github.com/login/device) -------------
CODE_RE = re.compile(r'one-time code: ([A-Z0-9]{4}-[A-Z0-9]{4})')
URL_RE = re.compile(r'(https://github\.com/login/device\S*)')


def login_state():
    d = {k: _login[k] for k in ('state', 'code', 'url', 'error', 'started')}
    return d


def login_start():
    """Começa o login do gh: devolve o código que a pessoa escreve em github.com/login/device."""
    with _lock:
        if _login['state'] == 'waiting' and _login['proc'] and _login['proc'].poll() is None:
            return login_state()
        exe = gh_exe()
        if not exe:
            _login.update(state='failed', error='Install the GitHub CLI first: winget install GitHub.cli')
            return login_state()
        p = subprocess.Popen([exe, 'auth', 'login', '--hostname', 'github.com', '--git-protocol', 'https',
                              '--web', '--skip-ssh-key'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace', creationflags=jobs.CREATE_NO_WINDOW)
        _login.update(state='waiting', code=None, url='https://github.com/login/device', error=None, proc=p,
                      started=time.time())

    def reader():
        buf = ''
        try:
            # Enter para "abrir o browser" e "sim" para o git usar a sessão do gh.
            p.stdin.write('\nY\n')
            p.stdin.flush()
        except OSError:
            pass
        for line in p.stdout:
            buf += line
            m = CODE_RE.search(line)
            if m:
                _login['code'] = m.group(1)
            m = URL_RE.search(line)
            if m:
                _login['url'] = m.group(1)
        rc = p.wait()
        if rc == 0:
            _login.update(state='done', proc=None)
            status(refresh=True)
            run(['auth', 'setup-git'], timeout=60)
        else:
            _login.update(state='failed', error=buf.strip()[-300:] or 'gh exited with %d' % rc, proc=None)
    threading.Thread(target=reader, daemon=True).start()
    for _ in range(40):  # o código aparece logo
        if _login['code'] or _login['state'] != 'waiting':
            break
        time.sleep(0.25)
    return login_state()


# -- partilhar uma correção: o fork e o pull request -------------------------------------------
def share_fix(job, worktree, slug, title, commits, summary, tests=''):
    """Envia os commits do assistente (o HEAD da worktree) para um ramo no fork da pessoa e abre o
    pull request para o ReXNative. Devolve o endereço do pull request, ou None."""
    st = status()
    if not st['logged_in']:
        job.event('info', 'Not signed in to GitHub: the fix stays only on this PC')
        return None
    repo = st['repo']
    rc, out, err = run(['repo', 'fork', repo, '--clone=false', '--remote=false'], timeout=120)
    if rc != 0 and 'already exists' not in (out + err):
        job.event('info', 'Could not fork %s (%s): the fix stays only on this PC' % (repo, (err or out)[-200:]))
        return None
    fork = '%s/%s' % (st['login'], repo.split('/', 1)[1])
    branch = 'fix/%s-%s' % (re.sub(r'[^a-z0-9-]+', '-', slug.lower())[:40], time.strftime('%Y%m%d-%H%M%S'))
    url = 'https://github.com/%s.git' % fork
    r = subprocess.run(['git', '-C', worktree, 'push', url, 'HEAD:refs/heads/%s' % branch], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=300,
                       creationflags=jobs.CREATE_NO_WINDOW)
    if r.returncode != 0:
        job.event('info', 'Could not send the fix to your fork (%s): it stays only on this PC'
                  % (r.stderr or r.stdout)[-200:])
        return None
    pr_title = commits[0].split(' ', 1)[1] if len(commits) == 1 and ' ' in commits[0] else \
        'Fixes for %s (%d commits)' % (title, len(commits))
    body = ('A fix made with the ReXNative Manager while preparing **%s**.\n\n**Commits**\n%s\n\n'
            '**What the assistant found**\n%s\n\n%s\n\n_Opened automatically by the ReXNative Manager._'
            % (title, '\n'.join('- %s' % c for c in commits), (summary or '').strip()[:3000],
               ('**Tests**\n' + tests) if tests else ''))
    rc, out, err = run(['pr', 'create', '--repo', repo, '--head', '%s:%s' % (st['login'], branch), '--base', 'main',
                        '--title', pr_title[:120], '--body', body], timeout=120)
    if rc != 0:
        job.event('info', 'The fix is in your fork (%s, branch %s) but the pull request was not opened: %s'
                  % (fork, branch, (err or out)[-200:]))
        return None
    pr = out.strip().splitlines()[-1] if out.strip() else None
    job.event('ok', 'Shared with ReXNative: pull request %s' % pr, pr=pr)
    return pr


def logged_in_fast():
    """Para cada pedido: o que se sabe (em cache), e a verificação de novo num fio à parte quando
    passou o tempo; só a primeira vez espera pelo gh."""
    if _status['data'] is None:
        return status()['logged_in']
    if time.time() - _status['at'] > 300 and not _status.get('refreshing'):
        _status['refreshing'] = True

        def bg():
            try:
                status(refresh=True)
            finally:
                _status['refreshing'] = False
        threading.Thread(target=bg, daemon=True).start()
    return bool(_status['data'].get('logged_in'))
