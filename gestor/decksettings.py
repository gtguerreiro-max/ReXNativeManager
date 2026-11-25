"""As definições que um jogo instalado no Deck usa: o ficheiro dele (<pasta>/<exe>.toml no Deck),
que o menu do jogo (View + Menu) também escreve.

Antes, as Definições do Deck na app escreviam só o deck.toml do PC e, para chegarem ao Deck,
mandavam o jogo outra vez e substituíam o ficheiro inteiro: o que se mudara no menu do jogo
perdia-se, e o que a app mostrava não era o que o jogo usava. Agora a app lê esse ficheiro (read,
values) e muda só as chaves escolhidas nele (push), com o jogo aberto ou não: o ReXNative 7d098f8
em diante lê-o outra vez quando muda e aplica-as logo; antes disso, no arranque seguinte. O
deck.toml continua a guardá-las para as instalações seguintes."""
import tomllib

from . import deck, games

# O executável mais recente da pasta (o que o play.sh arranca) e o .toml ao lado dele: o nome numa
# linha, depois o texto.
_READ = 'f=$(ls -t %s/*.exe 2>/dev/null | head -1); [ -n "$f" ] || exit 3; t="${f%%.exe}.toml"; echo "$t"; cat "$t" 2>/dev/null; true'


def _folder(slug):
    g = deck.index().get(slug)
    return g.get('path') if g else None


def read(slug, timeout=20):
    """(caminho no Deck, texto) do ficheiro de definições do jogo; (None, None) se o jogo não está
    no Deck ou o Deck não responde."""
    folder = _folder(slug)
    if not folder:
        return None, None
    try:
        r = deck.Deck().ssh(_READ % deck.q(folder), timeout=timeout)
    except Exception:  # noqa: BLE001 - sem Deck, a app usa o deck.toml
        return None, None
    if r.returncode != 0 or not r.stdout.strip():
        return None, None
    path, _, text = r.stdout.partition('\n')
    return path.strip(), text


def flat(text):
    """{secção.chave: valor} das tabelas que as Definições mostram (rexnative, ui, log, kernel)."""
    try:
        d = tomllib.loads(text or '')
    except tomllib.TOMLDecodeError:
        return {}
    return {'%s.%s' % (sec, k): v for sec, kv in d.items()
            if sec in ('rexnative', 'ui', 'log', 'kernel') and isinstance(kv, dict)
            for k, v in kv.items() if isinstance(v, (bool, int, float, str))}


def values(slug):
    """As definições que o jogo usa no Deck agora ({secção.chave: valor}), ou None sem Deck."""
    path, text = read(slug)
    return None if path is None else flat(text)


def push(slug, vals, base=None):
    """{secção.chave: valor} no ficheiro do jogo no Deck, só essas chaves (o resto, os comentários e o
    que o menu do jogo mudou ficam). None: o valor de `base` (o "Default" que a página mostra) ou a
    chave tirada. {'deck': 'ok' | 'unreachable' | 'not installed' | 'failed', 'path': ...}"""
    if not _folder(slug):
        return {'deck': 'not installed'}
    path, text = read(slug)
    if path is None:
        return {'deck': 'unreachable'}
    want = {k: (base[k] if v is None and base and k in base else v) for k, v in vals.items()}
    new = games.apply_values(text, want)
    err = games.validate_toml(new)
    if err:
        raise ValueError('the settings would not be valid TOML: %s' % err)
    try:
        r = deck.Deck().ssh('f=%s; cat > "$f.new" && mv "$f.new" "$f" && echo done' % deck.q(path),
                            input_text=new, timeout=30)
    except Exception as e:  # noqa: BLE001
        return {'deck': 'failed', 'path': path, 'error': str(e)[:200]}
    return {'deck': 'ok' if 'done' in r.stdout else 'failed', 'path': path,
            'error': None if 'done' in r.stdout else (r.stderr or r.stdout)[-200:]}
