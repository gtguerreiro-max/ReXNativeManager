"""O relógio da GPU do Deck enquanto um jogo ReXNative joga.

O play.sh do ReXNative mantém a GPU a 1000 MHz ou mais enquanto o jogo joga (até aos 1600 do Deck) e
devolve o relógio automático do SteamOS quando acaba: o APU do Deck reparte 15 W entre o CPU e a
GPU, e com os fios do jogo a 3,5 GHz o relógio automático deixava a GPU cair para 200-450 MHz a
meio dos frames (o Forza Horizon tinha frames de 45-70 ms; com o piso, nenhum, com a mesma
energia). Uma linha REXNATIVE_GPU_FLOOR=0 no deck.env do jogo tira o piso (set_gpu_floor)."""
import posixpath

from . import deck

MARK = '# rexnative-manager gpu-floor'


def set_gpu_floor(job, dk, dest, on):
    """O piso da GPU enquanto o jogo joga (o normal: sem linha no deck.env) ou o relógio
    automático do SteamOS (a linha REXNATIVE_GPU_FLOOR=0)."""
    env = posixpath.join(dest, 'deck.env')
    lines = '' if on else 'REXNATIVE_GPU_FLOOR=0  %s\n' % MARK
    cmd = ('f=%s; touch "$f"; grep -v %s "$f" > "$f.new"; '
           '[ -s "$f.new" ] && [ -n "$(tail -c1 "$f.new")" ] && echo >> "$f.new"; '
           'cat >> "$f.new"; mv "$f.new" "$f"; [ -s "$f" ] || rm -f "$f"; echo done'
           % (deck.q(env), deck.q(MARK)))
    r = dk.ssh(cmd, input_text=lines, timeout=30)
    if 'done' not in r.stdout:
        raise RuntimeError('could not change deck.env: %s' % r.stderr[-200:])
    job.event('ok', 'GPU clock while playing: %s' % (
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
    set_gpu_floor(job, dk, g['path'], on)
    deck.status(refresh=True, only=[])
    return {'gpu_floor': bool(on)}
