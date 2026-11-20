"""O que um pipeline está a fazer agora, com o pormenor que os registos dão: extrair o arquivo, a
atualização do jogo e os DLC a descarregar (com %), cada ronda da geração do código, as corridas do
jogo para encontrar funções (N de 12), a compilação ([N/M] do ninja), o teste de arranque (segundos
de 60), o Claude a corrigir (a última ferramenta que usou).

pipeline.run guarda em job.result o passo, a tentativa e quando começou; isto lê o registo desse
passo (e o build.log do ninja) cada vez que a página pergunta."""
import re
import time

from . import config

# (padrão, fase, texto): a última linha que bate diz a fase em que o passo está.
LINE = [
    (re.compile(r'^\s*7-Zip: (.+)$'), 'extract', lambda m: 'Extracting %s' % m.group(1)),
    (re.compile(r'^\s*STFS (\S+): (.+?) \('), 'extract', lambda m: 'Reading the package %s' % m.group(2)),
    (re.compile(r'downloading title update (\d+) \(([\d.]+) KB\)'), 'tu',
     lambda m: 'Downloading the title update (TU %s, %.1f MB)' % (m.group(1), float(m.group(2)) / 1024)),
    (re.compile(r'title update (\d+) installed'), 'tu', lambda m: 'Title update installed (TU %s)' % m.group(1)),
    (re.compile(r'downloading (.+?) \(([\d.]+) MB\)'), 'dlc',
     lambda m: 'Downloading the DLC %s (%s MB)' % (m.group(1), m.group(2))),
    (re.compile(r'^\s+[0-9A-F]{8} \S+\.(?:pe|xex)\b'), 'codegen', lambda m: 'Generating the game code (round 1)'),
    (re.compile(r'codegen round (\d+)'), 'codegen', lambda m: 'Generating the game code (round %d)' % (int(m.group(1)) + 2)),
    (re.compile(r'codegen: done \(round (\d+), (\d+) s\)'), 'codegen', lambda m: 'Code generated (%s rounds)' % (int(m.group(1)) + 1)),
    (re.compile(r'adapt: (\d+) of (\d+) functions'), 'adapt',
     lambda m: 'Hooking up the renderer (%s of %s functions)' % (m.group(1), m.group(2))),
    (re.compile(r': configure \(log'), 'compile', lambda m: 'Configuring the build (CMake)'),
    (re.compile(r': build \(log: (.+)\)'), 'compile', lambda m: 'Building'),
    (re.compile(r'(\d+) function starts codegen missed'), 'codegen',
     lambda m: 'The code was missing %s functions: generating it again' % m.group(1)),
    (re.compile(r': run (\d+)\b'), 'discover', lambda m: 'Running the game to find functions (run %s)' % m.group(1)),
    (re.compile(r'DLSS 5 look'), 'compile', lambda m: 'Finishing the build'),
]
PHASE_PT = {'extract': 'Extract', 'tu': 'Title update', 'dlc': 'DLC', 'codegen': 'Generate the code',
            'adapt': 'Hook up the renderer', 'compile': 'Build', 'discover': 'Find functions',
            'boot': 'Boot test', 'compare': 'Compare', 'claude': 'Claude fixing'}
PCT_LINE = re.compile(r'^\s+(\d+)% \(([\d.]+) MB/s\)')
NINJA = re.compile(r'\[(\d+)/(\d+)\]')


def _tail(path, n=24000):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - n))
            return f.read().decode('utf-8', 'replace')
    except OSError:
        return ''


def _discover_rounds():
    args = config.load().get('prepare_args') or []
    if '--discover' in args:
        try:
            return int(args[args.index('--discover') + 1])
        except (IndexError, ValueError):
            pass
    return None


def from_log(text, work):
    """{'phase', 'text', 'pct', 'rate', 'seen'} do registo de um passo prepare/build."""
    seen = []
    phase, txt, pct, rate, build_log = None, None, None, None, None
    for line in text.splitlines():
        m = PCT_LINE.match(line)
        if m and phase == 'dlc':
            pct, rate = float(m.group(1)), float(m.group(2)) * 1e6
            continue
        for rx, ph, fmt in LINE:
            m = rx.search(line)
            if m:
                phase, txt, pct, rate = ph, fmt(m), None, None
                if ph not in seen:
                    seen.append(ph)
                if ph == 'compile' and ': build (log:' in line:
                    build_log = m.group(1).strip()
                elif ph == 'discover':
                    n = _discover_rounds()
                    if n:
                        pct = min(100.0, 100.0 * int(m.group(1)) / n)
                        txt += ' of %d' % n
                break
    if phase == 'compile' and build_log and txt == 'Building':
        hits = NINJA.findall(_tail(build_log, 6000))
        if hits:
            a, b = int(hits[-1][0]), int(hits[-1][1])
            pct = 100.0 * a / max(1, b)
            txt = 'Building: %d of %d' % (a, b)
    return {'phase': phase, 'text': txt, 'pct': pct, 'rate': rate, 'seen': seen}


def pipeline(job, work):
    """O progresso detalhado de um pipeline (o job.progress dele)."""
    from . import pipeline as pl
    step = job.result.get('step')
    t0 = job.result.get('step_t0') or time.time()
    out = {'step': step, 'step_pt': pl.STEP_TITLE.get(step, step), 'elapsed': time.time() - t0,
           'steps_done': list(job.result.get('steps_done') or []), 'phases': [], 'phase': None,
           'pct': None}
    if step in ('prepare', 'build'):
        info = from_log(_tail(pl._step_log(job, step, job.result.get('attempt') or 1)), work)
        out.update(phase=info['text'], pct=info['pct'], rate=info['rate'],
                   phases=[{'id': p, 'name': PHASE_PT.get(p, p), 'now': p == info['phase']} for p in info['seen']])
        if not info['text']:
            out['phase'] = 'Starting' if step == 'build' else 'Extracting the game archive'
    elif step in ('boot', 'compare', 'deckpc'):
        cfg = config.load()
        secs = (max(cfg.get('compare_times') or [60]) if step in ('compare', 'deckpc') else cfg.get('boot_seconds', 60)) + 7
        el = out['elapsed']
        # pipeline.wait_live_free: "...: waiting for it to finish" (antes "à espera que termine").
        wait = [e for e in job.events[-3:] if any(w in e.get('text', '') for w in ('waiting for', 'à espera'))]
        if wait and el < 20:
            out['phase'] = wait[-1]['text'][:140]
        else:
            out['pct'] = min(99.0, 100.0 * el / secs)
            out['phase'] = '%s: %d of %d s' % ({'boot': 'The game running on the PC', 'compare': 'The classic renderer running',
                                               'deckpc': 'The game with the Deck settings'}[step], min(el, secs), secs)
    elif step == 'claude':
        tools = [e for e in job.events[-30:] if e.get('kind') == 'claude-tool']
        out['phase'] = 'Claude is fixing%s' % (': ' + tools[-1]['text'][:120] if tools else '')
    return out
