"""Gestor ReXNative no menu rápido (Decky): pergunta pelos pedidos e pelo espaço do Deck a quem faz o
trabalho: a app do PC, com o token que o Gestor no Deck já tem (~/.local/share/gestor-rexnative/
gestor.conf, escrito pela app do PC quando o instalou), ou o próprio Deck (o modo Sem PC, em
127.0.0.1:8370), conforme o ficheiro mode ao lado. Corre como o utilizador deck; não guarda nada."""
import asyncio
import hashlib
import json
import os
import urllib.error
import urllib.request

import decky

SHARE = os.path.join(decky.DECKY_USER_HOME, '.local', 'share', 'gestor-rexnative')
CONF = os.path.join(SHARE, 'gestor.conf')
# pc, local ou auto: quem faz o trabalho (escrito pelo serviço do Deck ou pela app do PC, nunca no
# gestor.conf, que o PC reescreve).
MODE = os.path.join(SHARE, 'mode')
LOCAL = 'http://127.0.0.1:8370'  # o modo Sem PC: o serviço no próprio Deck


def _version():
    """A versão deste plugin (o package.json que vai no ZIP): a app do PC avisa quando há outra."""
    v = getattr(decky, 'DECKY_PLUGIN_VERSION', None)
    if v:
        return v
    try:
        with open(os.path.join(decky.DECKY_PLUGIN_DIR, 'package.json'), encoding='utf-8') as f:
            return json.load(f).get('version') or ''
    except (OSError, ValueError, AttributeError):
        return ''


VERSION = _version()
NAME = 'Gestor ReXNative'  # o "name" do plugin.json: a Decky encontra o plugin por ele
# Um nome por versão (como a app do PC): um pedido de instalação à espera aponta para o ficheiro e
# o seu sha256, e trocá-lo por baixo fazia a instalação falhar.
ZIP = os.path.join(decky.DECKY_USER_HOME, 'Downloads', 'gestor-rexnative-decky-%s.zip')


