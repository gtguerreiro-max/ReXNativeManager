"""O Steam Deck por SSH: estado, jogos instalados (~/Games/ReXNative e ReXNative/ no cartão
microSD), espaço livre, instalar/reenviar (python -m rexnative deck), apagar um jogo (com cópia
de segurança dos saves e o atalho do Steam removido com o Steam fechado, como rexnative/deck.py
add_to_steam faz para os adicionar)."""
import datetime
import json
import os
import posixpath
import re
import shlex
import subprocess
import tarfile
import threading
import time

from . import config, games, jobs, state

q = shlex.quote

LIST_SCRIPT = r'''
import glob, json, os, subprocess, sys
home = os.path.expanduser('~')
light = 'light' in sys.argv[1:]  # sem medir pastas (apagar, repor: só é preciso saber onde estão)
# only=a,b: medir só estes jogos (depois de enviar um, os outros não mudaram)
only = next((a[5:].split(',') for a in sys.argv[1:] if a.startswith('only=')), None)
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ''
roots = [('interno', os.path.join(home, 'Games', 'ReXNative'))]
sd = None
for dev in ('/dev/mmcblk0p1', '/dev/mmcblk0'):
    out = run(['findmnt', '-rn', '-o', 'TARGET', '-S', dev]).strip()
    if out:
        sd = out.splitlines()[0].replace('\\x20', ' ')
        break
if sd:
    roots.append(('sd', os.path.join(sd, 'ReXNative')))
# Com um jogo aberto não se mede nada (du lê o disco todo do jogo e pode engasgar quem joga).
playing = run(['pgrep', '-af', '[S]teamLaunch AppId=']).strip()
playing_appid = None
for tok in playing.split():
    if tok.startswith('AppId='):
        playing_appid = int(tok[6:]) if tok[6:].isdigit() else None
        break
def du(p):
    if playing or light or (only is not None and os.path.basename(p.rstrip('/')) not in only):
        return None
    out = run(['du', '-sb', p]).split()
    return int(out[0]) if out else 0
def df(p):
    st = os.statvfs(p)
    return {'free': st.f_bavail * st.f_frsize, 'total': st.f_blocks * st.f_frsize, 'path': p}
games = []
kit = None
removed = []
for where, root in roots:
    if not os.path.isdir(root):
        continue
    # <raiz>/.removed/<jogo>: apagado pelo utilizador (o rexnative deck não o volta a enviar).
    rd = os.path.join(root, '.removed')
    marks = set(os.listdir(rd)) if os.path.isdir(rd) else set()
    for n in sorted(marks):
        try:
            at = open(os.path.join(rd, n)).read().strip()
        except OSError:
            at = ''
        removed.append({'slug': n, 'where': where, 'at': at})
    for n in sorted(os.listdir(root)):
        d = os.path.join(root, n)
        if n in ('prefix', 'common') or not os.path.isdir(d):
            continue
        files = os.listdir(d)
        exes = sorted(f for f in files if f.lower().endswith('.exe'))
        if not exes and 'game' not in files:
            continue
        if 'steam_shortcuts.py' in files:
            kit = kit or os.path.join(d, 'steam_shortcuts.py')
        ud = os.path.join(d, 'userdata')
        saves = sorted(os.path.relpath(p, ud) for p in glob.glob(os.path.join(ud, '*', '*', '00000001', '*')))
        skip = playing or light or (only is not None and n not in only)
        saves_size = (None if skip else sum(int((run(['du', '-sb', os.path.join(ud, s)]).split() or ['0'])[0]) for s in saves)) if saves else 0
        logs = sorted(glob.glob(os.path.join(d, 'logs', '*.log')), key=os.path.getmtime)
        # As conquistas que o SDK grava quando o jogo as dá: userdata/achievements/<TitleID>.toml.
        ach, cur = {}, None
        for p in glob.glob(os.path.join(ud, 'achievements', '*.toml')):
            try:
                for line in open(p, errors='replace'):
                    line = line.strip()
                    if line.startswith('[unlocked.') and line.endswith(']'):
                        cur = line[10:-1]
                        ach[cur] = 0
                    elif cur and line.startswith('filetime') and '=' in line:
                        ach[cur] = int(line.split('=', 1)[1].strip() or 0)
            except (OSError, ValueError):
                pass
        # Os snapshots de depuração que o jogador tirou no jogo (o Y no menu de definições do
        # ReXNative): snapshots/<data-hora>/ com a imagem e o trace.
        snaps = []
        sdir = os.path.join(d, 'snapshots')
        if os.path.isdir(sdir):
            for sn in sorted(os.listdir(sdir))[-5:]:
                sp = os.path.join(sdir, sn)
                if os.path.isdir(sp):
                    fs = os.listdir(sp)
                    snaps.append({'name': sn, 'mtime': os.path.getmtime(sp),
                                  'png': sum(f.endswith('.png') for f in fs),
                                  'trace': sum(f.endswith('.rxt') for f in fs)})
        games.append({'achievements': ach, 'snapshots': snaps,'slug': n, 'where': where, 'path': d, 'size': du(d),
                      'exe': exes[0] if exes else None, 'saves': saves, 'saves_size': saves_size,
                      'mtime': max([os.path.getmtime(os.path.join(d, e)) for e in exes] or [0]),
                      'complete': 'play.sh' in files, 'removed_mark': n in marks,
                      # A build Linux ao lado (linux/) e qual arranca (o deck.env com REXNATIVE_LINUX_BUILD).
                      'linux': os.path.isfile(os.path.join(d, 'linux', 'run-linux.sh')),
                      'runner': 'linux' if 'REXNATIVE_LINUX_BUILD=' in (open(os.path.join(d, 'deck.env')).read()
                                                                        if os.path.isfile(os.path.join(d, 'deck.env')) else '') else 'windows',
                      'last_played': os.path.getmtime(logs[-1]) if logs else None})
shortcuts = []
if kit:
    for line in run(['python3', kit, 'list']).splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        rest = parts[1]
        i = rest.find('  "')
        name, exe = (rest[:i], rest[i + 2:]) if i >= 0 else (rest, '')
        shortcuts.append({'appid': int(parts[0]), 'name': name.strip(), 'exe': exe.strip()})
space = {'interno': df(home)}
if sd:
    space['sd'] = df(sd)
playing_title = next((s['name'] for s in shortcuts if s['appid'] == playing_appid), None)
print(json.dumps({'games': games, 'shortcuts': shortcuts, 'space': space, 'sd': sd, 'removed': removed,
                  'playing': bool(playing), 'playing_appid': playing_appid, 'playing_line': playing[:400],
                  'playing_title': playing_title, 'measured': not (playing or light or only is not None),
                  'only': only,
                  'steam': bool(run(['pgrep', '-x', 'steam']).strip())}))
'''

