"""Definições da app: as de origem (DEFAULTS) com as do utilizador por cima (config.json, ao lado
do repositório, fora do git: tem caminhos desta máquina)."""
import copy
import glob
import json
import os
import shutil
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get('GESTOR_CONFIG') or os.path.join(ROOT, 'config.json')

# Onde a app guarda tudo por omissão (cada pasta muda nas Definições): uma pasta na do utilizador.
BASE = os.path.join(os.path.expanduser('~'), 'ReXNativeManager')

DEFAULTS = {
    # Os itens do Internet Archive com os jogos de quem usa a app (o nome do item, a parte final de
    # https://archive.org/download/<item>, e um nome curto). Vazio: cada um põe os seus nas
    # Definições, com jogos que pode usar; a app não traz nenhum.
    'sources': [],
    # Pastas com os teus jogos, como os tens (owngames.py): dumps (uma pasta com default.xex),
    # imagens .iso, arquivos .7z/.zip/.rar, pacotes do Xbox Live. Aparecem no catálogo.
    'own_dirs': [],
    # Para onde vão os downloads e os jogos novos.
    'download_dir': os.path.join(BASE, 'downloads'),
    'work_dir': os.path.join(BASE, 'work'),
    # Todas as pastas com jogos já preparados (cada subpasta com prepare.json é um jogo).
    'work_roots': [os.path.join(BASE, 'work')],
    # O estado da app, os registos das tarefas, as capas descarregadas, as cópias de segurança.
    'data_dir': os.path.join(BASE, 'data'),
    # A cópia do ReXNative só da app (um clone ou uma worktree que mais ninguém usa): atualizada para
    # o main publicado antes de cada tarefa (rexrepo.py).
    'rexnative_dir': os.path.join(BASE, 'ReXNative'),
    # O repositório do ReXNative (o clone, e para onde vão os pull requests de quem não o pode
    # publicar diretamente).
    'rexnative_repo': 'gtguerreiro-max/ReXNative',
    # Reports run in a lane of their own, beside the build lane, in a second copy of ReXNative that
    # only they use (a worktree of rexnative_dir's repository; empty: rexnative_dir + '-reports').
    # Off: reports wait their turn in the build lane, as before 1.18.
    'report_lane': True,
    'report_rexnative_dir': '',
    'python': '',  # vazio: o Python que corre a app
    # As ferramentas do ReXNative (o SDK do ReXGlue instalado, o LLVM, os SDKs opcionais): cada um
    # aponta para as suas nas Definições.
    'env': {
        'REXNATIVE_REXGLUE': '',
        'REXNATIVE_SDK_INSTALL': '',
        'REXNATIVE_SDK_SRC': '',
        'REXNATIVE_FIDELITYFX': '',
        'REXNATIVE_LLVM': '',
        'REXNATIVE_DLSS_SDK': '',
        'REXNATIVE_DLSS_NR': '',
    },
    'prepare_args': ['--title-update', '--dlc', '--project', '--discover', '12',
                     '--discover-seconds', '45'],
    'max_downloads': 2,
    # Teste de arranque no PC (scripts/live.ps1): o jogo tem de desenhar boot_min_frames frames
    # sem crash; espera boot_seconds, ou até boot_seconds_max se ainda não houver estatísticas (a
    # primeira vez de uma build nova pode passar dos 60 s).
    'boot_seconds': 60,
    # O arranque nos testes de suspeitos: só se o jogo arranca (frames, sem crash); as cenas de teste
    # é que comparam a imagem. Um jogo sem a cena do arranque faz o teste inteiro (grava-a).
    'quick_boot_seconds': 20,
    'boot_seconds_max': 150,
    'boot_min_frames': 150,
    # Capturas aos mesmos segundos no nativo (o teste de arranque) e no clássico (o renderizador
    # do ReXGlue), comparadas pelo modelo barato.
    'compare_enabled': True,
    'compare_times': [15, 30, 45, 60],
    # Botões carregados nas duas execuções (seg:botões), para sair do título: a primeira captura
    # (15 s) apanha o título, as outras o jogo.
    'compare_route': '18:START,21:A,24:A,27:A',
    # Quando a comparação vê erros no nativo, um relatório automático ao Claude (modelo forte).
    'compare_auto_report': True,
    # Também com as definições do Deck (1280x800, o upscaler com FSR), no PC, comparado com o teste
    # de arranque: erros que só o Deck veria (o Tetris Splash só com a metade esquerda).
    'deck_test_enabled': True,
    # When the native renderer fails the boot test and Claude finds no fix: the classic renderer
    # (Xenia's) if the game runs there, set as the game's renderer, instead of an error.
    'classic_fallback': True,
    # Depois de uma correção com commits no ReXNative: testar os jogos que o Claude aponta como
    # suspeitos de passar pelo código mudado (compilar, testar, comparar).
    'test_suspects_after_fix': True,
    # Claude Code em modo não interativo (claude -p) para corrigir o que falha.
    'claude_enabled': True,
    'claude_exe': '',  # vazio: `claude` no PATH, senão o mais recente da app Claude
    # As correções de jogos precisam do modelo mais capaz; o modelo barato chega para escolher
    # capas e para o autoteste.
    'claude_model': 'opus',
    'claude_effort': 'high',
    'claude_cheap_model': 'haiku',
    'claude_permission_mode': 'auto',
    'claude_max_attempts': 3,
    # Uma sessão do Claude que passe disto é parada (a fila das compilações espera por ela).
    'claude_timeout_min': 120,
    # Um pedido feito do Deck que foi dormir: o envio espera até isto que ele acorde.
    'deck_wait_hours': 12,
    # A comparação nativo / clássico na mesma execução do teste de arranque (o interruptor do
    # renderizador a meio, compare_switch_wait segundos antes da captura do clássico); quando os
    # pares não servem, uma segunda execução no clássico, como antes.
    'compare_one_run': True,
    'compare_switch_wait': 1.5,
    'claude_push': True,
    # Regras a mais para o assistente nesta máquina (uma por linha), e a linha de coautor dos
    # commits que ele faz.
    'agent_rules': [],
    'agent_trailer': '',  # vazio: a do assistente escolhido (agents.TRAILER)
    # O assistente: claude (Claude Code), codex (OpenAI Codex, com a conta do ChatGPT), gemini (Gemini
    # CLI), antigravity (Antigravity CLI da Google); o programa, e os modelos (vazio: os de origem).
    # Builds para Linux (experimental; linuxbuild.py): o WSL onde compilar, o SDK do ReXGlue
    # compilado para Linux (o caminho dentro do WSL), onde ficam as cópias, e o ramo do ReXNative com
    # as ferramentas (até entrarem no main).
    'linux_enabled': False,
    'linux_wsl_distro': '',
    'linux_sdk': '',
    'linux_builds_dir': '~/rexnative-linux',
    'linux_branch': 'vulkan-experiment',
    'linux_rexnative_dir': '',
    'agent': 'claude',
    # O modelo local (agent = local): Ollama ou LM Studio, e o endereço (vazio: o de origem de cada).
    'local_provider': 'ollama',
    'local_url': '',
    'agent_exe': '',
    'agent_model': '',
    'agent_cheap_model': '',
    'claude_budget_usd': '',
    # Steam Deck
    'deck_host': '',
    'deck_key': '~/.ssh/id_ed25519_steamdeck',
    'deck_try_seconds': 35,
    # Ligações guardadas ao Deck ({name, host, key}); a ativa é deck_host/deck_key.
    'deck_profiles': [],
    # Capas: SteamGridDB é opcional (chave da API em steamgriddb.com/profile/preferences/api).
    'steamgriddb_key': '',
    'port': 8360,
    # Modo Deck: a app também na rede de casa (só o /deck, só para aparelhos emparelhados).
    'lan_enabled': False,
}

