"""A ligação ao Steam Deck: perfis (endereço e chave), um teste que diz onde falha, a procura do
Deck na rede local, um vigia que vê de 20 em 20 s se ele responde, e o ajudante que liga o SSH no
Deck: o sshd do próprio utilizador deck na porta 2222 (sem sudo, só com a chave do PC), que pára
quando o Deck reinicia. A app serve setup.sh durante uns minutos na rede local e o utilizador corre
no Deck (Modo Desktop, Konsole):  curl -fsS http://<PC>:8765/setup.sh | bash"""
import concurrent.futures
import http.server
import ipaddress
import os
import re
import socket
import subprocess
import threading
import time

from . import config, jobs

SETUP_PORT = 8765
# O mesmo script que já pôs o SSH no Deck (pasta ~/.fromdust-sshd: a chave de anfitrião que lá está
# é a que o known_hosts do PC conhece; outra pasta faria uma chave nova e o PC recusava-a).
SETUP_SH = r'''#!/bin/bash
# Deixa o PC entrar neste Steam Deck por SSH sem palavra-passe e sem sudo: um servidor OpenSSH do
# próprio utilizador deck, na porta %(port)d, que só aceita a chave do PC. Pára quando o Deck
# reinicia (ou: kill $(cat ~/.fromdust-sshd/sshd.pid)). Feito pelo Gestor ReXNative.
set -e
pc=%(pc)s
mkdir -p ~/.ssh ~/.fromdust-sshd
chmod 700 ~/.ssh
key=$(curl -fsS "$pc/key.pub")
grep -qxF "$key" ~/.ssh/authorized_keys 2>/dev/null || echo "$key" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
cd ~/.fromdust-sshd
[ -f host_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -f host_ed25519
cat > sshd_config <<EOF
Port %(port)d
HostKey $HOME/.fromdust-sshd/host_ed25519
PidFile $HOME/.fromdust-sshd/sshd.pid
AuthorizedKeysFile $HOME/.ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM no
EOF
[ -f sshd.pid ] && kill "$(cat sshd.pid)" 2>/dev/null || true
/usr/bin/sshd -f "$HOME/.fromdust-sshd/sshd_config"
echo
echo "Done: the PC can now log in over SSH on port %(port)d."
ip -4 -o addr show | awk '!/ lo /{print "Deck IP: " $4}'
'''


def parse_host(spec):
    """'deck@steamdeck.local:2222' -> ('deck', 'steamdeck.local', 2222)."""
    spec = (spec or '').strip()
    port = 22
    m = re.search(r':(\d+)$', spec)
    if m:
        port = int(m.group(1))
        spec = spec[:m.start()]
    user, _, addr = spec.rpartition('@')
    return (user or 'deck'), addr, port


def make_host(user, addr, port):
    return '%s@%s%s' % (user, addr, '' if port == 22 else ':%d' % port)


def tcp_probe(addr, port, timeout=2.5):
    """('open', banner) | ('refused', '') | ('timeout', '') | ('unresolved', erro)."""
    try:
        ip = socket.getaddrinfo(addr, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except OSError as e:
        return 'unresolved', str(e)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        try:
            s.settimeout(2)
            banner = s.recv(128).decode('ascii', 'replace').strip()
        except OSError:
            banner = ''
        return 'open', banner
    except ConnectionRefusedError:
        return 'refused', ''
    except (socket.timeout, TimeoutError):
        return 'timeout', ''
    except OSError as e:
        return 'timeout', str(e)
    finally:
        s.close()


def _ssh(host, key, command, timeout=25, extra=()):
    user, addr, port = parse_host(host)
    cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-p', str(port)]
    if key:
        cmd += ['-i', os.path.expanduser(key)]
    cmd += list(extra) + ['%s@%s' % (user, addr), command]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 255, '', 'no answer in %d s' % timeout)


INFO_CMD = ('printf "host=%s\\n" "$(uname -n)"; . /etc/os-release 2>/dev/null; '
            'printf "os=%s\\n" "$PRETTY_NAME $VERSION_ID"; '
            'printf "battery=%s\\n" "$(cat /sys/class/power_supply/BAT1/capacity 2>/dev/null)"; '
            'printf "charging=%s\\n" "$(cat /sys/class/power_supply/BAT1/status 2>/dev/null)"; '
            'printf "uptime=%s\\n" "$(uptime -p)"; '
            'printf "playing=%s\\n" "$(pgrep -af "[S]teamLaunch AppId=" | grep -o "AppId=[0-9]*" | head -1)"; '
            'printf "steam=%s\\n" "$(pgrep -x steam >/dev/null && echo 1)"; '
            'printf "ip=%s\\n" "$(ip -4 -o addr show | awk \'!/ lo /{print $4}\' | tr \'\\n\' \' \')"')


