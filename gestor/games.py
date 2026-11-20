"""Os jogos já preparados: cada subpasta das work_roots com prepare.json (`rexnative prepare`)."""
import glob
import importlib
import json
import re
import os
import sys
import threading
import tomllib

from . import catalog, config, fsutil, state

_rex_lock = threading.Lock()


def rexnative(module):
    """Um módulo do pacote rexnative da cópia configurada (rexnative_dir). Quando o ficheiro mudou
    (a worktree foi atualizada para o main), é lido outra vez: antes ficava o de quando a app abriu."""
    root = config.load()['rexnative_dir']
    with _rex_lock:
        if root not in sys.path:
            sys.path.insert(0, root)
        mod = importlib.import_module('rexnative.' + module)
        f = getattr(mod, '__file__', None)
        try:
            mtime = os.path.getmtime(f) if f else None
        except OSError:
            mtime = None
        seen = _rex_mtime.get(module)
        if seen is not None and mtime is not None and mtime != seen:
            mod = importlib.reload(mod)
        _rex_mtime[module] = mtime
        return mod


_rex_mtime = {}


def local_lookup(deck_index=None):
    """Uma função entrada do catálogo -> o jogo preparado no PC (pelo slug do ficheiro, ou pelas
    palavras do título), ou None. Uma leitura das pastas para muitas entradas."""
    by_slug, by_key = {}, {}
    for g in scan(deck_index):
        by_slug[g['slug']] = g
        by_key.setdefault(g.get('key'), g)
    return lambda e: by_slug.get(e.get('slug')) or by_key.get(e.get('key'))


def exe_name(work):
    """O nome do projeto (o executável em run/ é <nome>.exe)."""
    m = sorted(glob.glob(os.path.join(work, '*_manifest.toml')))
    if m:
        return os.path.basename(m[0])[:-len('_manifest.toml')]
    run = os.path.join(work, 'run')
    exes = [f[:-4] for f in os.listdir(run) if f.lower().endswith('.exe')] if os.path.isdir(run) else []
    return exes[0] if len(exes) == 1 else None


def title_of(work, prep):
    """O nome do jogo como o kit do Deck o põe no Steam (rexnative.deck.title_of), em cache."""
    key = state.game_key(work)
    try:
        mtime = os.path.getmtime(os.path.join(work, 'prepare.json'))
    except OSError:
        mtime = 0
    cached = state.get('titles', key)
    if cached and cached.get('mtime') == mtime:
        return cached['title']
    try:
        title = rexnative('deck').title_of(work)
    except Exception:  # noqa: BLE001
        title = catalog.parse_name(os.path.basename(prep.get('source') or work))[0]
    state.update('titles', key, {'title': title, 'mtime': mtime})
    return title


def _read_json(p):
    try:
        return json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def info(work, deck_index=None):
    work = os.path.abspath(work)
    prep = _read_json(os.path.join(work, 'prepare.json'))
    name = exe_name(work)
    run = os.path.join(work, 'run')
    exe = os.path.join(run, name + '.exe') if name else None
    tu = (prep.get('steps') or {}).get('title_update') or {}
    dlc = _read_json(os.path.join(work, 'dlc.json'))
    art_dir = os.path.join(work, 'deck', 'art')
    slug = os.path.basename(work)
    g = {
        'slug': slug,
        'work': work,
        'root': os.path.dirname(work),
        'title': title_of(work, prep),
        'source': prep.get('source'),
        'title_id': (prep.get('xex') or {}).get('title_id'),
        'version': (prep.get('xex') or {}).get('version'),
        'prepared': bool(prep.get('ok')),
        'prepare_error': prep.get('error'),
        'exe': name,
        'built': bool(exe and os.path.exists(exe)),
        'built_at': os.path.getmtime(exe) if exe and os.path.exists(exe) else None,
        'pc_toml': os.path.join(run, name + '.toml') if name else None,
        'deck_toml': os.path.join(work, 'deck.toml'),
        'has_deck_toml': os.path.exists(os.path.join(work, 'deck.toml')),
        'title_update': tu.get('title_update'),
        'dlc': sum(len(v.get('installed', [])) for v in dlc.values() if isinstance(v, dict)),
        'art': sorted(f[:-4] for f in os.listdir(art_dir) if f.endswith('.png'))
               if os.path.isdir(art_dir) else [],
    }
    st = state.get('games', state.game_key(work), {}) or {}
    for k in ('boot', 'pipeline', 'compare', 'deckpc', 'regress'):
        g[k] = st.get(k)
    # Testes antigos não traziam o aviso de imagem suspeita: calculado agora.
    b = g['boot']
    if b and b.get('shot') and 'suspicious' not in b and os.path.exists(b['shot']):
        from . import pipeline
        b['suspicious'] = pipeline.suspicious(b['shot'])
    toml = read_text(g['pc_toml']) if g['pc_toml'] else ''
    deck = read_text(g['deck_toml'])
    classic = lambda t: bool(re.search(r'(?m)^\s*classic\s*=\s*true', t))  # noqa: E731
    g['classic'] = {'pc': classic(toml), 'deck': classic(deck)}
    g['key'] = catalog.words(g['title'])
    if deck_index is not None:
        g['deck'] = deck_index.get(slug)
    return g


