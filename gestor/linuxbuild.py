"""Builds para Linux (experimental): um jogo compilado nativo para Linux, sem Proton, desenhado pelo
renderizador do ReXGlue em Vulkan (o ReXNative só tem D3D12). Medido no Deck (docs/LINUX.md do
ReXNative): corre, mas gasta bem mais GPU do que o ReXNative com Proton; fica como opção por jogo,
compilada só quando se pede, para os jogos que um dia corram melhor (ou só corram) assim.

- As ferramentas vêm do ramo do ReXNative que as tem (linux_branch, de origem vulkan-experiment,
  até entrarem no main): uma worktree só da app (linux_rexnative_dir), atualizada antes de cada build.
- Compilar: `python -m rexnative project <jogo>` dessa worktree (a opção REXNATIVE do CMake; o build
  de Windows seguinte volta a gerar os ficheiros com o do main) e, no WSL, scripts/linux/build-game.sh
  com o SDK do ReXGlue compilado para Linux (linux_sdk), numa cópia em linux_builds_dir/<jogo>.
- No Deck: <pasta do jogo>/linux/ ao lado da versão Windows (game/ é uma ligação para a dela) e, para
  a escolher, duas linhas no deck.env do jogo (REXNATIVE_PROTON = a pasta do proton-shim,
  REXNATIVE_LINUX_BUILD = linux/): o play.sh arranca a versão Linux em vez do Proton.
  Tirá-las volta ao Windows. As gravações das duas versões são separadas."""
import os
import posixpath
import re
import subprocess
import time

from . import config, deck, jobs, state

MARK = '# rexnative-manager linux'
SHIM_DIR = 'Games/ReXNative/linux-shim'  # na pasta do utilizador do Deck


def cfg_ok(cfg=None):
    """(pronto, porque não): a opção ligada, o WSL e o SDK para Linux."""
    cfg = cfg or config.load()
    if not cfg.get('linux_enabled'):
        return False, 'Linux builds are off (Settings > Linux builds, experimental)'
    if not cfg.get('linux_sdk'):
        return False, 'Set the ReXGlue SDK built for Linux (Settings > Linux builds)'
    return True, ''


