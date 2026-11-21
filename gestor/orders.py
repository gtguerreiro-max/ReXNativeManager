"""Pedidos: um jogo do catálogo até à biblioteca do Deck numa só tarefa (o "Instalar" do Modo
Deck). Segue as tarefas de sempre, cada uma na sua fila: o download (se o arquivo ainda não estiver
no PC), a preparação com compilação e teste de arranque no PC (com as correções do Claude, se
falhar), e o envio para o Deck. O que já estiver feito salta-se: um jogo já compilado vai direto
para o Deck.

O pedido mostra a etapa e o progresso da tarefa que está a seguir; cancelá-lo cancela-a."""
import os
import time

from . import catalog, config, games, jobs, owngames

STAGES = ('download', 'build', 'deck')
STAGE_PT = {'download': 'Downloading', 'build': 'Preparing and building on the PC',
            'deck': 'Sending to the Deck', 'done': 'Ready', 'library': 'Ready: it joins the library '
            'when you leave the Manager', 'claude': 'Claude investigating on the PC',
            'deck_send': 'Sending the fixed version to the Deck'}


class Hooks:
    """O que o pedido usa da app (app.py preenche): manager, submit_download(item, name),
    submit_pipeline(title, source, work, steps), submit_deck(work, wait=True, root=None)."""
    manager = None
    submit_download = None
    submit_pipeline = None
    submit_deck = None


def local_work(entry):
    """A pasta de trabalho de um jogo do catálogo, se já estiver preparado no PC."""
    return games.local_lookup()(entry)


def download_path(item, name):
    return os.path.join(config.get('download_dir'), item, os.path.basename(name))


def _follow(job, sub, stage, hooks):
    job.result.update(stage=stage, sub=sub.id)
    job.event('step', '%s (job %s)' % (STAGE_PT[stage], sub.id), job=sub.id)
    while sub.status in ('queued', 'running'):
        if job._cancel.is_set():
            hooks.manager.cancel(sub.id)
            raise jobs.Cancelled()
        time.sleep(1.5)
    if sub.status != 'ok':
        raise RuntimeError('%s: %s' % (STAGE_PT[stage], sub.error or sub.status))
    return sub


def _progress(job, hooks):
    """O progresso do pedido: a etapa, e o da tarefa que segue (bytes do download e do envio;
    no pipeline o passo, a fase com %, as fases já feitas e quanto tempo leva)."""
    t0 = time.time()

    def f():
        stage = job.result.get('stage')
        sub = hooks.manager.get(job.result.get('sub')) if job.result.get('sub') else None
        p = {'stage': stage, 'elapsed': time.time() - t0}
        if sub is not None and sub.status == 'queued':
            p['waiting'] = hooks.manager.waiting(sub)
        if sub is not None:
            sp = sub.progress() if callable(sub.progress) else sub.progress
            if isinstance(sp, dict):
                if sp.get('total'):
                    p.update({k: sp.get(k) for k in ('done', 'total', 'rate', 'eta')})
                for k in ('step', 'step_pt', 'phase', 'pct', 'phases', 'steps_done', 'rate'):
                    if sp.get(k) is not None:
                        p[k if k != 'step' else 'pstep'] = sp[k]
                if sp.get('elapsed') is not None:
                    p['step_elapsed'] = sp['elapsed']
            if not p.get('phase'):
                steps = [e for e in sub.events if e['kind'] == 'step']
                if steps:
                    p['phase'] = steps[-1]['text'][:140]
            # O plugin do Decky (1.0) mostra 'step': a fase com o passo.
            p['step'] = ' · '.join(x for x in (p.get('step_pt'), p.get('phase')) if x)[:160] or None
            if p.get('waiting'):
                p['step'] = 'Waiting for the PC to finish %s' % (p['waiting'].get('title') or 'another job')
        return p
    return f


def order_job(job, hooks, entry):
    """entry: {item, name, title, slug, key, size} do catálogo."""
    job.progress = _progress(job, hooks)
    title = entry['title']
    g = local_work(entry)
    work = g['work'] if g else None
    built = bool(g and games.info(work).get('built'))
    if not built:
        source = (g or {}).get('source') if g else None
        if (not source or not os.path.exists(source)) and entry.get('path'):
            source = entry['path']  # um jogo teu: sem download
            job.event('info', 'Your file: %s' % source)
        if not source or not os.path.exists(source):
            source = download_path(entry['item'], entry['name'])
            have = os.path.getsize(source) if os.path.exists(source) else 0
            if have != entry.get('size'):
                active = next((j for j in hooks.manager.active(kind='download')
                               if j.params.get('item') == entry['item'] and
                               j.params.get('name') == entry['name']), None)
                sub = active or hooks.submit_download(entry['item'], entry['name'])
                _follow(job, sub, 'download', hooks)
        active = next(iter(hooks.manager.active(kind='pipeline', game=entry['slug'])), None)
        sub = active or hooks.submit_pipeline(title, source=source, steps=['prepare', 'boot', 'deckpc'])
        sub = _follow(job, sub, 'build', hooks)
        work = sub.result.get('work') or work
        if not work:
            g = local_work(entry)
            work = g and g['work']
        if not work:
            raise RuntimeError('the preparation ended without a game folder')
    else:
        job.event('info', 'Already built on the PC: going straight to the Deck')
    slug = os.path.basename(work)
    active = next(iter(hooks.manager.active(kind='deck', game=slug)), None)
    # root: 'sd' para o cartão microSD (a escolha no Modo Deck); None, o armazenamento interno.
    sub = active or hooks.submit_deck(work, wait=True, root=entry.get('root'))
    sub = _follow(job, sub, 'deck', hooks)
    deferred = bool(sub.result.get('deferred'))
    job.result.update(stage='library' if deferred else 'done', work=work, slug=slug)
    job.event('ok', '%s: %s' % (title, 'on the Deck; it joins the library when you leave the Manager'
                                if deferred else 'in the Deck library'))
    return {'work': work, 'slug': slug, 'deferred': deferred}


def entry_for(item, name):
    """O ficheiro do catálogo (item, name) como entrada completa. Um jogo teu (item '@local')
    só se o caminho estiver mesmo nas tuas pastas."""
    if item == owngames.ITEM:
        e = owngames.entry(name)
        return {k: e[k] for k in ('item', 'name', 'title', 'tags', 'size', 'slug', 'key', 'path')} if e else None
    f = catalog.find_file(item, name)
    if not f:
        return None
    title, tags = catalog.parse_name(name)
    return {'item': item, 'name': name, 'title': title, 'tags': tags, 'size': f['size'],
            'slug': catalog.slug(name), 'key': catalog.words(title)}