def _conf():
    """Os endereços do PC e o token deste Deck (gestor.conf, escrito pela app do PC; num Deck sem PC,
    URLS vazio e TOKEN="local")."""
    urls, token = [], ''
    try:
        with open(CONF, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('URLS='):
                    urls = line[5:].strip('"').split()
                elif line.startswith('TOKEN='):
                    token = line[6:].strip('"')
    except OSError:
        pass
    return urls, token


def _mode(urls):
    """O modo escolhido: o ficheiro mode; sem ele (ou ilegível), o PC se há moradas do PC, senão o Deck."""
    try:
        with open(MODE, encoding='utf-8') as f:
            m = f.read().strip()
    except (OSError, ValueError):
        m = ''
    if m in ('pc', 'local', 'auto'):
        return m
    return 'pc' if urls else 'local'


def _servers():
    """A quem perguntar, por ordem (pc: o PC; local: este Deck; auto: o PC, depois este Deck), o token
    e o modo."""
    urls, token = _conf()
    mode = _mode(urls)
    if mode == 'local':
        urls = [LOCAL]
    elif mode == 'auto':
        urls = [u for u in urls if u != LOCAL] + [LOCAL]
    return urls, token, mode


def vkey(v):
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except ValueError:
        return (0,)


class PcError(ConnectionError):
    """The PC app gave no usable answer, and why (the panel says it in words): 'unreachable' (the PC
    is off or asleep, or the app is closed), 'unpaired' (it does not know this Deck's token),
    'refused' (it does not accept the home network), 'login' (it waits for the GitHub sign-in),
    'error' (it answered with something else)."""

    def __init__(self, text, reason='unreachable'):
        super().__init__(text)
        self.reason = reason


REASONS = {401: 'unpaired', 403: 'refused', 428: 'login'}


def _detail(e):
    """What the PC app said when it refused (the "detail" of its JSON, or its text)."""
    try:
        body = e.read().decode('utf-8', 'replace').strip()
    except Exception:  # noqa: BLE001
        body = ''
    try:
        body = str(json.loads(body).get('detail') or body)
    except (ValueError, AttributeError):
        pass
    return (body or 'HTTP %s' % e.code)[:200]


def _work(w):
    """pc_work of /api/remote/home (the PC app from 1.19): the jobs building or investigating now, how
    many wait and a pending restart. None with an older app, which does not send it."""
    if not isinstance(w, dict):
        return None
    try:
        running = [{k: r.get(k) for k in ('title', 'kind', 'lane', 'game', 'for_s')}
                   for r in (w.get('running') or []) if isinstance(r, dict)]
        return {'running': running[:4], 'queued': int(w.get('queued') or 0), 'restart': bool(w.get('restart'))}
    except (TypeError, ValueError):
        return None


def _free(space, key):
    """The bytes free on that storage of the Deck (None when the PC did not say)."""
    v = space.get(key) if isinstance(space, dict) else None
    return v.get('free') if isinstance(v, dict) else None


ORDER_KEYS = ('id', 'title', 'name', 'status', 'stage', 'error', 'progress', 'created', 'started', 'ended',
              'kind', 'last', 'report', 'waiting')


def _orders(items, limit=12):
    """The requests for the panel: every one in progress (the oldest first: it is the one the PC is
    on), then the ones that ended last. By when they ended, not by when they were asked for: a long
    build that ends after a dozen newer requests must still be seen ending, for its notice."""
    items = [o for o in items or [] if isinstance(o, dict)]
    live = [o for o in items if o.get('status') in ('running', 'queued')]
    live.sort(key=lambda o: (o.get('status') != 'running', str(o.get('created') or '')))
    done = [o for o in items if o.get('status') not in ('running', 'queued')]
    done.sort(key=lambda o: str(o.get('ended') or o.get('created') or ''), reverse=True)
    return [{k: o.get(k) for k in ORDER_KEYS} for o in live[:limit] + done[:limit]], len(live)


# Instalar o ZIP pela Decky (o mesmo que "Instalar plugin a partir de um ZIP"): a API local da Decky,
# websocket em 127.0.0.1:1337 com o token de /auth/token. A Decky só tem UMA ligação de cada vez: a
# deste script tira o lugar à da interface do Deck (que volta sozinha 5 s depois), e a janela "instalar?"
# que a Decky mostraria vem para aqui. Quem carregou em Atualizar já escolheu: o script confirma esse
# pedido (utilities/confirm_plugin_install) e a Decky instala e recarrega o plugin.
INSTALL_SCRIPT = r"""
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
"""
LOG = os.path.join(decky.DECKY_USER_HOME, '.local', 'share', 'gestor-rexnative', 'plugin-install.log')


def spawn_install(path, version, sha256):
    """O script num processo à parte (o python3 do sistema, que tem o aiohttp, com o ambiente limpo
    das bibliotecas do PyInstaller da Decky): instalar tira este plugin a correr, e o script tem de
    sobreviver a isso."""
    import subprocess
    env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME')}
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log = open(LOG, 'a')
    subprocess.Popen(['/usr/bin/python3', '-c', INSTALL_SCRIPT, path, NAME, version, sha256, '2'],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env, start_new_session=True)

class Plugin:
    good = None  # o endereço do PC que respondeu da última vez

    def _req(self, path, method='GET'):
        # Um Deck sem PC tem TOKEN="local" (e URLS vazio): está instalado.
        urls, token, _ = _servers()
        if not token:
            raise LookupError('sem Gestor')
        order = ([self.good] if self.good in urls else []) + [u for u in urls if u != self.good]
        err = refusal = None
        for u in order:
            # O serviço do Deck não usa token: o do PC fica para o PC.
            headers = {} if u == LOCAL else {'X-Gestor-Token': token}
            if method != 'GET':
                headers['X-Gestor'] = '1'
            req = urllib.request.Request(u + path, method=method, headers=headers,
                                         data=b'{}' if method != 'GET' else None)
            if method != 'GET':
                req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(req, timeout=4) as r:
                    data = json.loads(r.read().decode('utf-8', 'replace'))
                self.good = u
                return data
            except urllib.error.HTTPError as e:
                # The PC app is there and refused: that says more than the address that did not
                # answer. The next address may still be the one it accepts.
                if refusal is None:
                    refusal = PcError(_detail(e), REASONS.get(e.code, 'error'))
            except Exception as e:  # noqa: BLE001 - tenta o endereço seguinte
                err = e
        raise refusal or PcError(str(err) if err else 'no address of the PC')

    def _status(self):
        # setting: the mode chosen (the mode file); mode: who answered (home.mode, "pc" or "local").
        setting = _servers()[2]
        try:
            h = self._req('/api/remote/home?beat=false' + ('&plugin=' + VERSION if VERSION else ''))
        except LookupError:
            return {'installed': False, 'version': VERSION}
        except Exception as e:  # noqa: BLE001
            return {'installed': True, 'online': False, 'error': str(e)[:200], 'version': VERSION,
                    'reason': getattr(e, 'reason', 'unreachable'), 'setting': setting}
        if not isinstance(h, dict):
            return {'installed': True, 'online': False, 'error': 'unexpected answer', 'version': VERSION,
                    'reason': 'error', 'setting': setting}
        space = (h.get('deck') or {}).get('space')
        orders, live = _orders(h.get('orders'))
        latest = h.get('plugin_latest')
        play = sorted((g for g in h.get('games') or [] if g.get('appid') and g.get('in_library') and g.get('complete', True)),
                      key=lambda g: -(g.get('last_played') or g.get('mtime') or 0))[:8]
        # What an older app on the PC does not send (pc_work, ssh, the microSD) goes as None: the
        # panel leaves that part out.
        return {'installed': True, 'online': True, 'pc': h.get('pc'), 'app_version': h.get('version'),
                'mode': 'local' if h.get('mode') == 'local' else 'pc', 'setting': setting,
                'deck_free': _free(space, 'interno'), 'sd_free': _free(space, 'sd'),
                'ssh': h.get('ssh'), 'pc_work': _work(h.get('pc_work')),
                'orders': orders, 'active': live, 'pending': h.get('pending') or {},
                'gestor_appid': h.get('gestor_appid'),
                'version': VERSION, 'plugin_latest': latest, 'gestor_open': bool(h.get('gestor_open')),
                'games': [{'title': g.get('title'), 'appid': g.get('appid'), 'last_played': g.get('last_played')}
                          for g in play],
                'plugin_update': bool(latest and VERSION and vkey(latest) > vkey(VERSION))}

    async def status(self):
        return await asyncio.get_event_loop().run_in_executor(None, self._status)

    async def flush(self):
        """Põe na biblioteca os jogos à espera (a app do PC fecha o Steam uma vez)."""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._req('/api/remote/closed', method='POST'))
        except Exception as e:  # noqa: BLE001
            return {'error': str(e)[:200]}

    def _download(self):
        """O ZIP do plugin que está no PC (ou no serviço do Deck), para ~/Downloads (onde a Decky o vai
        buscar). (versão, sha256)"""
        h = self._req('/api/remote/home?beat=false')
        version = h.get('plugin_latest') or 'dev'
        urls = _servers()[0]
        order = ([self.good] if self.good in urls else []) + [u for u in urls if u != self.good]
        err = None
        for u in order:
            try:
                with urllib.request.urlopen(u + '/static/deck-plugin.zip', timeout=20) as r:
                    data = r.read()
                path = ZIP % version
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if os.path.exists(path):  # já cá estava: é esse que conta
                    with open(path, 'rb') as f:
                        data = f.read()
                else:
                    with open(path, 'wb') as f:
                        f.write(data)
                return version, hashlib.sha256(data).hexdigest()
            except Exception as e:  # noqa: BLE001 - o endereço seguinte
                err = e
        raise ConnectionError(str(err))

    async def update(self):
        """O botão Atualizar (já confirmado no painel): traz o plugin novo (do PC ou do Deck) e a Decky instala-o e
        recarrega o painel uns segundos depois."""
        try:
            version, sha = await asyncio.get_event_loop().run_in_executor(None, self._download)
            spawn_install(ZIP % version, version, sha)
            return {'ok': True, 'version': version}
        except Exception as e:  # noqa: BLE001
            return {'error': str(e)[:200]}

    async def _main(self):
        decky.logger.info('Gestor ReXNative: a usar %s (modo %s)', CONF, _servers()[2])

    async def _unload(self):
        pass