# Mexe nos atalhos com o Steam fechado (Steam reescreve shortcuts.vdf ao sair): no Game Mode o
# steam-launcher.service é mascarado só enquanto isto corre e o trap volta a pô-lo a correr,
# como em rexnative/deck.py add_to_steam. STEAM_HEAD fecha o Steam; o resto do script é o que se
# faz com ele fechado.
STEAM_HEAD = r'''
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
masked=
desktop=
restore() {
  if [ -n "$masked" ]; then
    systemctl --user unmask --runtime steam-launcher.service >/dev/null 2>&1
    systemctl --user start steam-launcher.service >/dev/null 2>&1
  elif [ -n "$desktop" ]; then
    systemd-run --user --quiet --collect steam -silent >/dev/null 2>&1
  fi
}
trap restore EXIT
if pgrep -x steam >/dev/null; then
  systemctl --user is-active --quiet gamescope-session.target 2>/dev/null || desktop=1
  pid=$(pgrep -o -x steam)
  age=$(ps -o etimes= -p "$pid" | tr -d ' ')
  [ "${age:-0}" -lt 70 ] && sleep $(( 70 - ${age:-0} ))
  if systemctl --user is-active --quiet gamescope-session.target 2>/dev/null; then
    systemctl --user mask --runtime steam-launcher.service >/dev/null && masked=1
  fi
  # Um jogo que começou entretanto (a espera acima, a cópia antes desta): o Steam fica.
  if pgrep -f "[S]teamLaunch AppId=" >/dev/null; then echo "GAME_OPEN: a game started on the Deck"; exit 3; fi
  echo "closing Steam to change the shortcuts"
  steam -shutdown >/dev/null 2>&1
  for i in $(seq 1 120); do pgrep -x steam >/dev/null || break; sleep 0.5; done
  if pgrep -x steam >/dev/null; then echo "Steam did not close"; exit 1; fi
fi
'''
# Tirar atalhos (o Steam já fechado): a arte, a cache de shaders e o prefixo do Steam de cada um
# saem também (7 a 30 MB cada: sem o atalho ficavam lá para sempre).
REMOVE_BODY = r'''
python3 %(kit)s remove %(names)s || exit 1
grid=$(ls -d ~/.local/share/Steam/userdata/*/config/grid 2>/dev/null | grep -v '/userdata/0/' | head -1)
if [ -n "$grid" ]; then
  for a in %(appids)s; do rm -f "$grid/$a.png" "$grid/${a}p.png" "$grid/${a}_hero.png" "$grid/${a}_logo.png"; done
fi
for a in %(appids)s; do
  rm -rf ~/.local/share/Steam/steamapps/shadercache/"$a" ~/.local/share/Steam/steamapps/compatdata/"$a"
done
echo "shortcuts removed"
'''
REMOVE_SCRIPT = STEAM_HEAD + REMOVE_BODY