def public_key(key):
    p = os.path.expanduser(key or '') + '.pub'
    return open(p, encoding='utf-8').read().strip() if os.path.exists(p) else None


def diagnose(host=None, key=None):
    """O teste passo a passo: {'ok', 'steps': [{name, ok, text}], 'fix': texto, 'info': {...}}."""
    cfg = config.load()
    host = host or cfg['deck_host']
    key = key if key is not None else cfg['deck_key']
    user, addr, port = parse_host(host)
    steps = []
    out = {'host': host, 'key': key, 'ok': False, 'steps': steps, 'fix': None, 'info': None}
    if not addr:
        out['fix'] = 'Enter the Deck address (e.g. deck@steamdeck.local:22, or its IP address).'
        return out
    kpath = os.path.expanduser(key) if key else None
    if kpath and not os.path.exists(kpath):
        steps.append({'name': 'SSH key', 'ok': False, 'text': 'does not exist: %s' % kpath})
        out['fix'] = "Enter the right private key (its public key must be in the Deck's ~/.ssh/authorized_keys)."
        return out
    steps.append({'name': 'SSH key', 'ok': True, 'text': kpath or "(ssh's default)"})
    state, extra = tcp_probe(addr, port)
    if state == 'unresolved':
        steps.append({'name': 'Address', 'ok': False, 'text': 'cannot find %s (%s)' % (addr, extra)})
        out['fix'] = 'That name does not exist on the network: use the Deck IP or "Search the network".'
        return out
    if state == 'timeout':
        alt = tcp_probe(addr, 22, 1.5)[0] if port != 22 else None
        steps.append({'name': 'Network', 'ok': False, 'text': 'no answer from %s:%d' % (addr, port)})
        out['fix'] = ('The Deck is not responding: it is off or asleep, off the network, or its IP changed '
                      '(use "Search the network").' + (' Port 22 does not answer either.' if alt == 'timeout' else ''))
        return out
    if state == 'refused':
        steps.append({'name': 'Network', 'ok': True, 'text': '%s answers' % addr})
        steps.append({'name': 'SSH on port %d' % port, 'ok': False,
                      'text': 'connection refused: the SSH server is not running'})
        out['fix'] = ("The Deck is on but has no SSH on port %d (the deck user's sshd stops "
                      'when the Deck restarts). Use "Turn on SSH on the Deck" and run the command it '
                      'shows in Konsole on the Deck (Desktop Mode).' % port)
        out['needs_setup'] = True
        return out
    steps.append({'name': 'Network', 'ok': True, 'text': '%s:%d answers' % (addr, port)})
    steps.append({'name': 'SSH server', 'ok': extra.startswith('SSH-'), 'text': extra or '(no banner)'})
    r = _ssh(host, key, INFO_CMD)
    err = (r.stderr or '').strip()
    if r.returncode != 0:
        if 'Host key verification failed' in err or 'REMOTE HOST IDENTIFICATION HAS CHANGED' in err:
            changed = 'CHANGED' in err
            steps.append({'name': 'Deck identity', 'ok': False,
                          'text': 'the host key %s' % ('CHANGED' if changed else 'is unknown')})
            out['fix'] = ('The PC does not know this Deck at this address yet: "Trust this Deck" saves '
                          'its key.' if not changed else
                          'The host key changed since last time (the Deck was reinstalled, or another '
                          'device has this IP). If you are sure it is your Deck, use "Forget the old '
                          'key and trust".')
            out['trust'] = 'changed' if changed else 'new'
            return out
        if 'Permission denied' in err:
            steps.append({'name': 'Authentication', 'ok': False, 'text': 'the key is not accepted'})
            out['fix'] = ('The Deck does not accept this key: "Turn on SSH on the Deck" adds it to the '
                          "Deck's ~/.ssh/authorized_keys (or add it by hand).")
            out['public_key'] = public_key(key)
            out['needs_setup'] = True
            return out
        steps.append({'name': 'SSH session', 'ok': False, 'text': err[-300:] or 'exit code %d' % r.returncode})
        out['fix'] = 'SSH failed: see the message above.'
        return out
    info = dict(l.split('=', 1) for l in r.stdout.splitlines() if '=' in l)
    steps.append({'name': 'Authentication', 'ok': True, 'text': 'logged in as %s on %s' % (user, info.get('host'))})
    py = _ssh(host, key, 'python3 -c "print(1)"', timeout=15)
    steps.append({'name': 'python3 on the Deck', 'ok': py.returncode == 0 and py.stdout.strip() == '1',
                  'text': 'yes' if py.returncode == 0 else 'no (the game list needs it)'})
    out.update(ok=True, info=info)
    return out


