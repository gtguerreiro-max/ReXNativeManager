"""Cenas de teste: uns frames de um jogo gravados como trace do ReXNative (o que o jogo entrega ao
renderizador e a memória que ele lê: --rexnative_trace_record, `live.ps1 record`), com as imagens
que a compilação que os gravou desenhou (a referência).

Depois de uma mudança no ReXNative, cada cena é desenhada outra vez pela compilação nova
(--rexnative_trace_play, duas voltas, as imagens da segunda) e comparada pixel a pixel com a
referência. São os mesmos frames: uma diferença é do renderizador, nunca de um arranque mais lento
(as capturas aos 15/30/45/60 s do teste de arranque apanhavam intros e transições em momentos
diferentes, e davam "pior" sem nada estar pior).

As cenas vêm do jogo a sério: o jogador grava uma enquanto joga no PC ("Save this scene as a
test"), o Claude grava o sítio de cada relatório, e o teste de arranque grava uma vez o ecrã a que
chega. Ficam em <data_dir>/scenes/<jogo>/<cena>/: scene.rxt, ref/f<i>.png e scene.json."""
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import time

from . import config, fsutil, games, jobs

FRAMES = 3          # frames de cada cena (o primeiro lê alvos vazios na primeira volta: a segunda conta)
PLAY_TIMEOUT = 240  # o arranque do jogo até ao primeiro Swap, e as duas voltas
SAME_MEAN = 0.2     # diferença média (0-255) abaixo da qual duas imagens são iguais...
SAME_OVER = 0.05    # ...com menos desta percentagem de pixels a mais de 8 níveis


class SceneError(RuntimeError):
    def __init__(self, msg, stale=False, crashed=False):
        super().__init__(msg)
        self.stale = stale  # o trace é de uma compilação com outras estruturas: gravar outra vez
        self.crashed = crashed  # o jogo caiu a desenhá-la (o processo fica no tratador de crashes)


# A crash (ReXGlue's crash report), or a fault the renderer caught: then the Xenos plugin draws for
# the rest of the run, the trace is not played to its end and the game runs on by itself.
CRASH_RE = re.compile(r'crash report, rexglue|EXCEPTION_|exception: [A-Z_]+ \(0x|'
                      r'native path read a bad guest address|Xenos plugin draws (from the next Swap, )?for the rest',
                      re.I)


def broken_here(meta, work):
    """A cena fez cair esta mesma compilação do ReXNative: não vale a pena desenhá-la outra vez até o
    renderizador mudar (cada tentativa era um arranque e uma espera)."""
    b = meta.get('broken') or {}
    return bool(b) and b.get('rex') == build_rex(work)


def _mark_broken(meta, work, why):
    meta['broken'] = {'rex': build_rex(work), 'at': jobs.now(), 'why': str(why)[:400]}
    save(meta)


def root(slug):
    return config.data_dir('scenes', slug)


def scene_dir(slug, sid):
    return os.path.join(root(slug), sid)


def build_rex(work):
    """O commit do ReXNative com que a compilação do jogo foi feita (run/rexnative-build.json)."""
    try:
        with open(os.path.join(work, 'run', 'rexnative-build.json'), encoding='utf-8') as f:
            return (json.load(f).get('rexnative') or '')[:7] or None
    except (OSError, ValueError):
        return None