class Deck:
    def __init__(self):
        cfg = config.load()
        rex = games.rexnative('deck')
        try:
            self.d = rex.Deck(cfg['deck_host'], os.path.expanduser(cfg['deck_key']) if cfg['deck_key'] else None)
        except SystemExit as e:
            raise RuntimeError('The Deck is not set up: %s (Settings)' % e)
        self.rex = rex

    def ssh(self, command, input_text=None, timeout=120, input_bytes=None):
        # O stdin vai em bytes com \n: em modo texto o Windows escreveria \r\n e o bash do Deck
        # recusa um script assim (o Python aceita-o, por isso a lista funcionava).
        data = (input_text.replace('\r\n', '\n').encode('utf-8') if input_text is not None
                else input_bytes)
        r = subprocess.run(self.d.ssh_cmd(command), input=data, capture_output=True,
                           timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
        return subprocess.CompletedProcess(r.args, r.returncode,
                                           r.stdout.decode('utf-8', 'replace'),
                                           r.stderr.decode('utf-8', 'replace'))

    def reachable(self, tries=1):
        """(responde, erro). tries > 1 nas tarefas: o Wi-Fi do Deck muda de banda de vez em quando
        (alguns segundos sem rede) e outro programa a enviar para lá atrasa as respostas."""
        err = ''
        for i in range(tries):
            try:
                r = self.ssh('echo ok', timeout=20)
                if r.returncode == 0 and 'ok' in r.stdout:
                    return True, ''
                err = (r.stderr or '').strip()[-300:]
            except subprocess.TimeoutExpired:
                err = 'no answer in 20 s'
            if i + 1 < tries:
                time.sleep(5)
        return False, err + (' (%d tries)' % tries if tries > 1 else '')

    def check(self, tries=1):
        """Numa só ligação: o Deck responde e o que está a correr. (ok, erro, linha do pgrep)."""
        err = ''
        for i in range(tries):
            try:
                r = self.ssh('echo ok; pgrep -af "[S]teamLaunch AppId=" || true', timeout=25)
                if r.returncode == 0 and r.stdout.startswith('ok'):
                    return True, '', r.stdout[2:].strip()
                err = (r.stderr or '').strip()[-300:]
            except subprocess.TimeoutExpired:
                err = 'no answer in 25 s'
            if i + 1 < tries:
                time.sleep(5)
        return False, err + (' (%d tries)' % tries if tries > 1 else ''), None

    def listing(self, light=False, only=None, tries=1):
        """Os jogos, os atalhos, o espaço e o que está a correr (uma ligação). only: medir só esses
        jogos; tries: outra vez quando o ssh falha (o Wi-Fi do Deck muda de banda)."""
        args = (' light' if light else '') + (' only=%s' % ','.join(only) if only is not None else '')
        for i in range(tries):
            try:
                r = self.ssh('python3 -%s' % args, input_text=LIST_SCRIPT, timeout=240)
            except subprocess.TimeoutExpired:
                r = subprocess.CompletedProcess([], 255, '', 'no answer in 240 s')
            if r.returncode != 255 or i + 1 == tries:
                break
            time.sleep(5)
        if r.returncode != 0:
            raise RuntimeError('the Deck answered with an error: %s' % (r.stderr or r.stdout)[-400:])
        data = json.loads(r.stdout.strip().splitlines()[-1])
        try:
            from . import achievements
            achievements.from_listing(data)
        except Exception:  # noqa: BLE001 - as conquistas nunca estragam uma listagem
            import traceback
            traceback.print_exc()
        # Cada jogo com o seu atalho (o exe do atalho é "<pasta>/play.sh").
        for g in data['games']:
            sc = next((s for s in data['shortcuts']
                       if s['exe'].strip('"').rstrip('/').startswith(g['path'] + '/')), None)
            g['shortcut'] = sc
        return data


def status(refresh=True, only=None):
    """O estado do Deck (da cache quando refresh=False ou quando não responde). only: medir só esses
    jogos (os outros ficam com o tamanho da leitura anterior)."""
    cached = dict(state.get('deck', 'last') or {}, foreign=foreign_senders())
    if not refresh:
        return dict(cached, cached=True)
    try:
        dk = Deck()
    except RuntimeError as e:
        return dict(cached, reachable=False, error=str(e), cached=True)
    ok, err = dk.reachable()
    if not ok:
        return dict(cached, reachable=False, error=err or 'unreachable (asleep? sshd on port '
                    '2222 stopped after a restart?)', cached=True)
    data = dk.listing(only=only)
    if not data.get('measured'):
        before = {g['slug']: g for g in cached.get('games', [])}
        for g in data['games']:
            if g.get('size') is not None:
                continue  # medido agora (only=)
            old = before.get(g['slug'], {})
            g['size'] = old.get('size')
            g['saves_size'] = old.get('saves_size')
            g['size_old'] = True
    data.update(reachable=True, at=jobs.now(), error=None)
    state.update('deck', 'last', data)
    return dict(data, cached=False, foreign=cached['foreign'])


def index():
    """{slug: {where, path, size, ...}} dos jogos do Deck (última leitura)."""
    last = state.get('deck', 'last') or {}
    return {g['slug']: {k: g.get(k) for k in ('where', 'path', 'size', 'shortcut', 'saves', 'linux', 'runner')}
            for g in last.get('games', [])}


def _playing(dk):
    r = dk.ssh('pgrep -af "[S]teamLaunch AppId=" || true', timeout=30)
    if r.returncode != 0:
        raise RuntimeError('Could not check whether a game is open on the Deck: %s' % (
            r.stderr or 'ssh exit code %d' % r.returncode).strip()[-200:])
    return r.stdout.strip()


def gestor_appid():
    """O appid do atalho do Gestor no Steam do Deck (quando foi instalado pela app)."""
    return (state.get('deck', 'gestor') or {}).get('appid')


def busy(dk):
    """None com o Deck livre; senão {'appids', 'gestor', 'line'}. Com o Gestor aberto (gestor=True)
    enviam-se ficheiros e apagam-se pastas, mas os atalhos esperam (fechar o Steam fechava o
    Gestor); um jogo aberto impede tudo."""
    return busy_from(_playing(dk))


def busy_from(out):
    """busy() a partir da linha do pgrep que já se tem (check, listing)."""
    out = (out or '').strip()
    if not out:
        return None
    ids = sorted({int(m) for m in re.findall(r'AppId=(\d+)', out)})
    g = gestor_appid()
    return {'appids': ids, 'gestor': bool(ids) and g is not None and all(i == g for i in ids),
            'line': out[:200]}


_pending_lock = threading.Lock()
# Um só trabalho de cada vez a mexer no Steam ou a arrancar jogos no Deck: as tarefas da pista do
# Deck já são uma de cada vez, mas a captura dos relatórios corre noutra pista.
LOCK = threading.RLock()


def exclusive(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with LOCK:
            return fn(*a, **kw)
    return wrapper


def pending():
    """Atalhos à espera do Steam fechado: {'add': {slug: {title, at}}, 'remove': {appid: {name,
    slug, at}}}."""
    p = state.get('deck', 'pending') or {}
    return {'add': dict(p.get('add') or {}), 'remove': dict(p.get('remove') or {})}


def _set_pending(p):
    state.update('deck', 'pending', {'add': p['add'], 'remove': p['remove']})


def queue_add(slug, title):
    with _pending_lock:
        p = pending()
        p['add'][slug] = {'title': title, 'at': jobs.now()}
        _set_pending(p)


def queue_remove(name, appid, slug=None):
    with _pending_lock:
        p = pending()
        p['remove'][str(int(appid))] = {'name': name, 'slug': slug, 'at': jobs.now()}
        if slug:
            p['add'].pop(slug, None)
        _set_pending(p)


@exclusive
def flush_job(job, wait=90):
    """Põe na biblioteca do Steam os jogos instalados com o Gestor aberto e tira os atalhos dos
    que se apagaram entretanto, com o Steam fechado UMA vez. Espera até wait s que o Gestor feche."""
    p = pending()
    if not p['add'] and not p['remove']:
        job.event('ok', 'Nothing pending')
        return {'nothing': True}
    dk = Deck()
    ok, err, line = dk.check(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s): the shortcuts stay pending' % err)
    t0 = time.time()
    while True:
        b = busy_from(line)
        if not b:
            break
        if time.time() - t0 > wait:
            raise RuntimeError('The Deck is still busy (%s): the shortcuts wait until it is '
                               'free' % ('the Manager is open' if b['gestor'] else 'a game is open'))
        job.sleep(5)
        ok, err, line = dk.check(tries=2)
        if not ok:
            raise RuntimeError('The Deck stopped responding (%s): the shortcuts stay pending' % err)
    data = dk.listing(light=True)
    by_slug = {g['slug']: g for g in data['games']}
    have = {s['appid']: s for s in data['shortcuts']}
    kit = next((posixpath.join(g['path'], 'steam_shortcuts.py') for g in data['games']
                if g.get('complete', True)), None)
    gk = (state.get('deck', 'gestor') or {}).get('dir')
    if gk:
        kit = posixpath.join(gk, 'steam_shortcuts.py')
    if not kit:
        raise RuntimeError('steam_shortcuts.py not found on the Deck')
    rm = {k: v for k, v in p['remove'].items() if int(k) in have}
    adds = {slug: a for slug, a in p['add'].items()
            if slug in by_slug and not by_slug[slug].get('shortcut')}
    body = 'failed=\n'
    if rm:
        body += (REMOVE_BODY % {'kit': q(kit), 'names': ' '.join(q(v['name']) for v in rm.values()),
                                'appids': ' '.join(str(int(k)) for k in rm)}).replace('|| exit 1', '|| failed=1')
    for slug, a in adds.items():
        body += '(cd %s && bash install.sh %s) || failed=1\n' % (q(by_slug[slug]['path']), q(a['title']))
    body += 'echo "library updated"\n[ -z "$failed" ]\n'
    if rm or adds:
        job.event('step', 'Steam on the Deck closes and reopens once: %s' % '; '.join(
            x for x in ['%d game(s) into the library' % len(adds) if adds else '',
                        '%d shortcut(s) to remove' % len(rm) if rm else ''] if x))
        r = dk.ssh('bash -s', input_text=STEAM_HEAD + body, timeout=600)
        job.log((r.stdout + r.stderr).strip())
        if 'GAME_OPEN' in r.stdout:
            raise RuntimeError('A game started on the Deck: Steam was not closed and the shortcuts stay '
                               'pending until it is free')
        if r.returncode != 0:
            raise RuntimeError('Steam did not accept the shortcuts: %s' % (r.stdout + r.stderr)[-300:])
    # Só sai da fila o que foi tratado (ou já não precisa: o jogo foi apagado, o atalho já existe).
    with _pending_lock:
        now = pending()
        for slug in p['add']:
            now['add'].pop(slug, None)
        for k in p['remove']:
            now['remove'].pop(k, None)
        _set_pending(now)
    try:
        status(refresh=True, only=[])
    except Exception as e:  # noqa: BLE001
        job.log('Deck list not read again: %s' % e)
    job.event('ok', 'Steam library updated: %s' % (', '.join(a['title'] for a in adds.values())
                                                  or '%d shortcut(s) removed' % len(rm)))
    return {'added': list(adds), 'removed': [v['name'] for v in rm.values()]}


_foreign_cache = {'at': 0.0, 'value': []}


def foreign_senders(max_age=5.0):
    """Programas do PC, fora desta app, a enviar jogos para o Deck (python -m rexnative deck)
    ou a correr lá experiências (scripts/deck_drive.py): [{'pid', 'game', 'cmd', 'since'}].
    Um envio desses volta a pôr no Deck o que a app acabou de apagar e divide a rede com os
    envios da app. Guardado uns segundos (as páginas perguntam de 3 em 3 s)."""
    if time.time() - _foreign_cache['at'] < max_age:
        return list(_foreign_cache['value'])
    value = _foreign_senders()
    _foreign_cache.update(at=time.time(), value=value)
    return list(value)


def _foreign_senders():
    try:
        import psutil
    except ImportError:
        return []
    me = os.getpid()
    found = {}
    for p in psutil.process_iter(['pid', 'ppid', 'name', 'create_time']):
        try:
            # Só um Python a correr isso mesmo (uma shell com essas palavras no texto não conta).
            if not (p.info['name'] or '').lower().startswith('python'):
                continue
            args = p.cmdline() or []
            game = None
            for i, a in enumerate(args):
                if a == 'rexnative' and i and args[i - 1] == '-m' and args[i + 1:i + 2] == ['deck']:
                    game = args[i + 2] if i + 2 < len(args) else ''
                elif a.replace('\\', '/').endswith('scripts/deck_drive.py'):
                    game = args[i + 1] if i + 1 < len(args) else ''
            if game is None or any(a.pid == me for a in p.parents()):
                continue
            found[p.info['pid']] = {'pid': p.info['pid'], 'ppid': p.info['ppid'],
                                    'game': posixpath.basename(game.replace('\\', '/').rstrip('/')),
                                    'cmd': ' '.join(args)[:240], 'since': p.info['create_time']}
        except (psutil.Error, OSError):
            continue
    # O python.exe do .venv lança o do sistema com os mesmos argumentos: só o de cima.
    return [f for f in found.values() if f['ppid'] not in found]


def wait_foreign(job, minutes=30):
    """Espera (até minutes) que os outros programas acabem de usar o Deck."""
    t0 = time.time()
    said = False
    while True:
        f = foreign_senders()
        if not f:
            if said:
                job.event('info', 'The other program finished: continuing')
            return said  # True: esperou-se (o estado do Deck pode ter mudado)
        what = ', '.join(sorted({x['game'] or 'pid %d' % x['pid'] for x in f}))
        if not said:
            job.event('info', 'Another program on the PC is sending to the Deck (%s): waiting for it '
                              'to finish' % what)
            said = True
        if time.time() - t0 > minutes * 60:
            raise RuntimeError('Another program on the PC has been using the Deck for %d min (%s): '
                               'nothing was done, try again later' % (minutes, what))
        job.sleep(10)


def _log_since(path, offset):
    try:
        with open(path, 'rb') as f:
            f.seek(offset)
            return f.read().decode('utf-8', errors='replace')
    except OSError:
        return ''


COPIED_RE = re.compile(r'copied (\d+) of (\d+) MB')


def _copy_progress(path):
    """{'done', 'total'} da cópia para o Deck, da última linha 'copied N of M MB' do registo."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            text = f.read().decode('utf-8', 'replace')
    except OSError:
        return None
    m = COPIED_RE.findall(text)
    if not m:
        return None
    return {'done': int(m[-1][0]) * 1000000, 'total': int(m[-1][1]) * 1000000}


BROKE_RE = re.compile(r'the copy into (\S+) stopped after (\d+) of (\d+) MB \((.*?)\); deck again', re.S)
SPACE_RE = re.compile(r'([\d.]+) GB to copy into (\S+) and ([\d.]+) GB free there')


def _deck_error(out, rc):
    """A falha do rexnative deck em português (a última linha 'the Deck: ...' do registo)."""
    m = SPACE_RE.search(out)
    if m:
        return ('Not enough space on the Deck: the transfer needs %s GB and only %s GB are free. Delete '
                'games in the Steam Deck tab (or install to the microSD card, if you have one). Nothing '
                'was sent.' % (m.group(1), m.group(3)))
    m = BROKE_RE.search(out)
    if m:
        return ('The connection to the Deck dropped mid-transfer (%s of %s MB; %s). What arrived stays '
                'there: installing again resumes where it stopped.' % (m.group(2), m.group(3),
                                                                      m.group(4).strip()[-160:] or '?'))
    lines = [l for l in out.splitlines() if l.startswith('the Deck:')]
    if lines:
        return 'rexnative deck failed: %s' % lines[-1][:300]
    return 'rexnative deck failed (exit code %d): see the log' % rc


def _supports(cfg, flag):
    try:
        return flag in open(os.path.join(cfg['rexnative_dir'], 'rexnative', '__main__.py'),
                            encoding='utf-8').read()
    except OSError:
        return False


# -- tarefas ------------------------------------------------------------------------------------
@exclusive
def install_job(job, work, root=None, steam=True, try_seconds=None, force_settings=False,
                wait=False):
    """Envia um jogo compilado (python -m rexnative deck); steam: fecha o Steam para adicionar o
    atalho/arte; try_seconds: arranca-o e lê o log. Com o Gestor aberto no Deck os ficheiros vão
    já e o atalho fica para quando o Gestor fechar (flush_job); com um jogo aberto, wait espera
    que acabe em vez de desistir."""
    cfg = config.load()
    dk = Deck()
    ok, err, line = dk.check(tries=3)
    if not ok and wait:
        # Um pedido feito do Deck que depois foi dormir: o envio começa quando ele acordar.
        hours = float(cfg.get('deck_wait_hours') or 12)
        job.event('info', 'The Deck is asleep or offline: the transfer starts when it is back (waiting up '
                          'to %g h)' % hours)
        until = time.time() + hours * 3600
        job.drain_stop = True  # only waiting: a restart of the app does not wait for this
        while not ok and time.time() < until:
            job.sleep(60)
            ok, err, line = dk.check()
        job.drain_stop = False
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    if wait_foreign(job):
        line = _playing(dk)  # esperou-se: o que corre agora
    b = busy_from(line)
    said = False
    while b and not b['gestor']:
        if not wait:
            raise RuntimeError('You are playing on the Deck: try again when you are done (nothing was sent)')
        if not said:
            job.event('info', 'You are playing on the Deck: the transfer starts when you quit the game')
            said = True
        job.drain_stop = True
        job.sleep(60)
        job.drain_stop = False
        b = busy(dk)
    defer = bool(steam and b)
    if defer:
        steam, try_seconds = False, 0
        job.event('info', 'The Manager is open on the Deck: the files go now and the game joins the '
                          'library when you quit the Manager (Steam restarts for a few seconds)')
    cmd = [config.python_exe(), '-u', '-m', 'rexnative', 'deck', work]
    if root:
        cmd += ['--root', root]
    if steam:
        cmd.append('--steam')
    if try_seconds:
        cmd += ['--try', str(int(try_seconds))]
    # Instalar pela app é escolha do utilizador: também um jogo que ele tinha apagado do Deck.
    if _supports(cfg, '--reinstall'):
        cmd.append('--reinstall')
    job.event('step', 'Sending to the Deck%s%s' % (' (microSD card)' if root == 'sd' else '',
                                                  ', with a %d s test' % try_seconds if try_seconds else ''))
    # A barra: o rexnative deck escreve 'copied N of M MB' de 3 em 3 s.
    job.progress = jobs.with_rate(lambda: _copy_progress(job.log_path))
    tries = 3
    for attempt in range(1, tries + 1):
        start = os.path.getsize(job.log_path) if os.path.exists(job.log_path) else 0
        rc = job.run(cmd, cwd=cfg['rexnative_dir'], env=config.tool_env())
        if rc == 0:
            break
        out = _log_since(job.log_path, start)
        if 'no shortcut added' in out and steam:
            # ReXNative 5226a5a: um jogo começou no Deck enquanto isto se preparava para fechar o Steam.
            # Os ficheiros estão lá; o atalho fica à espera, como com o Gestor aberto.
            job.event('info', 'A game started on the Deck: the game is there and joins the library when '
                              'the Deck is free (Steam was not closed)')
            defer, try_seconds = True, 0
            break
        m = BROKE_RE.search(out)
        if not m or attempt == tries:
            raise RuntimeError(_deck_error(out, rc))
        # O que chegou fica (o rexnative deck só envia o que falta): tenta outra vez.
        job.event('info', 'The connection to the Deck dropped mid-transfer (%s of %s MB; %s): resuming '
                          '(try %d of %d)' % (m.group(2), m.group(3),
                                              m.group(4).strip()[-120:] or '?', attempt + 1, tries))
        job.sleep(15)
        ok, err = dk.reachable(tries=12)
        if not ok:
            raise RuntimeError('The connection to the Deck dropped mid-transfer and the Deck did not '
                               'come back (%s). What arrived stays there: installing again resumes '
                               'where it stopped.' % err)
    result = {}
    text = jobs.tail(job.log_path, 80)
    m = re.findall(r'^(.*?): (running|NOT running), (.*)$', text, re.M)
    if m:
        result['try'] = '%s: %s' % (m[-1][1], m[-1][2])
        job.event('ok' if m[-1][1] == 'running' else 'fail', 'Test on the Deck: %s, %s' % (m[-1][1], m[-1][2]))
    if defer:
        queue_add(os.path.basename(work), dk.rex.title_of(work))
        result['deferred'] = True
    try:
        data = status(refresh=True, only=[os.path.basename(work)])  # só este jogo mudou
    except Exception as e:  # noqa: BLE001 - o jogo já lá está: a lista lê-se outra vez mais tarde
        job.event('info', 'Sent, but the Deck list could not be read again: %s' % str(e)[-200:])
        data = {}
    if force_settings:
        name = games.exe_name(work)
        g = next((x for x in data.get('games', []) if x['slug'] == os.path.basename(work)), None)
        if not (g and name):
            raise RuntimeError('Sent, but the settings were not replaced: the game was not found in the '
                               'Deck list')
        p = g['path']
        r = dk.ssh('cd %s && cp %s %s && cp %s %s' % (
            q(p), q(name + '-deck.toml'), q(name + '.toml'), q(name + '-deck.toml'),
            q('.' + name + '-deck')), timeout=60)
        if r.returncode != 0:
            raise RuntimeError('Sent, but the settings were not replaced: %s' % r.stderr[-200:])
        job.event('ok', 'Deck settings replaced with the app ones')
    # A versão que foi para o Deck (o cartão do jogo no Modo Deck mostra o histórico).
    try:
        from . import changelog
        changelog.record_send(os.path.basename(work), work, games.info(work).get('built_at'))
    except Exception as e:  # noqa: BLE001 - o histórico não pára um envio
        job.log('version history: %s' % e)
    job.event('ok', 'Sent to the Deck' + (' (the shortcut joins the library when you quit the Manager)'
                                           if defer else ''))
    return result


def backup_saves(job, dk, g):
    """userdata/ do jogo (sem o conteúdo descarregável, que se reinstala) e as suas definições,
    num .tar em <data_dir>/backups. Devolve o caminho."""
    name = (g.get('exe') or '')[:-4]
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = os.path.join(config.data_dir('backups'), '%s-%s.tar' % (g['slug'], stamp))
    have = dk.ssh('cd %s && ls -d userdata %s 2>/dev/null; true' % (
        q(g['path']), q(name + '.toml') if name else ''), timeout=60).stdout.split()
    if not have:
        job.event('info', 'No saves or settings to back up (there is no userdata/)')
        return None
    n = _tar_from_deck(job, dk, g['path'], have, dest, '--exclude="*/00000002" ', 'The backup')
    job.event('ok', 'Backup: %s (%d entries, %.1f MB)' % (dest, n, os.path.getsize(dest) / 1e6))
    return dest


def fetch_saves(job, dk, g, dest):
    """Os saves do jogo no Deck (userdata/<perfil>/<jogo>/00000001 e os seus cabeçalhos, sem
    definições nem conteúdo descarregável) num .tar em dest. None se não tiver nenhum."""
    have = dk.ssh('cd %s && ls -d userdata/*/*/00000001 userdata/*/*/Headers/00000001 2>/dev/null; true' % (
        q(g['path'])), timeout=60).stdout.split()
    if not have:
        return None
    n = _tar_from_deck(job, dk, g['path'], have, dest, '', 'Copying the saves')
    job.event('ok', 'The saves from the Deck: %d entries, %.1f KB' % (n, os.path.getsize(dest) / 1e3))
    return dest


def recent_snapshots(g, hours=24):
    """Os snapshots do jogo no Deck das últimas `hours` horas (da listagem), o mais novo no fim."""
    now = time.time()
    return sorted((s for s in g.get('snapshots') or [] if now - (s.get('mtime') or 0) < hours * 3600),
                  key=lambda s: s['name'])


def fetch_snapshots(job, dk, g, dest, hours=24, limit=2):
    """Os snapshots que o jogador tirou no jogo no Deck (View + Menu, depois Y): a imagem do frame e
    o trace dos frames seguintes de cada um, os `limit` mais novos das últimas `hours` horas, para
    dest/snapshots/<nome>/. Devolve as pastas."""
    snaps = recent_snapshots(g, hours)[-limit:]
    if not snaps:
        return []
    tar = os.path.join(dest, 'snapshots.tar')
    _tar_from_deck(job, dk, g['path'], ['snapshots/' + s['name'] for s in snaps], tar, '',
                   'Copying the snapshots')
    try:
        with tarfile.open(tar) as t:
            t.extractall(dest, filter='data')
    finally:
        os.remove(tar)
    out = [p for p in (os.path.join(dest, 'snapshots', s['name']) for s in snaps) if os.path.isdir(p)]
    size = sum(os.path.getsize(os.path.join(p, f)) for p in out for f in os.listdir(p))
    job.event('ok', 'The snapshots you took in the game: %d (%.0f MB)' % (len(out), size / 1e6))
    return out


def _tar_from_deck(job, dk, cwd, members, dest, options, what):
    """Um .tar com estes caminhos da pasta cwd do Deck, verificado antes de ficar em dest; devolve
    quantas entradas tem."""
    cmd = dk.d.ssh_cmd('cd %s && tar -cf - %s%s' % (q(cwd), options, ' '.join(q(m) for m in members)))
    job.log('$ ' + ' '.join(cmd))
    part = dest + '.part'
    try:
        with open(part, 'wb') as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=1800,
                               creationflags=jobs.CREATE_NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError('%s failed: %s' % (what, r.stderr.decode(errors='replace')[-300:]))
        try:
            with tarfile.open(part) as t:
                n = len(t.getmembers())
        except tarfile.TarError as e:
            raise RuntimeError('%s is incomplete (%s): nothing was changed' % (what, e))
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return n


def delete_job(job, slug, backup=True):
    return delete_many_job(job, [slug], backup=backup)


@exclusive
def delete_many_job(job, slugs, backup=True):
    """Apaga vários jogos do Deck de uma vez: a cópia de segurança de cada um, os atalhos todos
    com o Steam fechado UMA vez, e as pastas. Nada é apagado se algum atalho não sair."""
    dk = Deck()
    ok, err, _ = dk.check(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    # Um envio de outro programa a meio voltava a pôr no Deck o que se apaga aqui.
    wait_foreign(job)
    job.event('step', 'Finding where the games are on the Deck')
    data = dk.listing(light=True, tries=3)
    b = busy_from(data.get('playing_line'))
    if b and not b['gestor']:
        raise RuntimeError('You are playing on the Deck: nothing was deleted')
    by_slug = {x['slug']: x for x in data['games']}
    targets = []
    for slug in slugs:
        g = by_slug.get(slug)
        if not g:
            job.event('info', '%s is not installed on the Deck: skipped' % slug)
            continue
        # Só uma pasta de jogo dentro de uma das raízes do kit, nunca a raiz, o prefixo ou common/.
        parent = posixpath.dirname(g['path'].rstrip('/'))
        if posixpath.basename(parent) != 'ReXNative' or g['slug'] in ('prefix', 'common', '', '.', '..'):
            raise RuntimeError('unexpected path, nothing deleted: %s' % g['path'])
        if g.get('size') is None:  # a lista leve não mede: só estas pastas
            out = dk.ssh('du -sb %s' % q(g['path']), timeout=300).stdout.split()
            g['size'] = int(out[0]) if out and out[0].isdigit() else 0
        targets.append(g)
    if not targets:
        raise RuntimeError('none of the games is on the Deck')
    total = sum(g['size'] or 0 for g in targets)
    job.event('step', 'Deleting %d game(s) from the Deck (%.2f GB): %s' % (
        len(targets), total / 1e9, ', '.join(g['slug'] for g in targets)))
    if backup:
        job.result['backups'] = [b for b in (backup_saves(job, dk, g) for g in targets) if b]
    shortcuts = [g['shortcut'] for g in targets if g.get('shortcut')]
    if shortcuts and b:
        # O Gestor está aberto: fechar o Steam fechava-o. Os atalhos saem quando ele fechar.
        for g in targets:
            if g.get('shortcut'):
                queue_remove(g['shortcut']['name'], g['shortcut']['appid'], g['slug'])
        job.event('info', 'The shortcuts leave the library when you quit the Manager (Steam restarts '
                          'for a few seconds)')
        shortcuts = []
    if shortcuts:
        kit = posixpath.join(targets[0]['path'], 'steam_shortcuts.py')
        script = REMOVE_SCRIPT % {'kit': q(kit), 'names': ' '.join(q(sc['name']) for sc in shortcuts),
                                  'appids': ' '.join(str(int(sc['appid'])) for sc in shortcuts)}
        job.event('step', 'Removing %d Steam shortcut(s) (Steam closes and reopens once)' % len(shortcuts))
        r = dk.ssh('bash -s', input_text=script, timeout=400)
        job.log((r.stdout + r.stderr).strip())
        if 'GAME_OPEN' in r.stdout:
            raise RuntimeError('A game started on the Deck: Steam was not closed and nothing was deleted')
        if r.returncode != 0:
            raise RuntimeError('The shortcuts were not removed (nothing was deleted): %s' % (r.stdout + r.stderr)[-300:])
    freed = 0
    failed = []
    for g in targets:
        # A marca <raiz>/.removed/<jogo>: o rexnative deck (de qualquer programa que envie uma
        # lista de jogos outra vez) deixa-o de fora; instalar pela app tira-a.
        marks = posixpath.join(posixpath.dirname(g['path'].rstrip('/')), '.removed')
        r = dk.ssh('rm -rf -- %s && mkdir -p %s && date "+%%Y-%%m-%%d %%H:%%M" > %s && echo "folder deleted"' % (
            q(g['path']), q(marks), q(posixpath.join(marks, g['slug']))), timeout=600)
        if r.returncode != 0 or 'folder deleted' not in r.stdout:
            job.event('fail', '%s: the folder was not deleted: %s' % (g['slug'], r.stderr[-200:]))
            failed.append(g['slug'])
            continue
        freed += g['size'] or 0
        job.event('ok', '%s deleted (%.2f GB)' % (g['slug'], (g['size'] or 0) / 1e9))
    try:
        status(refresh=True, only=[])
    except Exception as e:  # noqa: BLE001
        job.log('Deck list not read again: %s' % e)
    if failed:
        raise RuntimeError('%d of %d folder(s) were not deleted: %s' % (len(failed), len(targets),
                                                                        ', '.join(failed)))
    job.event('ok', '%d game(s) deleted, %.2f GB freed; they stay marked as removed, so a resend '
                    'from another program does not bring them back' % (len(targets), freed / 1e9))
    return {'freed': freed}


# -- cópias de segurança ----------------------------------------------------------------------------
def backups(slug=None):
    """As cópias em <data_dir>/backups (<pasta do jogo>-<data>.tar), as mais recentes primeiro."""
    d = config.data_dir('backups')
    out = []
    for n in sorted(os.listdir(d), reverse=True):
        m = re.match(r'(.+)-(\d{8}-\d{6})\.tar$', n)
        if not m or (slug and m.group(1) != slug):
            continue
        p = os.path.join(d, n)
        try:
            with tarfile.open(p) as t:
                names = t.getnames()
        except (OSError, tarfile.TarError):
            names = []
        out.append({'file': n, 'slug': m.group(1), 'at': datetime.datetime.strptime(
            m.group(2), '%Y%m%d-%H%M%S').isoformat(), 'size': os.path.getsize(p),
            'entries': len(names), 'saves': sum(1 for x in names if '/00000001/' in x),
            'settings': [x for x in names if x.endswith('.toml') and '/' not in x]})
    return out


@exclusive
def restore_job(job, slug, file):
    """Põe uma cópia de volta na pasta do jogo no Deck (o jogo tem de estar instalado)."""
    d = config.data_dir('backups')
    path = os.path.join(d, os.path.basename(file))
    if not os.path.isfile(path) or not os.path.basename(file).startswith(slug + '-'):
        raise RuntimeError('unknown backup: %s' % file)
    with tarfile.open(path) as t:  # só caminhos relativos dentro da pasta do jogo
        for m in t.getmembers():
            if m.name.startswith(('/', '..')) or '/../' in m.name or m.issym() or m.islnk():
                raise RuntimeError('the backup has a path outside the game folder: %s' % m.name)
    dk = Deck()
    ok, err = dk.reachable(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    b = busy(dk)
    if b and not b['gestor']:
        raise RuntimeError('You are playing on the Deck: nothing was restored')
    data = dk.listing(light=True)
    g = next((x for x in data['games'] if x['slug'] == slug), None)
    if not g:
        raise RuntimeError('%s is not installed on the Deck: install it first' % slug)
    job.event('step', 'Restoring %s into %s' % (os.path.basename(path), g['path']))
    with open(path, 'rb') as f:
        r = subprocess.run(dk.d.ssh_cmd('tar -xf - -C %s' % q(g['path'])), stdin=f,
                           capture_output=True, timeout=1800, creationflags=jobs.CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError('The restore failed: %s' % r.stderr.decode(errors='replace')[-300:])
    job.event('ok', 'Backup restored (%.1f MB)' % (os.path.getsize(path) / 1e6))
    status(refresh=True)
    return {'restored': path}


# -- relatórios a partir do Deck: o que o Deck sabe do jogo, e uma captura lá ------------------------
# -- jogar ------------------------------------------------------------------------------------------
@exclusive
def play_job(job, appid, title):
    """Arranca um jogo pelo Steam do Deck, depois de o Gestor fechar (e de o Steam voltar, se a
    biblioteca acabou de ser atualizada)."""
    dk = Deck()
    gid = gestor_appid()
    t0 = time.time()
    while True:
        out = dk.ssh('pgrep -af "[S]teamLaunch AppId=" || true; pgrep -x steam >/dev/null && '
                     'ps -o etimes= -p "$(pgrep -o -x steam)" || echo none', timeout=30).stdout
        ids = {int(m) for m in re.findall(r'AppId=(\d+)', out)}
        steam_age = out.strip().splitlines()[-1].strip() if out.strip() else 'none'
        gestor_open = gid is not None and gid in ids
        other = ids - {gid}
        if other:
            raise RuntimeError('Another game is already running on the Deck: %s not started' % title)
        if not gestor_open and steam_age.isdigit() and int(steam_age) > 20:
            break
        if time.time() - t0 > 180:
            raise RuntimeError('The Deck was not ready to start the game (%s)' % (
                'the Manager is still open' if gestor_open else 'Steam is not running'))
        job.sleep(3)
    gameid = (int(appid) << 32) | 0x02000000
    dk.ssh('DISPLAY=:0 nohup steam steam://rungameid/%d >/dev/null 2>&1 &' % gameid, timeout=30)
    job.event('ok', 'Started %s on the Deck' % title)
    return {'appid': appid}


# -- o plugin do Decky ---------------------------------------------------------------------------
# Um nome por versão: um pedido de instalação à espera de confirmação aponta para o ficheiro e o seu
# sha256; trocá-lo por baixo fazia a Decky falhar a meio (e já sem o plugin antigo).
PLUGIN_ZIP = '~/Downloads/gestor-rexnative-decky-%s.zip'
PLUGIN_NAME = 'Gestor ReXNative'  # o "name" do plugin.json: a Decky encontra o plugin por ele
# Instalar o ZIP pela Decky (o mesmo que "Instalar plugin a partir de um ZIP"): a API local da Decky,
# websocket em 127.0.0.1:1337 com o token de /auth/token, rota utilities/install_plugin. A Decky só tem
# UMA ligação de cada vez: a deste script tira o lugar à da interface do Deck (que volta sozinha 5 s
# depois), e a janela "instalar?" vem para aqui em vez de aparecer no ecrã. Quem carregou no botão já
# escolheu: o script confirma o pedido (utilities/confirm_plugin_install) e a Decky instala-o.
ASK_INSTALL = r'''
import asyncio, json, sys, aiohttp
path, name, version, sha, kind = sys.argv[1:6]
async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get('http://127.0.0.1:1337/auth/token') as r:
            tok = await r.text()
        async with s.ws_connect('http://127.0.0.1:1337/ws?auth=' + tok) as ws:
            await ws.send_json({'type': 0, 'id': 1, 'route': 'utilities/install_plugin',
                                'args': ['file://' + path, name, version, sha, int(kind)]})
            while True:
                msg = await asyncio.wait_for(ws.receive(), 120)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    print('CLOSED', flush=True); return
                d = json.loads(msg.data)
                if d.get('event') == 'loader/add_plugin_install_prompt':  # tipo 5 na Decky 3.3
                    rid = (d.get('args') or [None, None, None])[2]
                    print('REQUEST', rid, flush=True)
                    await ws.send_json({'type': 0, 'id': 2, 'route': 'utilities/confirm_plugin_install',
                                        'args': [rid]})
                elif d.get('id') == 1 and d.get('type') == -1:
                    print('ERROR', d.get('error'), flush=True); return
                elif d.get('id') == 2 and d.get('type') in (1, -1):
                    print('INSTALLED' if d['type'] == 1 else 'ERROR %s' % d.get('error'), flush=True); return
asyncio.run(main())
'''


@exclusive
def plugin_job(job, prompt=True):
    """O plugin do Decky que está no PC (gestor/static/deck-plugin.zip) vai para ~/Downloads do Deck
    e, com prompt, a Decky pede no Deck para o instalar (ou atualizar)."""
    import hashlib
    from . import versions
    path = os.path.join(config.ROOT, 'gestor', 'static', 'deck-plugin.zip')
    data = open(path, 'rb').read()
    version = versions.plugin_latest() or 'dev'
    dk = Deck()
    ok, err, line = dk.check(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    target = PLUGIN_ZIP % version
    r = dk.ssh('mkdir -p ~/Downloads && f=%s && { [ -s "$f" ] || cat > "$f"; } && echo "$HOME"' % target,
               input_bytes=data, timeout=60)
    if r.returncode != 0:
        raise RuntimeError('Could not copy the plugin: %s' % r.stderr[-200:])
    home = r.stdout.strip().splitlines()[-1]
    remote = target.replace('~', home, 1)
    # O que está no Deck com este nome é o que conta (uma versão já lá posta não é trocada).
    r2 = dk.ssh('sha256sum %s' % q(remote), timeout=30)
    sha = (r2.stdout.split() or [''])[0] or hashlib.sha256(data).hexdigest()
    job.event('ok', 'Decky plugin v%s copied to %s' % (version, remote))
    if not prompt:
        return {'path': remote, 'version': version}
    b = busy_from(line)
    if b and not b['gestor']:
        job.event('info', 'A game is open on the Deck: no install window now (install it from Decky > '
                          'Developer > Install Plugin from ZIP File, or press Update again later)')
        return {'path': remote, 'version': version, 'prompt': False}
    seen = (state.get('deck', 'plugin') or {}).get('version')
    r = dk.ssh('python3 - %s %s %s %s %d' % (q(remote), q(PLUGIN_NAME), q(version), sha, 2 if seen else 0),
               input_text=ASK_INSTALL, timeout=60)
    job.log((r.stdout + r.stderr).strip())
    if 'INSTALLED' not in r.stdout:
        raise RuntimeError('Decky did not install it (%s): install it from Decky > Developer > '
                           'Install Plugin from ZIP File (%s)' % ((r.stdout + r.stderr).strip()[-200:], remote))
    plug = state.get('deck', 'plugin') or {}
    state.update('deck', 'plugin', {'version': version, 'at': time.time(), 'before': plug.get('version')})
    job.event('ok', 'Decky %s the plugin v%s on the Deck' % ('updated' if seen else 'installed', version))
    return {'path': remote, 'version': version, 'installed': True}


def _fetch(dk, path):
    r = subprocess.run(dk.d.ssh_cmd('cat %s' % q(path)), capture_output=True, timeout=120,
                       creationflags=jobs.CREATE_NO_WINDOW)
    return r.stdout if r.returncode == 0 else None


def evidence(job, dk, g, dest):
    """Copia para dest o que o Deck tem do jogo: o registo mais recente (e o anterior), as
    definições que o jogo usa lá e as capturas do Steam (Steam + R1) das últimas 24 h."""
    import io
    os.makedirs(dest, exist_ok=True)
    out = {'logs': [], 'settings': None, 'screenshots': []}
    name = (g.get('exe') or '')[:-4]
    sc = g.get('shortcut') or {}
    # Uma ligação: a lista dos ficheiros (os 2 registos mais recentes, as definições, as capturas do
    # Steam das últimas 24 h) vai para um tar, que chega pelo stdout.
    script = '{ cd %s && ls -t logs/*.log 2>/dev/null | head -2 | sed "s|^|$PWD/|"; ' % q(g['path'])
    if name:
        script += '[ -f %s ] && echo "$PWD/%s"; ' % (q(name + '.toml'), name + '.toml')
    if sc.get('appid'):
        script += ('find ~/.local/share/Steam/userdata/*/760/remote/%d/screenshots -maxdepth 1 -name "*.jpg" '
                   '-mmin -1440 -printf "%%T@ %%p\\n" 2>/dev/null | sort -rn | head -3 | cut -d" " -f2-; '
                   % int(sc['appid']))
    script += '} | tar -cf - -P -T - 2>/dev/null'
    r = subprocess.run(dk.d.ssh_cmd(script), capture_output=True, timeout=180,
                       creationflags=jobs.CREATE_NO_WINDOW)
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
            for m in t.getmembers():
                if not m.isfile():
                    continue
                data = t.extractfile(m).read()
                base = posixpath.basename(m.name)
                if base.endswith('.log'):
                    p, key = os.path.join(dest, 'deck-' + base), 'logs'
                elif base.endswith('.toml'):
                    p, key = os.path.join(dest, 'deck-' + base), 'settings'
                else:
                    p, key = os.path.join(dest, 'steam-' + base), 'screenshots'
                with open(p, 'wb') as f:
                    f.write(data)
                if key == 'settings':
                    out['settings'] = p
                else:
                    out[key].append(p)
    except tarfile.TarError as e:
        job.log('Deck files: %s (%s)' % (e, r.stderr.decode(errors='replace')[-200:]))
    job.event('ok', 'From the Deck: %d log(s), %s, %d Steam screenshot(s)' % (
        len(out['logs']), 'the settings' if out['settings'] else 'no settings', len(out['screenshots'])))
    return out


@exclusive
def capture(job, dk, g, dest, seconds=40):
    """Abre o jogo no Deck pelo Steam com o pedido de captura do renderizador (try.flags, como o
    `rexnative deck --try`), captura aos `seconds` s, guarda as imagens e o registo em dest e fecha
    o jogo. Com o Gestor aberto também dá (o Steam passa para o jogo e volta)."""
    sc = g.get('shortcut') or {}
    if not sc.get('appid'):
        raise RuntimeError('the game is not in the Steam library yet: quit the Manager so it gets added, then try again')
    name = (g.get('exe') or '')[:-4]
    home = dk.ssh('echo $HOME', timeout=20).stdout.strip() or '/home/deck'
    path = g['path'] if g['path'].startswith('/') else posixpath.join(home, g['path'])
    cap = posixpath.join(path, 'capture-gestor')
    wine_cap = 'Z:' + cap.replace('/', chr(92))
    flags = ('--rexnative_capture_dir=%s --rexnative_capture_xenos=false --rexnative_capture_shown=true '
             '--rexnative_d3d_stats_frames=120' % wine_cap)
    exe_re = re.escape(name) + r'\.exe --log'
    dk.ssh('rm -rf %s && mkdir -p %s && cd %s && printf "%%s\n" %s > try.flags' % (
        q(cap), q(cap), q(path), q(flags)), timeout=30)
    gameid = (int(sc['appid']) << 32) | 0x02000000
    job.event('step', 'Opening %s on the Deck for the capture (%d s; it closes by itself)' % (g.get('title') or g['slug'], seconds))
    # O ecrã aceso durante a captura (o Game Mode apaga-o sem ninguém a mexer: um jogo a 1 frame/s).
    dk.ssh('XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1); export DISPLAY=:0 XAUTHORITY=$XA; '
           'xdotool key shift; (for i in $(seq 1 %d); do sleep 20; xdotool key shift; done) '
           '>/dev/null 2>&1 < /dev/null & disown; true' % (seconds // 20 + 3), timeout=30)
    saved = []
    try:
        dk.ssh('DISPLAY=:0 nohup steam steam://rungameid/%d >/dev/null 2>&1 & true' % gameid, timeout=30)
        job.sleep(seconds)
        dk.ssh('touch %s/capture.request' % q(cap), timeout=20)
        job.sleep(5)
        running = 'yes' in dk.ssh('pgrep -f %s >/dev/null && echo yes || echo no' % q(exe_re), timeout=20).stdout
        logrel = dk.ssh('cd %s && find logs -maxdepth 1 -name "*.log" -newer try.flags -printf "%%T@ %%p\n" '
                        '2>/dev/null | sort -n | tail -1 | cut -d" " -f2-' % q(path), timeout=20).stdout.strip()
        if logrel:
            data = _fetch(dk, posixpath.join(path, logrel))
            if data:
                p = os.path.join(dest, 'deck-captura-' + posixpath.basename(logrel))
                open(p, 'wb').write(data)
                saved.append(p)
        shots = dk.ssh('cd %s && ls *.png 2>/dev/null; true' % q(cap), timeout=20).stdout.split()
        for s in shots:
            if 'xenos' in s:
                continue
            data = _fetch(dk, posixpath.join(cap, s))
            if data:
                p = os.path.join(dest, 'deck-captura-' + s)
                open(p, 'wb').write(data)
                saved.append(p)
    finally:
        dk.ssh('p=$(pgrep -f %s); [ -n "$p" ] && kill $p; rm -f %s/try.flags; true' % (q(exe_re), q(path)), timeout=30)
    pngs = [p for p in saved if p.endswith('.png')]
    job.event('ok' if pngs else 'fail', 'Capture on the Deck: %s%s' % (
        ', '.join(os.path.basename(p) for p in pngs) or 'no image (did the game start?)',
        '' if running else ' (the game was no longer running at %d s)' % seconds))
    return saved
