"""O relógio da GPU do Deck enquanto um jogo ReXNative joga.

O play.sh do ReXNative mantém a GPU a 1000 MHz ou mais enquanto o jogo joga (até aos 1600 do Deck) e
devolve o relógio automático do SteamOS quando acaba: o APU do Deck reparte 15 W entre o CPU e a
GPU, e com os fios do jogo a 3,5 GHz o relógio automático deixava a GPU cair para 200-450 MHz a
meio dos frames (o Forza Horizon tinha frames de 45-70 ms; com o piso, nenhum, com a mesma
energia).

O piso é a definição do jogo [rexnative] gpu_floor (MHz, 0 para o relógio automático), a mesma que
o menu do jogo escreve (Display, GPU clock), e o vigia do play.sh (ReXNative e5646c0) segue-a a
cada segundo: mudada aqui com o jogo aberto, conta logo. Antes era uma linha
REXNATIVE_GPU_FLOOR=0 no deck.env do jogo, que só contava no arranque seguinte e que o menu do
jogo não via; set_gpu_floor tira-a."""
import posixpath

from . import deck, decksettings

MARK = '# rexnative-manager gpu-floor'
KEY = 'rexnative.gpu_floor'
FLOOR = 1000


def value(on):
    """O valor da definição: o piso em MHz, ou 0 (o relógio automático)."""
    return FLOOR if on else 0


def drop_env_line(dk, dest):
    """Tira a linha antiga (REXNATIVE_GPU_FLOOR=0 com a marca) do deck.env do jogo; o deck.env sem
    mais nada é apagado."""
    env = posixpath.join(dest, 'deck.env')
    cmd = ('f=%s; [ -f "$f" ] || { echo done; exit 0; }; grep -v %s "$f" > "$f.new"; '
           'mv "$f.new" "$f"; [ -s "$f" ] || rm -f "$f"; echo done' % (deck.q(env), deck.q(MARK)))
    r = dk.ssh(cmd, timeout=30)
    if 'done' not in r.stdout:
        raise RuntimeError('could not change deck.env: %s' % r.stderr[-200:])


def set_gpu_floor(job, dk, slug, dest, on):
    """O piso da GPU enquanto o jogo joga (o normal) ou o relógio automático do SteamOS, na definição
    do jogo no Deck."""
    res = decksettings.push(slug, {KEY: value(on)})
    if res.get('deck') != 'ok':
        raise RuntimeError('could not change the game\'s settings on the Deck (%s): %s'
                           % (res.get('deck'), res.get('error') or ''))
    drop_env_line(dk, dest)
    job.event('ok', 'GPU clock while playing: %s (at once if the game is running)' % (
        'kept at 1000 MHz or more (steadier frames)' if on else "SteamOS's automatic clock"))


@deck.exclusive
def gpu_floor_job(job, slug, on):
    dk = deck.Deck()
    ok, err, line = dk.check(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    data = dk.listing(light=True, tries=3)
    g = next((x for x in data['games'] if x['slug'] == slug), None)
    if not g:
        raise RuntimeError('%s is not on the Deck' % slug)
    set_gpu_floor(job, dk, slug, g['path'], on)
    deck.status(refresh=True, only=[])
    return {'gpu_floor': bool(on)}