_lock = threading.Lock()
_cache = None
_local = threading.local()


class override:
    """Settings for the code this thread runs inside the `with` only: the report lane works in its
    own copy of ReXNative and keeps its own live game (pipeline.report_job), while the build lane
    goes on with the usual ones. A thread started inside does not inherit them."""

    def __init__(self, **values):
        self.values = values

    def __enter__(self):
        self.before = getattr(_local, 'values', None)
        _local.values = dict(self.before or {}, **self.values)
        return self

    def __exit__(self, *exc):
        _local.values = self.before


def _stored():
    global _cache
    with _lock:
        if _cache is None:
            cfg = copy.deepcopy(DEFAULTS)
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, encoding='utf-8') as f:
                    user = json.load(f)
                for k, v in user.items():
                    if k == 'env' and isinstance(v, dict):
                        cfg['env'].update(v)
                    else:
                        cfg[k] = v
            _cache = cfg
        return copy.deepcopy(_cache)


def stored():
    """The settings as saved, whatever this thread overrides."""
    return _stored()


def load():
    cfg = _stored()
    cfg.update(getattr(_local, 'values', None) or {})
    return cfg


def get(key):
    """Uma definição só (sem copiar as outras todas, como load faz)."""
    over = getattr(_local, 'values', None) or {}
    if key in over:
        return copy.deepcopy(over[key])
    with _lock:
        if _cache is not None:
            return copy.deepcopy(_cache.get(key, DEFAULTS.get(key)))
    return load().get(key, DEFAULTS.get(key))