def wsl(cmd, timeout=120, input_bytes=None):
    cfg = config.load()
    args = ['wsl'] + (['-d', cfg['linux_wsl_distro']] if cfg.get('linux_wsl_distro') else []) + \
        ['--', 'bash', '-lc', cmd]
    r = subprocess.run(args, input=input_bytes, capture_output=True, timeout=timeout,
                       creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')


def wsl_path(p):
    """D:\\a\\b -> /mnt/d/a/b."""
    p = os.path.abspath(p)
    drive, rest = os.path.splitdrive(p)
    return '/mnt/%s%s' % (drive[0].lower(), rest.replace('\\', '/'))


def tools_dir(cfg=None):
    cfg = cfg or config.load()
    return cfg.get('linux_rexnative_dir') or (cfg['rexnative_dir'].rstrip('\\/') + '-linux')


def _git(args, cwd, timeout=300):
    r = subprocess.run(['git', '-C', cwd] + args, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def ensure_tools(job):
    """A worktree do ReXNative no ramo com as ferramentas de Linux, só desta app, na última versão."""
    cfg = config.load()
    d, branch = tools_dir(cfg), cfg.get('linux_branch') or 'vulkan-experiment'
    _git(['fetch', '-q', 'origin'], cfg['rexnative_dir'])
    if not os.path.isdir(d):
        rc, _, err = _git(['worktree', 'add', '--detach', d, 'origin/%s' % branch], cfg['rexnative_dir'])
        if rc != 0:
            raise RuntimeError('could not make the Linux tools copy of ReXNative (%s): %s' % (d, err[-300:]))
        ports = os.path.join(cfg['rexnative_dir'], 'ports.json')
        if os.path.exists(ports) and not os.path.exists(os.path.join(d, 'ports.json')):
            with open(ports, 'rb') as a, open(os.path.join(d, 'ports.json'), 'wb') as b:
                b.write(a.read())
    else:
        _, dirty, _ = _git(['status', '--porcelain', '--untracked-files=no'], d)
        if not dirty:
            _git(['checkout', '-q', '--detach', 'origin/%s' % branch], d)
    _, head, _ = _git(['log', '-1', '--format=%h %s'], d)
    job.event('info', 'Linux tools: ReXNative %s (%s)' % (head[:70], branch))
    if not os.path.exists(os.path.join(d, 'scripts', 'linux', 'build-game.sh')):
        raise RuntimeError('the branch %s has no scripts/linux/build-game.sh' % branch)
    return d


def copy_dir(slug, cfg=None):
    cfg = cfg or config.load()
    return posixpath.join(cfg.get('linux_builds_dir') or '~/rexnative-linux', slug)


def build_job(job, work):
    """Compila o jogo para Linux no WSL (sem ReXNative; o Xenos em Vulkan desenha-o)."""
    cfg = config.load()
    ok, why = cfg_ok(cfg)
    if not ok:
        raise RuntimeError(why)
    slug = os.path.basename(work)
    tools = ensure_tools(job)
    job.event('step', 'Project files with the REXNATIVE option (the Linux tools copy of ReXNative)')
    rc = job.run([config.python_exe(), '-u', '-m', 'rexnative', 'project', work], cwd=tools, env=config.tool_env())
    if rc != 0:
        raise RuntimeError('rexnative project failed (code %d): see the job log' % rc)
    job.event('step', 'Building for Linux in WSL (the first time copies the game files and takes a while)')
    script = wsl_path(os.path.join(tools, 'scripts', 'linux', 'build-game.sh'))
    cmd = 'bash %s %s %s %s' % (script, _q(wsl_path(work)), copy_dir(slug, cfg), _q(cfg['linux_sdk']))
    args = ['wsl'] + (['-d', cfg['linux_wsl_distro']] if cfg.get('linux_wsl_distro') else []) + ['--', 'bash', '-lc', cmd]
    t0 = time.time()
    rc = job.run(args, cwd=config.ROOT)
    tail = jobs.tail(job.log_path, 6)
    if rc != 0:
        raise RuntimeError('the Linux build failed (code %d): %s' % (rc, tail.strip().splitlines()[-1:] or ''))
    glibc = (re.findall(r'GLIBC_2\.\d+', tail) or [None])[-1]
    size = (re.findall(r'^(\S+)\s+\S*/linux\s*$', tail, re.M) or [None])[-1]
    state.update('games', state.game_key(work), {'linux': {
        'built_at': time.time(), 'copy': copy_dir(slug, cfg), 'glibc': glibc, 'size': size,
        'seconds': round(time.time() - t0)}})
    job.event('ok', 'Built for Linux in %d s%s%s' % (time.time() - t0, ', needs %s' % glibc if glibc else '',
                                                     ', %s' % size if size else ''))
    return {'linux': True}


def _q(s):
    return "'%s'" % str(s).replace("'", "'\\''")


def _deck_game(dk, slug):
    data = dk.listing(light=True, tries=3)
    g = next((x for x in data['games'] if x['slug'] == slug), None)
    if not g:
        raise RuntimeError('%s is not on the Deck: install its Windows build first' % slug)
    return g, data


@deck.exclusive
def deck_send_job(job, work, use_it=True):
    """Envia a build Linux para <pasta do jogo>/linux/ no Deck (game/ ligado ao da versão Windows),
    põe lá o proton-shim e, com use_it, escolhe-a para arrancar."""
    cfg = config.load()
    slug = os.path.basename(work)
    info = (state.get('games', state.game_key(work), {}) or {}).get('linux') or {}
    if not info.get('built_at'):
        raise RuntimeError('not built for Linux yet: Build for Linux first')
    dk = deck.Deck()
    ok, err, line = dk.check(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    b = deck.busy_from(line)
    if b and not b['gestor']:
        raise RuntimeError('You are playing on the Deck: try again when you are done')
    g, _ = _deck_game(dk, slug)
    dest = g['path']
    tools = tools_dir(cfg)
    shim = open(os.path.join(tools, 'scripts', 'linux', 'proton-shim'), 'rb').read().replace(b'\r\n', b'\n')
    r = dk.ssh('mkdir -p ~/%s && cat > ~/%s/proton && chmod +x ~/%s/proton && echo ok' % (SHIM_DIR, SHIM_DIR, SHIM_DIR),
               input_bytes=shim, timeout=60)
    if 'ok' not in r.stdout:
        raise RuntimeError('could not put the proton shim on the Deck: %s' % r.stderr[-200:])
    job.event('step', 'Sending the Linux build to %s/linux (the game files stay shared with the Windows build)' % dest)
    src = info.get('copy') or copy_dir(slug, cfg)
    tar = ['wsl'] + (['-d', cfg['linux_wsl_distro']] if cfg.get('linux_wsl_distro') else []) + [
        '--', 'bash', '-lc', 'cd %s && tar -cf - --exclude=linux/game --exclude=linux/title-update linux' % src]
    remote = ('rm -rf %s/linux.new && mkdir -p %s/linux.new && tar -xf - -C %s/linux.new && rm -rf %s/linux && '
              'mv %s/linux.new/linux %s/linux && rmdir %s/linux.new && ln -sfn ../game %s/linux/game && '
              '{ [ -d %s/title-update ] && ln -sfn ../title-update %s/linux/title-update; true; } && echo sent'
              % ((deck.q(dest),) * 10))
    p1 = subprocess.Popen(tar, stdout=subprocess.PIPE, creationflags=jobs.CREATE_NO_WINDOW)
    p2 = subprocess.run(dk.d.ssh_cmd(remote), stdin=p1.stdout, capture_output=True, timeout=1800,
                        creationflags=jobs.CREATE_NO_WINDOW)
    p1.stdout.close()
    p1.wait(timeout=60)
    if p2.returncode != 0 or b'sent' not in p2.stdout:
        raise RuntimeError('the Linux build did not reach the Deck: %s' % p2.stderr.decode('utf-8', 'replace')[-300:])
    job.event('ok', 'The Linux build is on the Deck')
    if use_it:
        set_runner(job, dk, dest, 'linux')
    deck.status(refresh=True, only=[])
    return {'dest': dest, 'runner': 'linux' if use_it else 'windows'}


def set_runner(job, dk, dest, runner):
    """O que o atalho do Steam arranca: 'linux' (as duas linhas no deck.env) ou 'windows' (sem elas)."""
    env = posixpath.join(dest, 'deck.env')
    lines = '' if runner != 'linux' else (
        'REXNATIVE_PROTON=$HOME/%s  %s\nREXNATIVE_LINUX_BUILD=%s  %s\n' % (SHIM_DIR, MARK, posixpath.join(dest, 'linux'), MARK))
    cmd = ('f=%s; touch "$f"; grep -v %s "$f" > "$f.new"; cat >> "$f.new"; mv "$f.new" "$f"; '
           '[ -s "$f" ] || rm -f "$f"; echo done' % (deck.q(env), deck.q(MARK)))
    if runner == 'linux':
        r0 = dk.ssh('test -x %s/linux/run-linux.sh && echo yes' % deck.q(dest), timeout=30)
        if 'yes' not in r0.stdout:
            raise RuntimeError('there is no Linux build in %s: send it first' % dest)
    r = dk.ssh(cmd, input_text=lines, timeout=30)
    if 'done' not in r.stdout:
        raise RuntimeError('could not change deck.env: %s' % r.stderr[-200:])
    job.event('ok', 'The Steam shortcut now starts the %s build' % ('Linux (native, Vulkan)' if runner == 'linux'
                                                                    else 'Windows (Proton, ReXNative)'))


@deck.exclusive
def runner_job(job, slug, runner):
    dk = deck.Deck()
    ok, err, line = dk.check(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    b = deck.busy_from(line)
    if b and not b['gestor']:
        raise RuntimeError('You are playing on the Deck: try again when you are done')
    g, _ = _deck_game(dk, slug)
    set_runner(job, dk, g['path'], runner)
    deck.status(refresh=True, only=[])
    return {'runner': runner}


def status(work):
    """O que se sabe da build Linux de um jogo: no PC (quando foi compilada) e no Deck (se lá está,
    e se é ela que arranca: a leitura do Deck)."""
    info = (state.get('games', state.game_key(work), {}) or {}).get('linux') or {}
    dg = (deck.index().get(os.path.basename(work)) or {})
    return {'enabled': cfg_ok()[0], 'why': cfg_ok()[1], 'built_at': info.get('built_at'), 'size': info.get('size'),
            'on_deck': bool(dg.get('linux')), 'runner': dg.get('runner') or 'windows'}
