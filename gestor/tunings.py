"""O que o ReXNative afina para um jogo, em frases para o cartão do jogo.

Não há uma tabela única no ReXNative: cada jogo é compilado com a sua camada, gerada pelo
rexnative/adapt.py (<work>/layer/layer.json e game_layer.h), e tem as suas definições no
run/<nome>.toml e, para o Deck, no deck.toml. Lê-se o que lá está: a versão do Direct3D do XDK, se
as chamadas de desenho vêm do push buffer (XDK antigo), os buffers de comandos, a oclusão, os
dispositivos, os argumentos remapeados, a cena aprendida, os ajustes à mão (overrides.json) e as
chaves [rexnative] das definições."""
import json
import os

from . import games

CMDBUF = {1: 'counted', 2: 'replayed'}


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _toml(path):
    import tomllib
    try:
        return tomllib.loads(games.read_text(path))
    except (tomllib.TOMLDecodeError, OSError, ValueError):
        return {}


def _fmt(v):
    if isinstance(v, bool):
        return 'on' if v else 'off'
    return str(v)


def read(work):
    """[{'k': o quê, 't': o que está}] por ordem: a camada, depois as definições do PC e do Deck."""
    out = []
    layer = _read_json(os.path.join(work, 'layer', 'layer.json'))
    if layer:
        d3d = (layer.get('target') or {}).get('d3d') or []
        if len(d3d) >= 2:
            out.append({'k': 'Direct3D', 't': '%s from XDK %s' % (d3d[0], d3d[1])})
        so = layer.get('stream_only') or {}
        if so:
            t = 'draws read from the push buffer (%s)' % (so.get('why') or 'older XDK')
            if so.get('texture_fetch') is not None:
                t += ', texture fetch offset %s' % so['texture_fetch']
            out.append({'k': 'Draws', 't': t})
        dflt = layer.get('defaults') or {}
        if dflt.get('enabled') is False:
            out.append({'k': 'Renderer', 't': 'ReXNative off by default (the classic renderer draws)'})
        if dflt.get('cmdbuf') in CMDBUF:
            t = CMDBUF[dflt['cmdbuf']]
            if dflt.get('cmdbuf_bin_mask'):
                t += ' (bin mask at %s)' % dflt['cmdbuf_bin_mask']
            out.append({'k': 'Command buffers', 't': t})
        if dflt.get('occlusion') is False:
            out.append({'k': 'Occlusion queries', 't': 'answered without the GPU (off)'})
        elif dflt.get('occlusion') is True:
            out.append({'k': 'Occlusion queries', 't': 'counted on the host'})
        if dflt.get('render_height') and dflt['render_height'] != 720:
            out.append({'k': 'Render height', 't': '%s lines' % dflt['render_height']})
        if dflt.get('display_aspect') and str(dflt['display_aspect']).replace(' ', '') not in ('16.0/9.0', '16/9'):
            out.append({'k': 'Aspect', 't': str(dflt['display_aspect'])})
        dev = layer.get('devices') or {}
        if dev.get('follow_swap_device_only'):
            out.append({'k': 'Devices', 't': 'follows only the device that presents (Swap)'})
        if dev.get('configure_at_first_device'):
            out.append({'k': 'Devices', 't': 'set up at the first device the game creates'})
        # Só conta como remapeado o que não está na ordem normal (r3, r4, ...).
        ca = layer.get('call_args') or {}
        remaps = [k for k, v in ca.items() if isinstance(v, dict) and v.get('args')
                  and list(v['args']) != list(range(3, 3 + len(v['args'])))] if isinstance(ca, dict) else []
        if remaps:
            out.append({'k': 'Arguments', 't': 'remapped for %s' % ', '.join(sorted(remaps)[:4])})
        sc = layer.get('scene') or {}
        if sc.get('auto'):
            out.append({'k': 'Scene', 't': 'its size learned at run time'})
        elif sc.get('width'):
            out.append({'k': 'Scene', 't': '%sx%s' % (sc.get('width'), sc.get('height'))})
        ov = layer.get('overrides') or {}
        if ov:
            out.append({'k': 'Hand-set', 't': ', '.join(sorted(ov)[:6])})
    name = games.exe_name(work)
    pc = (_toml(os.path.join(work, 'run', name + '.toml')).get('rexnative') or {}) if name else {}
    keys = {k: v for k, v in pc.items() if k in (
        'dlss5_look', 'classic', 'enabled', 'upscaler', 'upscaler_mode', 'frame_generation', 'menu_fps',
        'inline_draws_auto', 'cmdbuf', 'occlusion')}
    if keys:
        out.append({'k': 'PC settings', 't': ', '.join('%s %s' % (k.replace('_', ' '), _fmt(v)) for k, v in sorted(keys.items()))})
    deck = _toml(os.path.join(work, 'deck.toml'))
    dk = {('%s.%s' % (sec, k) if sec != 'rexnative' else k): v
          for sec, kv in deck.items() if isinstance(kv, dict) for k, v in kv.items()}
    if dk:
        out.append({'k': 'Deck settings', 't': ', '.join('%s %s' % (k.replace('_', ' '), _fmt(v)) for k, v in sorted(dk.items()))})
    if not layer:
        out.insert(0, {'k': 'Layer', 't': 'no generated layer in this build (an older build or a hand-written port)'})
    return out