def save(changes):
    """Guarda as definições alteradas (só as que diferem das de origem vão para config.json)."""
    global _cache
    cfg = _stored()  # never a thread's override
    for k, v in changes.items():
        if k in DEFAULTS:
            cfg[k] = v
    user = {k: v for k, v in cfg.items() if v != DEFAULTS.get(k)}
    from . import fsutil
    fsutil.write_json(CONFIG_PATH, user, indent=1)
    with _lock:
        _cache = None
    return load()


_made = set()


def data_dir(*parts):
    p = os.path.join(get('data_dir'), *parts)
    d = p if not os.path.splitext(p)[1] else os.path.dirname(p)
    if d not in _made:
        os.makedirs(d, exist_ok=True)
        _made.add(d)
    return p


def python_exe():
    return load()['python'] or sys.executable


def tool_env(extra=None):
    """O ambiente dos comandos do ReXNative: o desta app com as variáveis REXNATIVE_* e a
    saída em UTF-8."""
    env = dict(os.environ)
    cfg = load()
    env.update({k: str(v) for k, v in cfg['env'].items() if v})
    host = cfg.get('deck_host')
    if host:
        env['REXNATIVE_DECK'] = host
    if cfg.get('deck_key'):
        env['REXNATIVE_DECK_KEY'] = os.path.expanduser(cfg['deck_key'])
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    if extra:
        env.update(extra)
    return env


def _version_key(path):
    parts = []
    for p in path.replace('\\', '/').split('/'):
        if p and p[0].isdigit():
            parts = [int(x) if x.isdigit() else 0 for x in p.split('.')]
    return parts


def claude_exe():
    """O executável do Claude Code: o das definições, o `claude` do PATH, ou o mais recente
    que a app Claude para Windows instalou (%LOCALAPPDATA%\\Claude-Data\\*\\claude-code\\
    <versão>\\<id>\\claude.exe, que muda de pasta a cada atualização)."""
    cfg = load()
    if cfg['claude_exe'] and os.path.exists(cfg['claude_exe']):
        return cfg['claude_exe']
    found = shutil.which('claude')
    if found:
        return found
    local = os.environ.get('LOCALAPPDATA', '')
    cands = glob.glob(os.path.join(local, 'Claude-Data', '*', 'claude-code', '*', '*', 'claude.exe'))
    cands += glob.glob(os.path.join(os.path.expanduser('~'), '.local', 'bin', 'claude.exe'))
    if not cands:
        return None
    return max(cands, key=lambda p: (_version_key(p), os.path.getmtime(p)))
