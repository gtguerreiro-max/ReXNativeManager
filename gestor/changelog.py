"""As versões de cada jogo e o que cada uma corrige, para o cartão do jogo no Modo Deck.

- Cada envio para o Deck guarda que compilação foi (deck_versions no state.json): quando foi
  compilada, com que commit do ReXNative (run/rexnative-build.json) e quando chegou ao Deck.
- O que muda entre duas versões são as correções do ReXNative publicadas entre elas que entram no
  jogo (freshness.commits: renderer/ e o gerador). Uma compilação com mudanças locais (trabalho por
  publicar) conta pela data em que foi feita.
- Cada correção mostra-se com o assunto do commit tal como está (em inglês, a língua da app)."""
from . import freshness, jobs, state


# -- versões ------------------------------------------------------------------------------------
def version_of(work, built_at):
    """A versão de uma compilação: {built_at, commit, dirty, sdk, time} (time: até onde as correções
    publicadas entram nela)."""
    st = freshness.read_stamp(work) or {}
    commit, dirty = st.get('rexnative'), bool(st.get('dirty'))
    t = built_at
    if commit and not dirty and st.get('rexnative_date'):
        t = st['rexnative_date']
    return {'built_at': built_at, 'commit': commit[:7] if commit else None, 'dirty': dirty,
            'sdk': st.get('sdk'), 'time': t, 'exact': bool(commit) and not dirty}


def deck_version(slug, deck_mtime, hist=None):
    """A versão que está no Deck: a do último envio, se é a compilação que lá está (pela data do
    executável); senão (enviada antes de haver histórico) a compilação pela data do executável."""
    if hist is None:
        hist = (state.get('deck_versions', slug) or {}).get('history') or []
    if hist and deck_mtime and abs((hist[-1].get('built_at') or 0) - deck_mtime) < 120:
        return dict(hist[-1])
    if deck_mtime:
        return {'built_at': deck_mtime, 'commit': None, 'dirty': False, 'time': deck_mtime, 'exact': False,
                'sent_at': None}
    return None


def record_send(slug, work, built_at, deferred=False):
    """Um envio para o Deck: a versão que foi (as últimas 12), com as correções que traz desde a
    anterior guardadas logo (o cartão do jogo não as volta a pedir ao git, e ficam mesmo quando os
    commits saem dos últimos 400)."""
    v = version_of(work, built_at)
    v['sent_at'] = jobs.now()
    hist = (state.get('deck_versions', slug) or {}).get('history') or []
    if hist and abs((hist[-1].get('built_at') or 0) - (built_at or 0)) < 2:
        hist[-1]['sent_at'] = v['sent_at']  # a mesma compilação outra vez (definições): só a data
    else:
        v['changes'] = pack(between(hist[-1]['time'], v['time'])) if hist else []
        hist.append(v)
    state.update('deck_versions', slug, {'history': hist[-12:]})


def fill_changes(slug, hist):
    """As versões do histórico ainda sem a lista de correções (de antes de ela ser guardada no
    envio): calculada uma vez e guardada. Devolve o histórico com todas."""
    if all('changes' in v for v in hist):
        return hist
    out, prev = [], None
    for v in hist:
        v = dict(v)
        if 'changes' not in v:
            v['changes'] = pack(between(prev['time'], v['time'])) if prev else []
        out.append(v)
        prev = v
    state.update('deck_versions', slug, {'history': out})
    return out


def between(t0, t1):
    """As correções que entram no jogo publicadas depois de t0 e até t1 (None: até agora)."""
    return [c for c in freshness.commits() if c['build'] and c['at'] > (t0 or 0) and (t1 is None or c['at'] <= t1)]


def pack(cs):
    # 'pt' fica com o nome antigo (a página do Deck lê-o): é o assunto do commit, como 'en'.
    return [{'sha': c['sha'][:7], 'pt': c['subject'], 'en': c['subject'], 'at': c['at']} for c in cs]