def trust(host, forget_old=False):
    """Guarda a chave de anfitrião do Deck no known_hosts (accept-new); forget_old tira antes a
    antiga desse endereço (só por pedido explícito do utilizador)."""
    user, addr, port = parse_host(host)
    if forget_old:
        name = addr if port == 22 else '[%s]:%d' % (addr, port)
        subprocess.run(['ssh-keygen', '-R', name], capture_output=True, creationflags=jobs.CREATE_NO_WINDOW)
    r = _ssh(host, config.load()['deck_key'], 'true', extra=('-o', 'StrictHostKeyChecking=accept-new'))
    return {'ok': r.returncode == 0, 'text': (r.stderr or r.stdout or '').strip()[-300:]}


# -- procurar na rede ----------------------------------------------------------------------------
def local_ipv4s():
    ips = set()
    route = None
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # a interface da rota por omissão (não envia nada)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.0.2.1', 9))
        route = s.getsockname()[0]
        ips.add(route)
        s.close()
    except OSError:
        pass
    out = []
    for ip in ips:
        a = ipaddress.ip_address(ip)
        # 172.16-31: quase sempre as redes virtuais do Docker, WSL ou Hyper-V; só conta a da rota por
        # omissão (uma rede de casa nessa gama também existe).
        if a.is_private and not a.is_loopback and not ip.startswith('169.254.') and \
                not (ip.startswith('172.') and ip != route):
            out.append(ip)
    return sorted(out) or sorted(i for i in ips if not i.startswith('127.'))


def discover(ports=(2222, 22)):
    """Os aparelhos da rede local (a /24 de cada IP privado do PC, e steamdeck.local) com um
    servidor SSH; para cada um, se a chave entra e se é SteamOS."""
    cfg = config.load()
    user, _, cur_port = parse_host(cfg['deck_host'])
    ports = tuple(dict.fromkeys((cur_port,) + tuple(ports)))
    hosts = set()
    for ip in local_ipv4s():
        net = ipaddress.ip_network(ip + '/24', strict=False)
        hosts.update(str(h) for h in net.hosts() if str(h) != ip)
    try:
        hosts.add(socket.gethostbyname('steamdeck.local'))
    except OSError:
        pass
    found = []

    def probe(h, p):
        st, banner = tcp_probe(h, p, 0.6)
        return (h, p, banner) if st == 'open' else None
    with concurrent.futures.ThreadPoolExecutor(128) as ex:
        for r in ex.map(lambda hp: probe(*hp), [(h, p) for h in hosts for p in ports]):
            if r:
                found.append(r)
    out = []
    for h, p, banner in sorted(found, key=lambda x: (tuple(int(n) for n in x[0].split('.')), x[1])):
        host = make_host(user, h, p)
        name = None
        try:
            name = socket.gethostbyaddr(h)[0]
        except OSError:
            pass
        r = _ssh(host, cfg['deck_key'], '. /etc/os-release; echo "$ID $(uname -n)"', timeout=12)
        login = r.returncode == 0
        os_id = r.stdout.strip() if login else ''
        out.append({'host': host, 'addr': h, 'port': p, 'banner': banner, 'name': name,
                    'login': login, 'steamos': os_id.startswith('steamos'),
                    'hostname': os_id.split(' ', 1)[1] if ' ' in os_id else None,
                    'error': None if login else (r.stderr or '').strip()[-160:]})
    return {'scanned': len(hosts), 'networks': local_ipv4s(), 'found': out}


# -- o ajudante que liga o SSH no Deck -----------------------------------------------------------
class _Setup:
    server = None
    until = 0
    lock = threading.Lock()