def scan(deck_index=None):
    out = []
    seen = set()
    for root in config.load()['work_roots']:
        if not os.path.isdir(root):
            continue
        for n in sorted(os.listdir(root)):
            w = os.path.join(root, n)
            if os.path.isfile(os.path.join(w, 'prepare.json')) and os.path.normcase(w) not in seen:
                seen.add(os.path.normcase(w))
                try:
                    out.append(info(w, deck_index))
                except Exception as e:  # noqa: BLE001 - um jogo estragado não tapa os outros
                    out.append({'slug': n, 'work': w, 'title': n, 'error': str(e), 'key': n})
    return out


def find(slug_or_work):
    """A pasta de um jogo: um caminho completo, ou o nome (slug) de uma pasta com prepare.json
    numa das pastas de trabalho. Um nome com separadores ou '..' não é um slug (a rede de casa
    pedia assim qualquer pasta do PC)."""
    s = slug_or_work or ''
    if os.path.isabs(s):
        return os.path.abspath(s) if os.path.isdir(s) else None
    if not s or s in ('.', '..') or any(c in s for c in '/\\:') or '..' in s:
        return None
    for root in config.load()['work_roots']:
        w = os.path.join(root, slug_or_work)
        if os.path.isfile(os.path.join(w, 'prepare.json')):
            return w
    return None


# -- ficheiros de definições ---------------------------------------------------------------------
def settings_files(work):
    name = exe_name(work)
    files = {'deck': os.path.join(work, 'deck.toml')}
    if name:
        files['pc'] = os.path.join(work, 'run', name + '.toml')
    return files


def read_text(path):
    return open(path, encoding='utf-8').read() if os.path.exists(path) else ''


def validate_toml(text):
    """None se for TOML válido, senão a mensagem de erro."""
    try:
        tomllib.loads(text)
        return None
    except tomllib.TOMLDecodeError as e:
        return str(e)


def toml_value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def apply_values(text, values):
    """Põe {"secção.chave": valor} no texto TOML (rexnative.deck.toml_set mantém comentários e
    a ordem); um valor None tira a chave."""
    toml_set = rexnative('deck').toml_set
    import re
    for dotted, v in values.items():
        section, key = dotted.rsplit('.', 1)
        if v is None or v == '':
            # Tira a linha da chave dentro da secção.
            lines = text.splitlines()
            head = next((i for i, l in enumerate(lines) if l.strip() == '[%s]' % section), None)
            if head is not None:
                end = next((i for i in range(head + 1, len(lines)) if lines[i].lstrip().startswith('[')),
                           len(lines))
                lines = [l for i, l in enumerate(lines)
                         if not (head < i < end and re.match(r'\s*%s\s*=' % re.escape(key), l))]
                text = '\n'.join(lines) + '\n'
            continue
        text = toml_set(text, section, key, toml_value(v))
    return text


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        bak = path + '.bak'
        with open(path, 'rb') as src, open(bak, 'wb') as dst:
            dst.write(src.read())
    fsutil.write_text(path, text if text.endswith('\n') or not text else text + '\n')