def load(slug, sid):
    try:
        with open(os.path.join(scene_dir(slug, sid), 'scene.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(meta):
    d = scene_dir(meta['slug'], meta['id'])
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, 'scene.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, 'scene.json'))


def scenes(slug):
    """As cenas do jogo, as mais antigas primeiro."""
    d = config.data_dir('scenes')
    p = os.path.join(d, slug)
    if not os.path.isdir(p):
        return []
    out = [load(slug, sid) for sid in sorted(os.listdir(p))]
    return [m for m in out if m]


def refs(slug, sid):
    return _pngs(os.path.join(scene_dir(slug, sid), 'ref'))


def _settled_pngs(job, d, wait=5.0):
    """The replay's pictures once written: the renderer writes them on threads of its own, and a
    build older than ReXNative's FinishShots exits 2.5 s after the last loop, which on a busy PC
    left some empty (Limbo, 2026-11-23: 0-byte f3-f5-native.png failed the whole pipeline).
    Waits until none is empty and the sizes stop changing (up to `wait` s). An empty one is a
    SceneError (the scene fails, the test goes on): the pictures pair with the references by
    their order, so one left out would compare the wrong frames."""
    last, end = None, time.time() + wait
    while True:
        sizes = {}
        for x in _pngs(d):
            try:
                sizes[x] = os.path.getsize(x)
            except OSError:
                sizes[x] = 0
        if (sizes == last and all(sizes.values())) or time.time() > end:
            break
        last = sizes
        time.sleep(0.5)
    empty = [os.path.basename(x) for x, n in sizes.items() if not n]
    if empty:
        raise SceneError('the replay left %d picture(s) empty (%s): rebuild the game, its build '
                         'exits before they are written' % (len(empty), ', '.join(empty)))
    return _pngs(d)


def _pngs(d):
    def idx(p):
        m = re.search(r'f(\d+)', os.path.basename(p))
        return int(m.group(1)) if m else 0
    return sorted(glob.glob(os.path.join(d, 'f*.png')), key=idx)


def delete(slug, sid):
    d = scene_dir(slug, sid)
    if os.path.isdir(d) and os.path.dirname(d) == root(slug):
        shutil.rmtree(d)


# -- gravar ---------------------------------------------------------------------------------------
# Os testes veem o que o jogo desenha, sem o que se põe por cima: o DLSS 5 (o look, um modelo
# neural), o upscaler e a escala de resolução, a geração de frames e a anisotropia forçada. Com
# eles o nativo comparava-se ao clássico pelo look e não pela emulação (e o DLSS 5 nem dá sempre a
# mesma imagem duas vezes). A corrida com as definições do Deck passa as dela e fica como está.
RAW_FLAGS = ('--rexnative_dlss5=false', '--rexnative_upscaler=false', '--rexnative_resolution_scale=1',
             '--rexnative_anisotropy=1', '--rexnative_frame_generation=false')


def live_flags(run):
    """O que um jogo precisa para se lhe pedir uma cena enquanto corre (como live.ps1 start): o
    ficheiro de controlo, a pasta dos traces e a das capturas."""
    live = os.path.join(run, 'live')
    for d in ('cap', 'trace'):
        os.makedirs(os.path.join(live, d), exist_ok=True)
    return ['--rexnative_capture_dir=%s' % os.path.join(live, 'cap'),
            '--rexnative_d3d_control=%s' % os.path.join(live, 'control.txt'),
            '--rexnative_d3d_trace_dir=%s' % os.path.join(live, 'trace')]


def record_live(run, frames=FRAMES, timeout=30):
    """Pede ao jogo que está a correr (com live_flags) um trace dos próximos frames e devolve o
    caminho do .rxt quando está escrito."""
    tdir = os.path.join(run, 'live', 'trace')
    os.makedirs(tdir, exist_ok=True)
    start = time.time()
    fsutil.send_control(os.path.join(run, 'live', 'control.txt'), 'set rexnative_trace_record %d' % frames)
    found = None
    while not found and time.time() - start < timeout:
        time.sleep(0.3)
        cands = [p for p in glob.glob(os.path.join(tdir, '*.rxt')) if os.path.getmtime(p) >= start - 0.5]
        found = max(cands, key=os.path.getmtime) if cands else None
    if not found:
        raise SceneError('the game wrote no trace in %d s (is it the native renderer, with the '
                         'render thread on?)' % timeout)
    last = -1
    for _ in range(100):
        time.sleep(0.4)
        n = os.path.getsize(found)
        if n > 0 and n == last:
            break
        last = n
    return found


def add(work, slug, trace, source, label, report=None):
    """Guarda um trace como cena nova (movido para a pasta das cenas). A referência fica por fazer
    (make_refs), com a compilação que o gravou."""
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    sid = '%s-%s' % (stamp, source)
    d = scene_dir(slug, sid)
    os.makedirs(d, exist_ok=True)
    shutil.move(trace, os.path.join(d, 'scene.rxt'))
    meta = {'id': sid, 'slug': slug, 'source': source, 'label': label[:200], 'at': jobs.now(),
            'rec_rex': build_rex(work), 'ref_rex': None, 'frames': 0, 'report': report,
            'size': os.path.getsize(os.path.join(d, 'scene.rxt')), 'last': None}
    save(meta)
    return meta


# -- desenhar -------------------------------------------------------------------------------------
def play(job, work, trace, out_dir, extra=()):
    """A compilação do jogo desenha o trace duas vezes e grava as imagens da segunda (o primeiro
    frame da primeira lê alvos vazios). Devolve as imagens por ordem; SceneError se não sair nenhuma
    (stale=True quando o trace é de estruturas de outra compilação)."""
    name = games.exe_name(work)
    run = os.path.join(work, 'run')
    exe = os.path.join(run, (name or '?') + '.exe')
    if not name or not os.path.exists(exe):
        raise SceneError('the game is not built')
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    log_tag = 'scene-%d' % int(time.time())
    title = games.info(work).get('title') or os.path.basename(work)
    args = [exe, '--log_file=live\\%s.log' % log_tag, '--fullscreen=false', '--window_width=1280',
            '--window_height=720',
            # The window says what it is: the Manager's test scene, not a game to play.
            '--ui.title=%s - ReXNative Manager test scene: please do not play in this window' % title,
            '--rexnative_capture_dir=%s' % out_dir,
            '--rexnative_trace_play=%s' % trace, '--rexnative_trace_play_loops=2',
            '--rexnative_trace_play_dump=true', '--rexnative_trace_play_fps=0'] + list(extra or RAW_FLAGS)
    if job:
        job.log('$ ' + ' '.join(args))
    p = subprocess.Popen(args, cwd=run, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    end = time.time() + PLAY_TIMEOUT
    crash = None
    try:
        n = 0
        while p.poll() is None:
            if job:
                job.check()
            if time.time() > end:
                raise SceneError('the scene did not finish in %d s' % PLAY_TIMEOUT)
            time.sleep(0.5)
            n += 1
            # A game that crashed stays in ReXGlue's crash handler and never exits: its log says so.
            if n % 4 == 0:
                text = _log_text(run, log_tag)
                m = CRASH_RE.search(text)
                if m:
                    lines = [l.strip()[24:] for l in text[m.start():].splitlines()[:3]]
                    crash = ' | '.join(l for l in lines if l)[:300]
                    break
    finally:
        if p.poll() is None:
            p.kill()
    if crash:
        _drop_logs(run, log_tag)
        raise SceneError('the game crashed while drawing the scene: %s' % crash, crashed=True)
    imgs = _settled_pngs(job, out_dir)
    log = _log_text(run, log_tag)
    _drop_logs(run, log_tag)
    if not imgs:
        stale = bool(re.search(r'record (it )?again|recorded with|size', log, re.I) and 'trace' in log.lower())
        lines = [l for l in log.splitlines() if 'trace' in l.lower()][-3:]
        raise SceneError('no pictures from the scene%s' % (': ' + ' | '.join(l[-160:] for l in lines)
                                                           if lines else ''), stale=stale)
    return imgs


def _log_text(run, tag):
    out = ''
    for p in glob.glob(os.path.join(run, 'logs', 'live', tag + '.log*')):
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                out += f.read()[-20000:]
        except OSError:
            pass
    return out


def _drop_logs(run, tag):
    for p in glob.glob(os.path.join(run, 'logs', 'live', tag + '.log*')):
        try:
            os.remove(p)
        except OSError:
            pass


def make_refs(job, work, slug, sid):
    """As imagens de referência da cena, desenhadas pela compilação que o jogo tem agora."""
    meta = load(slug, sid)
    d = scene_dir(slug, sid)
    out = os.path.join(d, 'play')
    try:
        imgs = play(job, work, os.path.join(d, 'scene.rxt'), out)
    except SceneError as e:
        if e.crashed:
            _mark_broken(meta, work, e)
        raise
    meta.pop('broken', None)
    ref = os.path.join(d, 'ref')
    if os.path.isdir(ref):
        shutil.rmtree(ref)
    os.makedirs(ref)
    for i, p in enumerate(imgs):
        shutil.copyfile(p, os.path.join(ref, 'f%d.png' % i))
    shutil.rmtree(out, ignore_errors=True)
    meta.update(ref_rex=build_rex(work), frames=len(imgs), ref_at=jobs.now(), stale=False)
    save(meta)
    return meta


def gameplay(slug):
    """As cenas de jogo do jogo (a sessão que o leva até se estar a jogar), as que ainda servem."""
    return [m for m in scenes(slug) if m.get('source') == 'gameplay' and not m.get('stale')]


def pending_refs(slug):
    work = games.find(slug)
    return [m for m in scenes(slug) if not m.get('frames') and not m.get('stale')
            and not (work and broken_here(m, work))]


# -- comparar -------------------------------------------------------------------------------------
def diff(a, b):
    """{mean (0-255), over (% de pixels a mais de 8 níveis), box (onde mudou)}."""
    from PIL import Image, ImageChops, ImageStat
    x, y = Image.open(a).convert('RGB'), Image.open(b).convert('RGB')
    if x.size != y.size:
        return {'mean': 255.0, 'over': 100.0, 'box': None, 'size': [x.size, y.size]}
    d = ImageChops.difference(x, y).convert('L')
    h = d.histogram()
    n = x.size[0] * x.size[1]
    mask = d.point(lambda v: 255 if v > 8 else 0)
    return {'mean': round(ImageStat.Stat(d).mean[0], 3), 'over': round(sum(h[9:]) * 100.0 / n, 3),
            'box': mask.getbbox()}


def same(d):
    return d['mean'] < SAME_MEAN and d['over'] < SAME_OVER


def sheet(ref, new, box, path):
    """Antes | depois, a imagem inteira; por baixo, a zona que mudou ampliada."""
    from PIL import Image, ImageDraw
    a, b = Image.open(ref).convert('RGB'), Image.open(new).convert('RGB')
    w, h = 960, int(960 * a.size[1] / a.size[0])
    out = Image.new('RGB', (w * 2 + 10, h * 2 + 60), (24, 24, 24))
    dr = ImageDraw.Draw(out)
    dr.text((8, 6), 'BEFORE (reference)', fill=(255, 210, 0))
    dr.text((w + 18, 6), 'AFTER (this build)', fill=(255, 210, 0))
    out.paste(a.resize((w, h)), (0, 24))
    out.paste(b.resize((w, h)), (w + 10, 24))
    if box:
        x0, y0, x1, y1 = box
        pad = 24
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(a.size[0], x1 + pad), min(a.size[1], y1 + pad)
        crop = (x0, y0, x1, y1)
        s = min(w / (x1 - x0), h / (y1 - y0), 4.0)
        cw, ch = int((x1 - x0) * s), int((y1 - y0) * s)
        dr.text((8, h + 32), 'the region that changed, enlarged', fill=(255, 210, 0))
        out.paste(a.crop(crop).resize((cw, ch)), (0, h + 52))
        out.paste(b.crop(crop).resize((cw, ch)), (w + 10, h + 52))
        sc = w / a.size[0]
        for ox in (0, w + 10):
            dr.rectangle([ox + x0 * sc, 24 + y0 * sc, ox + x1 * sc, 24 + y1 * sc], outline=(255, 60, 60), width=2)
    out.save(path, quality=88)
    return path


JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'verdict': {'type': 'string', 'enum': ['igual', 'melhor', 'pior', 'inconclusivo']},
        'summary': {'type': 'string'},
    },
    'required': ['verdict', 'summary'],
}

JUDGE_PROMPT = """A change to ReXNative's native renderer changed how the Xbox 360 game "{title}" draws a
recorded scene ({label}). Read the image {sheet}. It is the SAME recorded frame drawn twice from the
same data, so nothing differs by timing: on the LEFT before the change (the reference, ReXNative
{before}), on the RIGHT after it (ReXNative {after}). The lower half enlarges the region whose pixels
changed (the red box above).

Verdict: "melhor" if the right one shows things the left one missed or fixes artifacts (garbage,
missing geometry, wrong text or colours), "pior" if the right one misses things the left one had or
shows new artifacts, a blank area or garbage, "igual" if the difference is too small to matter
(noise, a few pixels, slightly different filtering), or "inconclusivo".
summary: one or two short sentences in English for the user, saying what changed."""


def check(job, work, slug, sid, judge=True):
    """A cena desenhada pela compilação de agora contra a referência. Devolve o resultado (também
    guardado em scene.json 'last'): verdict same / igual / melhor / pior / inconclusivo / stale /
    failed."""
    meta = load(slug, sid)
    d = scene_dir(slug, sid)
    rex = build_rex(work)
    res = {'at': jobs.now(), 'rex': rex, 'ref_rex': meta.get('ref_rex')}
    rimgs = refs(slug, sid)
    if not rimgs:
        res.update(verdict='failed', summary='the scene has no reference pictures yet')
        meta['last'] = res
        save(meta)
        return res
    try:
        nimgs = play(job, work, os.path.join(d, 'scene.rxt'), os.path.join(d, 'new'))
    except SceneError as e:
        res.update(verdict='stale' if e.stale else 'failed', summary=str(e)[:400])
        if e.stale:
            meta['stale'] = True
        if e.crashed:
            meta['broken'] = {'rex': rex, 'at': jobs.now(), 'why': str(e)[:400]}
        meta['last'] = res
        save(meta)
        return res
    meta.pop('broken', None)
    diffs = [diff(a, b) for a, b in zip(rimgs, nimgs)]
    res['frames'] = diffs
    if len(nimgs) != len(rimgs):
        res['count'] = [len(rimgs), len(nimgs)]
    if all(same(x) for x in diffs) and len(nimgs) == len(rimgs):
        res.update(verdict='same', summary='The same pixels as the reference (%d frames)' % len(diffs))
    else:
        worst = max(range(len(diffs)), key=lambda i: diffs[i]['over'])
        path = sheet(rimgs[worst], nimgs[worst], diffs[worst]['box'], os.path.join(d, 'check.jpg'))
        res.update(sheet=path, worst=worst, verdict='inconclusivo',
                   summary='%.2f%% of the pixels changed in frame %d' % (diffs[worst]['over'], worst + 1))
        if judge:
            from . import claude
            try:
                ans, cost = claude.ask(JUDGE_PROMPT.format(
                    title=games.info(work)['title'], label=meta.get('label') or 'a scene',
                    sheet=os.path.basename(path), before=meta.get('ref_rex') or 'before',
                    after=rex or 'now'), JUDGE_SCHEMA, cwd=d)
                res.update(verdict=ans.get('verdict') or 'inconclusivo',
                           summary='%s (%.2f%% of the pixels changed)' % (ans.get('summary') or '', diffs[worst]['over']),
                           cost=cost)
            except Exception as e:  # noqa: BLE001 - sem o modelo, fica a diferença
                res['summary'] += ' (no opinion from the model: %s)' % str(e)[:160]
    meta['last'] = res
    save(meta)
    return res


def accept(slug, sid):
    """As imagens da última verificação passam a ser a referência (o novo aspeto está certo)."""
    meta = load(slug, sid)
    d = scene_dir(slug, sid)
    new = _pngs(os.path.join(d, 'new'))
    if not new:
        raise RuntimeError('no new pictures to accept: check the scene first')
    ref, prev = os.path.join(d, 'ref'), os.path.join(d, 'ref-prev')
    shutil.rmtree(prev, ignore_errors=True)
    if os.path.isdir(ref):
        os.replace(ref, prev)
    os.makedirs(ref)
    for i, p in enumerate(new):
        shutil.copyfile(p, os.path.join(ref, 'f%d.png' % i))
    meta.update(prev_ref_rex=meta.get('ref_rex'), ref_rex=(meta.get('last') or {}).get('rex'),
                frames=len(new), ref_at=jobs.now())
    if meta.get('last'):
        meta['last']['accepted'] = True
    save(meta)
    return meta


def undo_accept(slug, sid):
    """A referência de antes da última aceitação volta (um "melhor" que não o era)."""
    meta = load(slug, sid)
    d = scene_dir(slug, sid)
    ref, prev = os.path.join(d, 'ref'), os.path.join(d, 'ref-prev')
    if not os.path.isdir(prev):
        raise RuntimeError('there is no earlier reference to go back to')
    shutil.rmtree(ref, ignore_errors=True)
    os.replace(prev, ref)
    meta.update(ref_rex=meta.get('prev_ref_rex'), prev_ref_rex=None, frames=len(_pngs(ref)))
    if meta.get('last'):
        meta['last']['accepted'] = False
        meta['last']['undone'] = True
    save(meta)
    return meta


def view(m):
    """Uma cena para a interface."""
    d = scene_dir(m['slug'], m['id'])
    last = m.get('last') or {}
    r = _pngs(os.path.join(d, 'ref'))
    return dict(m, has_ref=bool(r), has_new=bool(_pngs(os.path.join(d, 'new'))),
                has_prev=os.path.isdir(os.path.join(d, 'ref-prev')),
                has_sheet=bool(last.get('sheet')) and os.path.exists(last.get('sheet') or ''),
                word=WORD.get(last.get('verdict'), last.get('verdict')) if last else None)


WORD = {'same': 'same', 'igual': 'same (tiny change)', 'melhor': 'BETTER', 'pior': 'WORSE',
        'inconclusivo': 'changed (look at it)', 'stale': 'needs recording again', 'failed': 'could not play'}


def check_all(job, work, slug, judge=True):
    """Todas as cenas do jogo (as que ainda não têm referência: fazem-na agora). Devolve
    {checked, worse, better, changed, results:[(meta, res)]}."""
    out = {'checked': 0, 'worse': [], 'better': [], 'changed': [], 'results': []}
    for meta in scenes(slug):
        if meta.get('stale'):
            continue
        if broken_here(meta, work):
            job.event('info', 'Scene "%s": skipped, it crashed this same build of ReXNative (%s); it is '
                              'tried again after a renderer change' % (meta['label'], meta['broken']['why'][:160]))
            continue
        if not meta.get('frames'):
            try:
                make_refs(job, work, slug, meta['id'])
                job.event('info', 'Scene "%s": reference pictures made with this build' % meta['label'])
            except SceneError as e:
                job.event('info', 'Scene "%s": %s' % (meta['label'], e))
            continue
        res = check(job, work, slug, meta['id'], judge=judge)
        out['checked'] += 1
        out['results'].append((meta, res))
        v = res['verdict']
        if v == 'pior':
            out['worse'].append(meta['label'])
        elif v == 'melhor':
            out['better'].append(meta['label'])
            accept(slug, meta['id'])  # o novo aspeto é a referência das próximas mudanças
        elif v == 'inconclusivo':
            out['changed'].append(meta['label'])
        job.event('fail' if v == 'pior' else 'ok' if v in ('same', 'igual', 'melhor') else 'info',
                  'Scene "%s": %s — %s' % (meta['label'], WORD.get(v, v), res.get('summary') or ''),
                  sheet=res.get('sheet'), cost=res.get('cost'))
    return out