def setup_state():
    if _Setup.server and time.time() > _Setup.until:
        stop_setup()
    if not _Setup.server:
        return {'running': False}
    ip = _Setup.server.server_address[0]
    return {'running': True, 'until': _Setup.until, 'url': 'http://%s:%d/setup.sh' % (ip, SETUP_PORT),
            'command': 'curl -fsS http://%s:%d/setup.sh | bash' % (ip, SETUP_PORT)}


def start_setup(minutes=15):
    """Serve setup.sh e a chave pública do PC na rede local (só esses dois ficheiros) por
    `minutes` minutos. O Windows pode perguntar se deixa o Python receber ligações: é o utilizador
    que responde."""
    cfg = config.load()
    pub = public_key(cfg['deck_key'])
    if not pub:
        raise RuntimeError('public key %s.pub not found' % os.path.expanduser(cfg['deck_key']))
    ips = local_ipv4s()
    if not ips:
        raise RuntimeError('the PC has no IP on the local network')
    ip = ips[0]
    _, _, port = parse_host(cfg['deck_host'])
    script = SETUP_SH % {'pc': 'http://%s:%d' % (ip, SETUP_PORT), 'port': port}
    files = {'/setup.sh': script.encode('utf-8'), '/key.pub': (pub + '\n').encode('utf-8')}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = files.get(self.path.split('?')[0])
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    with _Setup.lock:
        stop_setup()
        srv = http.server.ThreadingHTTPServer((ip, SETUP_PORT), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _Setup.server = srv
        _Setup.until = time.time() + minutes * 60
    return setup_state()


def stop_setup():
    srv = _Setup.server
    _Setup.server = None
    if srv:
        threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()


# -- o vigia -----------------------------------------------------------------------------------
class Watcher:
    """Vê de 20 em 20 s se a porta SSH do Deck responde (só uma ligação TCP, nada corre no Deck).
    Quando o Deck aparece, on_online() corre uma vez (a app lê então a lista dos jogos)."""

    def __init__(self, on_online=None, every=20):
        self.state = {'online': None, 'checked': None, 'since': None, 'host': None, 'detail': None}
        self.on_online = on_online
        self.every = every
        self.wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def check_now(self):
        self.wake.set()

    failing_since = None

    def _follow(self, host):
        """The Deck got another address (DHCP) while the PC's settings keep the old one: after 2
        minutes without an answer, if the paired Deck's page reached this PC in the last 10 minutes
        from another address and the SSH port answers there, the settings take that address (the
        same user and port). Returns the new host, or None."""
        now = time.time()
        if self.failing_since is None:
            self.failing_since = now
            return None
        if now - self.failing_since < 120:
            return None
        try:
            from . import lan
            user, addr, port = parse_host(host)
            seen = sorted((d for d in lan.devices() if d.get('ip') and now - (d.get('last_seen') or 0) < 600
                           and 'deck' in (d.get('name') or '').lower()), key=lambda d: -(d.get('last_seen') or 0))
            for d in seen:
                ip = d['ip']
                if ip == addr or ip.startswith('127.') or ':' in ip:
                    continue
                if tcp_probe(ip, port, 2.5)[0] == 'open':
                    new = make_host(user, ip, port)
                    config.save({'deck_host': new})
                    self.failing_since = None
                    print('Deck: %s answers no more; the paired Deck is at %s now: using it' % (host, new),
                          flush=True)
                    return new
        except Exception:  # noqa: BLE001 - the watcher never stops
            pass
        return None

    def _loop(self):
        while True:
            try:
                host = config.load()['deck_host']
                _, addr, port = parse_host(host)
                st, _ = tcp_probe(addr, port, 2.5) if addr else ('unresolved', '')
                online = st == 'open'
                if not online:
                    moved = self._follow(host)
                    if moved:
                        host = moved
                        _, addr, port = parse_host(host)
                        st, _ = tcp_probe(addr, port, 2.5)
                        online = st == 'open'
                else:
                    self.failing_since = None
                was = self.state['online']
                if online != was or host != self.state['host']:
                    self.state['since'] = jobs.now()
                self.state.update(online=online, checked=jobs.now(), host=host, detail=st)
                if online and not was and self.on_online:
                    threading.Thread(target=self.on_online, daemon=True).start()
            except Exception as e:  # noqa: BLE001 - o vigia nunca pára
                self.state.update(online=False, detail=str(e))
            self.wake.wait(self.every)
            self.wake.clear()
