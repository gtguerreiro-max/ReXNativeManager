"""A app na rede de casa, para o Gestor no Steam Deck (o Modo Deck, /deck) e outros aparelhos.

Só quando está ligada (lan_enabled): um servidor por cada endereço privado deste PC (a app de
sempre continua em 127.0.0.1), e cada pedido de fora traz o token de um aparelho emparelhado
(cookie gestor_dev, HttpOnly). Os tokens guardam-se só como SHA-256, em <data_dir>/devices.json.

Emparelhar: "Instalar o Gestor no Deck" escreve o token no Deck por SSH (nada a escrever); outro
aparelho usa um código de 6 algarismos que a app do PC mostra durante 5 minutos."""
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import threading
import time

from . import config, connection, fsutil

COOKIE = 'gestor_dev'
_lock = threading.Lock()
_pair = {'code': None, 'until': 0.0, 'tries': 0}
_seen = {}  # id -> última vez gravada (last_seen grava-se no máximo de 5 em 5 min)


# -- aparelhos ------------------------------------------------------------------------------------
def _path():
    return os.path.join(config.data_dir(), 'devices.json')


def _load():
    try:
        with open(_path(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(data):
    fsutil.write_json(_path(), data, indent=1)


def _hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_device(name, kind='outro', ip=None):
    """Um aparelho novo; devolve (id, token). O token só existe aqui (guarda-se o hash)."""
    token = secrets.token_urlsafe(32)
    dev_id = secrets.token_hex(4)
    with _lock:
        data = _load()
        data[dev_id] = {'name': name[:60], 'kind': kind, 'hash': _hash(token),
                        'created': time.time(), 'last_seen': None, 'ip': ip}
        _save(data)
    return dev_id, token


def check(token, ip=None):
    """O aparelho do token (sem o hash), ou None."""
    if not token or len(token) > 200:
        return None
    h = _hash(token)
    with _lock:
        data = _load()
        for dev_id, d in data.items():
            if secrets.compare_digest(d.get('hash', ''), h):
                now = time.time()
                if now - _seen.get(dev_id, 0) > 300 or d.get('ip') != ip:
                    d['last_seen'] = now
                    d['ip'] = ip
                    _seen[dev_id] = now
                    _save(data)
                return dict({k: v for k, v in d.items() if k != 'hash'}, id=dev_id)
    return None


def devices():
    with _lock:
        data = _load()
    return [dict({k: v for k, v in d.items() if k != 'hash'}, id=i) for i, d in data.items()]


def revoke(dev_id):
    with _lock:
        data = _load()
        gone = data.pop(dev_id, None)
        _save(data)
    return gone is not None


def revoke_kind(kind):
    """Tira os aparelhos deste tipo (um Gestor reinstalado no Deck substitui o anterior)."""
    with _lock:
        data = _load()
        for i in [i for i, d in data.items() if d.get('kind') == kind]:
            data.pop(i)
        _save(data)


# -- código para emparelhar --------------------------------------------------------------------
def start_pairing(minutes=5):
    with _lock:
        _pair.update(code='%06d' % secrets.randbelow(1000000), until=time.time() + minutes * 60,
                     tries=0)
        return dict(_pair)


def pairing():
    with _lock:
        if _pair['code'] and time.time() < _pair['until']:
            return {'code': _pair['code'], 'left': int(_pair['until'] - time.time())}
    return {'code': None}


def claim(code, name, ip):
    """O token de um aparelho novo se o código estiver certo e a valer (5 tentativas)."""
    with _lock:
        ok = (_pair['code'] and time.time() < _pair['until'] and
              secrets.compare_digest(str(code).strip(), _pair['code']))
        if not ok:
            _pair['tries'] += 1
            if _pair['tries'] >= 5:
                _pair.update(code=None, until=0)
            return None
        _pair.update(code=None, until=0)
    return new_device(name or 'Device %s' % ip, 'outro', ip)[1]


# -- este PC na rede ----------------------------------------------------------------------------
def pc_name():
    return socket.gethostname()


def lan_ips():
    return [ip for ip in connection.local_ipv4s() if is_private(ip)]


def urls():
    """Por onde os aparelhos chegam a esta app: os endereços e o nome .local (mDNS)."""
    port = config.load()['port']
    return ['http://%s:%d' % (ip, port) for ip in lan_ips()] + [
        'http://%s.local:%d' % (pc_name(), port)]


def allowed_hosts():
    """Os Host aceites de fora (contra DNS rebinding): só os nomes e endereços deste PC."""
    name = pc_name().lower()
    return set(lan_ips()) | {name, name + '.local'}


def is_private(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private and not a.is_loopback and not a.is_link_local


def is_loopback(ip):
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


# -- os servidores da rede -------------------------------------------------------------------
class Servers:
    """Um uvicorn por cada endereço privado deste PC (o de 127.0.0.1 é o da app); vê de minuto a
    minuto se os endereços mudaram (DHCP) ou se a opção foi ligada ou desligada."""

    def __init__(self, app):
        self.app = app
        self.running = {}  # ip -> (server, thread)
        self.error = None
        self.wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def refresh(self):
        self.wake.set()

    def state(self):
        return {'enabled': bool(config.load().get('lan_enabled')), 'listening': sorted(self.running),
                'urls': urls(), 'error': self.error}

    def _start(self, ip):
        import uvicorn
        cfg = uvicorn.Config(self.app, host=ip, port=config.load()['port'], log_level='warning',
                             proxy_headers=False, lifespan='off')
        server = uvicorn.Server(cfg)
        t = threading.Thread(target=server.run, daemon=True, name='lan-%s' % ip)
        t.start()
        self.running[ip] = (server, t)

    def _stop(self, ip):
        server, t = self.running.pop(ip)
        server.should_exit = True
        t.join(10)

    def _loop(self):
        time.sleep(3)  # a app acaba de arrancar primeiro
        while True:
            try:
                want = set(lan_ips()) if config.load().get('lan_enabled') else set()
                for ip in set(self.running) - want:
                    self._stop(ip)
                for ip in want - set(self.running):
                    self._start(ip)
                time.sleep(2)
                # Um servidor que não arrancou (porta ocupada) sai do registo: tenta outra vez daqui
                # a um minuto.
                dead = [ip for ip, (_, t) in self.running.items() if not t.is_alive()]
                for ip in dead:
                    self.running.pop(ip)
                self.error = ('could not open port %d on %s' % (
                    config.load()['port'], ', '.join(dead))) if dead else None
            except Exception as e:  # noqa: BLE001 - o ciclo nunca pára
                self.error = str(e)
            self.wake.wait(60)
            self.wake.clear()
