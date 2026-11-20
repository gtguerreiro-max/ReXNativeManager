"""Gestor ReXNative no menu rápido (Decky): pergunta à app do PC pelos pedidos e pelo espaço do Deck,
com o token que o Gestor no Deck já tem (~/.local/share/gestor-rexnative/gestor.conf, escrito pela
app do PC quando o instalou). Corre como o utilizador deck; não guarda nada."""
import asyncio
import hashlib
import json
import os
import urllib.request

import decky

CONF = os.path.join(decky.DECKY_USER_HOME, '.local', 'share', 'gestor-rexnative', 'gestor.conf')


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
    """Os endereços do PC e o token deste Deck (gestor.conf, escrito pela app do PC)."""
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


def vkey(v):
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except ValueError:
        return (0,)


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
        urls, token = _conf()
        if not token:
            raise LookupError('sem Gestor')
        order = ([self.good] if self.good in urls else []) + [u for u in urls if u != self.good]
        err = None
        for u in order:
            headers = {'X-Gestor-Token': token}
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
            except Exception as e:  # noqa: BLE001 - tenta o endereço seguinte
                err = e
        raise ConnectionError(str(err))

    def _status(self):
        try:
            h = self._req('/api/remote/home?beat=false' + ('&plugin=' + VERSION if VERSION else ''))
        except LookupError:
            return {'installed': False}
        except Exception as e:  # noqa: BLE001
            return {'installed': True, 'online': False, 'error': str(e)[:200]}
        sp = ((h.get('deck') or {}).get('space') or {}).get('interno') or {}
        orders = [{k: o.get(k) for k in ('id', 'title', 'name', 'status', 'stage', 'error', 'progress', 'created',
                                         'kind', 'last', 'report')}
                  for o in (h.get('orders') or [])[:12]]
        latest = h.get('plugin_latest')
        play = sorted((g for g in h.get('games') or [] if g.get('appid') and g.get('in_library') and g.get('complete', True)),
                      key=lambda g: -(g.get('last_played') or g.get('mtime') or 0))[:8]
        return {'installed': True, 'online': True, 'pc': h.get('pc'), 'deck_free': sp.get('free'),
                'orders': orders, 'pending': h.get('pending') or {}, 'gestor_appid': h.get('gestor_appid'),
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
        """O ZIP do plugin que está no PC, para ~/Downloads (onde a Decky o vai buscar). (versão, sha256)"""
        h = self._req('/api/remote/home?beat=false')
        version = h.get('plugin_latest') or 'dev'
        urls, _ = _conf()
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
        """O botão Atualizar (já confirmado no painel): traz o plugin novo do PC e a Decky instala-o e
        recarrega o painel uns segundos depois."""
        try:
            version, sha = await asyncio.get_event_loop().run_in_executor(None, self._download)
            spawn_install(ZIP % version, version, sha)
            return {'ok': True, 'version': version}
        except Exception as e:  # noqa: BLE001
            return {'error': str(e)[:200]}

    async def _main(self):
        decky.logger.info('Gestor ReXNative: a usar %s', CONF)

    async def _unload(self):
        pass
